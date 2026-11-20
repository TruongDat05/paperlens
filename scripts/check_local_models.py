"""Bounded checks of Qwen through 9Router and E5/BGE directly through FPT.

Run: python -m scripts.check_local_models --live --output reports/local_models.json
Uses synthetic text only, calls real adapters without model failover, and
returns a nonzero exit status if any model check fails.
"""

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import httpx

from backend.app.core.config import get_settings
from backend.app.providers.fpt import FPTProvider
from backend.app.providers.llm_gateway import LLMGateway


async def check():
    settings = get_settings()
    retrieval = FPTProvider()
    gateway = LLMGateway()
    gateway.max_tokens = 512
    messages = [
        {"role": "system", "content": 'Return only JSON with answer_blocks, each containing text and evidence_ids. Use only the supplied evidence.'},
        {"role": "user", "content": '[p1] Self-attention replaces recurrence. What replaces recurrence? Cite p1.'},
    ]

    async def generate(stream=False):
        chunks = []
        result = await gateway.generate_step(
            settings.models.high, messages, mock=False,
            on_chunk=(lambda raw, text: chunks.append(text)) if stream else None,
        )
        blocks = result.get("answer_blocks", [])
        assert blocks and any("p1" in b.evidence_ids for b in blocks), "Missing cited answer"
        if stream:
            assert chunks, "No streaming chunks received"
        return {"finish_reason": result["finish_reason"], "usage": result["usage"],
                "answer_blocks": [b.model_dump() for b in blocks], "chunks_received": len(chunks)}

    async def embed():
        vectors = await retrieval.get_embeddings(
            ["Self-attention replaces recurrence.", "Bananas are yellow."], mock=False,
        )
        return {"count": len(vectors), "dimensions": [len(v) for v in vectors]}

    async def rerank():
        scores = await retrieval.rerank(
            "What replaces recurrence?",
            ["Self-attention replaces recurrence.", "Bananas are yellow."], mock=False,
        )
        assert len(scores) == 2 and scores[0][0] == 0, "Incorrect rerank alignment or ordering"
        return {"scores": [{"index": i, "score": score} for i, score in scores]}

    async def probe(operation, endpoint, model, call):
        result = {"operation": operation, "endpoint": endpoint, "model": model}
        start = time.monotonic()
        try:
            result.update(await asyncio.wait_for(call(), timeout=45), ok=True)
        except Exception as err:
            result.update(ok=False, error_type=type(err).__name__, error=str(err))
            if isinstance(err, httpx.HTTPStatusError):
                result["http_status"] = err.response.status_code
        result["elapsed_seconds"] = round(time.monotonic() - start, 3)
        return result

    # Keep Qwen requests sequential to avoid overlapping the same provider.
    checks = await asyncio.gather(
        probe("qwen_json", gateway.api_url.rstrip("/") + "/chat/completions", settings.models.high, generate),
        probe("e5_embedding", retrieval.embedding_url, retrieval.e5_model.split("/")[-1], embed),
        probe("bge_rerank", retrieval.rerank_url, retrieval.bge_model.split("/")[-1], rerank),
    )
    checks.append(await probe("qwen_stream", gateway.api_url.rstrip("/") + "/chat/completions",
                              settings.models.high, lambda: generate(stream=True)))
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "gateway_base": settings.llm_api_url, "retrieval_base": settings.api_url, "mock_providers": False,
              "browser_verified": False, "all_passed": all(c["ok"] for c in checks), "checks": checks}
    text = json.dumps(report, indent=2, ensure_ascii=False)
    for secret in (settings.api_key, settings.llm_api_key):
        if secret:
            text = text.replace(secret, "<REDACTED>")
    return text, report["all_passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text, passed = asyncio.run(check())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    raise SystemExit(0 if passed else 1)
