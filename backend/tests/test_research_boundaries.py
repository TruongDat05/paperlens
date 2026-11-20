"""Research retrieval must never substitute fixtures for unavailable live sources."""
import httpx
import pytest

from backend.app.core.config import get_settings
from backend.app.core.limits import reserve_quota, get_remaining_quotas
from backend.app.retrieval.hybrid import is_research_extension_query
from backend.app.retrieval.scholarly import search_external_scholarly, _SCHOLARLY_CACHE


@pytest.mark.asyncio
async def test_live_outage_never_returns_synthetic_papers(monkeypatch):
    _SCHOLARLY_CACHE.clear()
    real_client = httpx.AsyncClient
    calls = []
    def unavailable(request):
        calls.append(request)
        return httpx.Response(503)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(unavailable), **kw))
    assert await search_external_scholarly('unavailable niche topic', force_mock=False) == []
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_mock_cache_cannot_contaminate_live_search(monkeypatch):
    _SCHOLARLY_CACHE.clear()
    await search_external_scholarly('sparse attention', force_mock=True)
    real_client = httpx.AsyncClient
    calls = []
    def empty(request):
        calls.append(request)
        return httpx.Response(200, json={'data': []}) if 'semanticscholar' in request.url.host else httpx.Response(200, text='<feed/>')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(empty), **kw))
    assert await search_external_scholarly('sparse attention', force_mock=False) == []
    assert len(calls) == 2


def test_exact_vietnamese_research_direction_question():
    assert is_research_extension_query('Từ paper trên, tôi có thể tìm hướng mới trong nghiên cứu nào')


def test_local_daily_limits_are_configurable(monkeypatch):
    monkeypatch.setenv('DAILY_AGENT_TURNS', '-1')
    get_settings.cache_clear()
    assert all(reserve_quota('local', 'agent_turns') for _ in range(8))
    assert get_remaining_quotas('local')['agent_turns'] is None


@pytest.fixture
def research_paper():
    from backend.app.core.schemas import PaperIngestRequest
    from backend.app.cache.paper_store import store_paper_and_chunks
    from backend.app.retrieval.chunking import chunk_paper
    req = PaperIngestRequest(title='Attention Is All You Need', arxiv_id='scope-test',
        canonical_url='https://arxiv.org/html/scope-test',
        sections=[dict(id='s', heading='Method', path='Method', order=0)],
        paragraphs=[dict(id='p1', section_id='s', section_path='Method', order=0,
                         text='Self-attention replaces recurrence. Attention has quadratic complexity.')])
    store_paper_and_chunks('scope-paper', 'owner', req, 'hash', chunk_paper(req.paragraphs, paper_id='scope-paper'))
    return 'scope-paper'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['A1', 'A2'])
async def test_product_refusal_precedes_all_tools_and_finishes_stream(research_paper, monkeypatch, mode):
    from backend.app.agent.runs import create_or_get_run, _active_run_tasks, get_run
    from backend.app.agent.schemas import AgentRunRequest
    from backend.app.providers.llm_gateway import LLMGateway
    from backend.app.agent.tools import PaperAgentTools
    from backend.app.main import app
    async def refuse(self, **kwargs):
        return {'research_plan': {'scope': 'refuse', 'language': 'vi'}, 'usage': {}}
    async def forbidden(*args, **kwargs):
        pytest.fail('Out-of-scope requests must never execute tools')
    monkeypatch.setattr(LLMGateway, 'generate_step', refuse)
    monkeypatch.setattr(PaperAgentTools, 'execute_tool', forbidden)
    req = AgentRunRequest(request_id='refuse', paper_id=research_paper, question='Hôm nay thời tiết thế nào?', mode=mode)
    res, _, _ = await create_or_get_run(req, 'owner')
    await _active_run_tasks[('owner', res.run_id)]
    result = get_run(res.run_id, 'owner')
    assert result.status.value == 'refused'
    assert result.evidence == []
    assert 'chỉ hỗ trợ nghiên cứu' in result.answer_blocks[0].text
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        stream = await client.get(f'/api/v1/agent/runs/{res.run_id}/events', headers={'Authorization': 'Bearer owner'})
    assert '"status": "refused"' in stream.text


@pytest.mark.asyncio
async def test_invalid_scope_fails_closed_before_retrieval(research_paper, monkeypatch):
    from backend.app.agent.runs import create_or_get_run, _active_run_tasks, get_run
    from backend.app.agent.schemas import AgentRunRequest
    from backend.app.providers.llm_gateway import LLMGateway
    from backend.app.agent.tools import PaperAgentTools
    async def malformed(self, **kwargs):
        return {'research_plan': {'scope': 'anything'}, 'usage': {}}
    async def forbidden(*args, **kwargs):
        pytest.fail('An unvalidated scope must never reach tools')
    monkeypatch.setattr(LLMGateway, 'generate_step', malformed)
    monkeypatch.setattr(PaperAgentTools, 'execute_tool', forbidden)
    res, _, _ = await create_or_get_run(AgentRunRequest(request_id='invalid-scope', paper_id=research_paper, question='Analyze this paper'), 'owner')
    await _active_run_tasks[('owner', res.run_id)]
    assert get_run(res.run_id, 'owner').status.value == 'failed'


@pytest.mark.asyncio
async def test_vietnamese_product_plan_searches_literature_before_answer(research_paper):
    from backend.app.agent.runs import create_or_get_run, _active_run_tasks, get_run, _run_event_history, register_run_listener, unregister_run_listener
    from backend.app.agent.schemas import AgentRunRequest
    req = AgentRunRequest(request_id='research', paper_id=research_paper,
                          question='Từ paper trên, tôi có thể tìm hướng mới trong nghiên cứu nào')
    res, _, _ = await create_or_get_run(req, 'owner')
    queue, events = register_run_listener('owner', res.run_id)
    await _active_run_tasks[('owner', res.run_id)]
    while not queue.empty():
        events.append(queue.get_nowait())
    unregister_run_listener('owner', res.run_id, queue)
    assert ('owner', res.run_id) not in _run_event_history
    result = get_run(res.run_id, 'owner')
    assert result.status.value in ('completed', 'partial')
    assert any(e.passage_id.startswith('ext_') for e in result.evidence)
    assert any(eid.startswith('ext_') for b in result.answer_blocks for eid in b.evidence_ids)
    calls = [e['tool_name'] for e in events if e['type'] == 'tool_call']
    assert calls == ['search_evidence', 'search_external_papers']


@pytest.mark.asyncio
async def test_missing_literature_is_disclosed(research_paper, monkeypatch):
    from backend.app.agent.controller import run_bounded_agent
    async def empty(*args, **kwargs):
        return []
    monkeypatch.setattr('backend.app.retrieval.scholarly.search_external_scholarly', empty)
    result = await run_bounded_agent('r', research_paper, 'owner', 'Propose research directions', external_query='efficient attention')
    assert all(not e.passage_id.startswith('ext_') for e in result.evidence)
    assert 'External scholarly sources could not be retrieved' in result.limitations


def test_finite_quota_still_enforced_with_reset_time(monkeypatch):
    from backend.app.core.limits import check_quota_or_raise
    from fastapi import HTTPException
    monkeypatch.setattr(get_settings().quotas, 'daily_agent_turns', 1)
    check_quota_or_raise('limited', 'agent_turns')
    with pytest.raises(HTTPException) as err:
        check_quota_or_raise('limited', 'agent_turns')
    assert err.value.status_code == 429
    assert err.value.detail['code'] == 'DAILY_QUOTA_EXCEEDED'
    assert err.value.detail['reset_at'].endswith('00:00:00+00:00')
    assert int(err.value.headers['Retry-After']) > 0


@pytest.mark.asyncio
async def test_over_specific_arxiv_query_broadens_once_then_caches(monkeypatch):
    from backend.tests.test_scholarly import SAMPLE_ARXIV_ATOM
    import backend.app.retrieval.scholarly as scholarly
    _SCHOLARLY_CACHE.clear()
    real_client = httpx.AsyncClient
    queries = []
    def respond(request):
        queries.append(request.url.params['search_query'])
        return httpx.Response(200, text='<feed/>' if len(queries) == 1 else SAMPLE_ARXIV_ATOM)
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    monkeypatch.setattr(scholarly, '_last_arxiv_request', -100)
    async def no_wait(seconds):
        return None
    monkeypatch.setattr(scholarly.asyncio, 'sleep', no_wait)
    query = 'table retrieval augmented generation hierarchical memory'
    papers = await search_external_scholarly(query, force_mock=False)
    assert len(papers) == 1
    assert queries[-1] == 'all:table AND all:retrieval AND all:augmented'
    assert await search_external_scholarly(query, force_mock=False) == papers
    assert len(queries) == 2
