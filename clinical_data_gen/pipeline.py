"""End-to-end incremental clinical data pipeline.

Examples (from repo root):
  python clinical_data_gen/pipeline.py trajectories --resume --submit --wait
  python clinical_data_gen/pipeline.py soap --only-new --submit --wait
  python clinical_data_gen/pipeline.py db-sync
  python clinical_data_gen/pipeline.py ingest
  python clinical_data_gen/pipeline.py all --resume --submit --wait
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
TRAJ_SCRIPT = REPO_ROOT / "clinical_data_gen" / "structured_clinical_data" / "generate.py"
SOAP_SCRIPT = REPO_ROOT / "clinical_data_gen" / "soap_notes" / "generate.py"


def _default_trajectories_path() -> Path:
    env_path = os.getenv("PATIENT_TRAJECTORIES_PATH", "").strip()
    if env_path:
        return Path(env_path)
    return REPO_ROOT / "clinical_data_gen" / "structured_clinical_data" / "output" / "patient_trajectories.json"


def _run(cmd: list[str], *, cwd: Path) -> int:
    print(f"\n→ {' '.join(cmd)}")
    return subprocess.call(cmd, cwd=cwd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Incremental HERA clinical data pipeline")
    parser.add_argument(
        "step",
        choices=("trajectories", "soap", "db-sync", "ingest", "all"),
        help="Pipeline stage to run",
    )
    parser.add_argument("--count", type=int, help="Trajectory batch size for this run")
    parser.add_argument("--input", type=Path, help="Trajectory JSON for SOAP step")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--only-new", action="store_true")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--reset-db", action="store_true", help="Full DB reload instead of incremental sync")
    parser.add_argument("--reset-ingest", action="store_true", help="Truncate embeddings before ingest")
    args = parser.parse_args()

    trajectories = args.input or _default_trajectories_path()
    py = sys.executable

    if args.step in ("trajectories", "all"):
        cmd = [py, str(TRAJ_SCRIPT)]
        if args.count:
            cmd.extend(["--count", str(args.count)])
        if args.resume:
            cmd.append("--resume")
        if args.submit:
            cmd.append("--submit")
        if args.wait:
            cmd.append("--wait")
        code = _run(cmd, cwd=REPO_ROOT)
        if code != 0:
            return code

    if args.step in ("soap", "all"):
        cmd = [py, str(SOAP_SCRIPT), "--input", str(trajectories)]
        if args.only_new or args.step == "all":
            cmd.append("--only-new")
        if args.resume:
            cmd.append("--resume")
        if args.submit:
            cmd.append("--submit")
        if args.wait:
            cmd.append("--wait")
        code = _run(cmd, cwd=REPO_ROOT)
        if code != 0:
            return code

    if args.step in ("db-sync", "all"):
        flag = "--reset" if args.reset_db else "--sync"
        code = _run([py, "-m", "app.db.sync_database", flag], cwd=BACKEND_ROOT)
        if code != 0:
            return code

    if args.step in ("ingest", "all"):
        cmd = [py, "-m", "scripts.ingest_ehr"]
        if args.reset_ingest:
            cmd.append("--reset")
        code = _run(cmd, cwd=BACKEND_ROOT)
        if code != 0:
            return code

    print("\nPipeline step complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
