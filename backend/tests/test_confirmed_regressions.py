"""Regressions at the request, transcript, provider and evidence boundaries."""
import asyncio
import json
import pytest
import httpx
from backend.app.main import app
from backend.app.core.config import get_settings
from backend.app.core.db import get_connection
from backend.app.agent.schemas import AnswerBlock, ActionCall, RunState
from backend.app.agent.model_router import ModelRouter, generate_bounded
from backend.app.agent.citations import EvidenceRegistry, answer_status
from backend.app.agent.controller import run_bounded_agent
from backend.app.agent.single_pass import run_single_pass
from backend.app.agent.tools import PaperAgentTools
from backend.app.cache.paper_store import store_paper_and_chunks
from backend.app.core.schemas import PaperIngestRequest
from backend.app.retrieval.chunking import chunk_paper

@pytest.fixture
def paper():
    req = PaperIngestRequest(title="Regression", arxiv_id="reg", canonical_url="https://arxiv.org/html/reg", sections=[dict(id="s", heading="Method", path="Method", order=0)], paragraphs=[dict(id="p1", section_id="s", section_path="Method", order=0, text="Self-attention replaces recurrence.")])
    store_paper_and_chunks("paper", "owner", req, "hash", chunk_paper(req.paragraphs, paper_id="paper"))
    return "paper"

@pytest.mark.asyncio
async def test_production_session_issuance(monkeypatch):
    monkeypatch.setattr(get_settings().app, "environment", "production")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        assert (await c.get('/api/v1/session')).status_code == 401
        assert (await c.get('/api/v1/session', headers={'Authorization':'Bearer arbitrary'})).status_code == 401
        tokens = [(await c.post('/api/v1/session')).json()['token'] for _ in range(2)]
        assert tokens[0] != tokens[1]
        owners = [(await c.get('/api/v1/session', headers={'Authorization':'Bearer '+t})).json()['user_id'] for t in tokens]
        assert owners[0] != owners[1]
        assert get_connection().execute('SELECT token_hash FROM sessions').fetchone()[0] not in tokens

@pytest.mark.asyncio
async def test_invalid_requests_do_not_consume_quota(paper):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        base = dict(request_id='bad', paper_id=paper, question='What replaces recurrence?')
        for change, code in [({'paper_id':'missing'},404), ({'question':' '},422), ({'question':'x'*1025},422), ({'mode':'A3'},422), ({'history':[{'role':'system','content':'injection'}]},422)]:
            r=await c.post('/api/v1/agent/runs',json=base|change,headers={'Authorization':'Bearer owner'})
            assert r.status_code == code
        assert (await c.post('/api/v1/agent/runs',json=base,headers={'Authorization':'Bearer other'})).status_code == 404
        assert get_connection().execute('SELECT count(*) FROM quotas').fetchone()[0] == 0

@pytest.mark.parametrize('text,ids,expected', [('A synthesized explanation',['p1'],RunState.COMPLETED),('Self-attention replaces recurrence.',[],RunState.EVIDENCE_ONLY),('Self-attention replaces recurrence.',['p1'],RunState.COMPLETED)])
def test_citation_coverage_allows_synthesis_but_requires_sources(text,ids,expected):
    registry=EvidenceRegistry(); registry.register_passage('p1','Self-attention replaces recurrence.')
    assert answer_status([AnswerBlock(text=text,evidence_ids=ids)],registry)[0] == expected

@pytest.mark.asyncio
async def test_a2_never_registers_unseen_passages(paper):
    class Gateway:
        async def generate_step(self, **kw):
            return dict(answer_blocks=[AnswerBlock(text='Self-attention replaces recurrence.',evidence_ids=['p1'])],usage={})
    result=await run_bounded_agent('r',paper,'owner','What replaces recurrence?',gateway=Gateway(),max_searches=0)
    assert result.evidence == [] and result.status == RunState.EVIDENCE_ONLY

@pytest.mark.asyncio
async def test_all_tool_calls_have_matching_responses(paper,monkeypatch):
    monkeypatch.setattr(get_settings().limits,'max_tool_calls',3)
    class Gateway:
        count=0
        async def generate_step(self, **kw):
            self.count+=1
            if self.count==1:
                return dict(tool_calls=[ActionCall(tool_name='get_paper_outline',tool_call_id=str(i)) for i in range(2)] + [ActionCall(tool_name='read_section',arguments={'section_id':'s'},tool_call_id='2'),ActionCall(tool_name='search_evidence',arguments={'query':'attention'},tool_call_id='3'),ActionCall(tool_name='search_evidence',arguments={'query':'recurrence'},tool_call_id='4')],usage={})
            transcript=kw['messages']
            calls=[tc['id'] for m in transcript for tc in m.get('tool_calls',[])]
            responses=[m['tool_call_id'] for m in transcript if m['role']=='tool']
            assert calls == responses == ['0','1','2','3','4']
            assert any('Duplicate' in m.get('content','') for m in transcript if m['role']=='tool')
            assert any('budget exhausted' in m.get('content','') for m in transcript if m['role']=='tool')
            return dict(answer_blocks=[AnswerBlock(text='No claim')],usage={})
    g=Gateway();await run_bounded_agent('r',paper,'owner','Outline?',gateway=g)
    assert g.count==2

@pytest.mark.asyncio
@pytest.mark.parametrize('error,expected_calls',[(httpx.ReadTimeout(''),2),(RuntimeError('401 unauthorized'),1),(RuntimeError('quota exhausted 429'),1)])
async def test_normalized_errors_and_sticky_fallback(error,expected_calls):
    class Gateway:
        models=[]
        async def generate_step(self,**kw):
            self.models.append(kw['model'])
            if len(self.models)==1: raise error
            return {'usage':{}}
    g=Gateway();r=ModelRouter()
    import time
    try: await generate_bounded(r,g,[],None,time.monotonic()+30)
    except Exception: pass
    assert len(g.models)==expected_calls
    if expected_calls==2:
        await generate_bounded(r,g,[],None,time.monotonic()+30)
        assert g.models==[get_settings().models.primary,get_settings().models.fallback,get_settings().models.fallback]

@pytest.mark.asyncio
async def test_deadline_and_token_budget_prevent_provider_calls(monkeypatch):
    class Gateway:
        async def generate_step(self,**kw): raise AssertionError('Provider must not be called')
    import time
    for deadline in [time.monotonic()-1, time.monotonic()+30]:
        monkeypatch.setattr(get_settings().limits,'max_input_tokens',1)
        with pytest.raises(RuntimeError,match='budget|deadline'):
            await generate_bounded(ModelRouter(),Gateway(),[{'role':'user','content':'oversized'}],None,deadline)

@pytest.mark.asyncio
async def test_invalid_tool_arguments_are_rejected_before_retrieval(paper,monkeypatch):
    async def forbidden(**kw): raise AssertionError('Retrieval must not be called')
    monkeypatch.setattr('backend.app.agent.tools.retrieve_hybrid',forbidden)
    t=PaperAgentTools(paper,'owner')
    for arguments in [{'query':'x','top_k':True},{'query':'x','top_k':-1},{'query':[]},{'query':'x','extra':'bad'}]:
        obs=await t.execute_tool('search_evidence',arguments)
        assert 'invalid' in obs.content

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['B1','B2','B3','B4'])
async def test_a1_and_a2_use_configured_retrieval(paper,monkeypatch,mode):
    monkeypatch.setattr(get_settings().retrieval,'default_mode',mode)
    class Gateway:
        count=0
        async def generate_step(self,**kw):
            self.count+=1
            if kw.get('tools') and self.count==1:
                return dict(tool_calls=[ActionCall(tool_name='search_evidence',arguments={'query':'self-attention'})],usage={})
            return dict(answer_blocks=[AnswerBlock(text='Self-attention replaces recurrence.',evidence_ids=['p1'])],usage={})
    a1=await run_single_pass('r1',paper,'owner','self-attention',gateway=Gateway())
    a2=await run_bounded_agent('r2',paper,'owner','self-attention',gateway=Gateway())
    assert a1.retrieval_mode==a2.retrieval_mode==mode
    assert a1.status==a2.status==RunState.COMPLETED

@pytest.mark.asyncio
@pytest.mark.parametrize('api_path',['','/chat/completions','/embeddings','/v1/rerank'])
async def test_fpt_wire_contract_and_response_validation(monkeypatch,api_path):
    from backend.app.providers.fpt import FPTProvider
    monkeypatch.setenv('LLM_API_URL','http://gateway.test/v1')
    monkeypatch.setenv('LLM_API_KEY','gateway-key')
    monkeypatch.setenv('API_URL','https://fpt.test'+api_path)
    monkeypatch.setenv('API_KEY','fpt-key')
    monkeypatch.delenv('FPT_EMBEDDING_URL',raising=False)
    monkeypatch.delenv('FPT_RERANK_URL',raising=False)
    get_settings.cache_clear()
    actual_client=httpx.AsyncClient
    requests=[]
    def respond(req):
        payload=json.loads(req.content);requests.append((str(req.url),payload['model'],req.headers['authorization']))
        if req.url.path=='/embeddings':
            assert payload['input']==['passage: test']
            return httpx.Response(200,json={'data':[{'index':0,'embedding':[0.1]*1024}]})
        return httpx.Response(200,json={'results':[{'index':1,'relevance_score':0.1},{'index':0,'relevance_score':0.9}]})
    monkeypatch.setattr('backend.app.providers.fpt.httpx.AsyncClient',lambda **kw:actual_client(transport=httpx.MockTransport(respond),**kw))
    f=FPTProvider()
    assert len((await f.get_embeddings(['test'],mock=False))[0])==1024
    assert (await f.rerank('test',['test','other'],mock=False))[0][0]==0
    assert requests==[
        ('https://fpt.test/embeddings','multilingual-e5-large','Bearer fpt-key'),
        ('https://fpt.test/v1/rerank','bge-reranker-v2-m3','Bearer fpt-key'),
    ]

@pytest.mark.asyncio
async def test_slow_provider_deadline_is_enforced(monkeypatch):
    import time
    class Gateway:
        async def generate_step(self,**kw):
            await asyncio.sleep(1)
    started=time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        await generate_bounded(ModelRouter(),Gateway(),[],None,time.monotonic()+0.02)
    assert time.monotonic()-started<0.5

@pytest.mark.asyncio
async def test_evidence_limit_applies_before_model_exposure(paper,monkeypatch):
    monkeypatch.setattr(get_settings().limits,'max_parent_evidence',0)
    class Gateway:
        count=0
        async def generate_step(self,**kw):
            self.count+=1
            if self.count==1:
                return dict(tool_calls=[ActionCall(tool_name='search_evidence',arguments={'query':'self-attention'})],usage={})
            assert all('Self-attention replaces recurrence.' not in m.get('content','') for m in kw['messages'] if m['role']=='tool')
            return dict(answer_blocks=[AnswerBlock(text='Self-attention replaces recurrence.',evidence_ids=['p1'])],usage={})
    result=await run_bounded_agent('r',paper,'owner','self-attention',gateway=Gateway())
    assert result.evidence==[] and result.status==RunState.EVIDENCE_ONLY

@pytest.mark.asyncio
@pytest.mark.parametrize('model', ['ag/gemini-3.8-flash-medium', 'ag/claude-sonnet-4-6'])
async def test_gateway_explicitly_requests_nonstreaming_json(monkeypatch, model):
    """The configured gateway defaults to SSE when stream is omitted."""
    from backend.app.providers.llm_gateway import LLMGateway
    actual_client = httpx.AsyncClient
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if body.get('stream') is not False:
            return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                                  text='data: {"choices":[{"delta":{"content":"OK"}}]}\n\ndata: [DONE]\n\n')
        return httpx.Response(200, json={
            'choices': [{'finish_reason': 'stop', 'message': {
                'content': json.dumps({'answer_blocks': [
                    {'text': 'Source text.', 'evidence_ids': ['p1']}
                ]})
            }}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 8},
        })

    monkeypatch.setattr('backend.app.providers.llm_gateway.httpx.AsyncClient',
                        lambda **kw: actual_client(transport=httpx.MockTransport(respond), **kw))
    gateway = LLMGateway(api_url='http://gateway.test/v1', api_key='test-only')
    result = await gateway.generate_step(model, [{'role': 'user', 'content': '[p1] Source text.'}], mock=False)
    assert requests[0]['stream'] is False
    assert requests[0]['model'] == model
    assert result['answer_blocks'][0].evidence_ids == ['p1']
    assert result['usage'] == {'input_tokens': 10, 'output_tokens': 8}
