# Design Decisions

Every ambiguity we encountered, what we chose, why, and what we'd ask the PM if we could.

---

## 1 — CSV upload over live API integration

**Ambiguity:** Should we pull data directly from SAP/Concur/utility APIs, or let users upload CSV files?

**What we chose:** CSV file upload.

**Why:**
- ESG data is typically collected in batches (monthly bills, quarterly travel reports) — not real-time.
- CSV is the one format every enterprise system can export, even legacy on-prem ones.
- Uploads are auditable — you can compare two files to see what changed.
- No need to deal with API keys, OAuth tokens, or webhooks for each tenant.

**What we handle:** Any CSV with headers that can be mapped to our expected fields via the UI.  
**What we ignore:** Real-time API connectors, webhook listeners, or streaming data ingestion.

---

## 2 — Billing period from service dates, not invoice date

**Ambiguity:** When assigning a utility bill to a time period, should we use the invoice/billing date or the actual service window?

**What we chose:** Use `SERVICE_START` / `SERVICE_END` from the utility export as the emission period.

**Why:**
- ESG standards (GHG Protocol, CDP) require emissions to match the period when the activity happened — not when the bill arrived.
- Utility bills often arrive 2–6 weeks late. Using the invoice date could push December emissions into January, messing up annual totals.

**What we handle:** Rows that have both `SERVICE_START` and `SERVICE_END` fields.  
**What we ignore:** Pro-rating bills that span two calendar months (we assign the full amount to the period).

---

## 3 — Use recorded travel distance, not calculated distance

**Ambiguity:** When a travel record has airport codes but no distance, should we auto-calculate the flight distance?

**What we chose:** Use the `DISTANCE_MILES` field from the travel system export. If it's missing, fall back to spend-based estimation and flag the row for review.

**Why:**
- Actual booked routes often differ from straight-line distance (layovers, indirect routing, charter flights).
- Auto-calculating from airport codes needs a coordinate database that adds complexity and maintenance.
- Flagging estimated rows is transparent — reviewers can see exactly which records used a fallback.

**What we handle:** Rows with explicit distance, or rows with cost (spend-based fallback).  
**What we ignore:** Automatic geodesic distance calculation from IATA codes or city pairs.

---

## 4 — Separate tables per tenant (physical isolation)

**Ambiguity:** Should all tenants share one big table with a `tenant_id` column, or get their own tables?

**What we chose:** Create `tenant_{id}_*` physical tables for each tenant on first login.

**Why:**
- Eliminates any risk of one tenant accidentally seeing another's data (no forgotten `WHERE tenant_id = ?`).
- Makes it trivial to delete all data for a single tenant (just drop their tables).
- See [MODEL.md](MODEL.md) for the full schema details.

**What we handle:** Complete data isolation per tenant with auto-provisioning on login.  
**What we ignore:** Shared-table multi-tenancy patterns (row-level security, schema-per-tenant in PostgreSQL).

---

## 5 — Single average hotel factor, not property-level

**Ambiguity:** Should hotel emissions use a global average or look up the specific hotel/city/chain?

**What we chose:** Apply one DEFRA 2024 average factor (0.0000617 MTCO₂e/room-night) for all hotel stays.

**Why:**
- Standard expense reports don't include the hotel's actual energy data.
- Looking up property-level factors needs a hotel name + address, and those are often messy in expense systems.
- DEFRA's average is the methodology most commonly accepted by CDP and GRI auditors for Scope 3 reporting.

**What we handle:** Any row identified as a hotel stay with a `NIGHTS` value.  
**What we ignore:** Property-level factors (HCMI data), city-specific averages, or star-rating adjustments.

---

## 6 — Single "FLAGGED" status instead of multiple review states

**Ambiguity:** Should we have separate states like "anomaly detected", "under review", "escalated"?

**What we chose:** One `FLAGGED` status with a `flag_reason` text field explaining what's wrong.

**Why:**
- For a prototype, every flagged row needs the same action: a human looks at it and decides approve/reject.
- A full state machine (anomaly → under review → escalated → resolved) adds UI and backend complexity without changing the outcome.
- The `flag_reason` field gives reviewers all the context they need.

**What we handle:** Auto-flagging for missing fields, zero/negative values, and spend-based estimates.  
**What we ignore:** Multi-stage review workflows, escalation paths, or team-based assignment.

---

## What I'd ask the Product Manager

If I could get clarification before the next iteration:

### Q1 — Electricity factor granularity
> Should we use a single US national average, or support regional factors (e.g. California vs. Southeast)?  Do any tenants have facilities outside the US?

This matters because regional factors can differ by 2–3× from the national average.

### Q2 — Auto-calculate flight distance from airport codes?
> Is it OK to just flag rows with no distance, or should we add a lookup table to estimate great-circle distance from IATA codes?

Auto-calculation would reduce the number of flagged rows but adds a database dependency.

### Q3 — Hotel factor detail
> Is the global average acceptable, or do tenants need city/chain-level factors? Some CDP reporters use property-level data.

This tells us whether we need to extend the hotel parser.

### Q4 — Period boundary handling
> When a utility bill spans two months (e.g. Dec 15 – Jan 14), do we pro-rate across both months or assign to the end month?

Pro-rating is more accurate but requires extra logic.

### Q5 — Re-upload behaviour
> If a tenant uploads the same file again, should we reject it as a duplicate, replace the old data, or keep both? Currently we keep both (additive).

The answer depends on whether re-uploads are corrections or additions.
