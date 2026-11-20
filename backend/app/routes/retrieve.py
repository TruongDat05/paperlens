"""Expose POST /api/v1/retrieve for Evidence Mode.

Authenticate the owner and check access to paper_id. Validate the
question, top-k, and index readiness before passing the loaded paper and
index to the retrieval engine.

Return EvidenceResult with source passages, ranks, retrieval_mode, and
fallback_reason when applicable. Return the appropriate status while
indexing is in progress so the side panel can keep polling.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.config import get_settings
from backend.app.core.security import get_current_user
from backend.app.core.schemas import (
    RetrieveRequest,
    EvidenceResult,
)
from backend.app.cache.paper_store import (
    get_paper_status,
    get_paper_chunks,
    get_bm25_index,
)
from backend.app.retrieval.hybrid import retrieve_hybrid

router = APIRouter(tags=["retrieve"])


@router.post("/retrieve", response_model=EvidenceResult)
async def post_retrieve(
    payload: RetrieveRequest,
    user_id: str = Depends(get_current_user),
) -> EvidenceResult:
    """Perform evidence retrieval for the authenticated owner and paper."""
    settings = get_settings()

    # Validate question length
    if not payload.question.strip() or len(payload.question) > settings.limits.max_question_chars:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Question length exceeds maximum limit of {settings.limits.max_question_chars} characters",
        )

    # Check paper status and owner access
    paper_status = get_paper_status(payload.paper_id, user_id)
    if not paper_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paper not found or unauthorized",
        )

    if not paper_status.lexical_ready:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Paper indexing is still in progress",
        )

    mode = payload.mode or "B1"
    if mode in ["B2", "B3", "B4"]:
        from backend.app.core.limits import check_quota_or_raise
        check_quota_or_raise(user_id, "semantic_retrievals")

    chunks = get_paper_chunks(payload.paper_id, user_id)
    bm25_index = get_bm25_index(payload.paper_id, user_id)

    top_k = min(payload.top_k, 20)
    result = await retrieve_hybrid(
        query=payload.question,
        chunks=chunks,
        bm25_index=bm25_index,
        mode=mode,
        top_k=top_k,
        request_id=payload.request_id,
        paper_id=payload.paper_id,
        owner_id=user_id,
    )
    return result
