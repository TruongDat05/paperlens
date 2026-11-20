"""Product chat budget, model levels, images and grounded synthesis regressions."""
import asyncio
import base64
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from backend.tests.test_confirmed_regressions import paper
from backend.app.agent.schemas import AgentRunRequest, ImageInput, AnswerBlock
from backend.app.agent.model_router import ModelRouter, generate_bounded
from backend.app.agent.runs import create_or_get_run, _active_run_tasks, get_run, get_chat_state
from backend.app.core.db import get_connection

PNG = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aB3sAAAAASUVORK5CYII='


@pytest.mark.parametrize('level,model', [('low','ag/gemini-3.8-flash-low'),('medium','ag/gemini-3.8-flash-medium'),('high','fpt/Qwen3.8-27B')])
def test_level_uses_exact_model(level, model):
    assert ModelRouter(level=level).get_active_model() == model


def test_images_are_validated_at_request_boundary():
    assert ImageInput(data_url=PNG)
    for url in ['https://example.com/a.png', 'data:image/svg+xml;base64,AAAA', 'data:image/png;base64,AAAA']:
        with pytest.raises(ValidationError):
            ImageInput(data_url=url)
    with pytest.raises(ValidationError):
        AgentRunRequest(request_id='q', paper_id='p', question='Explain image', images=[{'data_url':PNG}]*4)


async def finish(req):
    res, _, _ = await create_or_get_run(req, 'owner')
    await _active_run_tasks[('owner', res.run_id)]
    return get_run(res.run_id, 'owner')


@pytest.mark.asyncio
async def test_chat_usage_accumulates_is_idempotent_and_resets_in_new_chat(paper):
    first_req = AgentRunRequest(request_id='q1', paper_id=paper, question='Explain self-attention')
    first = await finish(first_req)
    assert first.chat_id and first.tokens_used > 0
    repeat, new, conflict = await create_or_get_run(first_req, 'owner')
    assert not new and not conflict and repeat.tokens_used == first.tokens_used
    second = await finish(AgentRunRequest(request_id='q2', paper_id=paper, question='What replaces recurrence?', chat_id=first.chat_id))
    assert second.tokens_used > first.tokens_used
    assert second.follow_ups
    fresh = await finish(AgentRunRequest(request_id='q3', paper_id=paper, question='Explain self-attention'))
    assert fresh.chat_id != first.chat_id
    assert fresh.tokens_used < second.tokens_used


@pytest.mark.asyncio
async def test_full_chat_blocked_and_other_owner_cannot_read_or_use_it(paper):
    first = await finish(AgentRunRequest(request_id='q1', paper_id=paper, question='Explain self-attention'))
    conn = get_connection()
    conn.execute('UPDATE conversations SET tokens_used = 500000 WHERE chat_id = ?', (first.chat_id,)); conn.commit()
    assert get_chat_state(first.chat_id,'attacker') == {}
    with pytest.raises(HTTPException) as err:
        await create_or_get_run(AgentRunRequest(request_id='full', paper_id=paper, question='One more?',chat_id=first.chat_id),'owner')
    assert err.value.status_code == 409
    assert 'new chat' in err.value.detail


@pytest.mark.asyncio
async def test_image_bytes_reach_scope_and_answer_with_paper_evidence(paper, monkeypatch):
    from backend.app.providers.llm_gateway import LLMGateway
    calls = []
    async def visual(self, **kwargs):
        calls.append(kwargs)
        parts = [part for m in kwargs['messages'] if isinstance(m.get('content'), list) for part in m['content']]
        assert any(p.get('image_url',{}).get('url') == PNG for p in parts)
        if 'You classify requests' in kwargs['messages'][0]['content']:
            return {'research_plan': {'scope':'paper','paper_query':'self attention recurrence'},'usage':{'input_tokens':100,'output_tokens':20}}
        text = str(kwargs['messages'])
        assert 'Self-attention replaces recurrence.' in text and 'img_1' in text
        return {'answer_blocks':[AnswerBlock(text='The image visualizes self-attention replacing recurrence.',evidence_ids=['p1','img_1'])],
                'follow_ups':['Which connection corresponds to a query vector?'], 'usage':{'input_tokens':200,'output_tokens':50}}
    monkeypatch.setattr(LLMGateway,'generate_step',visual)
    result = await finish(AgentRunRequest(request_id='vision', paper_id=paper, question='Explain this figure using the paper.', images=[{'name':'figure.png','data_url':PNG}],level='medium'))
    assert result.status.value == 'completed'
    assert result.limitations is None
    assert result.tokens_used == 370
    assert result.follow_ups == ['Which connection corresponds to a query vector?']
    assert all(c['model']=='ag/gemini-3.8-flash-medium' for c in calls)


@pytest.mark.asyncio
async def test_chat_budget_rejects_provider_call_before_exceeding_limit():
    import time
    router=ModelRouter(token_budget=100)
    class Gateway:
        async def generate_step(self,**kw): pytest.fail('Exhausted chat must not spend tokens')
    with pytest.raises(RuntimeError,match='Chat token budget'):
        await generate_bounded(router,Gateway(),[{'role':'user','content':'x'}],None,time.monotonic()+10)
    assert router.budget_exhausted


@pytest.mark.asyncio
async def test_failed_provider_attempt_is_accounted(paper, monkeypatch):
    from backend.app.providers.llm_gateway import LLMGateway
    async def broken(self,**kwargs): raise RuntimeError('401 invalid authentication')
    monkeypatch.setattr(LLMGateway,'generate_step',broken)
    result=await finish(AgentRunRequest(request_id='failed',paper_id=paper,question='Explain attention'))
    assert result.status.value == 'failed'
    assert result.tokens_used > 0 and result.usage_estimated


@pytest.mark.asyncio
@pytest.mark.parametrize('image_notes', [
    ['Proposed = 73; Baseline = 17. Synthetic chart, not reported paper results.'],
    ['Proposed = 73.', 'Baseline = 17.', 'Synthetic chart.', 'Not reported paper results.'],
])
async def test_high_uses_visual_reader_then_qwen_synthesis(paper, monkeypatch, image_notes):
    from backend.app.providers.llm_gateway import LLMGateway
    models = []
    async def generate(self, **kw):
        models.append(kw['model'])
        if len(models) == 1:
            assert kw['model'] == 'ag/gemini-3.8-flash-low'
            assert any(isinstance(m['content'],list) for m in kw['messages'])
            return {'research_plan':{'scope':'paper','paper_query':'self attention', 'image_notes':image_notes}, 'usage':{'input_tokens':200,'output_tokens':80}}
        assert kw['model'] == 'fpt/Qwen3.8-27B'
        assert not any(isinstance(m['content'],list) for m in kw['messages'])
        assert 'Proposed = 73' in str(kw['messages'])
        return {'answer_blocks':[AnswerBlock(text='The synthetic chart shows a 56-point difference. The paper uses self-attention.',evidence_ids=['img_1','p1'])], 'usage':{'input_tokens':300,'output_tokens':100}}
    monkeypatch.setattr(LLMGateway,'generate_step',generate)
    result=await finish(AgentRunRequest(request_id='high-image',paper_id=paper,question='Compare the chart and paper.',images=[{'data_url':PNG}],level='high'))
    assert result.status.value == 'completed' and result.tokens_used == 680
    assert result.serving_model == 'fpt/Qwen3.8-27B'


def test_specific_explanation_is_not_misrouted_to_overview():
    from backend.app.retrieval.hybrid import is_overview_query
    assert is_overview_query('Explain this paper')
    assert not is_overview_query('Explain the retrieval algorithm and ablation design in this paper')
    assert not is_overview_query('Explain equation 4 from the paper step by step')


@pytest.mark.asyncio
async def test_outline_does_not_force_answer_before_reading_method(paper):
    from backend.app.agent.controller import run_bounded_agent
    from backend.app.agent.schemas import ActionCall
    class Gateway:
        calls=0
        async def generate_step(self, **kw):
            self.calls+=1
            if self.calls==1:
                return {'tool_calls':[ActionCall(tool_name='get_paper_outline',arguments={})], 'usage':{'input_tokens':100,'output_tokens':10}}
            if self.calls==2:
                assert kw['tools'], 'A technical request must still be able to read a section after the outline'
                return {'tool_calls':[ActionCall(tool_name='read_section',arguments={'section_id':'s'})], 'usage':{'input_tokens':100,'output_tokens':10}}
            assert any(m['role']=='tool' for m in kw['messages'])
            assert 'Self-attention' in str(kw['messages'])
            return {'answer_blocks':[AnswerBlock(text='Self-attention replaces recurrence.',evidence_ids=['p1'])],'usage':{'input_tokens':100,'output_tokens':10}}
    g=Gateway();result=await run_bounded_agent('r',paper,'owner','Explain the algorithm in this paper',gateway=g)
    assert g.calls==3 and result.status.value=='completed'


@pytest.mark.asyncio
async def test_native_tool_preface_does_not_discard_valid_calls(monkeypatch):
    import httpx
    from backend.app.providers.llm_gateway import LLMGateway
    real=httpx.AsyncClient
    def respond(request):
        return httpx.Response(200,json={'choices':[{'finish_reason':'tool_calls','message':{
            'content':'I will read the method section first.',
            'tool_calls':[{'id':'read','type':'function','function':{'name':'read_section','arguments':'{"section_id":"s"}'}}]}}], 'usage':{'prompt_tokens':100,'completion_tokens':20}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(respond),**kwargs))
    result=await LLMGateway(api_key='test').generate_step('ag/claude-sonnet-4-6',[{'role':'user','content':'Explain the algorithm'}],tools=[{'type':'function','function':{'name':'read_section'}}],mock=False)
    assert result['tool_calls'][0].tool_name=='read_section'
    assert result['answer_blocks']==[]


@pytest.mark.asyncio
async def test_gateway_reason_metadata_does_not_break_section_reading(paper):
    from backend.app.agent.tools import PaperAgentTools
    tools=PaperAgentTools(paper,'owner')
    outline=await tools.execute_tool('get_paper_outline',{'reason':'Find the exact method section'})
    assert 'Method' in outline.content
    section=await tools.execute_tool('read_section',{'section_id':'s','reason':'Read the method'})
    assert 'Self-attention' in section.content
    bad=await tools.execute_tool('read_section',{'section_id':'s','extra':'unrecognized operation control'})
    assert 'invalid tool arguments' in bad.content


@pytest.mark.asyncio
async def test_image_final_answer_reserves_pixels_before_compacting_sources(paper, monkeypatch):
    from backend.app.agent.controller import run_bounded_agent
    from backend.app.agent.schemas import Observation, ImageInput
    from backend.app.core.schemas import EvidenceItem,SourceLocation
    from backend.app.core.config import get_settings
    from backend.app.agent.tools import PaperAgentTools
    monkeypatch.setattr(get_settings().limits,'max_input_tokens',24000)
    ev=EvidenceItem(passage_id='p1',parent_passage_id='p1',text='Self-attention mathematical explanation. '*600,rank=1,score=1,section_path='Method',section_heading='Method',locator=SourceLocation(element_id='p1'))
    async def tool(self,*args,**kwargs):return Observation(tool_name='search_evidence',content=ev.text,raw_evidence=[ev])
    monkeypatch.setattr(PaperAgentTools,'execute_tool',tool)
    router=ModelRouter();router.record_success(4000,200)
    class Gateway:
        calls=0
        async def generate_step(self,**kwargs):
            self.calls+=1
            assert any(isinstance(m.get('content'),list) for m in kwargs['messages'])
            assert 'Self-attention mathematical explanation.' in str(kwargs['messages'])
            return {'answer_blocks':[AnswerBlock(text='The figure illustrates self-attention.',evidence_ids=['img_1'])],'usage':{'input_tokens':1000,'output_tokens':40}}
    gateway=Gateway()
    result=await run_bounded_agent('r',paper,'owner','Explain this image',router=router,gateway=gateway,max_steps=1,images=[ImageInput(data_url=PNG)])
    assert gateway.calls==1 and result.answer_blocks, result.limitations


def test_500k_chat_budget_and_old_turn_recall(paper):
    import json
    from backend.app.core.config import CHAT_TOKEN_LIMIT
    from backend.app.agent.runs import conversation_history
    assert CHAT_TOKEN_LIMIT == 500000
    conn=get_connection()
    conn.execute("INSERT INTO conversations(chat_id,owner_id,paper_id) VALUES ('long','owner',?)",(paper,))
    for i in range(14):
        q='Remember Orion calibration alpha=0.375' if i==0 else f'Unrelated experiment number {i}'
        answer='Orion calibration alpha is 0.375.' if i==0 else f'Experiment {i} discussion.'
        conn.execute("INSERT INTO runs(run_id,owner_id,paper_id,request_id,request_fingerprint,status,created_at,updated_at,deadline,chat_id,question,answer_blocks) VALUES (?,?,?,?,'fp','completed',?,?,?,'long',?,?)",(f'memory{i}','owner',paper,f'memory{i}',f'2026-11-20T00:{i:02}:00', 'now','later',q,json.dumps([{'text':answer,'evidence_ids':[]}])) )
    conn.commit()
    history=conversation_history('long','owner','What was the Orion calibration alpha?')
    assert any('0.375' in m['content'] for m in history)
    assert any('number 13' in m['content'] for m in history)
    assert conversation_history('long','other-owner','Orion') == []


def test_latex_response_json_preserves_unescaped_tex_commands():
    from backend.app.providers.llm_gateway import parse_response_content
    raw = r'{"answer_blocks":[{"text":"Use \(\alpha_i=\frac{a}{b}+\beta\) and $$\theta=\sum_i x_i$$.","evidence_ids":["p1"]}],"follow_ups":[]}'
    parsed=parse_response_content(raw)
    assert r'\frac{a}{b}' in parsed['answer_blocks'][0].text
    assert r'\beta' in parsed['answer_blocks'][0].text


def test_latex_json_repair_keeps_valid_escaping_and_plain_newlines():
    import json
    from backend.app.providers.llm_gateway import parse_response_content
    text = 'Explanation\n\n' + r'\[\begin{aligned}a&=\frac{1}{2}\\b&=\beta_i\end{aligned}\]'
    result=parse_response_content(json.dumps({'answer_blocks':[{'text':text,'evidence_ids':['p1']}]}))
    assert result['answer_blocks'][0].text == text


def test_existing_chat_upgrade_keeps_usage_and_reopens_old_50k_exhaustion(paper):
    from backend.app.core.db import init_db
    conn=get_connection()
    conn.execute("INSERT INTO conversations(chat_id,owner_id,paper_id,tokens_used,exhausted,token_limit) VALUES ('upgrade','owner',?,33934,1,50000)",(paper,));conn.commit()
    init_db()
    state=get_chat_state('upgrade','owner')
    assert state['tokens_used']==33934 and state['token_limit']==500000 and not state['chat_exhausted']


def test_fenced_response_with_prose_inner_quotes_and_double_escaped_math():
    from backend.app.providers.llm_gateway import parse_response_content
    raw = r'''Here is the analysis.
```json
{"answer_blocks":[{"text":"Example \\(x_i\\) with the query "find the tables".\\n\\nUse \\[x_i=\\frac{a}{b}\\].","evidence_ids":["p1"]}],"follow_ups":["How can we test this?","Which assumption matters?"],"limitations":null}
```'''
    result=parse_response_content(raw)
    assert '"find the tables"' in result['answer_blocks'][0].text
    assert '\n\n' in result['answer_blocks'][0].text
    assert len(result['follow_ups'])==2
    assert 'follow_ups' not in result['answer_blocks'][0].text


@pytest.mark.parametrize('bad_quote', [False, True])
def test_display_math_newlines_do_not_become_spurious_tex_commands(bad_quote):
    import json
    from backend.app.providers.llm_gateway import parse_response_content
    text = 'Definition\n\n' + r'\[' + '\nr_{t+1} = ' + r'\alpha P^\top r_t' + '\n' + r'\]'
    raw = json.dumps({'answer_blocks':[{'text':text, 'evidence_ids':['p1']}]})
    if bad_quote:
        raw = raw.replace('Definition', 'Use the query "find tables". Definition')
    result = parse_response_content(raw)['answer_blocks'][0].text
    assert '\nr_{t+1}' in result and r'\nr_' not in result
    assert r'\alpha P^\top' in result


@pytest.mark.asyncio
async def test_product_directory_leaves_planning_steps_for_actual_sections(paper):
    from backend.app.agent.controller import run_bounded_agent
    from backend.app.agent.schemas import ActionCall
    class Gateway:
        calls = 0
        async def generate_step(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                assert '# Paper Outline:' in str(kwargs['messages'])
                return {'tool_calls':[ActionCall(tool_name='read_section',arguments={'section_id':'s'})],
                        'usage':{'input_tokens':100,'output_tokens':20}}
            return {'answer_blocks':[AnswerBlock(text='Self-attention replaces recurrence.',evidence_ids=['p1'])],
                    'usage':{'input_tokens':100,'output_tokens':20}}
    gateway = Gateway()
    result = await run_bounded_agent('r',paper,'owner','Explain the retrieval algorithm in detail',
                                     gateway=gateway,paper_query='self attention',max_steps=2)
    assert gateway.calls == 2 and result.answer_blocks
