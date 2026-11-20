"""Research profiles and memory/history remain private across session changes."""
import json
import httpx
import pytest

from backend.app.main import app
from backend.app.core.db import get_connection
from backend.app.agent.schemas import AgentRunRequest, AnswerBlock, MemoryCandidate
from backend.app.agent.runs import create_or_get_run, _active_run_tasks, get_run
from backend.app.providers.llm_gateway import LLMGateway
from backend.app.user_state import profile, personal_evidence, update_profile, ProfileInput
from backend.tests.test_confirmed_regressions import paper


@pytest.mark.parametrize('question,expected',[
    ('Hãy ghi nhớ thiết lập Orion alpha=0.375 cho nghiên cứu của tôi.',True),
    ('Please remember that my Orion pilot uses alpha=0.375.',True),
    ('Do you remember my Orion setting from last time?',False),
    ("Do not remember this hypothetical Orion setting.",False),
    ('Đừng ghi nhớ thông tin nghiên cứu này.',False),
])
def test_explicit_research_memory_keeps_user_words_even_when_provider_omits_metadata(paper,question,expected):
    from backend.app.user_state import remember_result,list_memories
    from backend.app.agent.schemas import AgentResult,RunState
    req=AgentRunRequest(request_id='q',paper_id=paper,question=question)
    result=AgentResult(run_id='r',paper_id=paper,status=RunState.COMPLETED,serving_model='test')
    # No source run is needed for this unit: persist the valid fixture run first.
    c=get_connection();c.execute("INSERT INTO runs(run_id,owner_id,paper_id,request_id,request_fingerprint,status,created_at,updated_at,deadline) VALUES ('r','owner',?,'q','x','completed','now','now','later')",(paper,));c.commit()
    remember_result('owner',req,result)
    memories=list_memories('owner')
    assert bool(memories)==expected
    if expected:assert memories[0]['text']==question


def test_recent_user_context_is_not_displaced_by_newer_paper_notes(paper):
    from backend.app.user_state import save_memory
    save_memory('owner','My long-term research goal is efficient table reasoning.')
    for i in range(3):
        save_memory('owner',f'Paper observation number {i} about a different topic.',kind='paper_knowledge',paper_id=paper)
    sources=personal_evidence('owner','Can we discuss my research direction?')
    assert any('efficient table reasoning' in source.text for source in sources)


@pytest.mark.asyncio
async def test_profile_memory_api_validation_and_owner_isolation():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        owner={'Authorization':'Bearer owner'}; other={'Authorization':'Bearer other'}
        assert (await c.get('/api/v1/account',headers=owner)).json()['onboarded'] is False
        value=dict(name='Linh',research_area='Graph retrieval',nationality='Vietnamese',memory_enabled=True)
        assert (await c.put('/api/v1/account/profile',headers=owner,json=value)).json()['onboarded']
        assert (await c.get('/api/v1/account',headers=other)).json()['name']==''
        assert (await c.put('/api/v1/account/profile',headers=owner,json={**value,'nationality':' '})).status_code==422
        note='Our Orion pilot uses alpha=0.375.'
        memory=(await c.post('/api/v1/account/memories',headers=owner,json={'text':note})).json()['memory_id']
        assert (await c.get('/api/v1/account/memories',headers=other)).json()==[]
        assert (await c.delete('/api/v1/account/memories/'+memory,headers=other)).status_code==404
        assert (await c.put('/api/v1/account/memories/'+memory,headers=owner,json={'text':' '*20})).status_code==422
        assert (await c.put('/api/v1/account/memories/'+memory,headers=owner,json={'text':'Our Orion pilot now uses alpha=0.5.'})).status_code==200
        assert (await c.get('/api/v1/account/memories',headers=owner)).json()[0]['text'].endswith('0.5.')
        assert (await c.delete('/api/v1/account/memories/'+memory,headers=owner)).status_code==200


@pytest.mark.asyncio
async def test_grounded_memory_survives_new_chat_without_leaking_other_sessions(paper,monkeypatch):
    update_profile('owner',ProfileInput(name='Linh',research_area='RAG',nationality='Vietnamese'))
    question='For our Orion pilot, set the damping factor alpha=0.375.'
    calls=[]
    async def generate(self,**kw):
        calls.append(kw)
        if 'You classify requests' in str(kw['messages'][0]):
            return {'research_plan':{'scope':'paper','paper_query':'self attention','language':'en'},'usage':{'input_tokens':100,'output_tokens':20}}
        if question in str(kw['messages']) and 'mem_' not in str(kw['messages']):
            return {'answer_blocks':[AnswerBlock(text='Your pilot setting is user context; the paper uses self-attention.',evidence_ids=['p1'])],
                'memory_candidates':[
                    MemoryCandidate(kind='user_context',quote=question),
                    MemoryCandidate(kind='paper_knowledge',quote='Self-attention replaces recurrence.',evidence_id='p1'),
                    MemoryCandidate(kind='paper_knowledge',quote='The paper achieves an invented score of 99.9.',evidence_id='p1')],
                'usage':{'input_tokens':100,'output_tokens':40}}
        transcript=str(kw['messages'])
        assert 'mem_' in transcript and 'alpha=0.375' in transcript
        assert 'Long-term research memory' in transcript
        return {'answer_blocks':[AnswerBlock(text='Your earlier Orion pilot uses 0.375, independently of the paper.',evidence_ids=['p1'])],
                'usage':{'input_tokens':100,'output_tokens':40}}
    monkeypatch.setattr(LLMGateway,'generate_step',generate)
    first,_,_=await create_or_get_run(AgentRunRequest(request_id='remember',paper_id=paper,question=question),'owner')
    await _active_run_tasks[('owner',first.run_id)]
    assert get_run(first.run_id,'owner').answer_blocks
    memories=get_connection().execute('SELECT * FROM memories WHERE owner_id=?',('owner',)).fetchall()
    assert len(memories)==2 and all('99.9' not in row['text'] for row in memories)
    second,_,_=await create_or_get_run(AgentRunRequest(request_id='recall',paper_id=paper,question='How does my Orion pilot relate to this method?'),'owner')
    await _active_run_tasks[('owner',second.run_id)]
    assert get_run(second.run_id,'owner').chat_id != get_run(first.run_id,'owner').chat_id
    assert len(calls)==4, 'Remembering must reuse generation rather than add another provider call'
    assert personal_evidence('other','Orion')==[]
    update_profile('owner',ProfileInput(name='Linh',research_area='RAG',nationality='Vietnamese',memory_enabled=False))
    assert all(not ev.passage_id.startswith('mem_') for ev in personal_evidence('owner','Orion'))


@pytest.mark.asyncio
async def test_history_restores_old_chats_and_images_and_deletes_only_owned_chat(paper):
    c=get_connection()
    for i in range(2):
        c.execute('INSERT INTO conversations(chat_id,owner_id,paper_id) VALUES (?,?,?)',(f'chat{i}','owner',paper))
        c.execute('''INSERT INTO runs(run_id,owner_id,paper_id,request_id,request_fingerprint,status,created_at,
                     updated_at,deadline,chat_id,question,answer_blocks,images) VALUES (?,?,?,?,'x','completed',?,?,?,?,?,?,?)''',
                  (f'run{i}','owner',paper,f'q{i}',f'2026-11-20T00:00:0{i}+00:00',f'2026-11-20T00:00:0{i}+00:00','later',f'chat{i}',
                   f'Explain Orion step {i}',json.dumps([dict(text='A saved answer.',evidence_ids=['p1'])]),json.dumps([dict(name='chart.png',data_url='data:image/png;base64,AAA')]) ))
    c.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        owner={'Authorization':'Bearer owner'};other={'Authorization':'Bearer other'}
        result=(await client.get('/api/v1/account/chats',headers=owner)).json()
        assert [chat['chat_id'] for chat in result]==['chat1','chat0']
        assert (await client.get('/api/v1/account/chats',headers=other)).json()==[]
        assert (await client.get('/api/v1/account/chats/chat0',headers=other)).status_code==404
        restored=(await client.get('/api/v1/account/chats/chat0',headers=owner)).json()
        assert restored['messages'][0]['attachments'][0]['name']=='chart.png'
        assert restored['messages'][1]['answerBlocks'][0]['text']=='A saved answer.'
        assert (await client.delete('/api/v1/account/chats/chat0',headers=other)).status_code==404
        assert (await client.delete('/api/v1/account/chats/chat0',headers=owner)).status_code==200
        assert len((await client.get('/api/v1/account/chats',headers=owner)).json())==1
