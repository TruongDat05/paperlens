import pytest
from backend.app.retrieval.scholarly import (
    ScholarlyPaper,
    parse_arxiv_atom,
    search_external_scholarly,
    _SCHOLARLY_CACHE,
)
from backend.app.core.schemas import EvidenceItem

SAMPLE_ARXIV_ATOM = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/" xmlns:arxiv="http://arxiv.org/schemas/atom" xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2001.04451v1</id>
    <title>Reformer: The Efficient Transformer</title>
    <summary>Large Transformer models routinely achieve state-of-the-art results but training can be prohibitively expensive.</summary>
    <published>2020-01-13T18:00:00Z</published>
    <author><name>Nikita Kitaev</name></author>
    <author><name>Lukasz Kaiser</name></author>
    <link href="https://arxiv.org/abs/2001.04451v1" rel="alternate" type="text/html"/>
  </entry>
</feed>
"""


def test_parse_arxiv_atom():
    papers = parse_arxiv_atom(SAMPLE_ARXIV_ATOM)
    assert len(papers) == 1
    p = papers[0]
    assert p.paper_id == "arxiv:2001.04451v1"
    assert p.title == "Reformer: The Efficient Transformer"
    assert "Nikita Kitaev" in p.authors
    assert p.year == 2020
    assert "Large Transformer models" in p.abstract
    assert p.url == "https://arxiv.org/abs/2001.04451v1"


def test_scholarly_paper_to_evidence_item():
    paper = ScholarlyPaper(
        paper_id="arxiv:2001.04451",
        title="Reformer: The Efficient Transformer",
        authors=["Nikita Kitaev", "Lukasz Kaiser"],
        year=2020,
        abstract="Reformer reduces memory complexity using locality-sensitive hashing.",
        url="https://arxiv.org/abs/2001.04451",
    )
    ev = paper.to_evidence_item(rank=2)
    assert isinstance(ev, EvidenceItem)
    assert ev.passage_id == "ext_arxiv_2001.04451"
    assert ev.rank == 2
    assert "Reformer" in ev.section_heading
    assert "External Scholarly Literature" in ev.section_path
    assert ev.locator.xpath == "https://arxiv.org/abs/2001.04451"
    assert "Locality-sensitive hashing" in ev.text.lower() or "reformer" in ev.text.lower()


@pytest.mark.asyncio
async def test_search_external_scholarly_mock():
    _SCHOLARLY_CACHE.clear()
    results = await search_external_scholarly("efficient transformer attention", max_results=2, force_mock=True)
    assert len(results) <= 2
    assert len(results) > 0
    assert any("transformer" in r.title.lower() or "attention" in r.title.lower() for r in results)


@pytest.mark.asyncio
async def test_search_external_scholarly_caching():
    _SCHOLARLY_CACHE.clear()
    res1 = await search_external_scholarly("flash attention", max_results=2, force_mock=True)
    assert not _SCHOLARLY_CACHE  # Fixtures must never populate the live cache.
    res2 = await search_external_scholarly("flash attention", max_results=2, force_mock=True)
    assert res1 == res2


@pytest.mark.asyncio
async def test_agent_tools_search_external_papers(paper):
    from backend.app.agent.tools import PaperAgentTools
    tools = PaperAgentTools(paper_id="test_paper", owner_id="test_owner")
    obs = await tools.execute_tool("search_external_papers", {"query": "sparse attention", "top_k": 2})
    assert obs.tool_name == "search_external_papers"
    assert len(obs.evidence_ids) > 0
    assert all(eid.startswith("ext_") for eid in obs.evidence_ids)
    assert len(obs.raw_evidence) > 0
    assert obs.raw_evidence[0].section_path == "External Scholarly Literature"


@pytest.fixture
def paper():
    from backend.app.cache.paper_store import store_paper_and_chunks
    from backend.app.core.schemas import PaperIngestRequest
    req = PaperIngestRequest(title="Test", arxiv_id="test", canonical_url="https://arxiv.org/abs/test",
                            sections=[], paragraphs=[])
    store_paper_and_chunks("test_paper", "test_owner", req, "hash", [])


@pytest.mark.asyncio
async def test_bounded_agent_research_extension_flow(tmp_path, monkeypatch):
    from backend.app.agent.controller import run_bounded_agent
    from backend.app.cache.paper_store import store_paper_and_chunks
    from backend.app.core.schemas import PaperIngestRequest, SectionInput, ParagraphInput

    paper_req = PaperIngestRequest(
        title="Attention Is All You Need",
        arxiv_id="1706.03762",
        version="v7",
        canonical_url="https://arxiv.org/abs/1706.03762",
        sections=[
            SectionInput(id="sec1", heading="1 Introduction", path="1 Introduction", order=1),
            SectionInput(id="sec5", heading="5 Conclusion", path="5 Conclusion", order=2),
        ],
        paragraphs=[
            ParagraphInput(
                id="p1",
                section_id="sec1",
                section_path="1 Introduction",
                order=1,
                text="The Transformer relies entirely on self-attention to compute representations.",
            ),
            ParagraphInput(
                id="p2",
                section_id="sec5",
                section_path="5 Conclusion",
                order=2,
                text="A limitation of self-attention is its quadratic computational complexity with respect to sequence length.",
            ),
        ],
    )
    from backend.app.retrieval.chunking import chunk_paper
    chunks = chunk_paper(paper_req.paragraphs, paper_id="1706.03762")
    store_paper_and_chunks("1706.03762", "owner_ext_test", paper_req, "hash_ext", chunks)

    events = []
    def on_event(ev):
        events.append(ev)

    result = await run_bounded_agent(
        run_id="run_ext_test",
        paper_id=paper_req.arxiv_id,
        owner_id="owner_ext_test",
        question="Based on this paper, what promising extension or implementation directions could I explore?",
        on_event=on_event,
    )

    assert result.status.value in ("completed", "partial")
    assert len(result.answer_blocks) > 0
    # Confirm result preserves accurate backend model information
    from backend.app.core.config import get_settings
    assert result.serving_model in (get_settings().models.primary, "ag/gemini-3.8-flash-medium", "ag/gemini-3.8-flash-low", "ag/claude-sonnet-4-6")
    # Verify tool events included searching external literature
    tool_names = [e.get("tool_name") for e in events if e.get("type") == "tool_call"]
    assert "search_external_papers" in tool_names or any(eid.startswith("ext_") for eid in result.emitted_citation_ids)
