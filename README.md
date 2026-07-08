# HERA

Healthcare Eligibility & Reasoning Agent — synthetic clinical trial matching over generated patient trajectories and SOAP notes.

**Not for clinical use.** All patient data is synthetic.

---

## What it does

1. **Generate data** — `clinical_data_gen/` produces structured trajectories and SOAP progress notes via OpenAI Batch API.
2. **Load data** — Backend prepopulates Supabase (or local Postgres) on startup.
3. **Match trials** — Three-tier funnel: FTS → pgvector + math guard → Agent 2 deep evaluation.
4. **Audit** — Four-pane dashboard with copilot for cohort exploration and clinician overrides.

---

## Repository layout

```
HERA/
├── clinical_data_gen/          # Synthetic data generators
│   ├── structured_clinical_data/
│   └── soap_notes/
├── backend/
│   └── app/
│       ├── api/v1/             # HTTP routes only
│       ├── agents/             # Agent 2 + audit copilot (Pydantic AI)
│       ├── models/             # Pydantic schemas (ledger, search_payload, API types)
│       ├── services/           # Business logic (search, funnel, pipeline, chat agent)
│       └── workers/            # Tier 3 Modal / API fallback
├── frontend/                   # Next.js command center + audit dashboard
└── db_script/                  # Supabase push utilities
```

---

## Agents

| Agent | Module | Role |
|-------|--------|------|
| **Agent 1** | `agents/chat_agent.py` | Parses clinician intent → FTS keywords, semantic query, numeric constraints (`models/search_payload.py`) |
| **Agent 2** | `agents/analysis_agent.py` | Deep eligibility audit with vitals/labs/investigation tools → `PatientTrialAudit` |
| **Audit copilot** | `agents/audit_analysis_agent.py` | Exploratory Q&A inside a matching task; can apply overrides |

Tier 3 runs via `workers/modal_agent.py` (Modal GPU batch with OpenAI fallback).

---

## API ↔ Frontend

| Frontend | Backend |
|----------|---------|
| `POST /chat` | General orchestrator chat (Agent 1) |
| `POST /trials/match` | Start background matching pipeline |
| `GET /tasks/{id}` | Poll task progress (sidebar, 3s interval) |
| `GET /audit/tasks/{id}` | Audit dashboard payload |
| `POST /audit/tasks/{id}/copilot` | Audit copilot chat |
| `POST /audit/tasks/{id}/override` | Clinician override |
| `GET /criteria/prompts` | Criteria dropdown in command center |

**Pages:** `/` (Command Center), `/audit/[task_id]` (Audit Dashboard).

Set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8010/api/v1` in `frontend/.env.local`.

---

## Quick start

### 1. Environment

Copy `.env.example` → `.env` at repo root:

```env
OPENAI_API_KEY=sk-...
DATABASE_MODE=supabase
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SECRET_KEY=<service_role_key>
SUPABASE_DB_HOST=db.<project>.supabase.co
SUPABASE_DB_PASSWORD=<db_password>
```

Apply `backend/app/db/schema.sql` once in the Supabase SQL editor.

### 2. Backend

```bash
cd backend
docker compose up --build
```

Startup prepopulates the DB when empty (`PREPOPULATE_DB=if_empty`, default).

**Embeddings (Tier 2 search):** from `backend/` on the host:

```bash
pip install -r requirements-ingest.txt
python -m scripts.ingest_ehr --reset
```

Health: `http://127.0.0.1:8010/health`

**Local Postgres:** `DATABASE_MODE=local` then `docker compose --profile local up --build`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

### 4. End-to-end flow

1. Open Command Center → paste trial criteria (or pick from dropdown).
2. Sidebar polls until task completes → click **Explore Audit Ledger**.
3. Review timeline, metrics, ledger; toggle copilot or overrule a verdict.

---

## Matching pipeline

```
User prompt
    → Agent 1 (search plan)
    → Tier 1 FTS (Postgres tsvector)
    → Tier 2 pgvector + math_guard (windowed numeric checks)
    → Tier 3 Agent 2 (per-patient audit ledger)
    → trial_matching_tasks.result_summary
    → Audit dashboard
```

Key modules: `services/search.py`, `services/math_guard.py`, `services/funnel_orchestrator.py`, `services/match_pipeline.py`, `services/task_storage.py`.

---

## Tests

```bash
cd backend
pytest tests/test_math_guard.py -v          # unit (no DB)
pytest tests/ -v                            # includes FTS/vector if DB creds set
```

---

## Data generation (optional)

```bash
cd clinical_data_gen/structured_clinical_data
python generate.py --count 50

cd ../soap_notes
python generate.py
```

Outputs land under `clinical_data_gen/*/output/`. Point `PATIENT_TRAJECTORIES_PATH` / `SOAP_NOTES_PATH` in `.env` if paths differ.

---

## Legacy / unused routes

These exist for demos and tooling but are not wired in the UI:

- `POST /trials/match/legacy` — mock funnel
- `GET /patients`, `GET /audit/logs/{patient_id}` — demo patient API
- `GET /criteria/random` — random criterion picker
