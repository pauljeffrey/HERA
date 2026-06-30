-- Run in the Supabase SQL editor before pushing notes.

create table if not exists clinical_progress_notes (
    id uuid primary key default gen_random_uuid(),
    patient_id text not null,
    encounter_id text not null,
    encounter_index integer not null,
    encounter_type text,
    specialty_key text,
    specialty_label text,
    scenario_brief text,
    soap_note text not null,
    created_at timestamptz not null default now(),
    unique (patient_id, encounter_index)
);

create index if not exists idx_clinical_progress_notes_patient_id
    on clinical_progress_notes (patient_id);

create index if not exists idx_clinical_progress_notes_specialty_key
    on clinical_progress_notes (specialty_key);
