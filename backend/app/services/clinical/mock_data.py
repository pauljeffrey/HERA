"""Rich mock clinical data for showcase — aligned with Pydantic schemas."""

from app.models.patients import (
    CertaintyStatus,
    EligiblePatient,
    ExtractedFeature,
    IndividualCriterionEvaluation,
    PatientAuditPayload,
    PatientEncounterNote,
    PatientSnapshotResponse,
    PipelineTier,
)
from app.models.ledger import CriteriaVerdict

TRIAL_ID = "TRIAL-HF-2026-001"
TRIAL_NAME = "PARADIGM-HF Extension: HFrEF with GDMT Optimization"

DEMO_PATIENTS = ["PT-000001", "PT-000002", "PT-000003"]

SOAP_NOTES: dict[str, list[PatientEncounterNote]] = {
    "PT-000001": [
        PatientEncounterNote(
            encounter_id="ENC-001",
            encounter_index=0,
            encounter_type="Admission",
            days_since_baseline=0,
            soap_note="""SUBJECTIVE:
Mr. Jeffrey Samad, a 68-year-old male with history of ischemic cardiomyopathy, presents with progressive dyspnea on exertion over 3 weeks. NYHA Class III symptoms. Denies chest pain. No recent hospitalizations.

OBJECTIVE:
Vitals: BP 98/62 mmHg, HR 88 bpm, RR 20, Temp 36.8°C, SpO2 94% on RA.
Cardiac: Regular rhythm, S3 gallop present. JVP elevated to 12 cm.
Labs: Creatinine 1.4 mg/dL, eGFR 52 mL/min/1.73m². BNP 890 pg/mL.
Echo: LVEF is profoundly depressed at around twenty-five percent. Moderate mitral regurgitation.
Diagnosis: HFrEF (LVEF ≤35%), ischemic cardiomyopathy.

ASSESSMENT/PLAN:
1. Acute on chronic HFrEF exacerbation — initiate IV diuresis, uptitrate GDMT.
2. Rule out myocardial infarction — troponin pending.
3. Cardiology consult for GDMT optimization trial screening.""",
        ),
        PatientEncounterNote(
            encounter_id="ENC-002",
            encounter_index=1,
            encounter_type="ICU Day 2",
            days_since_baseline=2,
            soap_note="""SUBJECTIVE:
Day 2 ICU. Patient reports improved breathing. Still fatigued.

OBJECTIVE:
Vitals: BP 102/68 mmHg, HR 82 bpm, SpO2 96% on 2L NC.
Labs: Creatinine 2.1 mg/dL (up from 1.4), potassium 4.8 mEq/L. BNP 720 pg/mL.
Echo repeat: LVEF 28%, no change in MR severity.
Diuresis ongoing — net negative 1.2L yesterday.
Troponin negative x2 — myocardial infarction ruled out.

ASSESSMENT/PLAN:
1. HFrEF — continue GDMT titration, monitor renal function closely.
2. Creatinine elevation likely cardiorenal — hold further diuresis if Cr >2.2.
3. Trial eligibility review: LVEF criterion met; renal function borderline.""",
        ),
        PatientEncounterNote(
            encounter_id="ENC-003",
            encounter_index=2,
            encounter_type="Discharge",
            days_since_baseline=5,
            soap_note="""SUBJECTIVE:
Feeling significantly better. Ambulating independently. NYHA Class II.

OBJECTIVE:
Vitals: BP 108/70 mmHg, HR 78 bpm, SpO2 97% on RA.
Labs: Creatinine 1.8 mg/dL (improved), eGFR 48 mL/min/1.73m².
Medications: Sacubitril/valsartan 24/26 mg BID, carvedilol 12.5 mg BID, spironolactone 25 mg daily, furosemide 40 mg daily.
Echo: LVEF 30%.

ASSESSMENT/PLAN:
1. Stable for discharge on optimized GDMT.
2. Follow-up in 2 weeks. Trial screening deferred pending repeat renal panel.""",
        ),
    ],
    "PT-000002": [
        PatientEncounterNote(
            encounter_id="ENC-001",
            encounter_index=0,
            encounter_type="Admission",
            days_since_baseline=0,
            soap_note="""SUBJECTIVE:
Ms. Elena Rodriguez, 54-year-old female, referred for metastatic breast cancer with new-onset dyspnea.

OBJECTIVE:
Vitals: BP 118/76 mmHg, HR 92 bpm, SpO2 93% on RA.
Labs: Creatinine 0.9 mg/dL, hemoglobin 9.2 g/dL, troponin 0.02 ng/mL.
Echo: LVEF 55%, no regional wall motion abnormalities.
CT chest: Bilateral pleural effusions, no pulmonary embolism.
Diagnosis: Malignant pleural effusion secondary to metastatic breast cancer. No heart failure.

ASSESSMENT/PLAN:
1. Thoracentesis for symptomatic relief.
2. Oncology to evaluate for cardiotoxicity monitoring trial — preserved EF excludes HFrEF trial.""",
        ),
    ],
    "PT-000003": [
        PatientEncounterNote(
            encounter_id="ENC-001",
            encounter_index=0,
            encounter_type="ICU Admission",
            days_since_baseline=0,
            soap_note="""SUBJECTIVE:
Mr. David Chen, 71-year-old male, post-CABG day 1, cardiogenic shock requiring IABP.

OBJECTIVE:
Vitals: BP 85/55 mmHg on norepinephrine 0.08 mcg/kg/min, HR 105 bpm, lactate 4.2 mmol/L.
Labs: Creatinine 1.6 mg/dL, BNP 2100 pg/mL.
Echo: LVEF 22%, severe global hypokinesis post-CABG.
Diagnosis: Post-operative cardiogenic shock, HFrEF.

ASSESSMENT/PLAN:
1. Continue mechanical support, wean vasopressors as tolerated.
2. GDMT contraindicated acutely — trial screening after hemodynamic stabilization.""",
        ),
    ],
}

EXTRACTED_FEATURES: dict[str, list[ExtractedFeature]] = {
    "PT-000001": [
        ExtractedFeature(
            field_name="LVEF",
            raw_text="EF is profoundly depressed at around twenty-five percent",
            normalized_value="LVEF: 25%",
            pipeline_tier=PipelineTier.REGEX,
            confidence_score=0.96,
            encounter_index=0,
            source_span_start=312,
            source_span_end=365,
            certainty=CertaintyStatus.CONFIRMED,
            negated=False,
        ),
        ExtractedFeature(
            field_name="Creatinine",
            raw_text="Creatinine 2.1 mg/dL (up from 1.4)",
            normalized_value="Creatinine: 2.1 mg/dL",
            pipeline_tier=PipelineTier.REGEX,
            confidence_score=0.98,
            encounter_index=1,
            source_span_start=145,
            source_span_end=178,
            certainty=CertaintyStatus.CONFIRMED,
            negated=False,
        ),
        ExtractedFeature(
            field_name="NYHA Class",
            raw_text="NYHA Class III symptoms",
            normalized_value="NYHA: III",
            pipeline_tier=PipelineTier.FULL_TEXT_SEARCH,
            confidence_score=0.91,
            encounter_index=0,
            source_span_start=98,
            source_span_end=120,
            certainty=CertaintyStatus.CONFIRMED,
            negated=False,
        ),
        ExtractedFeature(
            field_name="Myocardial Infarction",
            raw_text="Rule out myocardial infarction — troponin pending",
            normalized_value="MI: Under Evaluation",
            pipeline_tier=PipelineTier.AGENTIC_SEARCH,
            confidence_score=0.89,
            encounter_index=0,
            source_span_start=520,
            source_span_end=565,
            certainty=CertaintyStatus.NEGATIVE,
            negated=True,
        ),
        ExtractedFeature(
            field_name="Myocardial Infarction",
            raw_text="myocardial infarction ruled out",
            normalized_value="MI: Ruled Out",
            pipeline_tier=PipelineTier.AGENTIC_SEARCH,
            confidence_score=0.94,
            encounter_index=1,
            source_span_start=280,
            source_span_end=310,
            certainty=CertaintyStatus.RULED_OUT,
            negated=True,
        ),
        ExtractedFeature(
            field_name="LVEF",
            raw_text="LVEF 28%",
            normalized_value="LVEF: 28%",
            pipeline_tier=PipelineTier.REGEX,
            confidence_score=0.97,
            encounter_index=1,
            source_span_start=195,
            source_span_end=203,
            certainty=CertaintyStatus.CONFIRMED,
            negated=False,
        ),
        ExtractedFeature(
            field_name="Creatinine",
            raw_text="Creatinine 1.8 mg/dL (improved)",
            normalized_value="Creatinine: 1.8 mg/dL",
            pipeline_tier=PipelineTier.REGEX,
            confidence_score=0.97,
            encounter_index=2,
            source_span_start=130,
            source_span_end=160,
            certainty=CertaintyStatus.CONFIRMED,
            negated=False,
        ),
    ],
    "PT-000002": [
        ExtractedFeature(
            field_name="LVEF",
            raw_text="LVEF 55%",
            normalized_value="LVEF: 55%",
            pipeline_tier=PipelineTier.REGEX,
            confidence_score=0.99,
            encounter_index=0,
            source_span_start=210,
            source_span_end=218,
            certainty=CertaintyStatus.CONFIRMED,
            negated=False,
        ),
    ],
    "PT-000003": [
        ExtractedFeature(
            field_name="LVEF",
            raw_text="LVEF 22%",
            normalized_value="LVEF: 22%",
            pipeline_tier=PipelineTier.REGEX,
            confidence_score=0.98,
            encounter_index=0,
            source_span_start=195,
            source_span_end=203,
            certainty=CertaintyStatus.CONFIRMED,
            negated=False,
        ),
    ],
}

CRITERIA_LEDGER_PT001 = [
    IndividualCriterionEvaluation(
        criterion_text="LVEF ≤35% documented on echocardiography within 12 months",
        is_inclusion=True,
        verdict=CriteriaVerdict.MET,
        evidence_quote="LVEF is profoundly depressed at around twenty-five percent",
        confidence_score=0.96,
    ),
    IndividualCriterionEvaluation(
        criterion_text="NYHA Class II-IV heart failure symptoms",
        is_inclusion=True,
        verdict=CriteriaVerdict.MET,
        evidence_quote="NYHA Class III symptoms",
        confidence_score=0.91,
    ),
    IndividualCriterionEvaluation(
        criterion_text="Serum creatinine <2.0 mg/dL at screening",
        is_inclusion=True,
        verdict=CriteriaVerdict.BORDERLINE,
        evidence_quote="Creatinine 2.1 mg/dL (up from 1.4)",
        confidence_score=0.72,
    ),
    IndividualCriterionEvaluation(
        criterion_text="Active myocardial infarction within 30 days",
        is_inclusion=False,
        verdict=CriteriaVerdict.MET,
        evidence_quote="myocardial infarction ruled out",
        confidence_score=0.94,
    ),
    IndividualCriterionEvaluation(
        criterion_text="Estimated GFR <30 mL/min/1.73m²",
        is_inclusion=False,
        verdict=CriteriaVerdict.MET,
        evidence_quote="eGFR 52 mL/min/1.73m²",
        confidence_score=0.93,
    ),
]

MOCK_AUDIT_PAYLOAD = PatientAuditPayload(
    selected_patients=[
        EligiblePatient(
            patient_id="PT-000001",
            trial_id=TRIAL_ID,
            overall_eligible=False,
            justification=(
                "Patient excluded because a serum creatinine of 2.1 mg/dL was noted on Encounter 2 "
                "(ICU Day 2), violating the inclusion threshold of <2.0 mg/dL. "
                "LVEF criterion met (25-28%). Myocardial infarction ruled out. "
                "Repeat creatinine at discharge improved to 1.8 mg/dL — human review recommended."
            ),
            criteria_ledger=CRITERIA_LEDGER_PT001,
        ),
    ],
    execution_latency_ms=1420,
    token_cost_usd=0.0015,
    search_space_raw=100_000,
    search_space_after_fts=10_000,
    search_space_after_vs=1_000,
    search_space_final=1,
)


def get_patient_snapshot(patient_id: str, trial_id: str = TRIAL_ID) -> PatientSnapshotResponse | None:
    encounters = SOAP_NOTES.get(patient_id)
    if not encounters:
        return None
    return PatientSnapshotResponse(
        patient_id=patient_id,
        trial_id=trial_id,
        snapshot_id=f"SNAP-{patient_id}",
        encounters=encounters,
        extracted_features=EXTRACTED_FEATURES.get(patient_id, []),
        audit_payload=MOCK_AUDIT_PAYLOAD if patient_id == "PT-000001" else PatientAuditPayload(
            selected_patients=[],
            execution_latency_ms=800,
            token_cost_usd=0.001,
            search_space_raw=100_000,
            search_space_after_fts=10_000,
            search_space_after_vs=1_000,
            search_space_final=0,
        ),
    )
