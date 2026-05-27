# Data Model

This document explains the database design — how we store emissions data, track where it came from, handle multiple tenants, and maintain an audit trail.

---

## Design goals

| Requirement | How the model handles it |
|-------------|--------------------------|
| **Multi-tenancy** | Each tenant gets its own physical tables (`tenant_1_*`, `tenant_2_*`). No shared data tables = impossible to accidentally leak data between tenants. |
| **Scope 1/2/3 categorization** | Every emission row has a `scope` field (1, 2, or 3) and a `source_type` that identifies which system produced it. |
| **Source-of-truth tracking** | `raw_source_data` stores the original CSV row verbatim. `ingestion_log_id` links back to the upload. You always know which file, which row, when it was uploaded. |
| **Unit normalization** | All outputs are in MTCO₂e. The `activity_unit` field records what the input was measured in (liters, kWh, miles, room-nights, USD). |
| **Audit trail** | A separate append-only `audittrail` table logs every approve/reject/flag action with who did it and when. Rows are never updated or deleted. |

---

## Tables overview

| Table | Type | What it stores |
|-------|------|----------------|
| `ingestion_tenant` | Shared (one for all) | List of tenants — created by Django migration |
| `tenant_{id}_ingestionlog` | Per-tenant | One row per uploaded CSV file |
| `tenant_{id}_normalizedemissionrow` | Per-tenant | One emission record per CSV row (the main data) |
| `tenant_{id}_audittrail` | Per-tenant | Log of every approve/reject action |

> **How per-tenant tables are created:** When a tenant logs in for the first time, `tenant_router.py` runs raw SQL (`CREATE TABLE IF NOT EXISTS ...`) to create their 3 tables. Django's migration system is not involved — we use `managed = False` model classes built dynamically with Python's `type()`.

---

## ingestion_tenant

```
id          SERIAL PRIMARY KEY
name        VARCHAR(255) NOT NULL
slug        VARCHAR(100) NOT NULL UNIQUE
created_at  TIMESTAMPTZ  DEFAULT now()
```

This is the only shared table. It just keeps a registry of which tenants exist.

---

## tenant_{id}_ingestionlog

```
id              SERIAL PRIMARY KEY
tenant_id       INTEGER NOT NULL
source_type     VARCHAR(30) NOT NULL   -- SAP_FUEL | UTILITY_ELECTRICITY | CORPORATE_TRAVEL
file_name       VARCHAR(255)
status          VARCHAR(20) NOT NULL   -- PROCESSING | COMPLETE | FAILED
row_count       INTEGER DEFAULT 0
error_count     INTEGER DEFAULT 0
created_at      TIMESTAMPTZ DEFAULT now()
updated_at      TIMESTAMPTZ DEFAULT now()
```

**What this does:** Every time a user uploads a CSV, one row is created here. It tracks:
- What type of data it is (`source_type`)
- The original filename
- How many rows were in it
- Whether processing succeeded or failed

**Status transitions:** `PROCESSING → COMPLETE` (normal) or `PROCESSING → FAILED` (file was unparseable).

---

## tenant_{id}_normalizedemissionrow

This is the **main table** — one row per emission record.

```
id                    SERIAL PRIMARY KEY
tenant_id             INTEGER NOT NULL
ingestion_log_id      INTEGER NOT NULL  -- links back to which upload this came from
source_type           VARCHAR(30) NOT NULL   -- SAP_FUEL | UTILITY_ELECTRICITY | CORPORATE_TRAVEL
scope                 INTEGER NOT NULL  -- 1 | 2 | 3
description           TEXT
source_reference      VARCHAR(255)      -- DOC_NUM / METER_ID / TRIP_ID
raw_source_data       JSONB NOT NULL    -- the original CSV row, stored as-is
normalized_data       JSONB NOT NULL    -- calculation details (factor used, method, etc.)
activity_value        NUMERIC(20,6)     -- the quantity (e.g. 1500 liters, 42500 kWh)
activity_unit         VARCHAR(50)       -- liters | kWh | miles | room-nights | USD
emission_factor       NUMERIC(20,10)    -- the multiplier used
emission_factor_unit  VARCHAR(50)       -- e.g. MTCO2e/L, MTCO2e/kWh
co2e_mt               NUMERIC(20,6)     -- final result in Metric Tons CO2 Equivalent
period_start          DATE
period_end            DATE
status                VARCHAR(20) NOT NULL  -- PENDING | FLAGGED | APPROVED | REJECTED
flag_reason           TEXT              -- why it was flagged (if applicable)
locked_at             TIMESTAMPTZ       -- timestamp when approved/rejected (prevents further changes)
created_at            TIMESTAMPTZ DEFAULT now()
updated_at            TIMESTAMPTZ DEFAULT now()
```

### Key fields explained

| Field | Why it exists |
|-------|---------------|
| `raw_source_data` | Stores the original CSV row exactly as uploaded. If we ever change emission factors or fix a bug, we can always go back to the original input and recalculate. |
| `normalized_data` | Stores the calculation details (which factor was used, cabin multiplier, calculation method). Auditors can see exactly how we got the `co2e_mt` number without re-running code. |
| `scope` | Categorizes emissions: **1** = direct (fuel burning), **2** = purchased energy (electricity), **3** = value chain (travel). Required by GHG Protocol. |
| `source_reference` | A human-readable ID from the source system (meter number, trip ID, SAP doc number) so you can trace back to the original record. |
| `locked_at` | Set when a reviewer approves or rejects. Once locked, the UI prevents further changes — this is a lightweight compliance lock. |

### Activity units by source

| Source | What we measure | Unit stored |
|--------|----------------|-------------|
| SAP Fuel | Volume of fuel purchased | liters |
| Utility Electricity | Energy consumed | kWh |
| Flight | Distance flown | miles (or USD if distance missing) |
| Hotel | Duration of stay | room-nights (or USD if nights missing) |
| Ground transport | Distance travelled | miles (or USD if distance missing) |

> Rows that use the USD spend-based fallback are always auto-flagged — a human must review them.

### Status lifecycle

```
          CSV uploaded
               │
            PENDING  ──── clean data, all fields present
               │
            FLAGGED  ──── something is missing or anomalous
               │
        ┌──────┴──────┐
     APPROVED      REJECTED
        │               │
   (locked_at set)  (locked_at set)
```

- **PENDING** = looks good, waiting for review
- **FLAGGED** = system detected an issue (missing distance, zero quantity, spend-based estimate)
- **APPROVED** = reviewer confirmed it's correct
- **REJECTED** = reviewer marked it as bad data

---

## tenant_{id}_audittrail

```
id            SERIAL PRIMARY KEY
tenant_id     INTEGER NOT NULL
emission_row  INTEGER NOT NULL  -- which emission record this action is about
action        VARCHAR(20) NOT NULL  -- APPROVED | REJECTED | FLAGGED
actor         VARCHAR(255)          -- who did it (username or "system")
note          TEXT                   -- optional comment
created_at    TIMESTAMPTZ DEFAULT now()
```

**Rules:**
- This table is **append-only** — the app never updates or deletes rows.
- Every approve/reject click creates a new audit row.
- This gives a tamper-evident history that ESG reporting frameworks (GRI, CDP) require.

**Example:** If reviewer `test-1` approves emission row #42, the audit trail gets:
```json
{ "emission_row": 42, "action": "APPROVED", "actor": "test-1", "created_at": "2026-05-27T14:30:00Z" }
```

---

## Per-tenant physical isolation

Instead of one big shared table with a `tenant_id` column (and filtering with `WHERE tenant_id = ?`), each tenant gets **completely separate tables**:

```
tenant_1_ingestionlog
tenant_1_normalizedemissionrow
tenant_1_audittrail

tenant_2_ingestionlog
tenant_2_normalizedemissionrow
tenant_2_audittrail
```

### Why this approach?

| Benefit | Explanation |
|---------|-------------|
| **No accidental data leaks** | A query on `tenant_1_*` physically cannot return tenant 2's data — there's no `WHERE` clause to forget. |
| **Easy tenant deletion** | To remove all of tenant 42's data: `DROP TABLE tenant_42_*`. No risk of partial deletes. |
| **Simple backups** | Back up one tenant: `pg_dump -t 'tenant_42_*'`. |

### The trade-off

Django migrations don't manage these tables (they're created at runtime). Cross-tenant analytics would need dynamic SQL. For a prototype this is fine — see [TRADEOFFS.md](TRADEOFFS.md) for what a production system would do differently.
