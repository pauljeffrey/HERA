"""Build audit dashboard payloads from matching task results."""

from __future__ import annotations

import logging

from app.models.ledger import TrialMatchAuditLedger
from app.models.patients import ExtractedFeature, PatientBiodata, PatientEncounterNote
from app.services.audit.ledger_utils import top_diagnoses
from app.services.clinical.mock_data import EXTRACTED_FEATURES, get_patient_snapshot
from app.services.clinical.patient_data import fetch_patient_biodata, fetch_patient_notes

logger = logging.getLogger(__name__)


def _load_encounters(patient_id: str) -> list[PatientEncounterNote]:
    snapshot = get_patient_snapshot(patient_id)
    if snapshot:
        return snapshot.encounters

    notes = fetch_patient_notes(patient_id)
    return [
        PatientEncounterNote(
            encounter_id=row.get("encounter_id", f"ENC-{row.get('encounter_index', 0)}"),
            encounter_index=int(row.get("encounter_index", 0)),
            encounter_type=row.get("encounter_type") or "Encounter",
            days_since_baseline=0,
            soap_note=row.get("soap_note") or "",
        )
        for row in notes
    ]


def _load_features(patient_id: str) -> list[ExtractedFeature]:
    snapshot = get_patient_snapshot(patient_id)
    if snapshot and snapshot.extracted_features:
        return snapshot.extracted_features
    return EXTRACTED_FEATURES.get(patient_id, [])


def build_dashboard(task: dict) -> dict:
    summary = task.get("result_summary") or {}
    if "patients" not in summary:
        return {
            "task_id": task["task_id"],
            "trial_id": task.get("trial_id"),
            "status": task.get("status"),
            "progress_percentage": task.get("progress_percentage", 0),
            "cohort_size": 0,
            "patient_ids_preview": [],
            "top_diagnoses": [],
            "search_metrics": {},
            "patients": [],
        }

    ledger = TrialMatchAuditLedger.model_validate(summary)
    patients_out: list[dict] = []
    logger.debug("Building dashboard for task_id=%s with %s patient audits", task.get("task_id"), len(ledger.patients))

    for audit in ledger.patients:
        encounters = _load_encounters(audit.patient_id)
        features = _load_features(audit.patient_id)
        biodata_row = fetch_patient_biodata(audit.patient_id)
        biodata = PatientBiodata.model_validate(biodata_row) if biodata_row else None
        patients_out.append(
            {
                "patient_id": audit.patient_id,
                "trial_id": audit.trial_id,
                "overall_status": audit.overall_status,
                "chain_of_thought_summary": audit.chain_of_thought_summary,
                "criteria_ledger": [item.model_dump() for item in audit.criteria_ledger],
                "encounters": [enc.model_dump() for enc in encounters],
                "extracted_features": [feat.model_dump() for feat in features],
                "override_status": None,
                "biodata": biodata.model_dump() if biodata else None,
            }
        )

    return {
        "task_id": task["task_id"],
        "trial_id": ledger.trial_id,
        "status": task.get("status"),
        "progress_percentage": task.get("progress_percentage", 0),
        "cohort_size": len(patients_out),
        "patient_ids_preview": [p["patient_id"] for p in patients_out[:8]],
        "top_diagnoses": top_diagnoses(ledger.patients),
        "search_metrics": {
            "search_space_raw": ledger.search_space_raw,
            "search_space_after_fts": ledger.search_space_after_fts,
            "search_space_after_vs": ledger.search_space_after_vs,
            "execution_latency_ms": ledger.execution_latency_ms,
            "token_cost_usd": ledger.token_cost_usd,
        },
        "patients": patients_out,
    }


def apply_patient_override(
    task: dict,
    *,
    patient_id: str,
    override_status: str,
    reason: str,
) -> dict:
    summary = dict(task.get("result_summary") or {})
    patients = summary.get("patients") or []
    updated: list[dict] = []

    for row in patients:
        item = dict(row)
        if item.get("patient_id") == patient_id:
            item["override_status"] = override_status
            if override_status == "OVERRULED":
                item["overall_status"] = "OVERRULED_BY_CLINICIAN"
            elif override_status == "APPROVED":
                item["overall_status"] = "ELIGIBLE"
        updated.append(item)

    summary["patients"] = updated
    logger.info(
        "Applied clinician override task_id=%s patient_id=%s override_status=%s",
        task.get("task_id"),
        patient_id,
        override_status,
    )
    return summary
