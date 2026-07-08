"""Chronological per-patient note index, built once per evaluate_patients() batch.

Replaces per-encounter, per-tool-call DB round-trips with a single bulk
fetch (`patient_data.fetch_patient_notes_bulk`) merged in memory, keyed by
patient so the analysis agent can read a patient's complete timeline (not
just the latest note) and cite exact text spans without hitting the DB again.
"""

from __future__ import annotations

from dataclasses import dataclass


def _note_date(note: dict) -> str:
    return str(note.get("created_at") or note.get("occurred_at") or "")


def _note_header(note: dict) -> str:
    return f"[Encounter {note.get('encounter_id', '?')} — {note.get('encounter_type') or 'Encounter'} — {_note_date(note)}]"


def _note_block(note: dict) -> str:
    return f"{_note_header(note)}\n{note.get('soap_note') or ''}"


@dataclass
class NotesIndex:
    _by_patient: dict[str, list[dict]]

    @classmethod
    def build(cls, notes_by_patient: dict[str, list[dict]]) -> "NotesIndex":
        ordered = {
            patient_id: sorted(notes, key=lambda n: (n.get("encounter_index", 0), _note_date(n)))
            for patient_id, notes in notes_by_patient.items()
        }
        return cls(_by_patient=ordered)

    def notes_for(self, patient_id: str) -> list[dict]:
        return self._by_patient.get(patient_id, [])

    def full_text(self, patient_id: str) -> str:
        """Complete chronological note text for one patient — not truncated,
        so criteria mentioned only in older encounters are still visible."""
        return "\n\n".join(_note_block(note) for note in self.notes_for(patient_id))

    def find_between(
        self,
        patient_id: str,
        start_text: str,
        end_text: str = "",
        *,
        window: int = 400,
    ) -> dict | None:
        """Locate `start_text` in the patient's full note text and return the
        span through `end_text` (or a bounded window if `end_text` isn't
        found), plus the encounter it came from — for verbatim citation."""
        text = self.full_text(patient_id)
        start_idx = text.find(start_text)
        if start_idx < 0:
            return None

        search_from = start_idx + len(start_text)
        end_idx = text.find(end_text, search_from) if end_text else -1
        if end_idx >= 0:
            snippet = text[start_idx : end_idx + len(end_text)]
        else:
            snippet = text[start_idx : search_from + window]

        return {"encounter_id": self._encounter_for_offset(patient_id, start_idx), "snippet": snippet}

    def _encounter_for_offset(self, patient_id: str, offset: int) -> str | None:
        cursor = 0
        for note in self.notes_for(patient_id):
            block_len = len(_note_block(note)) + 2  # + the "\n\n" join separator
            if cursor <= offset < cursor + block_len:
                return note.get("encounter_id")
            cursor += block_len
        return None
