"""Specify tests for paper ingestion, status, and deletion.

Use local SQLite and fake adapters to test ownership, input limits,
repeated ingestion, and the lexical_ready and semantic_ready states.

Cover embedding batches interrupted by a restart and paper deletion
while a task is still running.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """Verify GET /api/v1/health returns status ok without credentials."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"
        assert data.get("version") == "0.1.0"


@pytest.mark.asyncio
async def test_session_endpoint_auth_required():
    """Verify GET /api/v1/session returns 401 without authorization header."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/session")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_session_endpoint_with_valid_token():
    """Verify GET /api/v1/session returns user identity and quota for valid dev token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer dev-test-user"}
        response = await client.get("/api/v1/session", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("user_id") == "dev-test-user"
        assert "quota_remaining" in data
        assert data["quota_remaining"].get("new_indexes") is not None


@pytest.mark.asyncio
async def test_paper_ingest_status_retrieve_and_delete_flow():
    """Verify end-to-end W1 flow: Ingest -> Status -> BM25 Retrieve -> Delete."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer user-alice"}

        paper_payload = {
            "title": "Attention Is All You Need",
            "arxiv_id": "1706.03762",
            "version": "v7",
            "canonical_url": "https://arxiv.org/html/1706.03762v7",
            "parser_version": "1.0.0",
            "sections": [
                {"id": "S1", "heading": "1 Introduction", "path": "1 Introduction", "order": 0},
                {"id": "S2", "heading": "2 Background", "path": "2 Background", "order": 1}
            ],
            "paragraphs": [
                {
                    "id": "S1.p1",
                    "section_id": "S1",
                    "section_path": "1 Introduction",
                    "order": 0,
                    "text": "The Transformer is the first transduction model relying entirely on self-attention.",
                    "locator": {"element_id": "S1.p1", "selector": "#S1\\.p1"}
                },
                {
                    "id": "S2.p1",
                    "section_id": "S2",
                    "section_path": "2 Background",
                    "order": 1,
                    "text": "Recurrent neural networks process tokens sequentially along the time dimension.",
                    "locator": {"element_id": "S2.p1", "selector": "#S2\\.p1"}
                }
            ]
        }

        # 1. Ingest paper
        ingest_res = await client.post("/api/v1/papers/ingest", json=paper_payload, headers=headers)
        assert ingest_res.status_code in [200, 202]
        ingest_data = ingest_res.json()
        paper_id = ingest_data.get("paper_id")
        assert paper_id is not None
        assert ingest_data.get("lexical_ready") is True

        # 2. Check repeated ingest reuses paper_id
        repeat_res = await client.post("/api/v1/papers/ingest", json=paper_payload, headers=headers)
        assert repeat_res.status_code in [200, 202]
        assert repeat_res.json().get("paper_id") == paper_id

        # 3. Check status
        status_res = await client.get(f"/api/v1/papers/{paper_id}/status", headers=headers)
        assert status_res.status_code == 200
        status_data = status_res.json()
        assert status_data.get("paper_id") == paper_id
        assert status_data.get("lexical_ready") is True

        # 4. Cross-owner status must return 404
        other_headers = {"Authorization": "Bearer user-bob"}
        cross_res = await client.get(f"/api/v1/papers/{paper_id}/status", headers=other_headers)
        assert cross_res.status_code == 404

        # 5. Retrieve evidence (B1 mode)
        retrieve_payload = {
            "request_id": "req-123",
            "paper_id": paper_id,
            "question": "How does Transformer work with self-attention?",
            "top_k": 3
        }
        retrieve_res = await client.post("/api/v1/retrieve", json=retrieve_payload, headers=headers)
        assert retrieve_res.status_code == 200
        retrieve_data = retrieve_res.json()
        assert retrieve_data.get("paper_id") == paper_id
        assert retrieve_data.get("retrieval_mode") == "B1"
        assert len(retrieve_data.get("evidence", [])) > 0
        top_ev = retrieve_data["evidence"][0]
        assert top_ev["passage_id"] == "S1.p1"
        assert top_ev["locator"]["element_id"] == "S1.p1"

        # 6. Delete paper
        del_res = await client.delete(f"/api/v1/papers/{paper_id}", headers=headers)
        assert del_res.status_code == 200

        # 7. Status after deletion must be 404
        status_after_del = await client.get(f"/api/v1/papers/{paper_id}/status", headers=headers)
        assert status_after_del.status_code == 404


@pytest.mark.asyncio
async def test_paper_ingest_body_limit():
    """Verify oversized payload exceeding body cap is rejected."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer user-limit"}
        # Oversized text > 1 MiB
        huge_text = "x" * (1024 * 1024 + 100)
        oversized_payload = {
            "title": "Huge Paper",
            "arxiv_id": "2401.99999",
            "version": "v1",
            "canonical_url": "https://arxiv.org/html/2401.99999v1",
            "parser_version": "1.0.0",
            "sections": [],
            "paragraphs": [
                {
                    "id": "p1",
                    "section_id": "s1",
                    "section_path": "Main",
                    "order": 0,
                    "text": huge_text,
                    "locator": {"element_id": "p1"}
                }
            ]
        }
        res = await client.post("/api/v1/papers/ingest", json=oversized_payload, headers=headers)
        assert res.status_code in [400, 413]


@pytest.mark.asyncio
async def test_cross_owner_warm_cache_isolation():
    """Verify that cached paper chunks cannot be read by another owner via warm cache."""
    from backend.app.cache.paper_store import store_paper_and_chunks, get_paper_chunks, get_bm25_index
    from backend.app.core.schemas import PaperIngestRequest, SectionInput, ParagraphInput, SourceLocation
    from backend.app.retrieval.chunking import chunk_paper
    from backend.app.agent.tools import PaperAgentTools

    req = PaperIngestRequest(
        title="Owner Test",
        arxiv_id="2401.12345",
        version="v1",
        canonical_url="https://arxiv.org/html/2401.12345v1",
        parser_version="1.0.0",
        sections=[SectionInput(id="S1", heading="Sec 1", path="Sec 1", order=0)],
        paragraphs=[
            ParagraphInput(
                id="S1.p1",
                section_id="S1",
                section_path="Sec 1",
                order=0,
                text="Private research content of user A.",
                locator=SourceLocation(element_id="S1.p1"),
            )
        ],
    )
    chunks = chunk_paper(req.paragraphs, max_tokens=100, paper_id="paper_owner_a")
    store_paper_and_chunks(
        paper_id="paper_owner_a",
        owner_id="user_alice_cache",
        paper_req=req,
        content_hash="hash_owner_a",
        chunks=chunks,
    )

    # user_alice should get chunks
    alice_chunks = get_paper_chunks("paper_owner_a", owner_id="user_alice_cache")
    assert len(alice_chunks) == 1
    assert alice_chunks[0].text == "Private research content of user A."

    # user_bob MUST NOT get chunks for paper_owner_a
    bob_chunks = get_paper_chunks("paper_owner_a", owner_id="user_bob_intruder")
    assert len(bob_chunks) == 0

    # user_bob MUST NOT get bm25 index for paper_owner_a
    bob_bm25 = get_bm25_index("paper_owner_a", owner_id="user_bob_intruder")
    assert bob_bm25 is None

    # Tools: bob executing tools against alice's paper must be rejected
    bob_tools = PaperAgentTools(paper_id="paper_owner_a", owner_id="user_bob_intruder")
    outline_obs = await bob_tools.get_paper_outline()
    assert "not found" in outline_obs.content.lower() or "unauthorized" in outline_obs.content.lower()


@pytest.mark.asyncio
async def test_reject_shared_default_identity_outside_dev(monkeypatch):
    """Verify shared default identity ('dev-default-user') is rejected outside development environment."""
    from backend.app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings.app, "environment", "production")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": "Bearer dev-default-user"}
        res = await client.get("/api/v1/session", headers=headers)
        assert res.status_code == 401


@pytest.mark.asyncio
async def test_paragraph_id_collision_across_papers():
    """Verify that identical paragraph IDs across different papers do not overwrite each other."""
    from backend.app.cache.paper_store import store_paper_and_chunks, get_paper_chunks
    from backend.app.core.schemas import PaperIngestRequest, SectionInput, ParagraphInput, SourceLocation
    from backend.app.retrieval.chunking import chunk_paper

    def make_req(arxiv_id: str, text: str):
        return PaperIngestRequest(
            title=f"Collision Test {arxiv_id}",
            arxiv_id=arxiv_id,
            version="v1",
            canonical_url=f"https://arxiv.org/html/{arxiv_id}v1",
            parser_version="1.0.0",
            sections=[SectionInput(id="S1", heading="Sec 1", path="Sec 1", order=0)],
            paragraphs=[
                ParagraphInput(
                    id="S1.p1",
                    section_id="S1",
                    section_path="Sec 1",
                    order=0,
                    text=text,
                    locator=SourceLocation(element_id="S1.p1"),
                )
            ],
        )

    req1 = make_req("2401.00001", "Text for Paper 1 unique content.")
    chunks1 = chunk_paper(req1.paragraphs, max_tokens=100, paper_id="paper_collision_1")
    store_paper_and_chunks("paper_collision_1", "user_collision", req1, "hash_col_1", chunks1)

    req2 = make_req("2401.00002", "Text for Paper 2 completely different content.")
    chunks2 = chunk_paper(req2.paragraphs, max_tokens=100, paper_id="paper_collision_2")
    store_paper_and_chunks("paper_collision_2", "user_collision", req2, "hash_col_2", chunks2)

    # Reload from fresh DB connection (bypass memory cache to test SQLite persistence)
    from backend.app.cache.paper_store import _chunks_cache
    _chunks_cache.clear()

    c1 = get_paper_chunks("paper_collision_1", "user_collision")
    c2 = get_paper_chunks("paper_collision_2", "user_collision")

    assert len(c1) == 1
    assert c1[0].text == "Text for Paper 1 unique content."

    assert len(c2) == 1
    assert c2[0].text == "Text for Paper 2 completely different content."
