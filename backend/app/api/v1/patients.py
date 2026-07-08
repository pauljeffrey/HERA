from fastapi import APIRouter, HTTPException

from app.models.patients import PatientSnapshotResponse
from app.services.clinical.mock_data import DEMO_PATIENTS, TRIAL_ID, get_patient_snapshot

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=list[str])
async def list_demo_patients():
    return DEMO_PATIENTS


@router.get("/{patient_id}", response_model=PatientSnapshotResponse)
async def get_patient(patient_id: str, trial_id: str = TRIAL_ID):
    snapshot = get_patient_snapshot(patient_id.strip().upper(), trial_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return snapshot

@router.get("/{patient_id}/encounters/{encounter_index}")
async def get_encounter(patient_id: str, encounter_index: int, trial_id: str = TRIAL_ID):
    snapshot = get_patient_snapshot(patient_id.strip().upper(), trial_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Patient not found")
    for enc in snapshot.encounters:
        if enc.encounter_index == encounter_index:
            return enc
    raise HTTPException(status_code=404, detail="Encounter not found")
