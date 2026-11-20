"""Expose endpoints for managing a user's papers.

Register POST /api/v1/papers/ingest, GET
/api/v1/papers/{paper_id}/status, and DELETE /api/v1/papers/{paper_id}.
Derive the owner from the authenticated session. Return HTTP 202 with
paper_id and index_status while ingestion is in progress.

Delegate ingestion and status lookup to their respective modules. On
deletion, remove the paper, index, and related runs, and prevent pending
tasks from writing the data back.
"""

from typing import Dict
from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.security import get_current_user
from backend.app.core.schemas import (
    PaperIngestRequest,
    PaperIngestResponse,
    PaperStatusResponse,
)
from backend.app.ingest import ingest_paper
from backend.app.cache.paper_store import (
    get_paper_status,
    delete_paper,
)

router = APIRouter(prefix="/papers", tags=["papers"])


@router.post("/ingest", response_model=PaperIngestResponse, status_code=status.HTTP_200_OK)
async def post_ingest_paper(
    payload: PaperIngestRequest,
    user_id: str = Depends(get_current_user),
) -> PaperIngestResponse:
    """Ingest, validate, and index paper passages under the owner's identity."""
    return await ingest_paper(payload, user_id)


@router.get("/{paper_id}/status", response_model=PaperStatusResponse)
async def get_status(
    paper_id: str,
    user_id: str = Depends(get_current_user),
) -> PaperStatusResponse:
    """Return index readiness and status for the owner's paper."""
    status_obj = get_paper_status(paper_id, user_id)
    if not status_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found or unauthorized",
        )
    return status_obj


@router.delete("/{paper_id}", response_model=Dict[str, str])
async def delete_paper_endpoint(
    paper_id: str,
    user_id: str = Depends(get_current_user),
) -> Dict[str, str]:
    """Delete the owner's paper, index, and derived data."""
    deleted = delete_paper(paper_id, user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found or unauthorized",
        )
    return {"status": "deleted", "paper_id": paper_id}
