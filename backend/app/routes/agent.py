"""Expose HTTP endpoints to start, inspect, and cancel agent runs.

Register POST /api/v1/agent/runs, GET /api/v1/agent/runs/{run_id}, and
POST /api/v1/agent/runs/{run_id}/cancel. Authenticate the owner and
validate the paper, question, history, and request_id before passing
them to runs.py.

Return HTTP 202 and run_id on start. Polling returns progress or a
result with validated citations, the serving model, and fallback details
when applicable.
"""

import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from backend.app.core.security import get_current_user
from backend.app.agent.schemas import AgentRunRequest, AgentRunResponse
from backend.app.agent.runs import (
    create_or_get_run,
    get_run,
    cancel_run,
    register_run_listener,
    unregister_run_listener,
)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/runs", response_model=AgentRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def post_start_run(
    payload: AgentRunRequest,
    request: Request,
    user_id: str = Depends(get_current_user),
) -> AgentRunResponse:
    """Create or resume an agent run. Return HTTP 202 with run status."""
    if len(await request.body()) > 3 * 1024 * 1024:
        raise HTTPException(413, "Question and images exceed the 3 MiB request limit")
    res, is_new, is_conflict = await create_or_get_run(payload, user_id)
    if is_conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Request ID '{payload.request_id}' has already been used with a different question or paper.",
        )
    return res


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_run_status(
    run_id: str,
    user_id: str = Depends(get_current_user),
) -> AgentRunResponse:
    """Poll run status and results for the owner."""
    res = get_run(run_id, user_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found or unauthorized",
        )
    return res


@router.get("/runs/{run_id}/events")
async def get_run_events(
    run_id: str,
    user_id: str = Depends(get_current_user),
):
    """Stream real-time agent execution events, activity states, and answer text deltas."""
    run = get_run(run_id, user_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found or unauthorized",
        )

    terminal_states = {"completed", "partial", "evidence_only", "cancelled", "failed", "refused"}

    async def event_generator():
        q, history = register_run_listener(user_id, run_id)
        try:
            # Yield any historical events already recorded
            for ev in history:
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if ev.get("type") in ("done", "error") or ev.get("status") in terminal_states:
                    return

            # If the run was already completed before listener registered and no history
            if run.status.value in terminal_states and not history:
                done_ev = {
                    "type": "done",
                    "status": run.status.value,
                    "answer_blocks": [b.model_dump() for b in (run.answer_blocks or [])],
                    "evidence": [e.model_dump() for e in (run.evidence or [])],
                    "serving_model": run.serving_model,
                    "fallback_reason": run.fallback_reason,
                    "limitations": run.limitations,
                    **{k: getattr(run, k) for k in ("follow_ups", "chat_id", "tokens_used", "token_limit", "chat_exhausted", "usage_estimated")},
                }
                yield f"data: {json.dumps(done_ev, ensure_ascii=False)}\n\n"
                return

            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=12.0)
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                    if ev.get("type") in ("done", "error") or ev.get("status") in terminal_states:
                        break
                except asyncio.TimeoutError:
                    # Keep-alive heartbeat comment
                    yield ": keep-alive\n\n"
                    # Check if run has finished in database
                    current = get_run(run_id, user_id)
                    if current and current.status.value in terminal_states:
                        done_ev = {
                            "type": "done",
                            "status": current.status.value,
                            "answer_blocks": [b.model_dump() for b in (current.answer_blocks or [])],
                            "evidence": [e.model_dump() for e in (current.evidence or [])],
                            "serving_model": current.serving_model,
                            "fallback_reason": current.fallback_reason,
                            "limitations": current.limitations,
                            **{k: getattr(current, k) for k in ("follow_ups", "chat_id", "tokens_used", "token_limit", "chat_exhausted", "usage_estimated")},
                        }
                        yield f"data: {json.dumps(done_ev, ensure_ascii=False)}\n\n"
                        break
        finally:
            unregister_run_listener(user_id, run_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}/cancel", response_model=AgentRunResponse)
async def post_cancel_run(
    run_id: str,
    user_id: str = Depends(get_current_user),
) -> AgentRunResponse:
    """Cancel an active agent run."""
    from backend.app.agent.runs import _active_run_tasks
    task = _active_run_tasks.get((user_id, run_id))
    res = cancel_run(run_id, user_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run not found or unauthorized",
        )
    if task:
        try:
            await task
        except asyncio.CancelledError:
            pass
    return get_run(run_id, user_id)


@router.get("/chats/{chat_id}")
async def get_chat(chat_id: str, user_id: str = Depends(get_current_user)):
    from backend.app.agent.runs import get_chat_state
    result = get_chat_state(chat_id, user_id)
    if not result:
        raise HTTPException(404, "Chat not found or unauthorized")
    return result
