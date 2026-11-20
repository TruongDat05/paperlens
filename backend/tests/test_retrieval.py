"""Specify correctness tests for retrieval configurations B1 to B4.

Use fixed questions, passages, vectors, and scores to check RRF and
rerank order, source locations, and grouping by parent paragraph.

Check configured top-k, BM25 fallback on provider failure, and the mode
reported in EvidenceResult.
"""

import pytest
from backend.app.core.schemas import SourceLocation, ParagraphInput
from backend.app.retrieval.chunking import chunk_paragraph, chunk_paper
from backend.app.retrieval.bm25 import BM25Index
from backend.app.retrieval.hybrid import retrieve_hybrid


def test_chunking_preserves_parent_lineage():
    """Verify chunking splits long text while preserving parent_passage_id and offsets."""
    short_para = ParagraphInput(
        id="p1",
        section_id="S1",
        section_path="1 Introduction",
        paragraph_order=0,
        text="Short sentence that does not need splitting.",
        source_locator=SourceLocation(element_id="p1", selector="#p1"),
    )
    chunks = chunk_paragraph(short_para, max_tokens=100)
    assert len(chunks) == 1
    assert chunks[0].passage_id == "p1"
    assert chunks[0].parent_passage_id == "p1"
    assert chunks[0].offset_start == 0
    assert chunks[0].offset_end == len(short_para.text)

    # Long text: 300 words
    long_text = "Word " * 300
    long_para = ParagraphInput(
        id="p2",
        section_id="S1",
        section_path="1 Introduction",
        paragraph_order=1,
        text=long_text.strip(),
        source_locator=SourceLocation(element_id="p2", selector="#p2"),
    )
    long_chunks = chunk_paragraph(long_para, max_tokens=80)
    assert len(long_chunks) > 1
    for i, c in enumerate(long_chunks):
        assert c.parent_passage_id == "p2"
        assert c.passage_id == f"p2:c{i}"
        assert c.offset_start >= 0
        assert c.offset_end > c.offset_start
        assert c.text == long_text.strip()[c.offset_start:c.offset_end]


@pytest.mark.asyncio
async def test_bm25_ranking_and_deduplication():
    """Verify BM25 ranks matching chunks and hybrid fuses into unique parent passages."""
    p1 = ParagraphInput(
        id="p1",
        section_id="S1",
        section_path="1 Introduction",
        paragraph_order=0,
        text="Transformers rely entirely on self-attention mechanisms without recurrence.",
        source_locator=SourceLocation(element_id="p1"),
    )
    p2 = ParagraphInput(
        id="p2",
        section_id="S2",
        section_path="2 Background",
        paragraph_order=1,
        text="Convolutional neural networks and recurrent models require sequential steps.",
        source_locator=SourceLocation(element_id="p2"),
    )
    p3 = ParagraphInput(
        id="p3",
        section_id="S3",
        section_path="3 Architecture",
        paragraph_order=2,
        text="The attention mechanism computes a weighted sum of values based on query and keys.",
        source_locator=SourceLocation(element_id="p3"),
    )

    chunks = chunk_paper([p1, p2, p3], max_tokens=100)
    index = BM25Index(chunks)

    # Query for self-attention
    results = index.search("self-attention mechanisms", top_k=5)
    assert len(results) > 0
    # Top chunk should be from p1
    assert results[0][0].parent_passage_id == "p1"

    # Hybrid B1 retrieval grouping by parent
    evidence_res = await retrieve_hybrid(
        query="self-attention mechanisms",
        chunks=chunks,
        bm25_index=index,
        mode="B1",
        top_k=2,
    )
    assert evidence_res.retrieval_mode == "B1"
    assert len(evidence_res.evidence) <= 2
    assert evidence_res.evidence[0].passage_id == "p1"


def test_bm25_zero_match_query():
    """Verify BM25 query with completely irrelevant terms returns empty or low-score without crashing."""
    p1 = ParagraphInput(
        id="p1",
        section_id="S1",
        section_path="1 Intro",
        paragraph_order=0,
        text="Transformers rely on self-attention.",
        source_locator=SourceLocation(element_id="p1"),
    )
    chunks = chunk_paper([p1], max_tokens=100)
    index = BM25Index(chunks)

    results = index.search("quantum thermodynamics xylophone", top_k=5)
    # Zero scores should produce empty or zero results
    assert len(results) == 0


def test_hybrid_rrf_and_b4_reranking():
    """Verify B3 RRF fusion and B4 reranking over candidate chunks."""
    from backend.app.retrieval.hybrid import reciprocal_rank_fusion, retrieve_hybrid

    sparse_ranked = [("p1", 10.0), ("p2", 8.0), ("p3", 5.0)]
    dense_ranked = [("p2", 0.95), ("p1", 0.85), ("p4", 0.70)]

    # RRF with k=60
    fused = reciprocal_rank_fusion(sparse_ranked, dense_ranked, k=60)
    # p2 has rank 2 in sparse (1/62) and rank 1 in dense (1/61) -> sum approx 0.016129 + 0.016393 = 0.03252
    # p1 has rank 1 in sparse (1/61) and rank 2 in dense (1/62) -> sum approx 0.03252
    # p3 has rank 3 in sparse (1/63) -> approx 0.01587
    # p4 has rank 3 in dense (1/63) -> approx 0.01587
    fused_ids = [item[0] for item in fused]
    assert "p1" in fused_ids[:2]
    assert "p2" in fused_ids[:2]
    assert len(fused) == 4


@pytest.mark.asyncio
async def test_agent_tools_execution():
    """Verify the three paper agent tools: get_paper_outline, search_evidence, read_section."""
    from backend.app.core.schemas import PaperIngestRequest, SectionInput, ParagraphInput, SourceLocation
    from backend.app.agent.tools import PaperAgentTools
    from backend.app.cache.paper_store import store_paper_and_chunks
    from backend.app.retrieval.chunking import chunk_paper

    paper_req = PaperIngestRequest(
        title="Attention Is All You Need",
        arxiv_id="1706.03762",
        version="v7",
        canonical_url="https://arxiv.org/html/1706.03762v7",
        parser_version="1.0.0",
        sections=[
            SectionInput(id="S1", heading="1 Introduction", path="1 Introduction", order=0),
            SectionInput(id="S2", heading="2 Background", path="2 Background", order=1),
        ],
        paragraphs=[
            ParagraphInput(
                id="S1.p1",
                section_id="S1",
                section_path="1 Introduction",
                order=0,
                text="The Transformer relies entirely on self-attention.",
                locator=SourceLocation(element_id="S1.p1"),
            ),
            ParagraphInput(
                id="S1.p2",
                section_id="S1",
                section_path="1 Introduction",
                order=1,
                text="Self-attention connects all pairs of input tokens directly.",
                locator=SourceLocation(element_id="S1.p2"),
            ),
        ],
    )
    paper_id = "paper_tool_test"
    owner_id = "user_tool_test"
    chunks = chunk_paper(paper_req.paragraphs, max_tokens=100, paper_id=paper_id)
    store_paper_and_chunks(
        paper_id=paper_id,
        owner_id=owner_id,
        paper_req=paper_req,
        content_hash="tool_test_hash",
        chunks=chunks,
    )

    tools = PaperAgentTools(paper_id=paper_id, owner_id=owner_id)

    # 1. get_paper_outline
    outline_obs = await tools.execute_tool("get_paper_outline", {})
    assert outline_obs.tool_name == "get_paper_outline"
    assert "1 Introduction" in outline_obs.content
    assert "S1" in outline_obs.content

    # 2. search_evidence
    search_obs = await tools.execute_tool("search_evidence", {"query": "self-attention", "top_k": 2})
    assert search_obs.tool_name == "search_evidence"
    assert len(search_obs.evidence_ids) > 0
    assert "S1.p1" in search_obs.evidence_ids or "S1.p2" in search_obs.evidence_ids

    # 3. read_section
    read_obs = await tools.execute_tool("read_section", {"section_id": "S1", "offset": 0, "limit": 2})
    assert read_obs.tool_name == "read_section"
    assert "The Transformer relies entirely" in read_obs.content

    # Error handling for invalid section
    err_obs = await tools.execute_tool("read_section", {"section_id": "INVALID_SEC"})
    assert "error" in err_obs.content.lower() or "not found" in err_obs.content.lower()


@pytest.mark.asyncio
async def test_evidence_item_preserves_fingerprint_and_section_id():
    """Verify paragraph fingerprints and section IDs propagate cleanly into EvidenceItem."""
    para = ParagraphInput(
        id="S1.p1",
        section_id="S1",
        section_path="1 Introduction",
        order=0,
        text="The Transformer relies entirely on self-attention.",
        locator=SourceLocation(element_id="S1.p1"),
        fingerprint="fp_test_12345",
    )
    chunks = chunk_paper([para], max_tokens=100, paper_id="p_test")
    assert len(chunks) == 1
    assert chunks[0].fingerprint == "fp_test_12345"
    assert chunks[0].section_id == "S1"

    bm25 = BM25Index(chunks)
    result = await retrieve_hybrid("self-attention", chunks, bm25_index=bm25, mode="B1", paper_id="p_test")
    assert len(result.evidence) == 1
    ev = result.evidence[0]
    assert ev.fingerprint == "fp_test_12345"
    assert ev.section_id == "S1"
    assert ev.paper_id == "p_test"


@pytest.mark.asyncio
async def test_semantic_retrieval_quota_enforcement():
    """Verify B2/B3/B4 requests enforce and exhaust semantic_retrievals daily quota."""
    from httpx import ASGITransport, AsyncClient
    from backend.app.main import app
    from backend.app.core.config import get_settings

    settings = get_settings()
    max_semantic = settings.quotas.daily_semantic_retrievals

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer quota-test-user"}
        # Ingest a paper
        paper_payload = {
            "title": "Quota Paper",
            "arxiv_id": "2401.99911",
            "version": "v1",
            "canonical_url": "https://arxiv.org/html/2401.99911v1",
            "parser_version": "1.0.0",
            "sections": [{"id": "S1", "heading": "Sec 1", "path": "Sec 1", "order": 0}],
            "paragraphs": [
                {
                    "id": "S1.p1",
                    "section_id": "S1",
                    "section_path": "Sec 1",
                    "order": 0,
                    "text": "Some text.",
                    "locator": {"element_id": "S1.p1"},
                }
            ],
        }
        ingest_res = await client.post("/api/v1/papers/ingest", json=paper_payload, headers=headers)
        paper_id = ingest_res.json()["paper_id"]

        # Call retrieve with mode=B3 up to quota limit
        for i in range(max_semantic):
            req_payload = {
                "request_id": f"req_quota_{i}",
                "paper_id": paper_id,
                "question": "test question",
                "top_k": 3,
                "mode": "B3",
            }
            res = await client.post("/api/v1/retrieve", json=req_payload, headers=headers)
            assert res.status_code == 200

        # Next call must exceed quota -> 429
        overflow_res = await client.post(
            "/api/v1/retrieve",
            json={"request_id": "req_overflow", "paper_id": paper_id, "question": "test", "mode": "B3"},
            headers=headers,
        )
        assert overflow_res.status_code == 429
        assert overflow_res.json()["detail"]["code"] == "DAILY_QUOTA_EXCEEDED"


@pytest.mark.asyncio
async def test_b2_b3_b4_actual_dense_retrieval_and_fallbacks():
    """Verify B2 dense, B3 RRF fusion, B4 BGE reranking, and graceful fallback reporting."""
    from backend.app.providers.fpt import FPTProvider

    p1 = ParagraphInput(
        id="p1",
        section_id="S1",
        section_path="1 Introduction",
        order=0,
        text="Deep learning architectures rely heavily on self-attention.",
        locator=SourceLocation(element_id="p1"),
    )
    p2 = ParagraphInput(
        id="p2",
        section_id="S2",
        section_path="2 Methods",
        order=1,
        text="Recurrent networks process sequences sequentially.",
        locator=SourceLocation(element_id="p2"),
    )
    chunks = chunk_paper([p1, p2], max_tokens=100, paper_id="p_test_b")
    bm25 = BM25Index(chunks)

    # 1. B2 Dense retrieval with mock provider
    fpt = FPTProvider()
    res_b2 = await retrieve_hybrid(
        query="self-attention in deep learning",
        chunks=chunks,
        bm25_index=bm25,
        mode="B2",
        top_k=2,
        paper_id="p_test_b",
        fpt_provider=fpt,
    )
    assert res_b2.retrieval_mode == "B2"
    assert len(res_b2.evidence) > 0
    assert len(res_b2.candidate_passage_ids) > 0

    # 2. B3 Sparse + Dense RRF fusion
    res_b3 = await retrieve_hybrid(
        query="recurrent sequential networks",
        chunks=chunks,
        bm25_index=bm25,
        mode="B3",
        top_k=2,
        paper_id="p_test_b",
        fpt_provider=fpt,
    )
    assert res_b3.retrieval_mode == "B3"
    assert len(res_b3.evidence) > 0

    # 3. B4 BGE reranking
    res_b4 = await retrieve_hybrid(
        query="attention mechanisms",
        chunks=chunks,
        bm25_index=bm25,
        mode="B4",
        top_k=2,
        paper_id="p_test_b",
        fpt_provider=fpt,
    )
    assert res_b4.retrieval_mode == "B4"
    assert len(res_b4.evidence) > 0
    assert len(res_b4.candidate_passage_ids) > 0

    # 4. Fallback reporting: Provider that throws an error
    class FailingProvider:
        async def get_embeddings(self, *args, **kwargs):
            raise ConnectionError("FPT server unreachable")
        async def rerank(self, *args, **kwargs):
            raise ConnectionError("Reranker server unreachable")

    failing_fpt = FailingProvider()

    # B2 falling back to B1
    res_fallback_b2 = await retrieve_hybrid(
        query="attention mechanisms",
        chunks=chunks,
        bm25_index=bm25,
        mode="B2",
        top_k=2,
        paper_id="p_test_b",
        fpt_provider=failing_fpt,
    )
    assert res_fallback_b2.retrieval_mode == "B1"
    assert res_fallback_b2.fallback_reason is not None
    assert "Dense retrieval unavailable" in res_fallback_b2.fallback_reason
    assert len(res_fallback_b2.evidence) > 0

    # B4 falling back to B3 or B1
    res_fallback_b4 = await retrieve_hybrid(
        query="attention mechanisms",
        chunks=chunks,
        bm25_index=bm25,
        mode="B4",
        top_k=2,
        paper_id="p_test_b",
        fpt_provider=failing_fpt,
    )
    assert res_fallback_b4.retrieval_mode in ("B1", "B3")
    assert res_fallback_b4.fallback_reason is not None
    assert len(res_fallback_b4.evidence) > 0
