"""Initialize the PaperLens FastAPI application.

Expose the ASGI app at backend.app.main:app, mount routers under
/api/v1, and serve GET /api/v1/health.

Manage configuration, SQLite, provider connections, and background tasks
through the lifespan of a single process. On restart, let ingest and
runs recover their respective state.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.app.core.config import get_settings
from backend.app.core.db import init_db
from backend.app.routes import session, papers, retrieve, agent, account, auth


class HealthResponse(BaseModel):
    status: str
    version: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan: initialize SQLite and background pools."""
    settings = get_settings()
    init_db(settings.db_path)
    yield


app = FastAPI(
    title="PaperLens",
    version="0.1.0",
    description="Evidence-Grounded Research Paper Assistant API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root/versioned health check
@app.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
async def get_health() -> HealthResponse:
    """Return backend health and version without credentials or upstream calls."""
    settings = get_settings()
    return HealthResponse(status="ok", version=settings.app.version)


# Mount routers under /api/v1
app.include_router(session.router, prefix="/api/v1")
app.include_router(papers.router, prefix="/api/v1")
app.include_router(retrieve.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")
app.include_router(account.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
