"""Serve user session and quota state.

Authenticate callers and return owner session identity, daily feature quotas,
and active service limits.
"""

from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.core.security import get_current_user
from backend.app.core.limits import get_remaining_quotas

router = APIRouter(prefix="/session", tags=["session"])


class QuotaRemaining(BaseModel):
    new_indexes: Optional[int]
    agent_turns: Optional[int]
    semantic_retrievals: Optional[int]


class SessionResponse(BaseModel):
    user_id: str
    quota_remaining: QuotaRemaining


@router.get("", response_model=SessionResponse)
async def get_session(user_id: str = Depends(get_current_user)) -> SessionResponse:
    """Return caller's user ID and current remaining daily quota."""
    remaining = get_remaining_quotas(user_id)
    return SessionResponse(
        user_id=user_id,
        quota_remaining=QuotaRemaining(**remaining),
    )


@router.post("")
async def create_session():
    """Issue a unique anonymous capability; never accept caller-selected production identities."""
    import secrets
    import hashlib
    from backend.app.core.db import transaction
    token = secrets.token_urlsafe(32)
    owner = "anon_" + secrets.token_hex(16)
    with transaction() as conn:
        conn.execute("INSERT INTO sessions VALUES (?, ?)", (hashlib.sha256(token.encode()).hexdigest(), owner))
    return {"token": token}
