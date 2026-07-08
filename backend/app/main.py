import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.logging_config import configure_logging

configure_logging()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import audit, chat, criteria, patients, tasks
from app.config import get_settings
from app.services.clinical.plotting import PLOTS_DIR
from app.services.infra.prepopulate import run_prepopulate, should_prepopulate
from app.services.infra.redis_client import close_redis

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if should_prepopulate():
        try:
            await asyncio.to_thread(run_prepopulate)
        except Exception as exc:
            logger.warning("Prepopulate skipped during startup: %s", exc)
    yield
    await close_redis()


app = FastAPI(
    title="HERA API",
    description="Healthcare Eligibility & Reasoning Agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/plots", StaticFiles(directory=PLOTS_DIR), name="plots")

api_prefix = settings.api_prefix
app.include_router(tasks.router, prefix=api_prefix)
app.include_router(patients.router, prefix=api_prefix)
app.include_router(chat.router, prefix=api_prefix)
app.include_router(criteria.router, prefix=api_prefix)
app.include_router(audit.router, prefix=api_prefix)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "HERA", "version": "1.0.0"}
