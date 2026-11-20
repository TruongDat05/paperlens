"""Profile, memory and history APIs; every query is bound to the caller."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone

from backend.app.core.security import get_current_user
from backend.app.core.db import get_connection, transaction
from backend.app.core.config import get_settings
from backend.app import user_state

router = APIRouter(prefix='/account', tags=['account'])


@router.get('')
def get_account(owner: str = Depends(get_current_user)):
    settings = get_settings()
    return {**user_state.profile(owner), 'auth_providers':{
        p: bool(getattr(settings,p+'_client_id') and getattr(settings,p+'_client_secret')) for p in ('google','github')}}


@router.put('/profile')
def update_profile(value: user_state.ProfileInput, owner: str = Depends(get_current_user)):
    user_state.update_profile(owner,value)
    return get_account(owner)


@router.get('/memories')
def memories(owner: str = Depends(get_current_user)):
    return user_state.list_memories(owner)


class MemoryInput(BaseModel):
    text: str = Field(min_length=12,max_length=2000)

    @field_validator('text')
    @classmethod
    def meaningful(cls, value):
        value=value.strip()
        if len(value)<12:
            raise ValueError('Write a research note of at least 12 characters.')
        return value


@router.post('/memories')
def add_memory(value: MemoryInput, owner: str = Depends(get_current_user)):
    return {'memory_id':user_state.save_memory(owner,value.text)}


@router.put('/memories/{memory_id}')
def edit_memory(memory_id: str, value: MemoryInput, owner: str = Depends(get_current_user)):
    with transaction() as c:
        changed = c.execute("UPDATE memories SET text=?,updated_at=?,kind='user_context',paper_id=NULL,source_run_id=NULL,source_label='User-edited note',source_url=NULL WHERE memory_id=? AND owner_id=?",
                            (value.text,datetime.now(timezone.utc).isoformat(),memory_id,owner)).rowcount
        if not changed:
            raise HTTPException(404,'Memory not found')
    return {'status':'saved'}


@router.delete('/memories/{memory_id}')
def forget_memory(memory_id: str, owner: str = Depends(get_current_user)):
    with transaction() as c:
        if not c.execute('DELETE FROM memories WHERE memory_id=? AND owner_id=?',(memory_id,owner)).rowcount:
            raise HTTPException(404,'Memory not found')
    return {'status':'deleted'}


@router.get('/chats')
def chats(q: str = Query('',max_length=200), owner: str = Depends(get_current_user)):
    return user_state.conversations(owner,q)


@router.get('/chats/{chat_id}')
def chat(chat_id: str, owner: str = Depends(get_current_user)):
    return user_state.conversation_detail(owner,chat_id)


@router.delete('/chats/{chat_id}')
def delete_chat(chat_id: str, owner: str = Depends(get_current_user)):
    with transaction() as c:
        if not c.execute('SELECT 1 FROM conversations WHERE chat_id=? AND owner_id=?',(chat_id,owner)).fetchone():
            raise HTTPException(404,'Conversation not found')
        if c.execute("SELECT 1 FROM runs WHERE chat_id=? AND status IN ('queued','running')",(chat_id,)).fetchone():
            raise HTTPException(409,'Stop the current answer before deleting this chat.')
        c.execute('DELETE FROM runs WHERE chat_id=? AND owner_id=?',(chat_id,owner))
        c.execute('DELETE FROM conversations WHERE chat_id=? AND owner_id=?',(chat_id,owner))
    return {'status':'deleted'}
