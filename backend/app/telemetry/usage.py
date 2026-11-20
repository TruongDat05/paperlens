"""Record operational metrics by stage and provider attempt.

Record stage latency, cache hits, models, errors, tokens, and costs.
Distinguish provider-reported usage, estimates, and unknown usage from
attempts that timed out or were canceled.

Record the serving model and fallback reason per run. Limit product logs
to metadata needed for operations.
"""

from datetime import datetime, timezone
from typing import Optional
from backend.app.core.db import get_connection, transaction


def record_usage(
    owner_id: str,
    operation: str,
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost_usd: float = 0.0,
    status: str = "success",
    run_id: Optional[str] = None,
) -> None:
    """Record attempt usage and estimated cost into SQLite usage_ledger."""
    now = datetime.now(timezone.utc).isoformat()
    with transaction() as conn:
        conn.execute(
            """
            INSERT INTO usage_ledger (
                owner_id, run_id, operation, provider, model,
                input_tokens, output_tokens, cost_usd, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                run_id,
                operation,
                provider,
                model,
                input_tokens,
                output_tokens,
                cost_usd,
                status,
                now,
            ),
        )


def get_owner_daily_usage(owner_id: str) -> dict:
    """Compute aggregate usage for owner for the current UTC date."""
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = get_connection()
    cursor = conn.execute(
        """
        SELECT COUNT(*) as calls,
               SUM(input_tokens) as total_input,
               SUM(output_tokens) as total_output,
               SUM(cost_usd) as total_cost
        FROM usage_ledger
        WHERE owner_id = ? AND created_at LIKE ?
        """,
        (owner_id, f"{now_date}%"),
    )
    row = cursor.fetchone()
    return {
        "calls": row["calls"] if row else 0,
        "input_tokens": row["total_input"] or 0,
        "output_tokens": row["total_output"] or 0,
        "cost_usd": float(row["total_cost"] or 0.0),
    }
