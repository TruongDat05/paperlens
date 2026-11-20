"""Provider-bound OAuth, PKCE, single-use tickets, token rotation and guest history."""
import hashlib
import json
from urllib.parse import urlparse,parse_qs
import httpx
import pytest

from backend.app.main import app
from backend.app.core.config import get_settings
from backend.app.core.db import get_connection
from backend.app.routes.auth import digest

ORIGIN='chrome-extension://'+'a'*32
REDIRECT='https://'+'a'*32+'.chromiumapp.org/oauth'


@pytest.mark.asyncio
@pytest.mark.parametrize('provider',['google','github'])
async def test_oauth_requires_provider_identity_and_browser_ticket_before_rotating_session(provider,monkeypatch):
    settings=get_settings()
    monkeypatch.setattr(settings,provider+'_client_id','client')
    monkeypatch.setattr(settings,provider+'_client_secret','secret')
    real_client=httpx.AsyncClient
    requests=[]
    def provider_api(request):
        requests.append(request)
        if request.method=='POST':
            assert b'code_verifier=' in request.content
            return httpx.Response(200,json={'access_token':'upstream-only'})
        assert request.headers['authorization']=='Bearer upstream-only'
        return httpx.Response(200,json={'sub':'stable-google','id':17,'name':'Researcher Linh','login':'linh'})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(provider_api),**kw))
    async with real_client(transport=httpx.ASGITransport(app=app),base_url='http://test',follow_redirects=False) as c:
        token=(await c.post('/api/v1/session')).json()['token']
        headers={'Authorization':'Bearer '+token,'Origin':ORIGIN}
        owner=(await c.get('/api/v1/session',headers=headers)).json()['user_id']
        assert (await c.post(f'/api/v1/auth/{provider}/start',headers=headers,json={'redirect_uri':'https://attacker.test'})).status_code==400
        started=(await c.post(f'/api/v1/auth/{provider}/start',headers=headers,json={'redirect_uri':REDIRECT})).json()
        params=parse_qs(urlparse(started['authorization_url']).query)
        assert params['code_challenge_method']==['S256'] and len(params['code_challenge'][0])==43
        assert (await c.get(f'/api/v1/auth/{provider}/callback?state=wrong&code=x')).status_code==400
        callback=await c.get(f'/api/v1/auth/{provider}/callback',params={'state':started['state'],'code':'provider-code'})
        assert callback.status_code==307 and callback.headers['location'].startswith(REDIRECT)
        ticket=parse_qs(urlparse(callback.headers['location']).query)['ticket'][0]
        assert 'upstream-only' not in callback.headers['location']
        assert not get_connection().execute('SELECT 1 FROM identities').fetchone(), 'A callback alone must not upgrade a known guest bearer'
        assert (await c.get(f'/api/v1/auth/{provider}/callback',params={'state':started['state'],'code':'again'})).status_code==400
        stranger=(await c.post('/api/v1/session')).json()['token']
        assert (await c.post('/api/v1/auth/complete',headers={'Authorization':'Bearer '+stranger},json={'ticket':ticket})).status_code==400
        result=(await c.post('/api/v1/auth/complete',headers=headers,json={'ticket':ticket})).json()
        assert result['token']!=token and result['owner_id']==owner
        assert get_connection().execute('SELECT 1 FROM sessions WHERE token_hash=?',(digest(token),)).fetchone() is None
        account=(await c.get('/api/v1/account',headers={'Authorization':'Bearer '+result['token']})).json()
        assert account['name']=='Researcher Linh' and account['identities'][0]['provider']==provider
        assert (await c.post('/api/v1/auth/complete',headers={'Authorization':'Bearer '+result['token']},json={'ticket':ticket})).status_code==400
        second_headers={'Authorization':'Bearer '+stranger,'Origin':ORIGIN}
        second=(await c.post(f'/api/v1/auth/{provider}/start',headers=second_headers,json={'redirect_uri':REDIRECT})).json()
        redirected=await c.get(f'/api/v1/auth/{provider}/callback',params={'state':second['state'],'code':'second-device-code'})
        second_ticket=parse_qs(urlparse(redirected.headers['location']).query)['ticket'][0]
        linked=(await c.post('/api/v1/auth/complete',headers=second_headers,json={'ticket':second_ticket})).json()
        assert linked['owner_id']==owner, 'The provider subject, not a device or display name, identifies the account'
        signed_out=(await c.post('/api/v1/auth/logout',headers={'Authorization':'Bearer '+linked['token']})).json()
        assert signed_out['owner_id']!=owner
        assert (await c.get('/api/v1/account',headers={'Authorization':'Bearer '+signed_out['token']})).json()['name']==''
        assert (await c.get('/api/v1/account',headers={'Authorization':'Bearer '+result['token']})).json()['name']=='Researcher Linh'
        assert len(requests)==4


@pytest.mark.asyncio
async def test_unconfigured_provider_never_fakes_a_login():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as c:
        assert (await c.get('/api/v1/account',headers={'Authorization':'Bearer owner'})).json()['auth_providers']=={'google':False,'github':False}
        assert (await c.post('/api/v1/auth/google/start',headers={'Authorization':'Bearer owner','Origin':ORIGIN},json={'redirect_uri':REDIRECT})).status_code==503


def test_guest_merge_keeps_existing_account_and_coalesces_duplicate_papers():
    from backend.app.routes.auth import merge_guest
    from backend.app.core.schemas import PaperIngestRequest
    from backend.app.cache.paper_store import store_paper_and_chunks
    from backend.app.retrieval.chunking import chunk_paper
    req=PaperIngestRequest(title='Memory paper',arxiv_id='2504.01346',canonical_url='https://arxiv.org/html/2504.01346v4',version='v4',
        sections=[dict(id='s',heading='Method',path='Method',order=0)],paragraphs=[dict(id='p',section_id='s',section_path='Method',order=0,text='A sufficient source paragraph for research memory.')])
    for owner in ('guest','account'):
        store_paper_and_chunks(owner+'paper',owner,req,'same-content',chunk_paper(req.paragraphs,paper_id=owner+'paper'))
    c=get_connection()
    c.execute("INSERT INTO conversations(chat_id,owner_id,paper_id,tokens_used) VALUES ('old-chat','guest','guestpaper',1234)")
    c.execute("INSERT INTO identities VALUES ('google','stable','account','Existing researcher')")
    c.commit()
    with c: merge_guest(c,'guest','account')
    row=c.execute("SELECT * FROM conversations WHERE chat_id='old-chat'").fetchone()
    assert row['owner_id']=='account' and row['paper_id']=='accountpaper' and row['tokens_used']==1234
    assert c.execute("SELECT COUNT(*) FROM papers WHERE owner_id='account'").fetchone()[0]==1
    with c: merge_guest(c,'account','different-account')
    assert c.execute("SELECT owner_id FROM conversations WHERE chat_id='old-chat'").fetchone()[0]=='account'
