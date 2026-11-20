"""Explicit, bounded live contract/API check; uses a disposable database.
Run only with --live. Credentials are read from existing server configuration.
"""
import argparse
import asyncio
import json
import tempfile
from pathlib import Path

async def check():
    from backend.app.core.config import get_settings
    from backend.app.providers.llm_gateway import LLMGateway
    from backend.app.providers.fpt import FPTProvider
    from backend.app.agent.tools import AGENT_TOOLS_SCHEMA
    from backend.app.agent.model_router import normalize_provider_error
    from backend.app.agent.runs import _active_run_tasks
    from backend.app.core.db import _local
    from backend.app.main import app
    from httpx import AsyncClient, ASGITransport
    settings = get_settings()
    previous = settings.db_path, settings.mock_providers, settings.app.environment, settings.retrieval.default_mode
    results = {"kind": "bounded_live_check", "browser_verified": False, "contracts": [], "runs": []}
    with tempfile.TemporaryDirectory(prefix="paperlens-live-") as root:
        settings.db_path = str(Path(root) / "live.db")
        settings.mock_providers = False
        settings.app.environment = "production"
        try:
            fpt = FPTProvider()
            for operation, call in (("embedding", lambda: fpt.get_embeddings(["Self-attention replaces recurrence."])),
                                    ("rerank", lambda: fpt.rerank("attention", ["Self-attention replaces recurrence.", "Bananas."]))):
                try:
                    value = await asyncio.wait_for(call(), 15)
                    results["contracts"].append({"operation": operation, "ok": bool(value), "count": len(value),
                        "dimensions": len(value[0]) if operation == "embedding" and value else None})
                except Exception as err:
                    results["contracts"].append({"operation": operation, "ok": False, "error": normalize_provider_error(err)})
            gateway = LLMGateway()
            messages = [{"role": "system", "content": "Use search_evidence to find the requested fact. Do not answer before searching."},
                        {"role": "user", "content": "Search for self-attention."}]
            try:
                primary = await asyncio.wait_for(gateway.generate_step(settings.models.primary, messages, AGENT_TOOLS_SCHEMA), 10)
                calls = primary.get("tool_calls", [])
                results["contracts"].append({"model": settings.models.primary, "ok": bool(calls), "finish_reason": primary["finish_reason"], "usage": primary["usage"]})
                if calls:
                    messages.append({"role": "assistant", "content": None, "tool_calls": [{"id": c.tool_call_id, "type": "function", "function": {"name": c.tool_name, "arguments": json.dumps(c.arguments)}} for c in calls]})
                    messages.extend({"role": "tool", "tool_call_id": c.tool_call_id, "content": "[p1] Self-attention replaces recurrence."} for c in calls)
                messages.append({"role": "user", "content": 'Return JSON answer_blocks with text and evidence_ids. Evidence: [p1] Self-attention replaces recurrence.'})
            except Exception as err:
                results["contracts"].append({"model": settings.models.primary, "ok": False, "error": normalize_provider_error(err)})
            try:
                fallback = await asyncio.wait_for(gateway.generate_step(settings.models.fallback, messages), 12)
                results["contracts"].append({"model": settings.models.fallback, "ok": bool(fallback["answer_blocks"]), "finish_reason": fallback["finish_reason"], "usage": fallback["usage"]})
            except Exception as err:
                results["contracts"].append({"model": settings.models.fallback, "ok": False, "error": normalize_provider_error(err)})
            # Avoid repeated failed FPT calls during API checks.
            if not all(c["ok"] for c in results["contracts"][:2]):
                settings.retrieval.default_mode = "B1"
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                session = await client.post('/api/v1/session')
                session.raise_for_status()
                headers = {"Authorization": "Bearer " + session.json()["token"]}
                auth = await client.get('/api/v1/session', headers=headers)
                results['authentication_status'] = auth.status_code
                payload = {"title": "Live check fixture text", "arxiv_id": "live-check", "version": "v1", "canonical_url": "https://arxiv.org/html/live-checkv1", "sections": [{"id": "s1", "heading": "Method", "path": "Method", "order": 0}], "paragraphs": [{"id": "p1", "section_id": "s1", "section_path": "Method", "order": 0, "text": "Self-attention replaces recurrence.", "locator": {"element_id": "p1"}}]}
                ingest = await client.post('/api/v1/papers/ingest', json=payload, headers=headers)
                ingest.raise_for_status()
                paper_id = ingest.json()['paper_id']
                for mode in ('A1', 'A2'):
                    response = await client.post('/api/v1/agent/runs', json={"request_id": mode, "paper_id": paper_id, "mode": mode, "question": "What replaces recurrence? Search evidence before answering."}, headers=headers)
                    response.raise_for_status()
                    run_id = response.json()['run_id']
                    task = _active_run_tasks.get((auth.json()['user_id'], run_id))
                    if task:
                        await asyncio.wait_for(asyncio.shield(task), 32)
                    result = (await client.get('/api/v1/agent/runs/' + run_id, headers=headers)).json()
                    results['runs'].append({k: result.get(k) for k in ('status', 'serving_model', 'retrieval_mode', 'retrieval_fallback_reason', 'fallback_reason', 'limitations', 'error_message')})
        finally:
            conn = getattr(_local, 'connections', {}).pop(settings.db_path, None)
            if conn:
                conn.close()
            settings.db_path, settings.mock_providers, settings.app.environment, settings.retrieval.default_mode = previous
    return results

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.parse_args()
    print(json.dumps(asyncio.run(check()), indent=2))
