"""Structured patient reads used as agent tool calls."""

from __future__ import annotations

import logging
import random
import re
from datetime import datetime
from typing import Any

from app.config import get_settings
from app.db.connection import connect
from app.db.supabase_client import get_supabase_client
from app.services.clinical.mock_data import SOAP_NOTES

logger = logging.getLogger(__name__)

_READ_ONLY_SQL = re.compile(r"^\s*select\b", re.IGNORECASE)
_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create)\b",
    re.IGNORECASE,
)

def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _pick_encounter(rows: list[dict], at: datetime | None) -> dict | None:
    if not rows:
        return None
    if at is None:
        return rows[0]
    return min(rows, key=lambda row: abs((_parse_dt(row.get("occurred_at")) or at) - at))


def _fetch_encounters_postgres(patient_id: str) -> list[dict]:
    sql = """
        SELECT e.id, e.encounter_id, e.encounter_index, e.occurred_at,
               e.bp, e.pulse, e.res_rate, e.temperature, e.spo2
        FROM encounters e
        JOIN patients p ON p.patient_id = e.patient_id
        WHERE p.patient_id = %s
        ORDER BY e.occurred_at DESC
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (patient_id,))
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_encounters(patient_id: str) -> list[dict]:
    settings = get_settings()
    if settings.database_mode == "supabase":
        result = (
            get_supabase_client()
            .table("encounters")
            .select("id, encounter_id, encounter_index, occurred_at, bp, pulse, resp_rate, temperature, spo2")
            .eq("patient_id", patient_id)
            .order("occurred_at", desc=True)
            .execute()
        )
        return result.data or []

    try:
        return _fetch_encounters_postgres(patient_id)
    except Exception:
        return []


def get_vitals(patient_id: str, at: datetime | None = None) -> dict[str, Any]:
    encounter = _pick_encounter(_fetch_encounters(patient_id), at)
    if not encounter:
        return {"patient_id": patient_id, "vitals": None}
    return {
        "patient_id": patient_id,
        "encounter_id": encounter.get("encounter_id"),
        "occurred_at": encounter.get("occurred_at"),
        "vitals": {
            "BP": encounter.get("bp"),
            "PR": encounter.get("pulse"),
            "RR": encounter.get("resp_rate"),
            "Temp": encounter.get("temperature"),
            "SpO2": encounter.get("spo2"),
        },
    }


def _fetch_labs_postgres(encounter_db_id: int) -> list[dict]:
    sql = """
        SELECT lp.panel_name, lr.test_name, lr.test_value
        FROM lab_panels lp
        JOIN lab_results lr ON lr.lab_panel_id = lp.id
        WHERE lp.encounter_id = %s
    """
    with connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (encounter_db_id,))
        return [
            {"panel": row[0], "test_name": row[1], "test_value": row[2]}
            for row in cur.fetchall()
        ]


def get_lab_result(
    patient_id: str,
    at: datetime | None = None,
    *,
    test_name: str | None = None,
) -> dict[str, Any]:
    encounter = _pick_encounter(_fetch_encounters(patient_id), at)
    if not encounter:
        return {"patient_id": patient_id, "labs": []}

    settings = get_settings()
    labs: list[dict] = []

    if settings.database_mode == "supabase":
        panels = (
            get_supabase_client()
            .table("lab_panels")
            .select("id, panel_name")
            .eq("encounter_id", encounter["id"])
            .execute()
        ).data or []
        for panel in panels:
            rows = (
                get_supabase_client()
                .table("lab_results")
                .select("test_name, test_value")
                .eq("lab_panel_id", panel["id"])
                .execute()
            ).data or []
            for row in rows:
                labs.append(
                    {
                        "panel": panel.get("panel_name"),
                        "test_name": row.get("test_name"),
                        "test_value": row.get("test_value"),
                    }
                )
    else:
        try:
            labs = _fetch_labs_postgres(encounter["id"])
        except Exception:
            labs = []

    if test_name:
        needle = test_name.lower()
        labs = [row for row in labs if needle in str(row.get("test_name", "")).lower()]

    return {
        "patient_id": patient_id,
        "encounter_id": encounter.get("encounter_id"),
        "occurred_at": encounter.get("occurred_at"),
        "labs": labs,
    }


def get_investigation_result(
    patient_id: str,
    at: datetime | None = None,
    *,
    investigation: str | None = None,
) -> dict[str, Any]:
    encounter = _pick_encounter(_fetch_encounters(patient_id), at)
    if not encounter:
        return {"patient_id": patient_id, "investigations": []}

    settings = get_settings()
    investigations: list[str] = []

    if settings.database_mode == "supabase":
        rows = (
            get_supabase_client()
            .table("encounter_investigations")
            .select("investigation")
            .eq("encounter_id", encounter["id"])
            .execute()
        ).data or []
        investigations = [row["investigation"] for row in rows]
    else:
        try:
            with connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT investigation FROM encounter_investigations WHERE encounter_id = %s",
                    (encounter["id"],),
                )
                investigations = [row[0] for row in cur.fetchall()]
        except Exception:
            investigations = []

    if investigation:
        needle = investigation.lower()
        investigations = [item for item in investigations if needle in item.lower()]

    return {
        "patient_id": patient_id,
        "encounter_id": encounter.get("encounter_id"),
        "occurred_at": encounter.get("occurred_at"),
        "investigations": investigations,
    }


def _labs_for_encounter(encounter_db_id: str | int) -> list[dict[str, Any]]:
    settings = get_settings()
    if settings.database_mode == "supabase":
        labs: list[dict[str, Any]] = []
        panels = (
            get_supabase_client()
            .table("lab_panels")
            .select("id, panel_name")
            .eq("encounter_id", encounter_db_id)
            .execute()
        ).data or []
        for panel in panels:
            rows = (
                get_supabase_client()
                .table("lab_results")
                .select("test_name, test_value")
                .eq("lab_panel_id", panel["id"])
                .execute()
            ).data or []
            for row in rows:
                labs.append(
                    {
                        "panel": panel.get("panel_name"),
                        "test_name": row.get("test_name") or "",
                        "test_value": row.get("test_value") or "",
                    }
                )
        return labs
    try:
        return _fetch_labs_postgres(encounter_db_id)
    except Exception:
        return []


def _investigations_for_encounter(encounter_db_id: str | int) -> list[str]:
    settings = get_settings()
    if settings.database_mode == "supabase":
        rows = (
            get_supabase_client()
            .table("encounter_investigations")
            .select("investigation")
            .eq("encounter_id", encounter_db_id)
            .execute()
        ).data or []
        return [row["investigation"] for row in rows if row.get("investigation")]
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT investigation FROM encounter_investigations WHERE encounter_id = %s",
                (encounter_db_id,),
            )
            return [row[0] for row in cur.fetchall()]
    except Exception:
        return []


def fetch_patient_clinical_record(patient_id: str) -> dict[str, Any] | None:
    """Encounters, labs, and investigations for quick chart lookup by patient ID."""
    patient_id = patient_id.strip().upper()
    biodata = fetch_patient_biodata(patient_id)
    if not biodata:
        return None

    notes_by_index = {
        int(note.get("encounter_index", 0)): note for note in fetch_patient_notes(patient_id)
    }
    encounters_out: list[dict[str, Any]] = []
    for enc in sorted(_fetch_encounters(patient_id), key=lambda row: int(row.get("encounter_index", 0))):
        index = int(enc.get("encounter_index", 0))
        note = notes_by_index.get(index, {})
        soap = note.get("soap_note") or ""
        encounters_out.append(
            {
                "encounter_id": str(enc.get("encounter_id") or ""),
                "encounter_index": index,
                "encounter_type": str(note.get("encounter_type") or enc.get("encounter_type") or "Encounter"),
                "occurred_at": str(enc.get("occurred_at") or note.get("created_at") or "") or None,
                "soap_excerpt": soap[:480] + ("…" if len(soap) > 480 else ""),
                "labs": _labs_for_encounter(enc["id"]),
                "investigations": _investigations_for_encounter(enc["id"]),
            }
        )

    return {"biodata": biodata, "encounters": encounters_out}


def fetch_patient_notes(patient_id: str) -> list[dict[str, Any]]:
    if get_settings().database_mode == "supabase":
        rows = (
            get_supabase_client()
            .table("clinical_progress_notes")
            .select("encounter_id, encounter_index, encounter_type, soap_note, created_at")
            .eq("patient_id", patient_id)
            .order("encounter_index")
            .execute()
        ).data or []
        if rows:
            return rows

    try:
        sql = """
            SELECT c.encounter_id, c.encounter_index, c.encounter_type, c.soap_note, c.created_at
            FROM clinical_progress_notes c
            JOIN patients p ON p.patient_id = c.patient_id
            WHERE p.patient_id = %s
            ORDER BY c.encounter_index
        """
        with connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (patient_id,))
            cols = [desc[0] for desc in cur.description]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            if rows:
                return rows
    except Exception:
        pass

    mock = SOAP_NOTES.get(patient_id, [])
    return [
        {
            "encounter_id": note.encounter_id,
            "encounter_index": note.encounter_index,
            "encounter_type": note.encounter_type,
            "soap_note": note.soap_note,
        }
        for note in mock
    ]


def fetch_patient_notes_bulk(patient_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    """Fetch notes for many patients in as few queries as possible, grouped by patient_id.

    Used by evaluate_patients() batches so the analysis agent doesn't issue
    one notes query per patient.
    """
    ids = list(dict.fromkeys(patient_ids))
    if not ids:
        return {}

    grouped: dict[str, list[dict[str, Any]]] = {pid: [] for pid in ids}

    if get_settings().database_mode == "supabase":
        rows = (
            get_supabase_client()
            .table("clinical_progress_notes")
            .select("patient_id, encounter_id, encounter_index, encounter_type, soap_note, created_at")
            .in_("patient_id", ids)
            .order("encounter_index")
            .execute()
        ).data or []
        for row in rows:
            grouped.setdefault(row["patient_id"], []).append(row)
        missing = [pid for pid in ids if not grouped.get(pid)]
        for pid in missing:
            grouped[pid] = fetch_patient_notes(pid)
        return grouped

    try:
        sql = """
            SELECT c.patient_id, c.encounter_id, c.encounter_index, c.encounter_type, c.soap_note, c.created_at
            FROM clinical_progress_notes c
            JOIN patients p ON p.patient_id = c.patient_id
            WHERE p.patient_id = ANY(%s)
            ORDER BY c.patient_id, c.encounter_index
        """
        with connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (ids,))
            cols = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                record = dict(zip(cols, row))
                grouped.setdefault(record["patient_id"], []).append(record)
    except Exception:
        pass

    missing = [pid for pid in ids if not grouped.get(pid)]
    for pid in missing:
        grouped[pid] = fetch_patient_notes(pid)
    return grouped


def validate_constraint(code: str, context: dict[str, Any] | None = None) -> bool:
    # Restricted eval for numeric guard expressions supplied by Agent 2 tools.
    safe_globals = {"__builtins__": {"abs": abs, "min": min, "max": max, "round": round}}
    local_ctx = {"result": False, **(context or {})}
    exec(code, safe_globals, local_ctx)
    return bool(local_ctx.get("result", False))


def _parse_note_datetime(note: dict[str, Any]) -> str:
    return str(note.get("created_at") or note.get("occurred_at") or "")


def get_patient_complete_timeline(patient_id: str) -> dict[str, Any]:
    notes = fetch_patient_notes(patient_id)
    timeline = [
        {
            "encounter_id": row.get("encounter_id"),
            "encounter_index": row.get("encounter_index"),
            "encounter_type": row.get("encounter_type"),
            "encounter_date": _parse_note_datetime(row),
            "soap_note": row.get("soap_note") or "",
        }
        for row in notes
    ]
    return {"patient_id": patient_id, "encounters": timeline, "encounter_count": len(timeline)}


def _extract_medication_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(token in lowered for token in ("medication", " mg", "mcg", "tablet", "capsule", "prescribed")):
            cleaned = line.strip()
            if cleaned:
                lines.append(cleaned)
    return lines


def get_patient_medications(patient_id: str) -> dict[str, Any]:
    notes = fetch_patient_notes(patient_id)
    by_encounter: list[dict[str, Any]] = []
    for note in notes:
        lines = _extract_medication_lines(note.get("soap_note") or "")
        if lines:
            by_encounter.append(
                {
                    "encounter_id": note.get("encounter_id"),
                    "encounter_date": _parse_note_datetime(note),
                    "medication_lines": lines[:15],
                }
            )
    return {"patient_id": patient_id, "medication_encounters": by_encounter}


def get_patient_diagnoses(patient_id: str) -> dict[str, Any]:
    notes = fetch_patient_notes(patient_id)
    diagnoses: list[dict[str, str]] = []
    pattern = re.compile(
        r"(?:diagnosis|assessment|impression|problem list)[:\s-]+(.+)",
        re.IGNORECASE,
    )
    for note in notes:
        text = note.get("soap_note") or ""
        for match in pattern.finditer(text):
            snippet = match.group(1).strip().split("\n")[0][:240]
            if snippet:
                diagnoses.append(
                    {
                        "encounter_id": str(note.get("encounter_id", "")),
                        "encounter_date": _parse_note_datetime(note),
                        "diagnosis_text": snippet,
                    }
                )
    return {"patient_id": patient_id, "diagnoses": diagnoses[:40]}


def get_patient_clinical_snapshot(
    patient_id: str,
    at: datetime | None = None,
) -> dict[str, Any]:
    """Single structured read for vitals, labs, medications, and diagnoses."""
    return {
        "patient_id": patient_id,
        "vitals": get_vitals(patient_id, at),
        "labs": get_lab_result(patient_id, at),
        "investigations": get_investigation_result(patient_id, at),
        "medications": get_patient_medications(patient_id),
        "diagnoses": get_patient_diagnoses(patient_id),
    }


def search_patient_notes(patient_id: str, query: str, *, limit: int = 8) -> dict[str, Any]:
    needle = query.lower().strip()
    if not needle:
        return {"patient_id": patient_id, "matches": []}

    matches: list[dict[str, str]] = []
    for note in fetch_patient_notes(patient_id):
        text = note.get("soap_note") or ""
        idx = text.lower().find(needle)
        if idx < 0:
            continue
        start = max(0, idx - 120)
        end = min(len(text), idx + len(needle) + 120)
        matches.append(
            {
                "encounter_id": str(note.get("encounter_id", "")),
                "encounter_date": _parse_note_datetime(note),
                "snippet": text[start:end],
            }
        )
        if len(matches) >= limit:
            break
    return {"patient_id": patient_id, "query": query, "matches": matches}


# Mirrors app/db/schema.sql minus search-infra columns (fts_doc, embedding)
# so the agent writes SQL against real column names instead of guessing.
DATABASE_SCHEMA: dict[str, list[str]] = {
    "patients": [
        "patient_id", "name", "age", "sex", "inclusion_exclusion_criteria",
        "specialty_key", "specialty_label", "scenario_brief",
    ],
    "encounters": [
        "id", "patient_id", "encounter_id", "encounter_index", "encounter_type",
        "days_since_baseline", "occurred_at", "bp", "pulse", "resp_rate",
        "temperature", "spo2",
    ],
    "encounter_medications": ["id", "encounter_id", "medication"],
    "encounter_investigations": ["id", "encounter_id", "investigation"],
    "encounter_diagnoses": ["id", "encounter_id", "diagnosis"],
    "encounter_tags": ["id", "encounter_id", "tag"],
    "lab_panels": ["id", "encounter_id", "panel_name"],
    "lab_results": ["id", "lab_panel_id", "test_name", "test_value"],
    "clinical_progress_notes": [
        "id", "encounter_id", "patient_id", "encounter_index", "encounter_type",
        "specialty_key", "specialty_label", "scenario_brief", "soap_note",
    ],
    "audit_logs": [
        "log_id", "patient_id", "encounter_id", "trial_id",
        "clinician_override_status", "override_reason_text", "timestamp",
    ],
    "trial_matching_tasks": [
        "task_id", "user_id", "trial_id", "status", "progress_percentage",
        "result_summary", "created_at",
    ],
}

# Child tables reference encounters via its UUID surrogate `encounters.id`,
# NOT the human-readable TEXT `encounters.encounter_id` — joining on the wrong
# one raises `operator does not exist: text = uuid`.
SCHEMA_JOIN_HINTS: list[str] = [
    "patients.patient_id = encounters.patient_id",
    "encounters.id = encounter_medications.encounter_id (UUID join)",
    "encounters.id = encounter_investigations.encounter_id (UUID join)",
    "encounters.id = encounter_diagnoses.encounter_id (UUID join)",
    "encounters.id = encounter_tags.encounter_id (UUID join)",
    "encounters.id = lab_panels.encounter_id (UUID join)",
    "lab_panels.id = lab_results.lab_panel_id (UUID join)",
    "encounters.id = clinical_progress_notes.encounter_id (UUID join)",
    "patients.patient_id = clinical_progress_notes.patient_id",
]


def describe_database_schema() -> dict[str, Any]:
    return {
        "tables": DATABASE_SCHEMA,
        "join_hints": SCHEMA_JOIN_HINTS,
        "notes": [
            "Patient full names live in patients.name (single column; no first_name/last_name).",
            "lab_results.test_value is TEXT — cast before numeric comparisons.",
            "Free-text clinical narrative lives in clinical_progress_notes.soap_note.",
        ],
    }


def query_clinical_database_metadata() -> dict[str, Any]:
    settings = get_settings()
    tables = [
        "patients",
        "encounters",
        "clinical_progress_notes",
        "lab_panels",
        "lab_results",
        "encounter_investigations",
        "trial_matching_tasks",
    ]
    counts: dict[str, int | str] = {}
    if settings.database_mode == "supabase":
        client = get_supabase_client()
        for table in tables:
            try:
                result = client.table(table).select("*", count="exact").limit(1).execute()
                counts[table] = int(result.count or 0)
            except Exception as exc:
                counts[table] = f"unavailable: {exc}"
    else:
        try:
            with connect() as conn, conn.cursor() as cur:
                for table in tables:
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {table}")
                        counts[table] = int(cur.fetchone()[0])
                    except Exception:
                        counts[table] = "unavailable"
        except Exception as exc:
            return {"database_mode": settings.database_mode, "error": str(exc), "tables": tables}

    return {"database_mode": settings.database_mode, "table_counts": counts, "tables": tables}


def execute_analytical_sql_query(sql_query: str, *, limit: int = 100) -> dict[str, Any]:
    query = sql_query.strip().rstrip(";")
    if not _READ_ONLY_SQL.match(query):
        raise ValueError("Only read-only SELECT queries are permitted.")
    if _FORBIDDEN_SQL.search(query):
        raise ValueError("Query contains forbidden SQL keywords.")

    capped = f"SELECT * FROM ({query}) AS hera_analytics LIMIT {max(1, min(limit, 500))}"
    with connect() as conn, conn.cursor() as cur:
        cur.execute(capped)
        cols = [desc[0] for desc in cur.description]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    return {"row_count": len(rows), "rows": rows}


_NUMERIC_COLUMNS = {"age": "age"}
_SQL_AGGREGATES = {"count": "COUNT", "mean": "AVG", "avg": "AVG", "average": "AVG", "min": "MIN", "max": "MAX", "sum": "SUM"}


def compute_cohort_statistic(
    metric: str,
    *,
    patient_ids: list[str] | None = None,
    aggregation: str = "count",
) -> dict[str, Any]:
    """Real aggregation over the actual patient population — a known numeric
    column (e.g. age) via SQL AVG/COUNT/etc, or a full-text keyword match
    count over `clinical_progress_notes` for anything else. Never scans only
    the 3 demo mock patients — this needs to reflect the real cohort."""
    column = _NUMERIC_COLUMNS.get(metric.strip().lower())
    sql_func = _SQL_AGGREGATES.get(aggregation.strip().lower(), "COUNT")

    try:
        with connect() as conn, conn.cursor() as cur:
            if column:
                if patient_ids:
                    cur.execute(
                        f"SELECT {sql_func}({column}), COUNT(*) FROM patients WHERE patient_id = ANY(%s)",
                        (patient_ids,),
                    )
                else:
                    cur.execute(f"SELECT {sql_func}({column}), COUNT(*) FROM patients")
                value, matched = cur.fetchone()
                return {
                    "metric": metric,
                    "aggregation": aggregation,
                    "value": float(value) if value is not None else 0,
                    "patients_matched": int(matched),
                }

            sql = """
                SELECT COUNT(DISTINCT patient_id) FROM clinical_progress_notes
                WHERE soap_note ILIKE %s
            """
            params: list[Any] = [f"%{metric}%"]
            if patient_ids:
                sql += " AND patient_id = ANY(%s)"
                params.append(patient_ids)
            cur.execute(sql, params)
            (matched,) = cur.fetchone()
            return {"metric": metric, "aggregation": "count", "value": int(matched), "patients_matched": int(matched)}
    except Exception as exc:
        logger.warning("compute_cohort_statistic SQL path failed, falling back to demo data: %s", exc)

    ids = patient_ids or list(SOAP_NOTES.keys())
    values: list[float] = []
    for patient_id in ids:
        notes = fetch_patient_notes(patient_id)
        joined = "\n".join(note.get("soap_note") or "" for note in notes)
        if metric.lower() in joined.lower():
            values.append(1.0)

    if aggregation == "count":
        return {"metric": metric, "aggregation": aggregation, "value": len(values), "patients_matched": len(values)}
    if aggregation == "mean" and values:
        return {"metric": metric, "aggregation": aggregation, "value": sum(values) / len(values)}
    return {"metric": metric, "aggregation": aggregation, "value": 0, "patients_matched": 0}


def fetch_patient_biodata(patient_id: str) -> dict[str, Any] | None:
    """Return name, age, sex, and encounter count for one patient."""
    settings = get_settings()
    if settings.database_mode == "supabase":
        client = get_supabase_client()
        patient_result = (
            client.table("patients")
            .select("patient_id, name, age, sex, specialty_label")
            .eq("patient_id", patient_id)
            .limit(1)
            .execute()
        )
        if not patient_result.data:
            return None
        row = patient_result.data[0]
        enc_result = (
            client.table("encounters")
            .select("id", count="exact")
            .eq("patient_id", patient_id)
            .execute()
        )
        row["encounter_count"] = int(enc_result.count or 0)
        return row

    sql = """
        SELECT p.patient_id, p.name, p.age, p.sex, p.specialty_label,
               COUNT(e.id)::int AS encounter_count
        FROM patients p
        LEFT JOIN encounters e ON e.patient_id = p.patient_id
        WHERE p.patient_id = %s
        GROUP BY p.patient_id, p.name, p.age, p.sex, p.specialty_label
        LIMIT 1
    """
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (patient_id,))
            row = cur.fetchone()
            if not row:
                return None
            cols = [desc[0] for desc in cur.description]
            return dict(zip(cols, row))
    except Exception as exc:
        logger.warning("fetch_patient_biodata failed for %s: %s", patient_id, exc)
        return None


def fetch_random_patient() -> dict[str, Any] | None:
    """Pick one patient with biodata and encounter count for the command-center roulette."""
    settings = get_settings()
    if settings.database_mode == "supabase":
        client = get_supabase_client()
        ids_result = client.table("patients").select("patient_id").execute()
        rows = ids_result.data or []
        if not rows:
            return None
        patient_id = random.choice(rows)["patient_id"]
        patient_result = (
            client.table("patients")
            .select("patient_id, name, age, sex, specialty_label")
            .eq("patient_id", patient_id)
            .limit(1)
            .execute()
        )
        if not patient_result.data:
            return None
        row = patient_result.data[0]
        enc_result = (
            client.table("encounters")
            .select("id", count="exact")
            .eq("patient_id", patient_id)
            .execute()
        )
        row["encounter_count"] = int(enc_result.count or 0)
        return row

    sql = """
        SELECT p.patient_id, p.name, p.age, p.sex, p.specialty_label,
               COUNT(e.id)::int AS encounter_count
        FROM patients p
        LEFT JOIN encounters e ON e.patient_id = p.patient_id
        GROUP BY p.patient_id, p.name, p.age, p.sex, p.specialty_label
        ORDER BY RANDOM()
        LIMIT 1
    """
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
            if not row:
                return None
            cols = [desc[0] for desc in cur.description]
            return dict(zip(cols, row))
    except Exception as exc:
        logger.warning("fetch_random_patient failed: %s", exc)
        return None


def count_patients() -> int:
    settings = get_settings()
    if settings.database_mode == "supabase":
        result = get_supabase_client().table("patients").select("patient_id", count="exact").execute()
        return int(result.count or 0)
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM patients")
            (count,) = cur.fetchone()
            return int(count)
    except Exception:
        return len(SOAP_NOTES)
