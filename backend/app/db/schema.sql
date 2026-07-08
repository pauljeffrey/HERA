-- HERA Supabase / PostgreSQL schema
-- Apply once in the Supabase SQL editor, or automatically via Docker Postgres init.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- Core clinical entities (from patient_trajectories.json)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS patients (
    patient_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    age INTEGER NOT NULL,
    sex TEXT NOT NULL,
    inclusion_exclusion_criteria TEXT,
    specialty_key TEXT,
    specialty_label TEXT,
    scenario_brief TEXT,
    source_custom_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_patients_specialty_key ON patients (specialty_key);

CREATE TABLE IF NOT EXISTS encounters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id TEXT NOT NULL REFERENCES patients (patient_id) ON DELETE CASCADE,
    encounter_id TEXT NOT NULL,
    encounter_index INTEGER NOT NULL,
    encounter_type TEXT,
    days_since_baseline INTEGER NOT NULL DEFAULT 0,
    occurred_at TIMESTAMPTZ NOT NULL,
    bp TEXT,
    pulse INTEGER,
    resp_rate INTEGER,
    temperature REAL,
    spo2 INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (patient_id, encounter_index),
    UNIQUE (patient_id, encounter_id)
);

CREATE INDEX IF NOT EXISTS idx_encounters_patient_id ON encounters (patient_id);
CREATE INDEX IF NOT EXISTS idx_encounters_occurred_at ON encounters (occurred_at);

CREATE TABLE IF NOT EXISTS encounter_medications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    encounter_id UUID NOT NULL REFERENCES encounters (id) ON DELETE CASCADE,
    medication TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (encounter_id, medication)
);

CREATE INDEX IF NOT EXISTS idx_encounter_medications_encounter_id
    ON encounter_medications (encounter_id);

CREATE TABLE IF NOT EXISTS encounter_investigations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    encounter_id UUID NOT NULL REFERENCES encounters (id) ON DELETE CASCADE,
    investigation TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    fts_doc TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(investigation, ''))) STORED,
    UNIQUE (encounter_id, investigation)
);

CREATE INDEX IF NOT EXISTS idx_encounter_investigations_encounter_id
    ON encounter_investigations (encounter_id);
CREATE INDEX IF NOT EXISTS idx_encounter_investigations_fts
    ON encounter_investigations USING GIN (fts_doc);

CREATE TABLE IF NOT EXISTS lab_panels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    encounter_id UUID NOT NULL REFERENCES encounters (id) ON DELETE CASCADE,
    panel_name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (encounter_id, panel_name)
);

CREATE INDEX IF NOT EXISTS idx_lab_panels_encounter_id ON lab_panels (encounter_id);

CREATE TABLE IF NOT EXISTS lab_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lab_panel_id UUID NOT NULL REFERENCES lab_panels (id) ON DELETE CASCADE,
    test_name TEXT NOT NULL,
    test_value TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    fts_doc TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(test_name, '') || ' ' || coalesce(test_value, ''))
    ) STORED,
    UNIQUE (lab_panel_id, test_name)
);

CREATE INDEX IF NOT EXISTS idx_lab_results_lab_panel_id ON lab_results (lab_panel_id);
CREATE INDEX IF NOT EXISTS idx_lab_results_fts ON lab_results USING GIN (fts_doc);

CREATE TABLE IF NOT EXISTS encounter_diagnoses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    encounter_id UUID NOT NULL REFERENCES encounters (id) ON DELETE CASCADE,
    diagnosis TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (encounter_id, diagnosis)
);

CREATE INDEX IF NOT EXISTS idx_encounter_diagnoses_encounter_id
    ON encounter_diagnoses (encounter_id);

CREATE TABLE IF NOT EXISTS encounter_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    encounter_id UUID NOT NULL REFERENCES encounters (id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (encounter_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_encounter_tags_encounter_id ON encounter_tags (encounter_id);

-- ---------------------------------------------------------------------------
-- SOAP progress notes (from soap_progress_notes.json)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS clinical_progress_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    encounter_id UUID NOT NULL REFERENCES encounters (id) ON DELETE CASCADE,
    patient_id TEXT NOT NULL REFERENCES patients (patient_id) ON DELETE CASCADE,
    encounter_index INTEGER NOT NULL,
    encounter_type TEXT,
    specialty_key TEXT,
    specialty_label TEXT,
    scenario_brief TEXT,
    soap_note TEXT NOT NULL,
    fts_doc TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(soap_note, ''))) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (patient_id, encounter_index)
);

CREATE INDEX IF NOT EXISTS idx_clinical_progress_notes_patient_id
    ON clinical_progress_notes (patient_id);
CREATE INDEX IF NOT EXISTS idx_clinical_progress_notes_encounter_id
    ON clinical_progress_notes (encounter_id);
CREATE INDEX IF NOT EXISTS idx_clinical_progress_notes_fts
    ON clinical_progress_notes USING GIN (fts_doc);

-- ---------------------------------------------------------------------------
-- HERA application tables
-- ---------------------------------------------------------------------------

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

CREATE TABLE IF NOT EXISTS patient_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id TEXT NOT NULL,
    trial_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    timeline_state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_patient_snapshots_patient_id ON patient_snapshots (patient_id);

CREATE TABLE IF NOT EXISTS match_jobs (
    job_id TEXT PRIMARY KEY,
    trial_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    progress_pct REAL NOT NULL DEFAULT 0.0,
    result_payload JSONB,
    search_space_raw INTEGER DEFAULT 100000,
    search_space_fts INTEGER DEFAULT 10000,
    search_space_vs INTEGER DEFAULT 1000,
    execution_latency_ms INTEGER,
    token_cost_usd REAL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_match_jobs_trial_id ON match_jobs (trial_id);

CREATE TABLE IF NOT EXISTS trial_matching_tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(50) NOT NULL,
    trial_id TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    progress_percentage INTEGER NOT NULL DEFAULT 0,
    result_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trial_matching_tasks_user_id ON trial_matching_tasks (user_id);
CREATE INDEX IF NOT EXISTS idx_trial_matching_tasks_trial_id ON trial_matching_tasks (trial_id);
CREATE INDEX IF NOT EXISTS idx_trial_matching_tasks_status ON trial_matching_tasks (status);

-- ---------------------------------------------------------------------------
-- Step 0: Chunked EHR embeddings (Tier 1 FTS + Tier 2 pgvector)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS patient_notes_embeddings (
    chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id TEXT NOT NULL REFERENCES patients (patient_id) ON DELETE CASCADE,
    encounter_id TEXT NOT NULL,
    encounter_uuid UUID REFERENCES encounters (id) ON DELETE CASCADE,
    lab_result_id UUID REFERENCES lab_results (id) ON DELETE CASCADE,
    investigation_id UUID REFERENCES encounter_investigations (id) ON DELETE CASCADE,
    encounter_date TIMESTAMPTZ NOT NULL,
    chunk_index INT NOT NULL,
    source_type TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(768),
    fts_doc TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', coalesce(raw_text, ''))) STORED,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (patient_id, encounter_id, source_type, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_pne_patient_id ON patient_notes_embeddings (patient_id);
CREATE INDEX IF NOT EXISTS idx_pne_patient_encounter ON patient_notes_embeddings (patient_id, encounter_id);
CREATE INDEX IF NOT EXISTS idx_pne_encounter_date ON patient_notes_embeddings (encounter_date);
CREATE INDEX IF NOT EXISTS idx_pne_lab_result_id ON patient_notes_embeddings (lab_result_id);
CREATE INDEX IF NOT EXISTS idx_pne_investigation_id ON patient_notes_embeddings (investigation_id);
CREATE INDEX IF NOT EXISTS idx_pne_fts ON patient_notes_embeddings USING GIN (fts_doc);
CREATE INDEX IF NOT EXISTS idx_pne_vector ON patient_notes_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Upgrade path for databases created before lab_result_id/investigation_id existed.
ALTER TABLE patient_notes_embeddings ADD COLUMN IF NOT EXISTS lab_result_id UUID REFERENCES lab_results (id) ON DELETE CASCADE;
ALTER TABLE patient_notes_embeddings ADD COLUMN IF NOT EXISTS investigation_id UUID REFERENCES encounter_investigations (id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_pne_lab_result_id ON patient_notes_embeddings (lab_result_id);
CREATE INDEX IF NOT EXISTS idx_pne_investigation_id ON patient_notes_embeddings (investigation_id);

-- Upgrade path for databases created before FTS / vector columns were added.
ALTER TABLE clinical_progress_notes
    ADD COLUMN IF NOT EXISTS fts_doc TSVECTOR
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(soap_note, ''))) STORED;
CREATE INDEX IF NOT EXISTS idx_clinical_progress_notes_fts
    ON clinical_progress_notes USING GIN (fts_doc);

ALTER TABLE lab_results
    ADD COLUMN IF NOT EXISTS fts_doc TSVECTOR
    GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(test_name, '') || ' ' || coalesce(test_value, ''))
    ) STORED;
CREATE INDEX IF NOT EXISTS idx_lab_results_fts ON lab_results USING GIN (fts_doc);

ALTER TABLE encounter_investigations
    ADD COLUMN IF NOT EXISTS fts_doc TSVECTOR
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(investigation, ''))) STORED;
CREATE INDEX IF NOT EXISTS idx_encounter_investigations_fts
    ON encounter_investigations USING GIN (fts_doc);
