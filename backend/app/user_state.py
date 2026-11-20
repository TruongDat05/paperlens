"""Owner-scoped profiles, durable research memory and conversation history."""
import hashlib
import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.app.core.db import get_connection, transaction
from backend.app.core.schemas import EvidenceItem, SourceLocation
from backend.app.retrieval.bm25 import LuceneBM25, tokenize_text


class ProfileInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    research_area: str = Field(min_length=1, max_length=500)
    nationality: str = Field(min_length=1, max_length=100)
    memory_enabled: bool = True


def profile(owner):
    row = get_connection().execute("SELECT * FROM profiles WHERE owner_id=?", (owner,)).fetchone()
    data = dict(row) if row else dict(owner_id=owner, name='', research_area='', nationality='', memory_enabled=1)
    data['memory_enabled'] = bool(data['memory_enabled'])
    data['onboarded'] = all(data[key].strip() for key in ('name', 'research_area', 'nationality'))
    data['identities'] = [dict(r) for r in get_connection().execute(
        "SELECT provider, display_name FROM identities WHERE owner_id=? ORDER BY provider", (owner,))]
    return data


def update_profile(owner, value):
    values = {k: v.strip() if isinstance(v, str) else v for k, v in value.model_dump().items()}
    if not all(values[k] for k in ('name', 'research_area', 'nationality')):
        raise HTTPException(422, 'Please complete your name, research area and nationality.')
    with transaction() as c:
        c.execute('''INSERT INTO profiles(owner_id,name,research_area,nationality,memory_enabled) VALUES (?,?,?,?,?)
                     ON CONFLICT(owner_id) DO UPDATE SET name=excluded.name,research_area=excluded.research_area,
                     nationality=excluded.nationality,memory_enabled=excluded.memory_enabled''',
                  (owner, values['name'], values['research_area'], values['nationality'], values['memory_enabled']))
    return profile(owner)


def list_memories(owner):
    return [dict(r) for r in get_connection().execute(
        "SELECT * FROM memories WHERE owner_id=? ORDER BY updated_at DESC, memory_id", (owner,))]


def save_memory(owner, text, kind='user_context', paper_id=None, run_id=None, label='User note', url=None):
    text = ' '.join(text.split())
    if not 12 <= len(text) <= 2000:
        raise HTTPException(422, 'Research memories must contain 12–2,000 characters.')
    now = datetime.now(timezone.utc).isoformat()
    key = 'mem_' + hashlib.sha256(f'{owner}:{kind}:{paper_id}:{text}'.encode()).hexdigest()[:24]
    with transaction() as c:
        if c.execute('SELECT COUNT(*) FROM memories WHERE owner_id=?', (owner,)).fetchone()[0] >= 500:
            raise HTTPException(409, 'Memory is full. Remove an older note before adding another.')
        c.execute('''INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?,?)
                     ON CONFLICT(memory_id) DO UPDATE SET updated_at=excluded.updated_at''',
                  (key, owner, kind, text, paper_id, run_id, label, url, now, now))
    return key


def remember_result(owner, req, result):
    """Store exact source quotations, never an unverified model paraphrase."""
    if not profile(owner)['memory_enabled'] or result.status.value not in ('completed', 'partial'):
        return
    negative = re.search(r"(?:do not|don't|never|không|đừng)\s+(?:\w+\s+){0,3}(?:remember|ghi nhớ|nhớ)|ne\s+mémorise\s+pas",req.question,re.I)
    if negative:
        return
    explicit = re.search(r'(?:please remember|hãy ghi nhớ|ghi nhớ (?:rằng|thiết lập|thông tin)|^remember (?:that|this|my)|mémorise (?:que|ce|mon))',req.question.strip(),re.I)
    remembered_user = False
    sources = {ev.passage_id: ev for ev in result.evidence}
    paper = get_connection().execute('SELECT title,canonical_url FROM papers WHERE paper_id=? AND owner_id=?',
                                     (req.paper_id, owner)).fetchone()
    for candidate in result.memory_candidates[:3]:
        quote = ' '.join(candidate.quote.split())
        text, paper_id, label, url = req.question, None, 'Earlier user-provided research context', None
        if candidate.kind == 'paper_knowledge':
            source = sources.get(candidate.evidence_id)
            if not source or source.paper_id != req.paper_id or not paper or source.passage_id.startswith(('mem_','profile_','chat_','img_')):
                continue
            text, paper_id, label, url = source.text, req.paper_id, paper['title'], paper['canonical_url']
        if quote not in ' '.join(text.split()):
            continue
        try:
            save_memory(owner, quote, candidate.kind, paper_id, result.run_id, label, url)
            remembered_user |= candidate.kind == 'user_context'
        except HTTPException:
            continue  # A full memory library must not discard an otherwise usable answer.
    # Explicit research-memory commands do not depend on the model reproducing
    # a quote perfectly. Keep the user's original request, never its paraphrase.
    if explicit and not remembered_user:
        try:
            save_memory(owner,req.question,run_id=result.run_id,label='Explicitly remembered user research request')
        except HTTPException:
            pass


def personal_evidence(owner, question):
    data = profile(owner)
    result = []
    if data['onboarded']:
        text = json.dumps({k: data[k] for k in ('name', 'research_area', 'nationality', 'memory_enabled')}, ensure_ascii=False)
        result.append(EvidenceItem(passage_id='profile_context', parent_passage_id='profile_context',
            text='User-provided research profile (do not infer language or beliefs from nationality): '+text,
            rank=1,score=1,section_heading='Research profile',section_path='User profile',locator=SourceLocation()))
    if not data['memory_enabled']:
        return result
    memories = list_memories(owner)
    if not memories:
        return result
    corpus = [tokenize_text(m['text']) for m in memories]
    scores = LuceneBM25(corpus).get_scores(tokenize_text(question)) if any(corpus) else [0]*len(memories)
    selected = {i for i in sorted(range(len(memories)), key=lambda i: scores[i], reverse=True)[:3] if scores[i] > 0}
    selected.update([i for i,m in enumerate(memories) if m['kind'] == 'user_context'][:2])
    for i in sorted(selected):
        memory = memories[i]
        result.append(EvidenceItem(passage_id=memory['memory_id'],parent_passage_id=memory['memory_id'],
            text=f"Recorded {memory['updated_at']}; {memory['kind']}. Source: {memory['source_label']}\n{memory['text']}",
            rank=len(result)+1,score=1,section_heading=memory['source_label'],section_path='Long-term research memory',
            locator=SourceLocation(xpath=memory['source_url']),paper_id=memory['paper_id']))
    return result


def conversations(owner, query=''):
    rows = get_connection().execute('''SELECT c.chat_id,c.paper_id,p.title AS paper_title,p.canonical_url,
        p.arxiv_id,p.version,MIN(r.created_at) AS created_at,MAX(r.updated_at) AS updated_at,
        COUNT(r.run_id) AS turns,
        (SELECT question FROM runs f WHERE f.chat_id=c.chat_id AND f.owner_id=c.owner_id
          AND question IS NOT NULL ORDER BY created_at LIMIT 1) AS title
        FROM conversations c JOIN papers p ON c.paper_id=p.paper_id
        JOIN runs r ON r.chat_id=c.chat_id AND r.owner_id=c.owner_id
        WHERE c.owner_id=? GROUP BY c.chat_id ORDER BY updated_at DESC''', (owner,)).fetchall()
    return [dict(r) for r in rows if query.casefold() in ((r['title'] or '')+' '+r['paper_title']).casefold()]


def conversation_detail(owner, chat_id):
    from backend.app.agent.runs import get_chat_state
    chat = get_chat_state(chat_id, owner)
    if not chat:
        raise HTTPException(404, 'Conversation not found')
    paper = get_connection().execute('''SELECT p.* FROM papers p JOIN conversations c ON c.paper_id=p.paper_id
        WHERE c.chat_id=? AND c.owner_id=?''', (chat_id, owner)).fetchone()
    rows = get_connection().execute('SELECT * FROM runs WHERE chat_id=? AND owner_id=? ORDER BY created_at',
                                    (chat_id, owner)).fetchall()
    messages = []
    for row in rows:
        if not row['question']:
            continue
        timestamp = int(datetime.fromisoformat(row['created_at']).timestamp()*1000)
        images = json.loads(row['images'] or '[]')
        messages.append(dict(id=row['run_id']+'_q',role='user',content=row['question'],timestamp=timestamp,
            attachments=[dict(id=f"{row['run_id']}_{i}",name=image['name'],dataUrl=image['data_url'],type='image',size=0)
                         for i,image in enumerate(images)]))
        messages.append(dict(id=row['run_id']+'_a',role='assistant',content='',timestamp=timestamp,
            status=row['status'],answerBlocks=json.loads(row['answer_blocks'] or '[]'),
            evidence=json.loads(row['evidence_ids'] or '[]'),followUps=json.loads(row['follow_ups'] or '[]'),
            servingModel=row['serving_model'],limitations=row['limitations'],error=row['error_message']))
    active = next((r['run_id'] for r in reversed(rows) if r['status'] in ('queued','running')),None)
    return dict(budget=chat,messages=messages,paper_id=paper['paper_id'],canonical_url=paper['canonical_url'],active_run_id=active)
