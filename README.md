# Breathe ESG — Emissions Ingestion Prototype

A multi-tenant prototype that ingests raw CSV exports from three enterprise source systems, normalises them to a canonical emissions ledger, and surfaces them in a React review dashboard.

> **Live demo:** _deploy to Vercel + Railway and update this URL_

---

## Tenant onboarding & login flow

The app opens to a login screen with three inputs:

| Field | What to enter |
|-------|---------------|
| **Tenant ID** | Any positive integer (e.g. `1`, `42`, `100`) |
| **Username** | `test-{id}` (e.g. `test-1`) |
| **Password** | `pass-{id}` (e.g. `pass-1`) |

> **Example:** If Tenant ID = `1`, then Username = `test-1` and Password = `pass-1`.

**First-time login (new tenant):**
1. Enter any integer as Tenant ID along with the matching credentials.
2. The system automatically creates a record in the `ingestion_tenant` table.
3. Three per-tenant physical tables are created on the fly (`tenant_{id}_ingestionlog`, `tenant_{id}_normalizedemissionrow`, `tenant_{id}_audittrail`).
4. You land on the dashboard — ready to upload CSVs immediately.

**Returning tenant:**
1. Enter the same Tenant ID and credentials used previously.
2. Tables already exist — no DDL runs.
3. You land on the dashboard with all your previously ingested data intact.

> No registration page or admin approval is needed. Any integer ID "self-provisions" a fully isolated tenant on first login.

---

## Platform UI

After login, the single-page dashboard exposes the following components:

| Component | Purpose |
|-----------|---------|
| **Dashboard Summary** | KPI cards showing total rows ingested, rows needing review, flagged/approved/rejected counts, and total MTCO₂e emissions. |
| **File Upload Zone** | Drag-and-drop CSV upload with automatic header detection and a field-mapping UI for three data sources (SAP Fuel, Utility Electricity, Corporate Travel). |
| **Ingestion Log Table** | Lists recent uploads with source type, filename, row count, timestamp, and processing status (complete / processing / failed). |
| **Emissions Review Table** | Paginated, filterable table of normalized emission records with source/status tabs and inline Approve / Reject actions with toast notifications. |
| **Row Detail Modal** | Click any row to view raw vs. normalized data, emission calculation breakdown, flag reasons, and full audit trail history. |
| **Status Badge** | Color-coded pill (pending · flagged · approved · rejected) shown alongside each record for quick visual scanning. |

---

## What it does

The platform ingests raw CSV files exported from enterprise systems, automatically normalizes each row into a standardized emissions record expressed in **Metric Tons CO₂ Equivalent (MTCO₂e)**, and surfaces them for human review.

### Ingestion pipeline

1. **Upload** — User drops a CSV into the upload zone and maps columns to the expected schema via the field-mapping UI.
2. **Parse & normalize** — The backend identifies the data source and applies the appropriate emission factor to compute `co2e_mt = activity_value × emission_factor`.
3. **Flag / pass** — Rows with missing mandatory fields or zero/negative values are auto-flagged for review; valid rows are marked "pending".
4. **Review** — Analysts approve or reject each record from the Emissions Review Table; every action is logged in the per-tenant audit trail.

### Supported data sources & emission factors

| Source | Scope | Factor | Unit | Notes |
|--------|-------|--------|------|-------|
| **SAP Fuel & Procurement** | Scope 1 | Diesel 0.002701 / Petrol 0.002289 / LPG 0.001542 | MTCO₂e/L | IPCC AR6 fuel-specific; material number prefix determines fuel type |
| **Utility Electricity** | Scope 2 | 0.000386 | MTCO₂e/kWh | US EPA eGRID 2024 national average |
| **Travel — Flight** | Scope 3 | 0.000255 × cabin multiplier | MTCO₂e/mile | Economy ×1, Premium ×1.6, Business ×2.9, First ×4.0 (DEFRA 2024) |
| **Travel — Hotel** | Scope 3 | 0.0000617 | MTCO₂e/room-night | DEFRA 2024 UK average per room-night |
| **Travel — Ground (Car)** | Scope 3 | 0.000168 | MTCO₂e/mile | DEFRA 2024 |
| **Travel — Ground (Taxi/Rideshare)** | Scope 3 | 0.000211 | MTCO₂e/mile | DEFRA 2024 |
| **Travel — Ground (Train/Rail)** | Scope 3 | 0.0000041 | MTCO₂e/mile | DEFRA 2024 |
| **Travel — Ground (Bus)** | Scope 3 | 0.0000089 | MTCO₂e/mile | DEFRA 2024 |

> When distance is unavailable but cost is present, a spend-based fallback factor (0.0008 MTCO₂e/USD) is applied.

### Multi-tenancy & data isolation

Each tenant's data is stored in dedicated physical tables (`tenant_{id}_ingestionlog`, `tenant_{id}_normalizedemissionrow`, `tenant_{id}_audittrail`). There are no shared data tables — no `WHERE tenant_id = ?` filtering needed — eliminating cross-tenant data leakage by design.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  React 19 + Vite (frontend/)                                │
│  EmissionsTable  UploadModal  LoginScreen                   │
└──────────────────────┬──────────────────────────────────────┘
                       │  /api/…  (VITE_API_BASE in prod)
┌──────────────────────▼──────────────────────────────────────┐
│  Django 6 + DRF  (backend/)                                 │
│  IngestionView  EmissionsView  AuditView  AuthView          │
│  normalization.py  tenant_router.py                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│  PostgreSQL                                                 │
│  ingestion_tenant  (Tenant details store)                   │
│  tenant_{id}_ingestionlog           (per-tenant)            │
│  tenant_{id}_normalizedemissionrow  (per-tenant)            │
│  tenant_{id}_audittrail             (per-tenant)            │
└─────────────────────────────────────────────────────────────┘
```

Per-tenant physical tables are created on first login via raw DDL — no shared tables, no `WHERE tenant_id =` leakage.  See [MODEL.md](MODEL.md) for the full schema.

---

## Documentation

| File | Contents |
|------|----------|
| [MODEL.md](MODEL.md) | Database schema, per-tenant isolation, field-level rationale |
| [DECISIONS.md](DECISIONS.md) | Key design decisions and "what I'd ask the PM" |
| [TRADEOFFS.md](TRADEOFFS.md) | Deliberate shortcuts and what a production build would add |
| [SOURCES.md](SOURCES.md) | Raw CSV field provenance from SAP, Oracle, Concur, Navan |

---

## Sample data

All sample CSVs live under `sample_data/` organized by source type:

```
sample_data/
├── sap_fuel/
│   ├── sap_fuel_data.csv          # Canonical field names
│   ├── sap_fuel_set2.csv          # SAP European style
│   ├── sap_fuel_set3.csv          # Oracle/Concur style
│   └── sap_fuel_set4.csv          # Generic spreadsheet
├── electricity/
│   ├── utility_electricity.csv    # Canonical
│   ├── utility_electricity_set2.csv
│   ├── utility_electricity_set3.csv
│   └── utility_electricity_set4.csv
└── travel/
    ├── travel_data.csv            # Canonical
    ├── travel_set2.csv
    ├── travel_set3.csv
    └── travel_set4.csv
```

Each set uses different column naming conventions — the frontend field-mapping UI lets you map any header to the canonical schema before upload. Travel files include flight, hotel, and ground transport rows to exercise all normalisation paths.

---

## Deployment

| Service | Platform | Tier |
|---------|----------|------|
| Frontend (React SPA) | Vercel | Free |
| Backend (Django API) | Railway | Free ($5/month credit) |
| PostgreSQL | Railway | Free ($5/month credit) |

### Backend + Database → Railway

1. Sign in to [railway.app](https://railway.app) with GitHub.
2. New Project → Deploy from GitHub → select this repo.
3. Add a **PostgreSQL** service (+ New → Database → PostgreSQL).
4. Add a **Web Service** from the repo:
   - Root Directory: `backend`
   - Start Command: `gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 2`
5. Set environment variables:
   - `DATABASE_URL` → Railway provides this automatically from PostgreSQL
   - `SECRET_KEY` → any random string
   - `ALLOWED_HOSTS` → `your-app.up.railway.app`
   - `CORS_ALLOWED_ORIGINS` → `https://your-frontend.vercel.app`
   - `PYTHON_VERSION` → `3.13.3`

### Frontend → Vercel

1. Sign in to [vercel.com](https://vercel.com) with GitHub.
2. Import this repo → set Root Directory to `frontend`.
3. Framework Preset: Vite.
4. Add environment variable: `VITE_API_BASE` = `https://your-railway-backend.up.railway.app`
5. Deploy.

---

## Local setup

### Prerequisites
- Python 3.11+
- Node 20+
- PostgreSQL 14+

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

# Create a .env file at backend/.env:
#   DATABASE_URL=postgres://user:pass@localhost:5432/breathe_esg
#   SECRET_KEY=your-secret-key
#   ALLOWED_HOSTS=localhost,127.0.0.1
#   CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # dev server at http://localhost:5173
```
