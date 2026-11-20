"""Implement A1, the single-pass retrieval and answer flow.

In the benchmark, retrieve at most 8 original paragraphs from one B4
pass. The product alpha retrieves evidence according to its
configuration. Use the same evidence registry, model router, and answer
schema as A2.

Return a citation-validated result and metadata for the A1/A2
comparison.
"""

from typing import List, Optional
from backend.app.core.schemas import EvidenceItem
from backend.app.cache.paper_store import (
    get_paper_chunks,
    get_bm25_index,
)
from backend.app.retrieval.hybrid import retrieve_hybrid
from backend.app.agent.citations import EvidenceRegistry, validate_answer_citations
from backend.app.agent.schemas import AgentResult, RunState, AnswerBlock
from backend.app.agent.prompts import SYSTEM_PROMPT, build_a1_prompt
from backend.app.agent.model_router import ModelRouter, generate_bounded
from backend.app.agent.citations import answer_status
from backend.app.core.config import get_settings
import time
import asyncio
from backend.app.providers.llm_gateway import LLMGateway


async def run_single_pass(
    run_id: str,
    paper_id: str,
    owner_id: str,
    question: str,
    router: Optional[ModelRouter] = None,
    gateway: Optional[LLMGateway] = None,
    retrieval_mode: Optional[str] = None,
    top_k: Optional[int] = None,
) -> AgentResult:
    """Execute single-pass A1 retrieval and cited answer generation."""
    router = router or ModelRouter()
    gateway = gateway or LLMGateway()

    from backend.app.agent.tools import validate_paper_question
    validate_paper_question(paper_id, owner_id, question)
    settings = get_settings()
    deadline = time.monotonic() + settings.limits.turn_timeout_seconds
    retrieval_mode = retrieval_mode or settings.retrieval.default_mode
    top_k = min(top_k if top_k is not None else settings.retrieval.product_top_k, settings.limits.max_parent_evidence)

    # 1. Retrieve evidence passages
    chunks = get_paper_chunks(paper_id, owner_id)
    bm25_idx = get_bm25_index(paper_id, owner_id)

    ev_result = await asyncio.wait_for(retrieve_hybrid(
        query=question,
        chunks=chunks,
        bm25_index=bm25_idx,
        mode=retrieval_mode,
        top_k=top_k,
        request_id=run_id,
        paper_id=paper_id,
        owner_id=owner_id,
    ), max(0.001, deadline - time.monotonic()))

    if not ev_result.evidence:
        return AgentResult(
            run_id=run_id,
            paper_id=paper_id,
            status=RunState.EVIDENCE_ONLY,
            answer_blocks=[],
            evidence=[],
            serving_model=router.get_active_model(),
            limitations="No relevant evidence passages found in the paper to answer the question.",
        )

    # 2. Register evidence in per-run registry
    registry = EvidenceRegistry()
    for item in ev_result.evidence:
        registry.register_passage(
            passage_id=item.passage_id,
            text=item.text,
            locator=item.locator,
            section_heading=item.section_heading,
            section_path=item.section_path,
            score=item.score,
            rank=item.rank,
            fingerprint=item.fingerprint, section_id=item.section_id, paper_id=item.paper_id,
        )

    # 3. Construct prompt with calibrated complexity guidance
    from backend.app.agent.complexity import determine_question_complexity
    complexity = determine_question_complexity(question)
    user_prompt = build_a1_prompt(question, ev_result.evidence)
    user_prompt += (
        f"\n\n[Định mức output token & Hướng dẫn phân tích ({complexity.label})]:\n"
        f"- Mục tiêu độ dài: {complexity.target_tokens_min}–{complexity.target_tokens_max} tokens.\n"
        f"- {complexity.synthesis_guidance}\n"
        f"- Trích xuất đúng đoạn văn, bảng, công thức liên quan và trích dẫn rõ section/page."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    # 4. Generate response with router and gateway
    try:
        step_res = await generate_bounded(router, gateway, messages, None, deadline, output_token_cap=complexity.max_output_tokens)
        from backend.app.telemetry.usage import record_usage
        usage = step_res.get("usage", {})
        record_usage(owner_id=owner_id, run_id=run_id, operation="single_pass", provider="gateway",
                     model=router.get_active_model(), input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0), status="success")
        raw_blocks = step_res.get("answer_blocks", [])
    except Exception as err:
        return AgentResult(run_id=run_id, paper_id=paper_id, status=RunState.EVIDENCE_ONLY,
                           evidence=ev_result.evidence, serving_model=router.get_active_model(),
                           retrieval_mode=ev_result.retrieval_mode, retrieval_fallback_reason=ev_result.fallback_reason,
                           fallback_reason="Claude fallback applied" if router.fallback_count else None, limitations=f"Generation failed: {err}")

    # 5. Validate citations against registry
    status, sanitized_blocks, limitations = answer_status(raw_blocks, registry)

    return AgentResult(
        run_id=run_id,
        paper_id=paper_id,
        status=status,
        answer_blocks=sanitized_blocks,
        follow_ups=step_res.get("follow_ups", []),
        emitted_citation_ids=[eid for b in raw_blocks for eid in b.evidence_ids],
        evidence=ev_result.evidence,
        serving_model=router.get_active_model(),
        retrieval_mode=ev_result.retrieval_mode,
        retrieval_fallback_reason=ev_result.fallback_reason,
        limitations=limitations,
        fallback_reason="Claude fallback applied" if router.fallback_count > 0 else None,
    )
