"""Manage agent run lifecycle and results through FastAPI.

Store runs by owner, paper version, and request_id. A retry with the
same payload returns the existing run. Reusing request_id with a
different payload returns a conflict.

Load the paper and index before running A1 or A2. Record progress for
polling and pass cancellation and the deadline into the pipeline.
Publish results only when the current run state allows it.

On restart, end interrupted runs and retain unreconciled usage. Apply
the product retention limit of at most 24 hours for run data.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
import hashlib
import json
import uuid
import time

from backend.app.core.config import CHAT_TOKEN_LIMIT
from backend.app.core.db import get_connection, transaction
from backend.app.core.limits import check_quota_or_raise
from backend.app.core.schemas import EvidenceItem
from backend.app.agent.schemas import (
    AgentRunRequest,
    AgentRunResponse,
    RunState,
    AnswerBlock,
    StepProgress,
    AgentResult,
)
from backend.app.agent.single_pass import run_single_pass
from backend.app.agent.controller import run_bounded_agent

_active_run_tasks: Dict[Tuple[str, str], asyncio.Task] = {}
_run_event_listeners: Dict[Tuple[str, str], List[asyncio.Queue]] = {}
_run_event_history: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}


def publish_run_event(owner_id: str, run_id: str, event: Dict[str, Any]) -> None:
    """Broadcast an execution event to active listeners and record history for late subscribers."""
    key = (owner_id, run_id)
    history = _run_event_history.setdefault(key, [])
    if event.get("type") == "delta" and history and history[-1].get("type") == "delta":
        history[-1] = event  # Late subscribers only need the latest accumulated text.
    else:
        history.append(event)
    for q in list(_run_event_listeners.get(key, [])):
        try:
            q.put_nowait(event)
        except Exception:
            pass


def register_run_listener(owner_id: str, run_id: str) -> Tuple[asyncio.Queue, List[Dict[str, Any]]]:
    """Register an SSE listener for an active or completed run."""
    key = (owner_id, run_id)
    q: asyncio.Queue = asyncio.Queue()
    _run_event_listeners.setdefault(key, []).append(q)
    history = list(_run_event_history.get(key, []))
    return q, history


def unregister_run_listener(owner_id: str, run_id: str, q: asyncio.Queue) -> None:
    """Unregister an SSE listener."""
    key = (owner_id, run_id)
    if key in _run_event_listeners:
        try:
            _run_event_listeners[key].remove(q)
            if not _run_event_listeners[key]:
                _run_event_listeners.pop(key, None)
        except ValueError:
            pass


def compute_request_fingerprint(paper_id: str, question: str) -> str:
    """Compute deterministic SHA-256 fingerprint for request payload."""
    raw = f"{paper_id}:{question.strip()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()




def conversation_history(chat_id, owner_id, question):
    """Keep the full transcript in SQLite; select relevant old turns plus recency."""
    if not chat_id:
        return []
    from backend.app.retrieval.bm25 import LuceneBM25, tokenize_text
    rows = get_connection().execute("SELECT question, answer_blocks FROM runs WHERE chat_id = ? AND owner_id = ? AND status IN ('completed', 'partial') ORDER BY created_at", (chat_id, owner_id)).fetchall()
    turns = [(r["question"], "\n\n".join(b["text"] for b in json.loads(r["answer_blocks"] or "[]"))) for r in rows if r["question"]]
    if not turns:
        return []
    selected = set(range(max(0, len(turns)-3), len(turns)))
    corpus = [tokenize_text(q + " " + a) for q,a in turns]
    if any(corpus):
        scores = LuceneBM25(corpus).get_scores(tokenize_text(question))
        selected.update(i for i in sorted(range(len(turns)), key=lambda i: scores[i], reverse=True)[:3] if scores[i] > 0)
    return [item for i in sorted(selected) for item in ({"role":"user","content":turns[i][0]}, {"role":"assistant","content":turns[i][1][:4096]})]

def get_chat_state(chat_id, owner_id):
    row = get_connection().execute("SELECT * FROM conversations WHERE chat_id = ? AND owner_id = ?", (chat_id, owner_id)).fetchone()
    if not row:
        return {}
    return {"chat_id": chat_id, "tokens_used": row["tokens_used"], "token_limit": CHAT_TOKEN_LIMIT,
            "usage_estimated": bool(row["usage_estimated"]),
            "chat_exhausted": bool(row["exhausted"]) or row["tokens_used"] >= CHAT_TOKEN_LIMIT}


def settle_run_usage(run_id, owner_id, router):
    if router is None:
        return
    total = sum(a.input_tokens + a.output_tokens for a in router.attempts)
    with transaction() as conn:
        row = conn.execute("SELECT chat_id FROM runs WHERE run_id = ? AND owner_id = ?", (run_id, owner_id)).fetchone()
        if row and row["chat_id"]:
            conn.execute("UPDATE runs SET tokens_used = ? WHERE run_id = ?", (total, run_id))
            conn.execute("UPDATE conversations SET tokens_used = tokens_used + ?, usage_estimated = MAX(usage_estimated, ?), exhausted = MAX(exhausted, ?) WHERE chat_id = ? AND owner_id = ?",
                         (total, int(router.usage_estimated), int(router.budget_exhausted), row["chat_id"], owner_id))

def row_to_run_response(row: Any) -> AgentRunResponse:
    """Deserialize SQLite row to AgentRunResponse."""
    answer_blocks = None
    if row["answer_blocks"]:
        raw_blocks = json.loads(row["answer_blocks"])
        answer_blocks = [AnswerBlock(**b) for b in raw_blocks]

    evidence = None
    if row["evidence_ids"]:
        raw_ev = json.loads(row["evidence_ids"])
        evidence = [EvidenceItem(**e) for e in raw_ev]

    limitations = (
        row["limitations"]
        if ("limitations" in row.keys() and row["limitations"])
        else None
    )

    step_progress = None
    if "step_progress" in row.keys() and row["step_progress"]:
        try:
            raw_sp = json.loads(row["step_progress"])
            step_progress = [StepProgress(**s) for s in raw_sp]
        except Exception:
            pass

    return AgentRunResponse(
        run_id=row["run_id"],
        paper_id=row["paper_id"],
        status=RunState(row["status"]),
        retrieval_mode=row["retrieval_mode"],
        retrieval_fallback_reason=row["retrieval_fallback_reason"],
        serving_model=row["serving_model"],
        fallback_reason=row["fallback_reason"],
        limitations=limitations,
        answer_blocks=answer_blocks,
        evidence=evidence,
        step_progress=step_progress,
        error_message=row["error_message"],
        follow_ups=json.loads(row["follow_ups"] or "[]"),
        **get_chat_state(row["chat_id"], row["owner_id"]),
    )


async def _execute_run_worker(
    run_id: str,
    req: AgentRunRequest,
    owner_id: str,
) -> None:
    """Background task worker executing pipeline, handling cancellation and failures."""
    conn = get_connection()
    router = None
    accounted = False
    try:
        # Check if cancelled before starting
        cursor = conn.execute(
            "SELECT status, deadline FROM runs WHERE run_id = ? AND owner_id = ?",
            (run_id, owner_id),
        )
        row = cursor.fetchone()
        if not row or row["status"] == RunState.CANCELLED.value:
            return

        remaining_seconds = max(0, (datetime.fromisoformat(row["deadline"]) - datetime.now(timezone.utc)).total_seconds())
        with transaction() as tx_conn:
            tx_conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ? AND owner_id = ? AND status != ?",
                (
                    RunState.RUNNING.value,
                    datetime.now(timezone.utc).isoformat(),
                    run_id,
                    owner_id,
                    RunState.CANCELLED.value,
                ),
            )
        publish_run_event(owner_id, run_id, {"type": "status", "status": "running"})

        def handle_event(ev: Dict[str, Any]):
            publish_run_event(owner_id, run_id, ev)

        from backend.app.core.config import get_settings
        async with asyncio.timeout(remaining_seconds):
            from backend.app.agent.scope import plan_research, REFUSALS
            from backend.app.agent.model_router import ModelRouter
            from backend.app.providers.llm_gateway import LLMGateway
            from backend.app.cache.paper_store import get_paper_status
            from backend.app.user_state import personal_evidence, remember_result
            personal_sources = personal_evidence(owner_id, req.question)
            chat = get_chat_state(req.chat_id, owner_id)
            router, gateway = ModelRouter(level=req.level, token_budget=CHAT_TOKEN_LIMIT - chat.get("tokens_used", 0)), LLMGateway()
            deadline = time.monotonic() + remaining_seconds
            handle_event({"type": "activity", "state": "checking_scope", "message": "Understanding the research question..."})
            # The configured Claude gateway drops image blocks. Its High answers
            # use observations from a vision-capable reader, charged to this chat.
            scope_router = router
            if req.images and req.level == "high":
                from backend.app.agent.model_router import RoutingMode
                scope_router = ModelRouter(mode=RoutingMode.PRIMARY_ONLY, level="low", token_budget=router.token_budget)
            try:
                plan = await plan_research(req, get_paper_status(req.paper_id, owner_id).title,
                                           scope_router, gateway, deadline, owner_id, run_id,
                                           '\n'.join(source.text for source in personal_sources))
            finally:
                if scope_router is not router:
                    router.attempts.extend(scope_router.attempts)
                    router.usage_estimated = scope_router.usage_estimated
                    router.budget_exhausted = scope_router.budget_exhausted
            if req.images and req.level == "high" and plan.scope != "refuse" and len(plan.image_notes) != len(req.images):
                raise RuntimeError("The visual reader could not inspect every image. Please attach a clearer crop and retry.")
            if plan.scope == "refuse":
                result = AgentResult(run_id=run_id, paper_id=req.paper_id, status=RunState.REFUSED,
                                     answer_blocks=[AnswerBlock(text=REFUSALS[plan.language])],
                                     serving_model=router.get_active_model())
            elif req.mode == "A1" and plan.scope == "paper" and not req.images:
                result = await run_single_pass(run_id, req.paper_id, owner_id, req.question, router=router, gateway=gateway)
            else:
                result = await run_bounded_agent(
                    run_id, req.paper_id, owner_id, req.question, history=req.history, on_event=handle_event,
                    router=router, gateway=gateway, external_query=plan.query if plan.scope == "literature" else None,
                    allow_external=plan.scope == "literature",
                    images=req.images, image_notes=plan.image_notes or None, image_pixels=req.level != "high", paper_query=plan.paper_query or None,
                    turn_timeout_seconds=max(0.001, deadline - time.monotonic()),
                    personal_sources=personal_sources,
                )
            remember_result(owner_id, req, result)

        cursor = conn.execute(
            "SELECT status FROM runs WHERE run_id = ? AND owner_id = ?",
            (run_id, owner_id),
        )
        row = cursor.fetchone()
        if row and row["status"] == RunState.CANCELLED.value:
            return

        finish_time = datetime.now(timezone.utc).isoformat()
        blocks_json = json.dumps([b.model_dump() for b in result.answer_blocks])
        evidence_json = json.dumps([e.model_dump() for e in result.evidence])

        with transaction() as tx_conn:
            tx_conn.execute(
                """
                UPDATE runs SET
                    status = ?,
                    retrieval_mode = ?,
                    retrieval_fallback_reason = ?,
                    serving_model = ?,
                    fallback_reason = ?,
                    limitations = ?,
                    answer_blocks = ?,
                    evidence_ids = ?,
                    updated_at = ?
                WHERE run_id = ? AND owner_id = ? AND status != ?
                """,
                (
                    result.status.value,
                    result.retrieval_mode,
                    result.retrieval_fallback_reason,
                    result.serving_model,
                    result.fallback_reason,
                    result.limitations,
                    blocks_json,
                    evidence_json,
                    finish_time,
                    run_id,
                    owner_id,
                    RunState.CANCELLED.value,
                ),
            )
        with transaction() as tx_conn:
            tx_conn.execute("UPDATE runs SET follow_ups = ? WHERE run_id = ? AND owner_id = ?", (json.dumps(result.follow_ups), run_id, owner_id))
        settle_run_usage(run_id, owner_id, router)
        accounted = True
        publish_run_event(owner_id, run_id, {
            "type": "done",
            **get_chat_state(req.chat_id, owner_id),
            "follow_ups": result.follow_ups,
            "status": result.status.value,
            "answer_blocks": [b.model_dump() for b in result.answer_blocks],
            "evidence": [e.model_dump() for e in result.evidence],
            "serving_model": result.serving_model,
            "fallback_reason": result.fallback_reason,
            "limitations": result.limitations,
        })
    except asyncio.CancelledError:
        with transaction() as tx_conn:
            tx_conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ? AND owner_id = ?",
                (
                    RunState.CANCELLED.value,
                    datetime.now(timezone.utc).isoformat(),
                    run_id,
                    owner_id,
                ),
            )
        settle_run_usage(run_id, owner_id, router)
        accounted = True
        publish_run_event(owner_id, run_id, {"type": "status", "status": "cancelled", **get_chat_state(req.chat_id, owner_id)})
        raise
    except Exception as err:
        with transaction() as tx_conn:
            tx_conn.execute(
                "UPDATE runs SET status = ?, error_message = ?, updated_at = ? WHERE run_id = ? AND owner_id = ? AND status != ?",
                (
                    RunState.FAILED.value,
                    str(err),
                    datetime.now(timezone.utc).isoformat(),
                    run_id,
                    owner_id,
                    RunState.CANCELLED.value,
                ),
            )
        settle_run_usage(run_id, owner_id, router)
        accounted = True
        publish_run_event(owner_id, run_id, {"type": "error", "error": str(err), **get_chat_state(req.chat_id, owner_id)})
    finally:
        if not accounted:
            settle_run_usage(run_id, owner_id, router)
        _active_run_tasks.pop((owner_id, run_id), None)
        # Terminal answers are durable in SQLite; do not retain their stream forever.
        _run_event_history.pop((owner_id, run_id), None)


async def create_or_get_run(
    req: AgentRunRequest,
    owner_id: str,
) -> Tuple[Optional[AgentRunResponse], bool, bool]:
    """Create a new run or return existing run for idempotent request.

    Returns:
        (response, is_new, is_conflict)
    """
    from backend.app.cache.paper_store import get_paper_status
    from backend.app.core.config import get_settings
    from fastapi import HTTPException
    paper = get_paper_status(req.paper_id, owner_id)
    if not paper:
        raise HTTPException(404, "Paper not found or unauthorized")
    if not paper.lexical_ready:
        raise HTTPException(409, "Paper is not ready")
    fingerprint = hashlib.sha256(json.dumps(req.model_dump(exclude={"request_id"}), sort_keys=True).encode()).hexdigest()
    conn = get_connection()

    cursor = conn.execute(
        "SELECT * FROM runs WHERE owner_id = ? AND request_id = ?",
        (owner_id, req.request_id),
    )
    existing = cursor.fetchone()

    if existing:
        if existing["request_fingerprint"] == fingerprint:
            return row_to_run_response(existing), False, False
        else:
            return None, False, True

    chat_id = req.chat_id or f"chat_{uuid.uuid4().hex}"
    chat = get_chat_state(chat_id, owner_id)
    if req.chat_id and not chat:
        raise HTTPException(404, "Chat not found or unauthorized")
    if chat.get("chat_exhausted"):
        raise HTTPException(409, "This chat has reached its token budget. Start a new chat.")

    # Check and consume agent_turns quota
    check_quota_or_raise(owner_id, "agent_turns")

    run_id = f"run_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(seconds=get_settings().limits.turn_timeout_seconds)

    # Insert initial queued record
    with transaction() as tx_conn:
        if tx_conn.execute("SELECT 1 FROM runs WHERE chat_id = ? AND status IN ('queued', 'running')", (chat_id,)).fetchone():
            raise HTTPException(409, "A question is already running in this chat")
        if not req.chat_id:
            tx_conn.execute("INSERT INTO conversations (chat_id, owner_id, paper_id) VALUES (?, ?, ?)", (chat_id, owner_id, req.paper_id))
        elif not tx_conn.execute("SELECT 1 FROM conversations WHERE chat_id = ? AND owner_id = ? AND paper_id = ?", (chat_id, owner_id, req.paper_id)).fetchone():
            previous = tx_conn.execute("SELECT p.arxiv_id, p.version FROM conversations c JOIN papers p ON c.paper_id = p.paper_id WHERE c.chat_id = ? AND c.owner_id = ?", (chat_id, owner_id)).fetchone()
            if not previous or previous["arxiv_id"] != paper.arxiv_id or previous["version"] != paper.version:
                raise HTTPException(404, "Chat does not belong to this paper")
            tx_conn.execute("UPDATE conversations SET paper_id = ? WHERE chat_id = ? AND owner_id = ?", (req.paper_id, chat_id, owner_id))
        tx_conn.execute(
            """
            INSERT INTO runs (
                run_id, owner_id, paper_id, request_id, request_fingerprint,
                status, created_at, updated_at, deadline, chat_id, question, images
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                owner_id,
                req.paper_id,
                req.request_id,
                fingerprint,
                RunState.QUEUED.value,
                now.isoformat(),
                now.isoformat(),
                deadline.isoformat(),
                chat_id,
                req.question,
                json.dumps([image.model_dump() for image in req.images]),
            ),
        )

    worker_req = req.model_copy(update={"chat_id": chat_id, "history": conversation_history(chat_id, owner_id, req.question) or req.history})
    task = asyncio.create_task(_execute_run_worker(run_id, worker_req, owner_id))
    _active_run_tasks[(owner_id, run_id)] = task

    return (
        AgentRunResponse(
            run_id=run_id,
            paper_id=req.paper_id,
            status=RunState.QUEUED,
            **get_chat_state(chat_id, owner_id),
        ),
        True,
        False,
    )


def get_run(run_id: str, owner_id: str) -> Optional[AgentRunResponse]:
    """Retrieve owner-scoped run response by run_id."""
    conn = get_connection()
    cursor = conn.execute(
        "SELECT * FROM runs WHERE run_id = ? AND owner_id = ?",
        (run_id, owner_id),
    )
    row = cursor.fetchone()
    return row_to_run_response(row) if row else None


def cancel_run(run_id: str, owner_id: str) -> Optional[AgentRunResponse]:
    """Mark an active run as cancelled and cancel any in-flight background task."""
    with transaction() as conn:
        cursor = conn.execute(
            "SELECT * FROM runs WHERE run_id = ? AND owner_id = ?",
            (run_id, owner_id),
        )
        row = cursor.fetchone()
        if not row:
            return None

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ? AND owner_id = ?",
            (RunState.CANCELLED.value, now, run_id, owner_id),
        )

    publish_run_event(owner_id, run_id, {"type": "status", "status": "cancelled"})
    _run_event_history.pop((owner_id, run_id), None)

    task = _active_run_tasks.get((owner_id, run_id))
    if task and not task.done():
        task.cancel()

    return get_run(run_id, owner_id)


def cancel_paper_runs(
    paper_id: str,
    owner_id: str,
    db_path: Optional[str] = None,
) -> None:
    """Cancel all active runs and tasks associated with a paper."""
    conn = get_connection(db_path)
    cursor = conn.execute(
        "SELECT run_id FROM runs WHERE paper_id = ? AND owner_id = ? AND status IN ('queued', 'running')",
        (paper_id, owner_id),
    )
    for row in cursor.fetchall():
        cancel_run(row["run_id"], owner_id)
