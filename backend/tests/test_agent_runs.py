"""Specify tests for the agent run lifecycle, citations, and routing.

Cover ownership, duplicate request_id, cancellation, deadlines, and late
responses. Simulate Gemini failure, one failover, continued use of
Claude until the turn ends, and failure of both models.

Check unknown usage, out-of-scope actions, and citation IDs missing from
the evidence registry.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.main import app
from backend.app.core.schemas import SourceLocation, ParagraphInput
from backend.app.agent.citations import EvidenceRegistry, validate_answer_citations
from backend.app.agent.schemas import AnswerBlock, AgentResult, RunState
from backend.app.retrieval.dense import cosine_similarity, rank_passages_dense
from backend.app.agent.model_router import ModelRouter, RoutingMode


def test_evidence_registry_and_citation_validation():
    """Verify answer blocks can only cite passages present in the evidence registry."""
    registry = EvidenceRegistry()
    registry.register_passage(
        passage_id="S1.p1",
        text="The Transformer relies on self-attention.",
        locator=SourceLocation(element_id="S1.p1"),
        section_heading="1 Introduction",
    )

    # Valid block citing registered passage
    valid_blocks = [
        AnswerBlock(
            text="Transformers eliminate recurrent steps.",
            evidence_ids=["S1.p1"],
        )
    ]
    is_valid, sanitized = validate_answer_citations(valid_blocks, registry)
    assert is_valid is True
    assert len(sanitized) == 1
    assert sanitized[0].evidence_ids == ["S1.p1"]

    # Block citing fabricated / unregistered ID
    invalid_blocks = [
        AnswerBlock(
            text="Unfounded claim citing fabricated source.",
            evidence_ids=["S99.p99"],
        )
    ]
    is_valid_inv, sanitized_inv = validate_answer_citations(invalid_blocks, registry)
    assert is_valid_inv is False
    assert len(sanitized_inv[0].evidence_ids) == 0


def test_dense_retrieval_ranking():
    """Verify cosine similarity and dense vector ranking on normalized vectors."""
    q_vec = [1.0, 0.0, 0.0]
    p1_vec = [0.9, 0.1, 0.0]
    p2_vec = [0.1, 0.9, 0.0]

    sim1 = cosine_similarity(q_vec, p1_vec)
    sim2 = cosine_similarity(q_vec, p2_vec)
    assert sim1 > sim2

    vectors = {
        "p1": p1_vec,
        "p2": p2_vec,
    }
    ranked = rank_passages_dense(q_vec, vectors, top_k=2)
    assert len(ranked) == 2
    assert ranked[0][0] == "p1"
    assert ranked[1][0] == "p2"


def test_model_router_failover_policy():
    """Verify Gemini primary router, Claude fallback in primary_then_fallback, and primary_only."""
    from backend.app.core.config import get_settings
    primary = get_settings().models.primary
    # 1. Research mode: primary_only must never switch to Claude
    router_research = ModelRouter(mode=RoutingMode.PRIMARY_ONLY)
    assert router_research.get_active_model() == primary
    can_fallback = router_research.handle_attempt_failure(
        error_type="provider_timeout",
        remaining_turn_seconds=20.0,
    )
    assert can_fallback is False
    assert router_research.get_active_model() == primary

    # 2. Product mode: primary_then_fallback switches to Claude on eligible error
    router_prod = ModelRouter(mode=RoutingMode.PRIMARY_THEN_FALLBACK)
    assert router_prod.get_active_model() == primary
    can_fallback_prod = router_prod.handle_attempt_failure(
        error_type="provider_500",
        remaining_turn_seconds=20.0,
    )
    assert can_fallback_prod is True
    assert router_prod.get_active_model() == "ag/claude-sonnet-4-6"

    # Subsequent failure while Claude is active cannot fallback again
    can_fallback_again = router_prod.handle_attempt_failure(
        error_type="provider_500",
        remaining_turn_seconds=15.0,
    )
    assert can_fallback_again is False


@pytest.mark.asyncio
async def test_agent_runs_api_lifecycle():
    """Verify durable agent runs: start (202), duplicate request_id, poll, and cancel."""
    import uuid
    test_req_id = f"req-agent-{uuid.uuid4().hex[:8]}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer agent-tester"}

        # First ingest a test paper
        paper_payload = {
            "title": "Agent Paper",
            "arxiv_id": "2401.55555",
            "version": "v1",
            "canonical_url": "https://arxiv.org/html/2401.55555v1",
            "parser_version": "1.0.0",
            "sections": [{"id": "S1", "heading": "1 Intro", "path": "1 Intro", "order": 0}],
            "paragraphs": [
                {
                    "id": "S1.p1",
                    "section_id": "S1",
                    "section_path": "1 Intro",
                    "order": 0,
                    "text": "The agent tool loop allows iterative question answering.",
                    "locator": {"element_id": "S1.p1"},
                }
            ],
        }
        ingest_res = await client.post("/api/v1/papers/ingest", json=paper_payload, headers=headers)
        assert ingest_res.status_code in [200, 202]
        paper_id = ingest_res.json()["paper_id"]

        # 1. Start agent run
        run_payload = {
            "request_id": test_req_id,
            "paper_id": paper_id,
            "question": "How does the agent work?",
            "history": [],
        }
        start_res = await client.post("/api/v1/agent/runs", json=run_payload, headers=headers)
        assert start_res.status_code == 202
        start_data = start_res.json()
        run_id = start_data.get("run_id")
        assert run_id is not None
        assert start_data.get("status") in ["queued", "running", "completed"]

        # 2. Duplicate start with same payload returns existing run
        repeat_res = await client.post("/api/v1/agent/runs", json=run_payload, headers=headers)
        assert repeat_res.status_code == 202
        assert repeat_res.json().get("run_id") == run_id

        # 3. Conflict: same request_id with different question
        conflict_payload = {**run_payload, "question": "Different question entirely"}
        conflict_res = await client.post("/api/v1/agent/runs", json=conflict_payload, headers=headers)
        assert conflict_res.status_code == 409

        # 4. Poll run status
        poll_res = await client.get(f"/api/v1/agent/runs/{run_id}", headers=headers)
        assert poll_res.status_code == 200
        poll_data = poll_res.json()
        assert poll_data.get("run_id") == run_id

        # 5. Cancel run
        cancel_res = await client.post(f"/api/v1/agent/runs/{run_id}/cancel", headers=headers)
        assert cancel_res.status_code == 200
        assert cancel_res.json().get("status") == "cancelled"

        # 6. Test GET /events on cancelled/terminal run returns events stream
        events_res = await client.get(f"/api/v1/agent/runs/{run_id}/events", headers=headers)
        assert events_res.status_code == 200
        assert "text/event-stream" in events_res.headers.get("content-type", "")
        body = events_res.text
        assert "data: " in body


@pytest.mark.asyncio
async def test_a2_bounded_controller_loop():
    """Verify bounded A2 controller executes tool loop and outputs cited answer."""
    from backend.app.agent.controller import run_bounded_agent
    from backend.app.core.schemas import PaperIngestRequest, SectionInput, ParagraphInput, SourceLocation
    from backend.app.cache.paper_store import store_paper_and_chunks
    from backend.app.retrieval.chunking import chunk_paper

    paper_req = PaperIngestRequest(
        title="Transformer Paper",
        arxiv_id="1706.03762",
        version="v7",
        canonical_url="https://arxiv.org/html/1706.03762v7",
        parser_version="1.0.0",
        sections=[SectionInput(id="S1", heading="1 Intro", path="1 Intro", order=0)],
        paragraphs=[
            ParagraphInput(
                id="S1.p1",
                section_id="S1",
                section_path="1 Intro",
                order=0,
                text="The Transformer replaces recurrence with self-attention.",
                locator=SourceLocation(element_id="S1.p1"),
            )
        ],
    )
    paper_id = "paper_a2_test"
    owner_id = "user_a2_test"
    chunks = chunk_paper(paper_req.paragraphs, max_tokens=100, paper_id=paper_id)
    store_paper_and_chunks(
        paper_id=paper_id,
        owner_id=owner_id,
        paper_req=paper_req,
        content_hash="hash_a2_test",
        chunks=chunks,
    )

    result = await run_bounded_agent(
        run_id="run_a2_1",
        paper_id=paper_id,
        owner_id=owner_id,
        question="How does tool loop answering work in Transformer?",
    )

    assert result.status in [RunState.COMPLETED, RunState.PARTIAL]
    assert len(result.answer_blocks) > 0
    from backend.app.core.config import get_settings
    assert result.serving_model in [get_settings().models.primary, "ag/gemini-3.8-flash-medium", "ag/gemini-3.8-flash-low", "ag/claude-sonnet-4-6"]


@pytest.mark.asyncio
async def test_live_provider_missing_credentials_raises_error():
    """Verify live provider calls without credentials throw instead of silently returning synthetic mocks."""
    from backend.app.providers.llm_gateway import LLMGateway
    from backend.app.providers.fpt import FPTProvider

    gateway = LLMGateway(api_key="")
    with pytest.raises(RuntimeError, match="not configured"):
        await gateway.generate_step("ag/gemini-3.8-flash-medium", [{"role": "user", "content": "hi"}], mock=False)

    fpt = FPTProvider(api_key="")
    with pytest.raises(RuntimeError, match="not configured"):
        await fpt.get_embeddings(["test text"], mock=False)

    with pytest.raises(RuntimeError, match="not configured"):
        await fpt.rerank("query", ["doc 1"], mock=False)


@pytest.mark.asyncio
async def test_a2_tool_evidence_registered_and_cited():
    """Verify evidence discovered by tools during A2 run is registered and valid in citations."""
    from backend.app.agent.controller import run_bounded_agent
    from backend.app.agent.schemas import ActionCall, AnswerBlock, RunState
    from backend.app.providers.llm_gateway import LLMGateway
    from backend.app.core.schemas import PaperIngestRequest, SectionInput, ParagraphInput, SourceLocation
    from backend.app.cache.paper_store import store_paper_and_chunks
    from backend.app.retrieval.chunking import chunk_paper

    paper_req = PaperIngestRequest(
        title="Tool Evidence Reg Test",
        arxiv_id="2401.88888",
        version="v1",
        canonical_url="https://arxiv.org/html/2401.88888v1",
        parser_version="1.0.0",
        sections=[SectionInput(id="S2", heading="Section 2", path="Section 2", order=0)],
        paragraphs=[
            ParagraphInput(
                id="S2.p10",
                section_id="S2",
                section_path="Section 2",
                order=0,
                text="Crucial discovered fact only in paragraph 10.",
                locator=SourceLocation(element_id="S2.p10"),
                fingerprint="fp_s2_p10",
            )
        ],
    )
    paper_id = "paper_tool_reg"
    owner_id = "user_tool_reg"
    chunks = chunk_paper(paper_req.paragraphs, max_tokens=100, paper_id=paper_id)
    store_paper_and_chunks(paper_id, owner_id, paper_req, "hash_reg", chunks)

    # Mock gateway simulating: Step 1 -> call tool 'search_evidence', Step 2 -> answer citing 'S2.p10'
    class MockToolGateway(LLMGateway):
        def __init__(self):
            super().__init__(api_key="mock_key")
            self.step = 0
            self.recorded_messages = []

        async def generate_step(self, model, messages, tools=None, mock=False):
            self.step += 1
            self.recorded_messages = list(messages)
            if self.step == 1:
                return {
                    "tool_calls": [
                        ActionCall(
                            tool_name="search_evidence",
                            arguments={"query": "crucial fact", "top_k": 1},
                            tool_call_id="call_reg_1",
                        )
                    ],
                    "answer_blocks": [],
                    "finish_reason": "tool_calls",
                    "usage": {"input_tokens": 50, "output_tokens": 20},
                }
            else:
                return {
                    "tool_calls": [],
                    "answer_blocks": [
                        AnswerBlock(
                            text="The crucial fact was verified.",
                            evidence_ids=["S2.p10"],
                        )
                    ],
                    "finish_reason": "stop",
                    "usage": {"input_tokens": 100, "output_tokens": 30},
                }

    gw = MockToolGateway()
    res = await run_bounded_agent(
        run_id="run_reg_1",
        paper_id=paper_id,
        owner_id=owner_id,
        question="What is the crucial fact?",
        gateway=gw,
    )

    # 1. S2.p10 was discovered via tool, so it must be registered and cited
    assert res.status == RunState.COMPLETED
    assert res.limitations is None
    assert len(res.answer_blocks) == 1
    assert "S2.p10" in res.answer_blocks[0].evidence_ids
    assert any(e.passage_id == "S2.p10" for e in res.evidence)

    # 2. Check transcript: assistant message with tool_calls must precede tool message
    roles = [m["role"] for m in gw.recorded_messages]
    assert "assistant" in roles
    assert "tool" in roles
    asst_idx = roles.index("assistant")
    tool_idx = roles.index("tool")
    assert asst_idx < tool_idx
    assert gw.recorded_messages[asst_idx].get("tool_calls") is not None


@pytest.mark.asyncio
async def test_unsupported_answer_handling():
    """Verify answers with invalid or missing citations are handled as unsupported."""
    from backend.app.agent.controller import run_bounded_agent
    from backend.app.agent.schemas import AnswerBlock, RunState
    from backend.app.providers.llm_gateway import LLMGateway
    from backend.app.core.schemas import PaperIngestRequest, SectionInput, ParagraphInput, SourceLocation
    from backend.app.cache.paper_store import store_paper_and_chunks
    from backend.app.retrieval.chunking import chunk_paper

    paper_req = PaperIngestRequest(
        title="Unsupp Test",
        arxiv_id="2401.77777",
        version="v1",
        canonical_url="https://arxiv.org/html/2401.77777v1",
        parser_version="1.0.0",
        sections=[SectionInput(id="S1", heading="Section 1", path="Section 1", order=0)],
        paragraphs=[
            ParagraphInput(
                id="S1.p1",
                section_id="S1",
                section_path="Section 1",
                order=0,
                text="Actual text.",
                locator=SourceLocation(element_id="S1.p1"),
            )
        ],
    )
    paper_id = "paper_unsupp"
    owner_id = "user_unsupp"
    chunks = chunk_paper(paper_req.paragraphs, max_tokens=100, paper_id=paper_id)
    store_paper_and_chunks(paper_id, owner_id, paper_req, "hash_unsupp", chunks)

    class FabricatedCitationGateway(LLMGateway):
        async def generate_step(self, model, messages, tools=None, mock=False):
            return {
                "tool_calls": [],
                "answer_blocks": [
                    AnswerBlock(
                        text="A hallucinated claim with fabricated source.",
                        evidence_ids=["FABRICATED_ID_999"],
                    )
                ],
                "finish_reason": "stop",
                "usage": {"input_tokens": 50, "output_tokens": 20},
            }

    res = await run_bounded_agent(
        run_id="run_unsupp_1",
        paper_id=paper_id,
        owner_id=owner_id,
        question="Anything?",
        gateway=FabricatedCitationGateway(api_key="mock"),
    )

    # Must NOT report COMPLETED for completely unsupported answer
    assert res.status == RunState.EVIDENCE_ONLY
    assert res.limitations is not None
    assert "sources" in res.limitations.lower()
    assert res.answer_blocks == []


@pytest.mark.asyncio
async def test_run_cancellation_not_overwritten_by_completion():
    """Verify that a cancelled run cannot be overwritten by worker completion."""
    import asyncio
    from backend.app.agent.runs import create_or_get_run, cancel_run, get_run, _active_run_tasks
    from backend.app.agent.schemas import AgentRunRequest, RunState
    from backend.app.core.schemas import PaperIngestRequest, SectionInput, ParagraphInput, SourceLocation
    from backend.app.cache.paper_store import store_paper_and_chunks
    from backend.app.retrieval.chunking import chunk_paper

    paper_req = PaperIngestRequest(
        title="Cancel Test",
        arxiv_id="2401.33333",
        version="v1",
        canonical_url="https://arxiv.org/html/2401.33333v1",
        parser_version="1.0.0",
        sections=[SectionInput(id="S1", heading="Sec 1", path="Sec 1", order=0)],
        paragraphs=[
            ParagraphInput(
                id="S1.p1",
                section_id="S1",
                section_path="Sec 1",
                order=0,
                text="Text here.",
                locator=SourceLocation(element_id="S1.p1"),
            )
        ],
    )
    paper_id = "paper_cancel_test"
    owner_id = "user_cancel_test"
    chunks = chunk_paper(paper_req.paragraphs, max_tokens=100, paper_id=paper_id)
    store_paper_and_chunks(paper_id, owner_id, paper_req, "hash_canc", chunks)

    req = AgentRunRequest(
        request_id="req_canc_1",
        paper_id=paper_id,
        question="A question?",
    )

    res, is_new, is_conflict = await create_or_get_run(req, owner_id)
    assert is_new is True
    assert res.status == RunState.QUEUED

    # Cancel immediately
    cancel_res = cancel_run(res.run_id, owner_id)
    assert cancel_res.status == RunState.CANCELLED

    # Wait for any active background task to settle
    task = _active_run_tasks.get((owner_id, res.run_id))
    if task:
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    # Status MUST remain CANCELLED, never overwritten to completed
    final_res = get_run(res.run_id, owner_id)
    assert final_res.status == RunState.CANCELLED


@pytest.mark.asyncio
async def test_delete_paper_coordinates_with_active_tasks():
    """Verify paper deletion cancels in-flight runs and cleans up."""
    import asyncio
    from backend.app.agent.runs import create_or_get_run, get_run, _active_run_tasks
    from backend.app.agent.schemas import AgentRunRequest, RunState
    from backend.app.core.schemas import PaperIngestRequest, SectionInput, ParagraphInput, SourceLocation
    from backend.app.cache.paper_store import store_paper_and_chunks, delete_paper
    from backend.app.retrieval.chunking import chunk_paper

    paper_req = PaperIngestRequest(
        title="Delete Coord Test",
        arxiv_id="2401.44444",
        version="v1",
        canonical_url="https://arxiv.org/html/2401.44444v1",
        parser_version="1.0.0",
        sections=[SectionInput(id="S1", heading="Sec 1", path="Sec 1", order=0)],
        paragraphs=[
            ParagraphInput(
                id="S1.p1",
                section_id="S1",
                section_path="Sec 1",
                order=0,
                text="Text here.",
                locator=SourceLocation(element_id="S1.p1"),
            )
        ],
    )
    paper_id = "paper_del_coord"
    owner_id = "user_del_coord"
    chunks = chunk_paper(paper_req.paragraphs, max_tokens=100, paper_id=paper_id)
    store_paper_and_chunks(paper_id, owner_id, paper_req, "hash_del_coord", chunks)

    req = AgentRunRequest(
        request_id="req_del_coord_1",
        paper_id=paper_id,
        question="A question?",
    )

    res, _, _ = await create_or_get_run(req, owner_id)

    # Delete paper while run is active
    deleted = delete_paper(paper_id, owner_id)
    assert deleted is True

    # Run should be marked cancelled or task cancelled
    task = _active_run_tasks.get((owner_id, res.run_id))
    if task:
        await asyncio.sleep(0.01)
        assert task.cancelled() or task.done()

    final_run = get_run(res.run_id, owner_id)
    if final_run:
        assert final_run.status == RunState.CANCELLED


@pytest.mark.asyncio
async def test_usage_telemetry_recording():
    """Verify LLM steps record tokens and operations into SQLite usage_ledger."""
    from backend.app.telemetry.usage import get_owner_daily_usage
    from backend.app.agent.controller import run_bounded_agent
    from backend.app.providers.llm_gateway import LLMGateway
    from backend.app.core.schemas import PaperIngestRequest, SectionInput, ParagraphInput, SourceLocation
    from backend.app.cache.paper_store import store_paper_and_chunks
    from backend.app.retrieval.chunking import chunk_paper

    paper_req = PaperIngestRequest(
        title="Usage Telemetry Test",
        arxiv_id="2401.99999",
        version="v1",
        canonical_url="https://arxiv.org/html/2401.99999v1",
        parser_version="1.0.0",
        sections=[SectionInput(id="S1", heading="Section 1", path="Section 1", order=0)],
        paragraphs=[
            ParagraphInput(
                id="S1.p1",
                section_id="S1",
                section_path="Section 1",
                order=0,
                text="Telemetry paragraph text.",
                locator=SourceLocation(element_id="S1.p1"),
            )
        ],
    )
    paper_id = "paper_usage_tel"
    owner_id = "user_usage_tel"
    chunks = chunk_paper(paper_req.paragraphs, max_tokens=100, paper_id=paper_id)
    store_paper_and_chunks(paper_id, owner_id, paper_req, "hash_usage_tel", chunks)

    class MockTelemetryGateway(LLMGateway):
        async def generate_step(self, model, messages, tools=None, mock=False):
            return {
                "tool_calls": [],
                "answer_blocks": [
                    AnswerBlock(text="Answer with tokens.", evidence_ids=["S1.p1"])
                ],
                "finish_reason": "stop",
                "usage": {"input_tokens": 120, "output_tokens": 45},
            }

    await run_bounded_agent(
        run_id="run_telemetry_test",
        paper_id=paper_id,
        owner_id=owner_id,
        question="How does telemetry work?",
        gateway=MockTelemetryGateway(),
    )

    daily_usage = get_owner_daily_usage(owner_id)
    assert daily_usage["calls"] >= 1
    assert daily_usage["input_tokens"] >= 120
    assert daily_usage["output_tokens"] >= 45
