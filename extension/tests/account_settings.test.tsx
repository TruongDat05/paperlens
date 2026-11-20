/** @vitest-environment jsdom */
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {AccountPanel,claimLegacyStorage} from '../src/sidepanel/AccountPanel';
import {HistoryPanel} from '../src/sidepanel/HistoryPanel';
import {Composer} from '../src/sidepanel/Composer';
import {AccountProfile} from '../src/api/types';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
let el:HTMLDivElement,root:ReturnType<typeof createRoot>;
const account:AccountProfile={owner_id:'owner',name:'Linh',research_area:'RAG',nationality:'Vietnamese',memory_enabled:true,
  onboarded:true,identities:[],auth_providers:{google:false,github:false}};
beforeEach(()=>{el=document.createElement('div');document.body.append(el);root=createRoot(el);});
afterEach(async()=>{await act(async()=>root.unmount());el.remove();vi.unstubAllGlobals();});

it('shows only the context ring and warns near exhaustion',async()=>{
  await act(async()=>root.render(<Composer onSend={vi.fn()} onStop={vi.fn()} isBusy={false} tokensUsed={110900}/>));
  expect(el.textContent).not.toMatch(/110|500|tokens/);expect(el.querySelector('[role=meter]')).not.toBeNull();
  expect(el.querySelector('.context-notice')).toBeNull();
  await act(async()=>root.render(<Composer onSend={vi.fn()} onStop={vi.fn()} isBusy={false} tokensUsed={450000}/>));
  expect(el.querySelector('.context-notice')?.textContent).toContain('Context sắp hết');
  expect(el.querySelector('[role=meter]')?.getAttribute('aria-valuemax')).toBe('500000');
});

it('submits the research profile and exposes unavailable sign-in honestly',async()=>{
  const updateProfile=vi.fn().mockResolvedValue(account),onSaved=vi.fn(),getMemories=vi.fn();
  await act(async()=>root.render(<AccountPanel client={{updateProfile,getMemories} as any} account={account}
    onSaved={onSaved} refresh={vi.fn()} onboarding/>));
  expect(el.querySelectorAll('input[required]')).toHaveLength(2);
  expect(el.querySelector('textarea[required]')).not.toBeNull();
  expect([...el.querySelectorAll('button')].filter(b=>b.textContent?.startsWith('Continue with')).every(b=>b.disabled)).toBe(true);
  await act(async()=>el.querySelector('form')!.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
  expect(updateProfile).toHaveBeenCalledWith({name:'Linh',research_area:'RAG',nationality:'Vietnamese',memory_enabled:true});
  expect(onSaved).toHaveBeenCalledWith(account);expect(getMemories).not.toHaveBeenCalled();
});

it('forgets the selected long-term note without affecting other notes',async()=>{
  const memories=[{memory_id:'mem_1',text:'Our Orion pilot uses alpha=0.375.',source_label:'User research setting'},
    {memory_id:'mem_2',text:'Compare graph retrieval against dense retrieval.',source_label:'User research goal'}];
  const getMemories=vi.fn().mockImplementation(async()=>memories),deleteMemory=vi.fn().mockImplementation(async id=>{memories.splice(memories.findIndex(m=>m.memory_id===id),1);});
  await act(async()=>root.render(<AccountPanel client={{getMemories,deleteMemory} as any} account={account} onSaved={vi.fn()} refresh={vi.fn()}/>));
  expect(el.querySelectorAll('.memory-item')).toHaveLength(2);
  await act(async()=>el.querySelector<HTMLButtonElement>('.memory-item .danger-action')!.click());
  expect(deleteMemory).toHaveBeenCalledWith('mem_1');expect(el.querySelectorAll('.memory-item')).toHaveLength(1);
  expect(el.textContent).toContain('Compare graph retrieval');expect(el.textContent).not.toContain('0.375');
});

it('opens the selected historical chat with its own budget and source registry',async()=>{
  const saved={paper_id:'p',canonical_url:'https://arxiv.org/html/pv1',budget:{chat_id:'old',tokens_used:1234,token_limit:500000},
    messages:[{id:'a',role:'assistant',answerBlocks:[{text:'Original answer.',evidence_ids:['old-source']}],evidence:[{passage_id:'old-source'}]}]};
  const client={getChats:vi.fn().mockResolvedValue([{chat_id:'old',title:'Earlier research question',paper_title:'Original paper',updated_at:'2026-11-20T00:00:00Z',turns:1}]),
    getConversation:vi.fn().mockResolvedValue(saved)};
  const restore=vi.fn();
  await act(async()=>root.render(<HistoryPanel client={client as any} ownerId="owner" canonicalUrl={saved.canonical_url} onRestore={restore} onDeleted={vi.fn()}/>));
  await act(async()=>el.querySelector<HTMLButtonElement>('.chat-history-open')!.click());
  expect(client.getConversation).toHaveBeenCalledWith('old');expect(restore).toHaveBeenCalledWith(saved);
});

it('claims legacy caches once and never exposes them to a second account',async()=>{
  const data:Record<string,unknown>={'paperlens_chat_https://arxiv.org/html/pv1':{messages:['private']}};
  vi.stubGlobal('chrome',{storage:{local:{get:vi.fn(async()=>({...data})),set:vi.fn(async values=>Object.assign(data,values))}}});
  await claimLegacyStorage('owner-a');await claimLegacyStorage('owner-b');
  expect(data['paperlens_chat_owner-a:https://arxiv.org/html/pv1']).toEqual({messages:['private']});
  expect(data['paperlens_chat_owner-b:https://arxiv.org/html/pv1']).toBeUndefined();
});

it('reads a different paper’s archived chat and opens its own source without a fake save action',async()=>{
  const create=vi.fn().mockResolvedValue({id:2});vi.stubGlobal('chrome',{tabs:{create}});
  const saved={paper_id:'old-paper',canonical_url:'https://arxiv.org/html/2504.01346v4',budget:{chat_id:'old'},
    messages:[{id:'old-answer',role:'assistant',status:'completed',content:'',answerBlocks:[{text:'An archived scientific answer.',evidence_ids:['p1']}],
      evidence:[{passage_id:'p1',parent_passage_id:'p1',text:'The original source paragraph.',section_heading:'Method',section_path:'Method',score:1,rank:1,locator:{element_id:'S1.p1'}}]}]};
  const client={getChats:vi.fn().mockResolvedValue([{chat_id:'old',title:'Old research question',paper_title:'Old paper',updated_at:'2026-11-20T00:00:00Z',turns:1}]),getConversation:vi.fn().mockResolvedValue(saved)};
  await act(async()=>root.render(<HistoryPanel client={client as any} ownerId="owner" canonicalUrl="https://arxiv.org/html/9999.99999v1" onRestore={vi.fn()} onDeleted={vi.fn()}/>));
  await act(async()=>el.querySelector<HTMLButtonElement>('.chat-history-open')!.click());
  expect(el.textContent).toContain('An archived scientific answer.');
  expect(el.querySelector('[aria-label="Save answer to local notes"]')).toBeNull();
  await act(async()=>el.querySelector<HTMLButtonElement>('.citation-link')!.click());
  expect(create).toHaveBeenCalledWith({url:'https://arxiv.org/html/2504.01346v4#S1.p1'});
});
