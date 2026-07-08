"""Shared helpers for audit ledger summaries."""

from app.models.ledger import PatientTrialAudit


def top_diagnoses(patients: list[PatientTrialAudit]) -> list[str]:
    counts: dict[str, int] = {}
    for patient in patients:
        for item in patient.criteria_ledger:
            if item.is_inclusion and item.verdict.value in {"MET", "BORDERLINE"}:
                token = item.criterion_text.split()[0][:24]
                counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
    return [name for name, _ in ranked[:5]]
