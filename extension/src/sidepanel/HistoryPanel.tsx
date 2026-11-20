import React,{useEffect,useState} from 'react';
import {ApiClient} from '../api/client';
import {ChatSummary,SavedConversation} from '../api/types';
import {ConversationView} from './ConversationView';

interface Props {client:ApiClient;ownerId:string;canonicalUrl?:string|null;onRestore:(chat:SavedConversation)=>void;onDeleted:(id:string)=>void;}

export function HistoryPanel({client,ownerId,canonicalUrl,onRestore,onDeleted}:Props) {
  const [chats,setChats] = useState<ChatSummary[]>([]);
  const [query,setQuery] = useState('');
  const [selected,setSelected] = useState<SavedConversation|null>(null);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState('');
  const [confirmDelete,setConfirmDelete] = useState<string|null>(null);
  const reload = async()=>setChats(await client.getChats());
  useEffect(()=>{reload().catch(e=>setError(e.message)).finally(()=>setLoading(false));},[client,ownerId]);
  const open = async(chat:ChatSummary)=>{
    setError('');setLoading(true);
    try {const saved=await client.getConversation(chat.chat_id);
      if(saved.canonical_url === canonicalUrl) onRestore(saved); else setSelected(saved);
    } catch(e){setError((e as Error).message);} finally{setLoading(false);}
  };
  const openPaper = async()=>{
    if(!selected)return;
    await chrome.storage.local.set({[`paperlens_chat_${ownerId}:${selected.canonical_url}`]:{
      messages:selected.messages,budget:selected.budget,history:[],updatedAt:Date.now(),
    }});
    await chrome.tabs.create({url:selected.canonical_url});
  };
  if(selected)return <section className="history-reader"><div className="page-toolbar">
    <button className="btn btn-ghost btn-sm" onClick={()=>setSelected(null)}>Back to history</button>
    <button className="btn btn-secondary btn-sm" onClick={()=>void openPaper()}>Open paper to continue</button></div>
    <ConversationView messages={selected.messages} evidence={[]} onFollowUp={()=>{}} exhausted
      onSelectEvidence={()=>{}} onJump={source=>{void chrome.tabs.create({url:selected.canonical_url+(source.locator.element_id ? '#'+encodeURIComponent(source.locator.element_id) : '')});}}
      onRetry={()=>{}} isBusy={false} activeStep={null}/></section>;
  const filtered=chats.filter(chat=>((chat.title||'')+' '+chat.paper_title).toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  return <section className="history-panel" aria-label="Chat history"><div className="settings-heading"><h2>Chat history</h2><p className="description">Return to a research session, including chats from other papers.</p></div>
    <label className="sr-only" htmlFor="chat-history-search">Search chat history</label>
    <input id="chat-history-search" className="text-input" type="search" placeholder="Search chats and papers…" value={query} onChange={e=>setQuery(e.target.value)}/>
    {loading && <p className="description" role="status">Loading chats…</p>}
    {error && <p className="alert alert-danger" role="alert">{error}</p>}
    {!loading && !filtered.length && <p className="empty-state-copy">{query ? 'No matching chats.' : 'Your research conversations will appear here.'}</p>}
    <ul className="chat-history-list">{filtered.map(chat=><li key={chat.chat_id} className="chat-history-item">
      <button className="chat-history-open" disabled={loading} onClick={()=>void open(chat)}><strong>{(chat.title||'Research chat').slice(0,100)}</strong>
        <span>{chat.paper_title}</span><small>{new Date(chat.updated_at).toLocaleDateString()} · {chat.turns} {chat.turns===1 ? 'turn' : 'turns'}</small></button>
      {confirmDelete === chat.chat_id ? <div className="history-delete-confirm"><p>Delete this chat? Long-term memories are kept separately.</p>
        <button className="btn btn-secondary btn-sm" onClick={()=>setConfirmDelete(null)}>Cancel</button>
        <button className="btn btn-secondary btn-sm danger-action" disabled={loading} onClick={()=>{
          setLoading(true);setError('');void client.deleteConversation(chat.chat_id).then(async()=>{onDeleted(chat.chat_id);setConfirmDelete(null);await reload();})
            .catch(e=>setError(e.message)).finally(()=>setLoading(false));}}>Delete chat</button></div>
        : <button type="button" className="text-action history-delete" aria-label={`Delete chat ${(chat.title||'').slice(0,60)}`} onClick={()=>setConfirmDelete(chat.chat_id)}>Delete</button>}
    </li>)}</ul>
  </section>;
}
