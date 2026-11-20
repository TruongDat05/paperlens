"""Two live requests through the product ASGI API, using an existing disposable paper DB."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import secrets
import time

import httpx


async def main():
    from backend.app.core.db import get_connection, init_db
    from backend.app.main import app
    from backend.app.agent.runs import _active_run_tasks
    from backend.app.core.config import get_settings
    settings=get_settings()
    if settings.mock_providers:
        raise RuntimeError('Live verification requires MOCK_PROVIDERS=false')
    if not os.environ.get('PAPERLENS_DISPOSABLE_DB') or settings.db_path != os.environ['PAPERLENS_DISPOSABLE_DB']:
        raise RuntimeError('Set DB_PATH and PAPERLENS_DISPOSABLE_DB to the same disposable database.')
    init_db();c=get_connection()
    paper=c.execute('SELECT paper_id,owner_id FROM papers WHERE lexical_ready=1 ORDER BY created_at DESC LIMIT 1').fetchone()
    if not paper:
        raise RuntimeError('Ingest the test paper in the disposable database first.')
    owner=paper['owner_id'];token=secrets.token_urlsafe(32)
    c.execute('INSERT INTO sessions VALUES (?,?)',(hashlib.sha256(token.encode()).hexdigest(),owner));c.commit()
    report={'kind':'Live ASGI product API: automatic memory across new chats','turns':[],'checks':{}}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'Authorization':'Bearer '+token}) as client:
        async def ask(question):
            started=time.monotonic()
            r=await client.post('/api/v1/agent/runs',json={'request_id':secrets.token_hex(16),'paper_id':paper['paper_id'],
                'question':question,'level':'low'})
            r.raise_for_status();run_id=r.json()['run_id']
            await _active_run_tasks[(owner,run_id)]
            result=(await client.get('/api/v1/agent/runs/'+run_id)).json()
            result['question']=question;result['seconds']=round(time.monotonic()-started,3);report['turns'].append(result)
            print(json.dumps({'status':result['status'],'seconds':result['seconds'],'blocks':len(result.get('answer_blocks') or [])}),flush=True)
            assert result.get('answer_blocks'),result.get('error_message') or result.get('limitations')
            return result
        try:
            first=await ask('Trong thí nghiệm giả định Orion của tôi, tôi chọn alpha=0.375. Hãy ghi nhớ thiết lập nghiên cứu riêng này cho các session sau. Giải thích ngắn gọn nó liên hệ với damping factor trong Personalized PageRank của paper như thế nào, và phân biệt thiết lập của tôi với kết quả bài báo.')
            report['memories']=(await client.get('/api/v1/account/memories')).json()
            assert any(m['kind']=='user_context' and '0.375' in m['text'] for m in report['memories']), 'The explicit setting was not automatically remembered'
            report['checks']['automaticGroundedMemory']=True
            second=await ask('Trong session trước tôi đã chọn alpha bằng bao nhiêu cho thí nghiệm Orion? Phân biệt rõ thiết lập riêng của tôi với giá trị được paper báo cáo.')
            assert first['chat_id'] != second['chat_id']
            assert '0.375' in ' '.join(b['text'] for b in second['answer_blocks'])
            assert any(e['passage_id'].startswith('mem_') and '0.375' in e['text'] for e in second['evidence'])
            assert any(eid.startswith('mem_') for b in second['answer_blocks'] for eid in b['evidence_ids'])
            report['checks']['newSessionRecallsCitableMemory']=True
            chats=(await client.get('/api/v1/account/chats')).json()
            assert {first['chat_id'],second['chat_id']} <= {chat['chat_id'] for chat in chats}
            report['checks']['durableChatHistory']=True;report['ok']=True
        except Exception as error:
            report['ok']=False;report['failure']=str(error)
        Path('reports/memory_live_20261120.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'ok':report['ok'],'checks':report['checks'],'failure':report.get('failure')}),flush=True)
        if not report['ok']:
            raise SystemExit(1)


if __name__=='__main__':
    asyncio.run(main())
