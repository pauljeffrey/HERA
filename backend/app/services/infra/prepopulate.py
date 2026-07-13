"""Load clinical datasets into Supabase (REST) or local Postgres."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from supabase import Client

from app.config import SCHEMA_SQL, Settings, get_settings, load_json_list, soap_notes_path, trajectories_path
from app.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

HERA_UUID_NS = uuid.UUID("f47ac10b-58cc-4372-a567-0e02b2c3d479")
NULL_UUID = "00000000-0000-0000-0000-000000000000"

CLINICAL_TABLES = (
    "clinical_progress_notes",
    "lab_results",
    "lab_panels",
    "encounter_medications",
    "encounter_investigations",
    "encounter_diagnoses",
    "encounter_tags",
    "encounters",
    "patients",
)

SUPABASE_UPSERTS: list[tuple[str, str, int]] = [
    ("patients", "patient_id", 200),
    ("encounters", "patient_id,encounter_index", 200),
    ("encounter_medications", "encounter_id,medication", 200),
    ("encounter_investigations", "encounter_id,investigation", 200),
    ("encounter_diagnoses", "encounter_id,diagnosis", 200),
    ("encounter_tags", "encounter_id,tag", 200),
    ("lab_panels", "encounter_id,panel_name", 200),
    ("lab_results", "lab_panel_id,test_name", 200),
    ("clinical_progress_notes", "patient_id,encounter_index", 25),
]


@dataclass(frozen=True)
class ExpectedCounts:
    patients: int = 0
    encounters: int = 0
    medications: int = 0
    investigations: int = 0
    diagnoses: int = 0
    tags: int = 0
    lab_panels: int = 0
    lab_results: int = 0
    progress_notes: int = 0


@dataclass
class ClinicalDataset:
    patients: list[dict] = field(default_factory=list)
    encounters: list[dict] = field(default_factory=list)
    medications: list[dict] = field(default_factory=list)
    investigations: list[dict] = field(default_factory=list)
    diagnoses: list[dict] = field(default_factory=list)
    tags: list[dict] = field(default_factory=list)
    lab_panels: list[dict] = field(default_factory=list)
    lab_results: list[dict] = field(default_factory=list)
    progress_notes: list[dict] = field(default_factory=list)
    expected: ExpectedCounts = field(default_factory=ExpectedCounts)


def should_prepopulate() -> bool:
    value = os.getenv("PREPOPULATE_DB", get_settings().prepopulate_db or "").strip().lower()
    return value not in ("", "false", "0", "no", "off")


def run_prepopulate(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not should_prepopulate():
        logger.info("Prepopulate disabled (PREPOPULATE_DB=%s)", os.getenv("PREPOPULATE_DB", ""))
        return
    target = (
        settings.supabase_url
        if settings.database_mode == "supabase"
        else f"{settings.local_db_host}:{settings.local_db_port}"
    )
    logger.info(
        "Running prepopulate (PREPOPULATE_DB=%s, DATABASE_MODE=%s, target=%s)",
        settings.prepopulate_db,
        settings.database_mode,
        target,
    )
    prepopulate_db(settings)


def _parse_mode(value: str) -> str | None:
    mode = value.strip().lower()
    if mode in ("", "false", "0", "no", "off"):
        return None
    if mode in ("reset", "true", "yes", "1", "always"):
        return "reset"
    if mode in ("if_empty", "if-empty"):
        return "if_empty"
    if mode in ("sync", "incremental"):
        return "sync"
    raise ValueError(f"Unsupported PREPOPULATE_DB value: {value}")


def _encounter_uuid(patient_id: str, encounter_index: int) -> str:
    return str(uuid.uuid5(HERA_UUID_NS, f"encounter:{patient_id}:{encounter_index}"))


def _lab_panel_uuid(patient_id: str, encounter_index: int, panel_name: str) -> str:
    return str(uuid.uuid5(HERA_UUID_NS, f"panel:{patient_id}:{encounter_index}:{panel_name}"))


def _parse_occurred_at(raw: str) -> str:
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).isoformat()


def _as_int(value) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _as_float(value) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _patient_row(patient: dict) -> dict:
    meta = patient.get("_meta") or {}
    return {
        "patient_id": patient["patient_id"],
        "name": patient["name"],
        "age": int(patient["age"]),
        "sex": patient["sex"],
        "inclusion_exclusion_criteria": patient.get("inclusion_exclusion_criteria"),
        "specialty_key": meta.get("specialty_key"),
        "specialty_label": meta.get("specialty_label"),
        "scenario_brief": meta.get("scenario_brief"),
        "source_custom_id": meta.get("custom_id"),
    }


def _encounter_row(patient_id: str, encounter_index: int, encounter: dict) -> dict:
    vitals = encounter.get("vitals") or {}
    return {
        "id": _encounter_uuid(patient_id, encounter_index),
        "patient_id": patient_id,
        "encounter_id": encounter["id"],
        "encounter_index": encounter_index,
        "encounter_type": encounter.get("type"),
        "days_since_baseline": int(encounter.get("days_since_baseline") or 0),
        "occurred_at": _parse_occurred_at(encounter["datetime"]),
        "bp": vitals.get("BP"),
        "pulse": _as_int(vitals.get("PR")),
        "resp_rate": _as_int(vitals.get("RR")),
        "temperature": _as_float(vitals.get("Temp")),
        "spo2": _as_int(vitals.get("SpO2")),
    }


def build_clinical_dataset(patients: list[dict], notes: list[dict] | None = None) -> ClinicalDataset:
    dataset = ClinicalDataset()
    notes = notes or []
    encounter_keys: set[tuple[str, int]] = set()

    for patient in patients:
        dataset.patients.append(_patient_row(patient))
        for encounter_index, encounter in enumerate(patient.get("timeline") or []):
            patient_id = patient["patient_id"]
            enc_id = _encounter_uuid(patient_id, encounter_index)
            encounter_keys.add((patient_id, encounter_index))
            dataset.encounters.append(_encounter_row(patient_id, encounter_index, encounter))

            for sort_order, medication in enumerate(encounter.get("meds") or []):
                dataset.medications.append(
                    {"encounter_id": enc_id, "medication": medication, "sort_order": sort_order}
                )
            for sort_order, investigation in enumerate(encounter.get("procedures") or []):
                dataset.investigations.append(
                    {"encounter_id": enc_id, "investigation": investigation, "sort_order": sort_order}
                )
            for sort_order, diagnosis in enumerate(encounter.get("diagnosis") or []):
                dataset.diagnoses.append(
                    {"encounter_id": enc_id, "diagnosis": diagnosis, "sort_order": sort_order}
                )
            for sort_order, tag in enumerate(encounter.get("tags") or []):
                dataset.tags.append({"encounter_id": enc_id, "tag": tag, "sort_order": sort_order})

            for panel_index, panel in enumerate(encounter.get("labs") or []):
                panel_id = _lab_panel_uuid(patient_id, encounter_index, panel["panel"])
                dataset.lab_panels.append(
                    {
                        "id": panel_id,
                        "encounter_id": enc_id,
                        "panel_name": panel["panel"],
                        "sort_order": panel_index,
                    }
                )
                for result_index, result in enumerate(panel.get("results") or []):
                    dataset.lab_results.append(
                        {
                            "lab_panel_id": panel_id,
                            "test_name": result["test"],
                            "test_value": str(result["value"]),
                            "sort_order": result_index,
                        }
                    )

    for note in notes:
        key = (note["patient_id"], int(note["encounter_index"]))
        if key not in encounter_keys:
            continue
        soap_text = (note.get("soap_note") or "").strip()
        if not soap_text:
            continue
        patient_id, encounter_index = key
        dataset.progress_notes.append(
            {
                "encounter_id": _encounter_uuid(patient_id, encounter_index),
                "patient_id": patient_id,
                "encounter_index": encounter_index,
                "encounter_type": note.get("encounter_type"),
                "specialty_key": note.get("specialty_key"),
                "specialty_label": note.get("specialty_label"),
                "scenario_brief": note.get("scenario_brief"),
                "soap_note": soap_text,
            }
        )

    dataset.expected = ExpectedCounts(
        patients=len(dataset.patients),
        encounters=len(dataset.encounters),
        medications=len(dataset.medications),
        investigations=len(dataset.investigations),
        diagnoses=len(dataset.diagnoses),
        tags=len(dataset.tags),
        lab_panels=len(dataset.lab_panels),
        lab_results=len(dataset.lab_results),
        progress_notes=len(dataset.progress_notes),
    )
    return dataset


def _load_clinical_dataset(settings: Settings) -> ClinicalDataset:
    trajectories_file = trajectories_path(settings)
    soap_file = soap_notes_path(settings)
    if not trajectories_file.exists():
        raise FileNotFoundError(f"Patient trajectories file not found: {trajectories_file}")
    if not soap_file.exists():
        raise FileNotFoundError(f"SOAP notes file not found: {soap_file}")
    return build_clinical_dataset(
        load_json_list(trajectories_file, "patients"),
        load_json_list(soap_file, "notes"),
    )


def _filter_dataset_by_patient_ids(dataset: ClinicalDataset, patient_ids: set[str]) -> ClinicalDataset:
    if not patient_ids:
        return ClinicalDataset()
    patients = [row for row in dataset.patients if row["patient_id"] in patient_ids]
    encounters = [row for row in dataset.encounters if row["patient_id"] in patient_ids]
    encounter_ids = {row["id"] for row in encounters}
    lab_panels = [row for row in dataset.lab_panels if row["encounter_id"] in encounter_ids]
    lab_panel_ids = {row["id"] for row in lab_panels}
    filtered = ClinicalDataset(
        patients=patients,
        encounters=encounters,
        medications=[row for row in dataset.medications if row["encounter_id"] in encounter_ids],
        investigations=[row for row in dataset.investigations if row["encounter_id"] in encounter_ids],
        diagnoses=[row for row in dataset.diagnoses if row["encounter_id"] in encounter_ids],
        tags=[row for row in dataset.tags if row["encounter_id"] in encounter_ids],
        lab_panels=lab_panels,
        lab_results=[row for row in dataset.lab_results if row["lab_panel_id"] in lab_panel_ids],
        progress_notes=[row for row in dataset.progress_notes if row["patient_id"] in patient_ids],
    )
    filtered.expected = ExpectedCounts(
        patients=len(filtered.patients),
        encounters=len(filtered.encounters),
        medications=len(filtered.medications),
        investigations=len(filtered.investigations),
        diagnoses=len(filtered.diagnoses),
        tags=len(filtered.tags),
        lab_panels=len(filtered.lab_panels),
        lab_results=len(filtered.lab_results),
        progress_notes=len(filtered.progress_notes),
    )
    return filtered


def _fetch_supabase_patient_ids(client: Client) -> set[str]:
    ids: set[str] = set()
    offset = 0
    page_size = 1000
    while True:
        result = (
            client.table("patients")
            .select("patient_id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = result.data or []
        if not rows:
            break
        ids.update(row["patient_id"] for row in rows if row.get("patient_id"))
        if len(rows) < page_size:
            break
        offset += page_size
    return ids


def _new_patient_ids(full_dataset: ClinicalDataset, existing_ids: set[str]) -> set[str]:
    return {row["patient_id"] for row in full_dataset.patients if row["patient_id"] not in existing_ids}


def _should_skip(mode: str, patient_count: int, note_count: int, expected: ExpectedCounts) -> bool:
    if mode != "if_empty":
        return False
    if patient_count == 0:
        return False
    if note_count == 0:
        logger.warning(
            "Patients exist (%s) but clinical_progress_notes is empty — reloading",
            patient_count,
        )
        return False
    if patient_count >= expected.patients and note_count >= expected.progress_notes:
        logger.info(
            "Prepopulate skipped: clinical data already loaded (%s patients, %s SOAP notes)",
            patient_count,
            note_count,
        )
        return True
    logger.warning(
        "Partial data (patients=%s/%s, notes=%s/%s) — reloading",
        patient_count,
        expected.patients,
        note_count,
        expected.progress_notes,
    )
    return False


def _dataset_rows(dataset: ClinicalDataset) -> dict[str, list[dict]]:
    return {
        "patients": dataset.patients,
        "encounters": dataset.encounters,
        "encounter_medications": dataset.medications,
        "encounter_investigations": dataset.investigations,
        "encounter_diagnoses": dataset.diagnoses,
        "encounter_tags": dataset.tags,
        "lab_panels": dataset.lab_panels,
        "lab_results": dataset.lab_results,
        "clinical_progress_notes": dataset.progress_notes,
    }


def _supabase_count(client: Client, table: str) -> int:
    result = client.table(table).select("*", count="exact", head=True).execute()
    return int(result.count or 0)


def _supabase_clear(client: Client, table: str) -> None:
    if table == "patients":
        client.table(table).delete().neq("patient_id", "").execute()
    else:
        client.table(table).delete().neq("id", NULL_UUID).execute()


def _supabase_upsert(client: Client, table: str, rows: list[dict], on_conflict: str, batch_size: int) -> None:
    if not rows:
        return
    total = len(rows)
    for start in range(0, total, batch_size):
        chunk = rows[start : start + batch_size]
        client.table(table).upsert(chunk, on_conflict=on_conflict).execute()
        logger.info("Upserted %s/%s into %s", min(start + batch_size, total), total, table)


def _supabase_sync(client: Client, dataset: ClinicalDataset) -> None:
    rows = _dataset_rows(dataset)
    for table, on_conflict, batch_size in SUPABASE_UPSERTS:
        _supabase_upsert(client, table, rows[table], on_conflict, batch_size)


def _supabase_verify(client: Client, expected: ExpectedCounts) -> None:
    for table, target in (
        ("patients", expected.patients),
        ("encounters", expected.encounters),
        ("clinical_progress_notes", expected.progress_notes),
        ("lab_results", expected.lab_results),
    ):
        actual = _supabase_count(client, table)
        if actual != target:
            logger.warning("Row count mismatch for %s: expected %s, got %s", table, target, actual)


def _prepopulate_supabase(settings: Settings, mode: str) -> None:
    client = get_supabase_client()
    logger.info("Prepopulate via Supabase REST (mode=%s)", mode)

    try:
        _supabase_count(client, "patients")
    except Exception as exc:
        logger.error("Schema missing or unreachable. Apply %s first. %s", SCHEMA_SQL, exc)
        raise

    dataset = _load_clinical_dataset(settings)
    if not dataset.patients:
        logger.warning("Prepopulate skipped: no patients in trajectories file")
        return

    patient_count = _supabase_count(client, "patients")
    note_count = _supabase_count(client, "clinical_progress_notes")
    if mode == "sync":
        existing_ids = _fetch_supabase_patient_ids(client)
        new_ids = _new_patient_ids(dataset, existing_ids)
        if not new_ids:
            logger.info("Prepopulate sync: no new patients to load (%s already in DB)", len(existing_ids))
            return
        dataset = _filter_dataset_by_patient_ids(dataset, new_ids)
        logger.info("Prepopulate sync: upserting %s new patients", len(new_ids))
    elif _should_skip(mode, patient_count, note_count, dataset.expected):
        return
    elif mode == "reset" or note_count == 0:
        for table in CLINICAL_TABLES:
            logger.info("Clearing %s...", table)
            _supabase_clear(client, table)

    logger.info(
        "Loading %s patients, %s encounters, %s SOAP notes",
        dataset.expected.patients,
        dataset.expected.encounters,
        dataset.expected.progress_notes,
    )
    _supabase_sync(client, dataset)
    _supabase_verify(client, dataset.expected)
    logger.info(
        "Prepopulate complete — patients=%s encounters=%s notes=%s",
        _supabase_count(client, "patients"),
        _supabase_count(client, "encounters"),
        _supabase_count(client, "clinical_progress_notes"),
    )


def _postgres_sync(cur, dataset: ClinicalDataset, *, incremental: bool = False) -> None:
    from app.db.connection import execute_batch

    encounter_ids = [row["id"] for row in dataset.encounters]
    patient_ids = [row["patient_id"] for row in dataset.patients]
    lab_panel_ids = [row["id"] for row in dataset.lab_panels]
    execute_batch(
        cur,
        """
        INSERT INTO patients (
            patient_id, name, age, sex, inclusion_exclusion_criteria,
            specialty_key, specialty_label, scenario_brief, source_custom_id, updated_at
        ) VALUES (
            %(patient_id)s, %(name)s, %(age)s, %(sex)s, %(inclusion_exclusion_criteria)s,
            %(specialty_key)s, %(specialty_label)s, %(scenario_brief)s, %(source_custom_id)s, now()
        )
        ON CONFLICT (patient_id) DO UPDATE SET
            name = EXCLUDED.name, age = EXCLUDED.age, sex = EXCLUDED.sex,
            inclusion_exclusion_criteria = EXCLUDED.inclusion_exclusion_criteria,
            specialty_key = EXCLUDED.specialty_key, specialty_label = EXCLUDED.specialty_label,
            scenario_brief = EXCLUDED.scenario_brief, source_custom_id = EXCLUDED.source_custom_id,
            updated_at = now()
        """,
        dataset.patients,
        page_size=200,
    )
    execute_batch(
        cur,
        """
        INSERT INTO encounters (
            id, patient_id, encounter_id, encounter_index, encounter_type,
            days_since_baseline, occurred_at,
            bp, pulse, resp_rate, temperature, spo2, updated_at
        ) VALUES (
            %(id)s::uuid, %(patient_id)s, %(encounter_id)s, %(encounter_index)s, %(encounter_type)s,
            %(days_since_baseline)s, %(occurred_at)s,
            %(bp)s, %(pulse)s, %(resp_rate)s, %(temperature)s, %(spo2)s, now()
        )
        ON CONFLICT (patient_id, encounter_index) DO UPDATE SET
            id = EXCLUDED.id, encounter_id = EXCLUDED.encounter_id,
            encounter_type = EXCLUDED.encounter_type,
            days_since_baseline = EXCLUDED.days_since_baseline,
            occurred_at = EXCLUDED.occurred_at,
            bp = EXCLUDED.bp, pulse = EXCLUDED.pulse, resp_rate = EXCLUDED.resp_rate,
            temperature = EXCLUDED.temperature, spo2 = EXCLUDED.spo2, updated_at = now()
        """,
        dataset.encounters,
        page_size=200,
    )

    child_tables = (
        ("encounter_medications", ["encounter_id", "medication", "sort_order"], dataset.medications),
        ("encounter_investigations", ["encounter_id", "investigation", "sort_order"], dataset.investigations),
        ("encounter_diagnoses", ["encounter_id", "diagnosis", "sort_order"], dataset.diagnoses),
        ("encounter_tags", ["encounter_id", "tag", "sort_order"], dataset.tags),
    )
    for table, columns, rows in child_tables:
        if incremental and encounter_ids:
            cur.execute(f"DELETE FROM {table} WHERE encounter_id = ANY(%s::uuid[])", (encounter_ids,))
        elif not incremental:
            cur.execute(f"DELETE FROM {table}")
        if not rows:
            continue
        col_sql = ", ".join(columns)
        placeholders = ", ".join(
            f"%({c})s::uuid" if c == "encounter_id" else f"%({c})s" for c in columns
        )
        execute_batch(cur, f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})", rows, page_size=500)

    if incremental and encounter_ids:
        if lab_panel_ids:
            cur.execute("DELETE FROM lab_results WHERE lab_panel_id = ANY(%s::uuid[])", (lab_panel_ids,))
        cur.execute("DELETE FROM lab_panels WHERE encounter_id = ANY(%s::uuid[])", (encounter_ids,))
    else:
        cur.execute("DELETE FROM lab_results")
        cur.execute("DELETE FROM lab_panels")
    execute_batch(
        cur,
        """
        INSERT INTO lab_panels (id, encounter_id, panel_name, sort_order)
        VALUES (%(id)s::uuid, %(encounter_id)s::uuid, %(panel_name)s, %(sort_order)s)
        """,
        dataset.lab_panels,
        page_size=200,
    )
    execute_batch(
        cur,
        """
        INSERT INTO lab_results (lab_panel_id, test_name, test_value, sort_order)
        VALUES (%(lab_panel_id)s::uuid, %(test_name)s, %(test_value)s, %(sort_order)s)
        """,
        dataset.lab_results,
        page_size=500,
    )
    if incremental and patient_ids:
        cur.execute("DELETE FROM clinical_progress_notes WHERE patient_id = ANY(%s)", (patient_ids,))
    else:
        cur.execute("DELETE FROM clinical_progress_notes")
    execute_batch(
        cur,
        """
        INSERT INTO clinical_progress_notes (
            encounter_id, patient_id, encounter_index, encounter_type,
            specialty_key, specialty_label, scenario_brief, soap_note, updated_at
        ) VALUES (
            %(encounter_id)s::uuid, %(patient_id)s, %(encounter_index)s, %(encounter_type)s,
            %(specialty_key)s, %(specialty_label)s, %(scenario_brief)s, %(soap_note)s, now()
        )
        """,
        dataset.progress_notes,
        page_size=50,
    )


def _prepopulate_postgres(settings: Settings, mode: str) -> None:
    from psycopg import errors as pg_errors

    from app.db.connection import connect

    if not settings.database_url.startswith("postgresql"):
        logger.info("Skipping prepopulate: local mode requires PostgreSQL DATABASE_URL")
        return

    dataset = _load_clinical_dataset(settings)
    conn = connect(retries=5)
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("SELECT COUNT(*) FROM patients")
                patient_count = int(cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM clinical_progress_notes")
                note_count = int(cur.fetchone()[0])
            except pg_errors.UndefinedTable:
                logger.error("Schema missing. Apply %s first.", SCHEMA_SQL)
                raise

            if mode == "sync":
                cur.execute("SELECT patient_id FROM patients")
                existing_ids = {row[0] for row in cur.fetchall()}
                new_ids = _new_patient_ids(dataset, existing_ids)
                if not new_ids:
                    logger.info("Prepopulate sync: no new patients to load")
                    return
                dataset = _filter_dataset_by_patient_ids(dataset, new_ids)
                logger.info("Prepopulate sync: upserting %s new patients", len(new_ids))
            elif _should_skip(mode, patient_count, note_count, dataset.expected):
                return
            elif mode == "reset" or note_count == 0 or patient_count == 0:
                for table in CLINICAL_TABLES:
                    cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")

            if mode == "sync":
                _postgres_sync(cur, dataset, incremental=True)
            else:
                _postgres_sync(cur, dataset)
        conn.commit()
        logger.info(
            "Prepopulate complete — %s patients, %s encounters, %s SOAP notes",
            dataset.expected.patients,
            dataset.expected.encounters,
            dataset.expected.progress_notes,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def prepopulate_db(settings: Settings) -> None:
    mode = _parse_mode(settings.prepopulate_db or "")
    if mode is None:
        return
    if settings.database_mode == "supabase":
        _prepopulate_supabase(settings, mode)
    else:
        _prepopulate_postgres(settings, mode)
