"""Accept arXiv papers and coordinate indexing.

Accept paragraphs the user has consented to send. Validate the arXiv
source, version, structure, and input limits, then compute the content
hash on the server. Reuse paper_id for the same owner, content, and
index configuration.

Chunk paragraphs with chunking.py and build BM25 to reach lexical_ready.
Track embedding progress by batch and set semantic_ready once all
matching vectors are stored.
"""

from typing import Tuple
import hashlib
import uuid
from fastapi import HTTPException, status

from backend.app.core.config import get_settings
from backend.app.core.schemas import (
    PaperIngestRequest,
    PaperIngestResponse,
)
from backend.app.core.limits import check_quota_or_raise
from backend.app.cache.paper_store import (
    find_existing_paper,
    store_paper_and_chunks,
    get_paper_status,
)
from backend.app.retrieval.chunking import chunk_paper


def compute_content_hash(paper_req: PaperIngestRequest) -> str:
    """Compute deterministic SHA-256 hash over normalized section and paragraph content."""
    hasher = hashlib.sha256()
    hasher.update(paper_req.title.strip().encode("utf-8"))
    hasher.update(paper_req.arxiv_id.strip().encode("utf-8"))
    hasher.update(paper_req.version.strip().encode("utf-8"))
    hasher.update(paper_req.parser_version.encode("utf-8"))

    for sec in sorted(paper_req.sections, key=lambda s: s.order):
        hasher.update(f"{sec.id}:{sec.heading}:{sec.path}".encode("utf-8"))

    for p in sorted(paper_req.paragraphs, key=lambda p: p.paragraph_order):
        hasher.update(f"{p.id}:{p.text.strip()}".encode("utf-8"))

    return hasher.hexdigest()


def validate_paper_limits(paper_req: PaperIngestRequest) -> None:
    """Enforce body size, chunk counts, and origin limits."""
    settings = get_settings()

    # Enforce arXiv origin
    if not (paper_req.canonical_url.startswith("https://arxiv.org/html/") or
            paper_req.canonical_url.startswith("https://arxiv.org/abs/") or
            paper_req.canonical_url.startswith("http://localhost")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source URL must originate from arxiv.org",
        )

    # Compute total body size in bytes
    total_bytes = sum(len(p.text.encode("utf-8")) for p in paper_req.paragraphs)
    if total_bytes > settings.limits.max_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Paper body size ({total_bytes} bytes) exceeds limit ({settings.limits.max_body_bytes} bytes)",
        )


async def ingest_paper(
    paper_req: PaperIngestRequest,
    owner_id: str,
) -> PaperIngestResponse:
    """Process incoming paper payload, chunk, and index."""
    validate_paper_limits(paper_req)
    content_hash = compute_content_hash(paper_req)

    # Check if this owner already indexed this exact paper version/content
    existing_paper_id = find_existing_paper(
        owner_id=owner_id,
        arxiv_id=paper_req.arxiv_id,
        version=paper_req.version,
        content_hash=content_hash,
    )
    if existing_paper_id:
        existing_status = get_paper_status(existing_paper_id, owner_id)
        return PaperIngestResponse(
            paper_id=existing_paper_id,
            index_status="ready" if existing_status and existing_status.lexical_ready else "indexing",
            lexical_ready=existing_status.lexical_ready if existing_status else True,
            semantic_ready=existing_status.semantic_ready if existing_status else False,
            content_hash=content_hash,
        )

    # New paper indexing consumes new_indexes quota
    check_quota_or_raise(owner_id, "new_indexes")

    paper_id = f"paper_{uuid.uuid4().hex[:12]}"
    settings = get_settings()
    chunks = chunk_paper(
        paper_req.paragraphs,
        max_tokens=settings.retrieval.max_passage_tokens,
        paper_id=paper_id,
    )

    if len(chunks) > settings.limits.max_chunks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Paper produced {len(chunks)} chunks, exceeding max limit of {settings.limits.max_chunks}",
        )

    # Store paper, sections, passages, and initialize in-memory BM25 index
    store_paper_and_chunks(
        paper_id=paper_id,
        owner_id=owner_id,
        paper_req=paper_req,
        content_hash=content_hash,
        chunks=chunks,
        lexical_ready=True,
        semantic_ready=False,
    )

    return PaperIngestResponse(
        paper_id=paper_id,
        index_status="ready",
        lexical_ready=True,
        semantic_ready=False,
        content_hash=content_hash,
    )
