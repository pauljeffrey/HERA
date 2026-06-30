-- HERA production schema — PostgreSQL with pgvector
-- Run after creating the database: CREATE EXTENSION IF NOT EXISTS vector;

CREATE EXTENSION IF NOT EXISTS vector;

-- Clinical progress notes (from existing pipeline)
CREATE TABLE IF NOT EXISTS clinical_progress_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id TEXT NOT NULL,
    encounter_id TEXT NOT NULL,
    encounter_index INTEGER NOT NULL,
    encounter_type TEXT,
    specialty_key TEXT,
    specialty_label TEXT,
    scenario_brief TEXT,
    soap_note TEXT NOT NULL,
    embedding vector(384),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (patient_id, encounter_index)
);

CREATE INDEX IF NOT EXISTS idx_clinical_progress_notes_patient_id
    ON clinical_progress_notes (patient_id);
CREATE INDEX IF NOT EXISTS idx_clinical_progress_notes_embedding
    ON clinical_progress_notes USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Audit ledger — permanent paper trail for safety inspections
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id TEXT NOT NULL,
    encounter_id TEXT NOT NULL,
    trial_id TEXT NOT NULL,
    original_llm_raw_response TEXT,
    pydantic_parsed_payload JSONB,
    clinician_override_status TEXT,
    override_reason_text TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_patient_id ON audit_logs (patient_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_trial_id ON audit_logs (trial_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs (timestamp DESC);

-- Immutable patient timeline snapshots
CREATE TABLE IF NOT EXISTS patient_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id TEXT NOT NULL,
    trial_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    timeline_state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_patient_snapshots_patient_id ON patient_snapshots (patient_id);

-- Async match job tracking
CREATE TABLE IF NOT EXISTS match_jobs (
    job_id TEXT PRIMARY KEY,
    trial_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    progress_pct REAL NOT NULL DEFAULT 0.0,
    result_payload JSONB,
    search_space_raw INTEGER DEFAULT 100000,
    search_space_tier1 INTEGER DEFAULT 10000,
    search_space_tier2 INTEGER DEFAULT 1000,
    execution_latency_ms INTEGER,
    token_cost_usd REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_match_jobs_trial_id ON match_jobs (trial_id);
