from fastapi import APIRouter, HTTPException, Path

from app.models.patients import (
    PatientBiodata,
    PatientClinicalRecord,
    PatientSnapshotResponse,
    RandomPatientResponse,
)
from app.services.clinical.mock_data import DEMO_PATIENTS, TRIAL_ID, get_patient_snapshot
from app.services.clinical.patient_data import (
    count_patients,
    fetch_patient_biodata,
    fetch_patient_clinical_record,
    fetch_random_patient,
)

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=list[str])
async def list_demo_patients():
    return DEMO_PATIENTS


@router.get("/random", response_model=RandomPatientResponse)
async def random_patient():
    row = fetch_random_patient()
    total = count_patients()
    if not row:
        return RandomPatientResponse(total_patients=total, patient=None)
    return RandomPatientResponse(
        total_patients=total,
        patient=PatientBiodata.model_validate(row),
    )


@router.get("/{patient_id}/biodata", response_model=PatientBiodata)
async def get_patient_biodata(patient_id: str = Path(pattern=r"^PT-\d{6}$")):
    row = fetch_patient_biodata(patient_id.strip().upper())
    if not row:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return PatientBiodata.model_validate(row)


@router.get("/{patient_id}/record", response_model=PatientClinicalRecord)
async def get_patient_clinical_record(patient_id: str = Path(pattern=r"^PT-\d{6}$")):
    record = fetch_patient_clinical_record(patient_id.strip().upper())
    if not record:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return PatientClinicalRecord.model_validate(record)


@router.get("/{patient_id}", response_model=PatientSnapshotResponse)
async def get_patient(
    patient_id: str = Path(pattern=r"^PT-\d{6}$"),
    trial_id: str = TRIAL_ID,
):
    snapshot = get_patient_snapshot(patient_id.strip().upper(), trial_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return snapshot

@router.get("/{patient_id}/encounters/{encounter_index}")
async def get_encounter(
    patient_id: str = Path(pattern=r"^PT-\d{6}$"),
    encounter_index: int = Path(),
    trial_id: str = TRIAL_ID,
):
    snapshot = get_patient_snapshot(patient_id.strip().upper(), trial_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Patient not found")
    for enc in snapshot.encounters:
        if enc.encounter_index == encounter_index:
            return enc
    raise HTTPException(status_code=404, detail="Encounter not found")
