"""Regenerate backend/app/data/criteria_counts.json from patient trajectories."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import CRITERIA_COUNTS_CACHE, load_json_list, trajectories_path
from app.services.clinical.criteria import all_criteria_counts


def main() -> None:
    path = trajectories_path()
    patients = load_json_list(path, "patients")
    criteria = all_criteria_counts(patients)

    CRITERIA_COUNTS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CRITERIA_COUNTS_CACHE.write_text(
        json.dumps({"count": len(criteria), "criteria": criteria}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(criteria)} criteria to {CRITERIA_COUNTS_CACHE}")


if __name__ == "__main__":
    main()
