"""Centralized logging — stdout + a rotating file, so every pipeline stage
(chat dispatch, FTS/VS funnel, Tier 3 evaluation, dashboard build) is
debuggable from one place instead of scattered terminal output."""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "data" / "logs"
LOG_FILE = LOG_DIR / "hera.log"

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = os.getenv("HERA_LOG_LEVEL", "INFO").upper()
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    root = logging.getLogger()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    logging.getLogger(__name__).info("Logging configured: level=%s file=%s", level, LOG_FILE)
