"""Enforce PaperLens input caps, daily quotas, and budget reservations.

Check payload sizes, chunk counts, turn limits, and manage atomic quota
reservations and spend tracking.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from fastapi import HTTPException, status
import sqlite3

from backend.app.core.config import get_settings
from backend.app.core.db import get_connection, transaction


def get_current_date_str() -> str:
    """Return the current UTC date in YYYY-MM-DD format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_remaining_quotas(owner_id: str, db_path: str = None) -> Dict[str, Optional[int]]:
    """Return remaining quotas for the owner for today."""
    settings = get_settings()
    date_str = get_current_date_str()
    conn = get_connection(db_path)

    cursor = conn.execute(
        "SELECT new_indexes, agent_turns, semantic_retrievals FROM quotas WHERE owner_id = ? AND date = ?",
        (owner_id, date_str),
    )
    row = cursor.fetchone()

    return {
        key: None if limit == -1 else max(0, limit - (row[key] if row else 0))
        for key, limit in (
            ("new_indexes", settings.quotas.daily_new_indexes),
            ("agent_turns", settings.quotas.daily_agent_turns),
            ("semantic_retrievals", settings.quotas.daily_semantic_retrievals),
        )
    }


def reserve_quota(owner_id: str, quota_key: str, db_path: str = None) -> bool:
    """Atomically check and increment quota usage. Return True if reserved, False if exhausted."""
    settings = get_settings()
    limits_map = {
        "new_indexes": settings.quotas.daily_new_indexes,
        "agent_turns": settings.quotas.daily_agent_turns,
        "semantic_retrievals": settings.quotas.daily_semantic_retrievals,
    }
    max_allowed = limits_map.get(quota_key)
    if max_allowed is None:
        raise ValueError(f"Unknown quota key: {quota_key}")

    date_str = get_current_date_str()
    with transaction(db_path) as conn:
        cursor = conn.execute(
            "SELECT new_indexes, agent_turns, semantic_retrievals FROM quotas WHERE owner_id = ? AND date = ?",
            (owner_id, date_str),
        )
        row = cursor.fetchone()
        current_used = row[quota_key] if row else 0
        if max_allowed != -1 and current_used >= max_allowed:
            return False

        if row is None:
            conn.execute(
                f"INSERT INTO quotas (owner_id, date, {quota_key}) VALUES (?, ?, 1)",
                (owner_id, date_str),
            )
        else:
            conn.execute(
                f"UPDATE quotas SET {quota_key} = {quota_key} + 1 WHERE owner_id = ? AND date = ?",
                (owner_id, date_str),
            )
        return True


def check_quota_or_raise(owner_id: str, quota_key: str, db_path: str = None) -> None:
    """Reserve quota or raise HTTP 429 Too Many Requests."""
    if not reserve_quota(owner_id, quota_key, db_path):
        now = datetime.now(timezone.utc)
        reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        labels = {"agent_turns": "research questions", "new_indexes": "new paper indexes", "semantic_retrievals": "semantic searches"}
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "DAILY_QUOTA_EXCEEDED",
                "quota": quota_key,
                "message": f"Today's limit for {labels[quota_key]} has been reached. It resets at 00:00 UTC (07:00 Vietnam). For a local installation, configure DAILY_{quota_key.upper()} on the backend.",
                "reset_at": reset.isoformat(),
            },
            headers={"Retry-After": str(max(1, int((reset - now).total_seconds())))},
        )
