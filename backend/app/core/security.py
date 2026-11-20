"""Enforce caller authentication and owner identity.

Authenticate HTTP callers via bearer tokens and derive the owner identity
for scoping all paper, index, retrieval, and agent operations.
"""

from typing import Optional
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from backend.app.core.config import get_settings

security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_scheme),
) -> str:
    """Extract and validate the owner identity from the bearer token."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Empty authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    if token == "dev-default-user" and settings.app.environment != "development":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Shared default identity is not permitted outside development environment",
            headers={"WWW-Authenticate": "Bearer"},
        )

    from backend.app.core.db import get_connection
    import hashlib
    row = get_connection().execute("SELECT owner_id FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if row:
        return row["owner_id"]
    if settings.app.environment != "development":
        raise HTTPException(status_code=401, detail="Invalid session token")

    # In development/test mode, any non-empty bearer token identifies the user.
    # For "Bearer dev-user-1", owner_id is "dev-user-1".
    return token
