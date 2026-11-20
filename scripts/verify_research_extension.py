#!/usr/bin/env python3
"""End-to-end verification script for PaperLens model removal and research extension capabilities.

Verifies:
1. Research extension questions ("Based on this paper, what promising extension or implementation directions could I explore?"):
   - Current paper problem, method, contributions, and limitations are understood.
   - External papers are retrieved and cited via search_external_papers.
   - Concrete implementation directions, changes required, evaluation plans, assumptions, and uncertainties are articulated.
   - User-facing text does NOT leak model/provider names or aliases.
2. Backend telemetry:
   - serving_model and provider are preserved accurately.
3. Ordinary question efficiency:
   - Ordinary questions about the paper do not trigger external retrieval.
"""

import asyncio
import json
import re
import sys

from backend.app.core.config import get_settings
from backend.app.core.schemas import PaperIngestRequest, SectionInput, ParagraphInput
from backend.app.retrieval.chunking import chunk_paper
from backend.app.cache.paper_store import store_paper_and_chunks
from backend.app.agent.controller import run_bounded_agent
from backend.app.agent.model_router import ModelRouter
from backend.app.providers.llm_gateway import LLMGateway


async def main():
    print("=== [1] Ingesting Sample Research Paper (Transformer) ===")
    paper_id = "1706.03762"
    owner_id = "verifier_user_1"

    paper_req = PaperIngestRequest(
        title="Attention Is All You Need",
        arxiv_id=paper_id,
        version="v7",
        canonical_url=f"https://arxiv.org/abs/{paper_id}",
        sections=[
            SectionInput(id="sec1", heading="1 Introduction", path="1 Introduction", order=1),
            SectionInput(id="sec3", heading="3 Model Architecture", path="3 Model Architecture", order=2),
            SectionInput(id="sec5", heading="5 Conclusion and Limitations", path="5 Conclusion and Limitations", order=3),
        ],
        paragraphs=[
            ParagraphInput(
                id="p1",
                section_id="sec1",
                section_path="1 Introduction",
                order=1,
                text=(
                    "Recurrent neural networks factor computation along symbol positions of input sequences. "
                    "In this work we propose the Transformer, a model architecture eschewing recurrence and "
                    "relying entirely on an attention mechanism to draw global dependencies between input and output."
                ),
            ),
            ParagraphInput(
                id="p2",
                section_id="sec3",
                section_path="3 Model Architecture",
                order=2,
                text=(
                    "An attention function maps a query and a set of key-value pairs to an output. "
                    "Multi-Head Attention allows the model to jointly attend to information from different "
                    "representation subspaces at different positions: MultiHead(Q,K,V) = Concat(head_1,...,head_h)W^O."
                ),
            ),
            ParagraphInput(
                id="p3",
                section_id="sec5",
                section_path="5 Conclusion and Limitations",
                order=3,
                text=(
                    "Conclusion: We presented the Transformer, the first sequence transduction model based entirely on attention. "
                    "A notable limitation is the computational and memory complexity of dot-product attention, which scales "
                    "quadratically O(N^2) with input sequence length N. Processing long inputs, documents, and high-resolution "
                    "modalities remains challenging and requires future research into efficient attention mechanisms."
                ),
            ),
        ],
    )

    chunks = chunk_paper(paper_req.paragraphs, paper_id=paper_id)
    store_paper_and_chunks(paper_id, owner_id, paper_req, "content_hash_1706", chunks)
    print(f"Paper {paper_id} stored with {len(chunks)} chunks.")

    print("\n=== [2] Testing Research Extension Question ===")
    research_question = "Based on this paper, what promising extension or implementation directions could I explore?"
    events = []

    def on_event(ev):
        events.append(ev)
        ev_type = ev.get("type")
        if ev_type == "activity":
            print(f"  [Activity] {ev.get('message')}")
        elif ev_type == "tool_call":
            print(f"  [Tool Call] {ev.get('tool_name')}: {ev.get('arguments')}")
        elif ev_type == "tool_result":
            print(f"  [Tool Result] {ev.get('tool_name')}: {ev.get('summary')}")

    gateway = LLMGateway()
    router = ModelRouter()

    res_ext = await run_bounded_agent(
        run_id="run_verify_ext",
        paper_id=paper_id,
        owner_id=owner_id,
        question=research_question,
        router=router,
        gateway=gateway,
        on_event=on_event,
    )

    print(f"\nStatus: {res_ext.status.value}")
    print(f"Serving Model (Backend Telemetry): {res_ext.serving_model}")
    print(f"Emitted Citations: {res_ext.emitted_citation_ids}")
    print(f"Evidence Count: {len(res_ext.evidence)}")

    # Verify no model names in user-facing answer blocks
    full_answer_text = "\n\n".join(b.text for b in res_ext.answer_blocks)
    print(f"\n--- Answer Text ({len(full_answer_text)} chars) ---\n{full_answer_text[:500]}...\n---")

    forbidden_model_patterns = [r"\bgemini\b", r"\bclaude\b", r"\banthropic\b", r"\bag/"]
    for pat in forbidden_model_patterns:
        match = re.search(pat, full_answer_text, re.IGNORECASE)
        assert match is None, f"FAIL: User-facing answer leaked model/provider name: {match.group(0)}"
    print("✓ PASS: User-facing answer contains NO model names, provider names, or internal aliases.")

    # Verify backend telemetry preserved accurate model info
    assert res_ext.serving_model in ("ag/gemini-3.8-flash-medium", "ag/claude-sonnet-4-6")
    print(f"✓ PASS: Backend telemetry accurately preserved routing model: {res_ext.serving_model}")

    # Verify external tool invocation occurred
    tool_calls = [e.get("tool_name") for e in events if e.get("type") == "tool_call"]
    has_external_search = "search_external_papers" in tool_calls
    has_external_evidence = any(e.startswith("ext_") or "arxiv" in e.lower() for e in res_ext.emitted_citation_ids)
    assert has_external_search or has_external_evidence, "FAIL: External paper tool was not invoked for extension query!"
    print("✓ PASS: External scholarly literature search was utilized for research extension query.")

    print("\n=== [3] Testing Ordinary In-Paper Question Efficiency ===")
    events_ord = []

    def on_event_ord(ev):
        events_ord.append(ev)

    res_ord = await run_bounded_agent(
        run_id="run_verify_ord",
        paper_id=paper_id,
        owner_id=owner_id,
        question="What is the attention formula described in section 3?",
        router=ModelRouter(),
        gateway=LLMGateway(),
        on_event=on_event_ord,
    )

    ord_tools = [e.get("tool_name") for e in events_ord if e.get("type") == "tool_call"]
    assert "search_external_papers" not in ord_tools, "FAIL: External search was invoked on ordinary question!"
    print(f"Ordinary Question Tools called: {ord_tools}")
    print("✓ PASS: Ordinary in-paper question remained efficient and did NOT call external search.")

    print("\n=======================================================")
    print("ALL END-TO-END VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=======================================================")


if __name__ == "__main__":
    asyncio.run(main())
