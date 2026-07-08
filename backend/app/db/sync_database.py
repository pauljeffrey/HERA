"""CLI: python -m app.db.sync_database [--reset]"""

from __future__ import annotations

import logging
import os
import sys

from app.config import get_settings
from app.services.infra.prepopulate import run_prepopulate

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        os.environ["PREPOPULATE_DB"] = "reset"
        get_settings.cache_clear()
    run_prepopulate()
