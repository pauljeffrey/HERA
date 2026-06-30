from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import audit, chat, patients, trials
from app.config import get_settings
from app.database import Base, engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.mock_mode:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="HERA API",
    description="Healthcare Eligibility & Reasoning Agent — compliance-first clinical trial matching",
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

api_prefix = settings.api_prefix
app.include_router(trials.router, prefix=api_prefix)
app.include_router(patients.router, prefix=api_prefix)
app.include_router(chat.router, prefix=api_prefix)
app.include_router(audit.router, prefix=api_prefix)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "HERA", "mock_mode": settings.mock_mode}
