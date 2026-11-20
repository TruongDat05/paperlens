"""OAuth code + PKCE. Tokens stay server-side; the extension receives a one-use ticket."""
import base64
import hashlib
import json
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from backend.app.core.config import get_settings
from backend.app.core.db import transaction
from backend.app.core.security import get_current_user

router = APIRouter(prefix='/auth',tags=['auth'])
PROVIDERS = {
    'google':('https://accounts.google.com/o/oauth2/v2/auth','https://oauth2.googleapis.com/token',
              'https://openidconnect.googleapis.com/v1/userinfo','openid profile'),
    'github':('https://github.com/login/oauth/authorize','https://github.com/login/oauth/access_token',
              'https://api.github.com/user','read:user'),
}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def bearer(request):
    value = request.headers.get('authorization','')
    if not value.lower().startswith('bearer '):
        raise HTTPException(401,'Sign-in requires an existing session.')
    return value[7:].strip()


def credentials(provider):
    if provider not in PROVIDERS:
        raise HTTPException(404,'Unknown sign-in provider')
    settings = get_settings()
    client,secret = getattr(settings,provider+'_client_id'),getattr(settings,provider+'_client_secret')
    if not client or not secret:
        raise HTTPException(503,'This sign-in provider has not been configured by the service owner.')
    base=urlsplit(settings.auth_public_base_url)
    if not base.hostname or base.username or base.password or base.query or base.fragment or (
        base.scheme!='https' and not (base.scheme=='http' and base.hostname in ('localhost','127.0.0.1','::1'))):
        raise HTTPException(503,'Configure a secure public callback URL or a localhost development URL.')
    callback = settings.auth_public_base_url.rstrip('/')+'/api/v1/auth/'+provider+'/callback'
    return client,secret,callback


class StartInput(BaseModel):
    redirect_uri: str = Field(max_length=200)


@router.post('/{provider}/start')
def start(provider: str, value: StartInput, request: Request, owner: str = Depends(get_current_user)):
    client,_,callback = credentials(provider)
    match = re.fullmatch(r'https://([a-p]{32})\.chromiumapp\.org/oauth',value.redirect_uri)
    if not match or request.headers.get('origin') != 'chrome-extension://'+match[1]:
        raise HTTPException(400,'The sign-in redirect must belong to the requesting extension.')
    state,verifier = secrets.token_urlsafe(32),secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    with transaction() as c:
        token_hash = digest(bearer(request))
        if not c.execute('SELECT 1 FROM sessions WHERE token_hash=? AND owner_id=?',(token_hash,owner)).fetchone():
            raise HTTPException(401,'Create a registered session before signing in.')
        c.execute('DELETE FROM oauth_states WHERE expires_at<?',(time.time(),))
        c.execute('INSERT INTO oauth_states(state_hash,owner_id,session_hash,provider,redirect_uri,verifier,expires_at) VALUES (?,?,?,?,?,?,?)',
                  (digest(state),owner,token_hash,provider,value.redirect_uri,verifier,time.time()+600))
    url = PROVIDERS[provider][0]+'?'+urlencode(dict(client_id=client,redirect_uri=callback,response_type='code',
        scope=PROVIDERS[provider][3],state=state,code_challenge=challenge,code_challenge_method='S256'))
    return dict(authorization_url=url,state=state)


@router.get('/{provider}/callback')
async def callback(provider: str, state: str='', code: str='', error: str=''):
    client,secret,callback_url = credentials(provider)
    with transaction() as c:
        row = c.execute('SELECT * FROM oauth_states WHERE state_hash=? AND provider=? AND expires_at>?',
                        (digest(state),provider,time.time())).fetchone()
        if not row or not row['verifier']:
            raise HTTPException(400,'Sign-in expired or was already used. Please try again.')
        # Claim before contacting the provider so callbacks cannot race/replay.
        if not c.execute("UPDATE oauth_states SET verifier='' WHERE state_hash=? AND verifier!=''",(digest(state),)).rowcount:
            raise HTTPException(400,'Sign-in was already used.')
    if error or not code:
        return RedirectResponse(row['redirect_uri']+'?'+urlencode(dict(state=state,error='cancelled')))
    try:
        async with httpx.AsyncClient(timeout=20) as client_http:
            token_response = await client_http.post(PROVIDERS[provider][1],data=dict(client_id=client,client_secret=secret,
                code=code,redirect_uri=callback_url,grant_type='authorization_code',code_verifier=row['verifier']),
                headers={'Accept':'application/json'})
            token_response.raise_for_status()
            access_token = token_response.json()['access_token']
            response = await client_http.get(PROVIDERS[provider][2],headers={
                'Authorization':'Bearer '+access_token,'Accept':'application/json'})
            response.raise_for_status()
            user = response.json()
        subject_value = user['sub'] if provider == 'google' else user['id']
        if not isinstance(subject_value,(str,int)) or isinstance(subject_value,bool) or not subject_value:
            raise ValueError('Missing provider identity')
        subject = str(subject_value).strip()
        name = str(user.get('name') or user.get('login') or '')[:100]
        if not subject or not name:
            raise ValueError('Missing provider identity')
    except (httpx.HTTPError,KeyError,ValueError,TypeError):
        return RedirectResponse(row['redirect_uri']+'?'+urlencode(dict(state=state,error='provider_failed')))
    ticket = secrets.token_urlsafe(32)
    with transaction() as c:
        c.execute('UPDATE oauth_states SET ticket_hash=?,identity_json=?,expires_at=? WHERE state_hash=?',
                  (digest(ticket),json.dumps(dict(subject=subject,name=name)),time.time()+120,digest(state)))
    # Do not authenticate the initiating bearer until its browser receives this ticket.
    return RedirectResponse(row['redirect_uri']+'?'+urlencode(dict(state=state,ticket=ticket)),headers={'Cache-Control':'no-store'})


def merge_guest(c, guest, account):
    """Claim guest history on login, coalescing duplicate paper versions safely."""
    if guest == account:
        return
    if c.execute('SELECT 1 FROM identities WHERE owner_id=?',(guest,)).fetchone():
        return  # Account switching never merges two authenticated users' data.
    if c.execute("SELECT 1 FROM runs WHERE owner_id=? AND status IN ('queued','running')",(guest,)).fetchone():
        raise HTTPException(409,'Finish or stop the current answer before signing in.')
    for paper in c.execute('SELECT * FROM papers WHERE owner_id=?',(guest,)).fetchall():
        existing = c.execute('SELECT paper_id FROM papers WHERE owner_id=? AND arxiv_id=? AND version=? AND content_hash=?',
                             (account,paper['arxiv_id'],paper['version'],paper['content_hash'])).fetchone()
        if existing:
            for table in ('runs','conversations','memories'):
                c.execute(f'UPDATE {table} SET paper_id=? WHERE paper_id=? AND owner_id=?',(existing['paper_id'],paper['paper_id'],guest))
            c.execute('DELETE FROM papers WHERE paper_id=?',(paper['paper_id'],))
        else:
            c.execute('UPDATE papers SET owner_id=? WHERE paper_id=?',(account,paper['paper_id']))
            c.execute('UPDATE vectors SET owner_id=? WHERE paper_id=?',(account,paper['paper_id']))
    c.execute("UPDATE runs SET request_id='linked_'||run_id WHERE owner_id=? AND request_id IN (SELECT request_id FROM runs WHERE owner_id=?)",(guest,account))
    for table in ('runs','conversations','memories','usage_ledger'):
        c.execute(f'UPDATE {table} SET owner_id=? WHERE owner_id=?',(account,guest))
    for quota in c.execute('SELECT * FROM quotas WHERE owner_id=?',(guest,)).fetchall():
        c.execute('''INSERT INTO quotas VALUES (?,?,?,?,?) ON CONFLICT(owner_id,date) DO UPDATE SET
                     new_indexes=new_indexes+excluded.new_indexes,agent_turns=agent_turns+excluded.agent_turns,
                     semantic_retrievals=semantic_retrievals+excluded.semantic_retrievals''',
                  (account,quota['date'],quota['new_indexes'],quota['agent_turns'],quota['semantic_retrievals']))
    c.execute('DELETE FROM quotas WHERE owner_id=?',(guest,))
    if not c.execute('SELECT 1 FROM profiles WHERE owner_id=?',(account,)).fetchone():
        c.execute('UPDATE profiles SET owner_id=? WHERE owner_id=?',(account,guest))


class CompleteInput(BaseModel):
    ticket: str = Field(min_length=20,max_length=200)


@router.post('/complete')
def complete(value: CompleteInput, request: Request, owner: str = Depends(get_current_user)):
    old_hash,new_token = digest(bearer(request)),secrets.token_urlsafe(32)
    with transaction() as c:  # The shared transaction helper serializes identity lookup and claim.
        row = c.execute('SELECT * FROM oauth_states WHERE ticket_hash=? AND session_hash=? AND owner_id=? AND expires_at>?',
                        (digest(value.ticket),old_hash,owner,time.time())).fetchone()
        if not row or not row['identity_json']:
            raise HTTPException(400,'Invalid or expired sign-in ticket.')
        user = json.loads(row['identity_json'])
        identity = c.execute('SELECT owner_id FROM identities WHERE provider=? AND subject=?',(row['provider'],user['subject'])).fetchone()
        target = identity['owner_id'] if identity else owner
        merge_guest(c,owner,target)
        c.execute('INSERT INTO identities VALUES (?,?,?,?) ON CONFLICT(provider,subject) DO UPDATE SET display_name=excluded.display_name',
                  (row['provider'],user['subject'],target,user['name']))
        c.execute('INSERT INTO profiles(owner_id,name) VALUES (?,?) ON CONFLICT(owner_id) DO UPDATE SET name=CASE WHEN profiles.name=\'\' THEN excluded.name ELSE profiles.name END',
                  (target,user['name']))
        c.execute('DELETE FROM sessions WHERE token_hash=?',(old_hash,))
        c.execute('INSERT INTO sessions VALUES (?,?)',(digest(new_token),target))
        c.execute('DELETE FROM oauth_states WHERE state_hash=?',(row['state_hash'],))
    return dict(token=new_token,owner_id=target)


@router.post('/logout')
def logout(request: Request, owner: str = Depends(get_current_user)):
    token,anonymous = secrets.token_urlsafe(32),'anon_'+secrets.token_hex(16)
    with transaction() as c:
        c.execute('DELETE FROM sessions WHERE token_hash=?',(digest(bearer(request)),))
        c.execute('INSERT INTO sessions VALUES (?,?)',(digest(token),anonymous))
    return dict(token=token,owner_id=anonymous)
