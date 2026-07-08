from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class Vitals(BaseModel):
    BP: str = Field(description="e.g., '120/80 mmHg'")
    PR: int = Field(description="bpm")
    RR: int = Field(description="breaths per minute")
    Temp: float = Field(description="Temperature in Celsius")
    SpO2: int = Field(description="SpO2 percentage")


class LabResult(BaseModel):
    test: str = Field(description="Laboratory test name, e.g. 'Creatinine'")
    value: str = Field(description="Result with units, e.g. '1.2 mg/dL'")


class LabPanel(BaseModel):
    panel: str = Field(description="Panel name, e.g. 'kidney_panel' or 'CBC'")
    results: List[LabResult] = Field(description="Tests and values for this panel")


class Encounter(BaseModel):
    id: str = Field(description="Unique ID for this timeline milestone (e.g., 'ENC-001')")
    type: str = Field(description="e.g., 'First Presentation', 'ICU Day 2', 'Discharge Follow-up'")
    days_since_baseline: int = Field(
        description="Days elapsed from the first presentation encounter (0 for baseline)"
    )
    datetime: datetime
    vitals: Vitals
    labs: List[LabPanel] = Field(
        description=(
            "Laboratory panels with structured test results. "
            "e.g., [{'panel': 'kidney_panel', 'results': [{'test': 'Creatinine', 'value': '1.2 mg/dL'}]}]"
        )
    )
    meds: List[str] = Field(description="Active medications during this encounter")
    procedures: List[str] = Field(description="Active or prior procedures for this encounter")
    diagnosis: List[str] = Field(description="Active ICD-10 level text diagnoses")
    tags: List[str] = Field(description="Indexable search tags (e.g., 'HFrEF', 'GDMT_Titration')")


class PatientTrajectory(BaseModel):
    patient_id: str = Field(description="Globally unique patient identifier (e.g., 'PT-89412')")
    name: str = Field(description="Full synthetic realistic name")
    age: int
    sex: str = Field(description="Male, Female, or Intersex")
    inclusion_exclusion_criteria: str = Field(
        description="Trial eligibility constraints this profile validates or invalidates"
    )
    timeline: List[Encounter] = Field(
        description="Chronological history of presentations and follow-ups (2-4 encounters)"
    )
