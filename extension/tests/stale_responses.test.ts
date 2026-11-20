/** @vitest-environment jsdom */
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { describe, it, expect, vi } from 'vitest';
import { ApiClient } from '../src/api/client';
import { useAgentRun } from '../src/sidepanel/useAgentRun';
import { usePaper } from '../src/sidepanel/usePaper';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
const deferred = () => { let resolve!: (v:any)=>void; const promise = new Promise<any>(r=>resolve=r); return {promise,resolve}; };

describe('async context boundaries', () => {
  it('bootstraps the default client once with a unique issued capability', async () => {
    const fetch = vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({token:'issued-token'})})
      .mockResolvedValue({ok:true,json:async()=>({user_id:'unique-owner'})});
    vi.stubGlobal('fetch',fetch);
    const client = new ApiClient();
    await Promise.all([client.getSession(),client.getSession()]);
    expect(fetch.mock.calls.filter(c=>c[1]?.method==='POST')).toHaveLength(1);
    expect(fetch.mock.calls[1][1].headers.Authorization).toBe('Bearer issued-token');
    vi.unstubAllGlobals();
  });

  it.each(['paper', 'new_run', 'cancel'])('discards delayed run creation after %s', async (change) => {
    const delayed=deferred(); const client=new ApiClient({token:'test'});
    vi.spyOn(client,'createAgentRun').mockReturnValueOnce(delayed.promise)
      .mockResolvedValue({run_id:'new',paper_id:'p',status:'completed',answer_blocks:[{text:'new',evidence_ids:[]}]});
    vi.spyOn(client,'cancelAgentRun').mockResolvedValue({run_id:'old',paper_id:'p',status:'cancelled'});
    let hook:any; let paperId='p';
    function Harness(){hook=useAgentRun({client,paperId});return null;}
    const root=createRoot(document.createElement('div'));
    await act(async()=>root.render(React.createElement(Harness)));
    let pending!:Promise<void>;
    await act(async()=>{pending=hook.startRun('old');});
    await act(async()=>{
      if(change==='paper'){paperId='other';root.render(React.createElement(Harness));}
      else if(change==='new_run') await hook.startRun('new');
      else await hook.cancelRun();
    });
    await act(async()=>{delayed.resolve({run_id:'old',paper_id:'p',status:'completed',answer_blocks:[{text:'stale',evidence_ids:[]}]});await pending;});
    expect(hook.answerBlocks.some((b:any)=>b.text==='stale')).toBe(false);
    expect(hook.runId).not.toBe('old');
    await act(async()=>root.unmount());
  });

  it('resets paper state and ignores ingestion resolving after navigation', async()=>{
    const delayed=deferred(); const client=new ApiClient({token:'test'});
    vi.spyOn(client,'ingestPaper').mockReturnValue(delayed.promise);
    const status=vi.spyOn(client,'getPaperStatus');
    let activated!:()=>void; let hook:any;
    vi.stubGlobal('chrome',{runtime:{lastError:null},tabs:{query:async()=>[{id:1}],
      onActivated:{addListener:(fn:any)=>activated=fn,removeListener:vi.fn()},
      onUpdated:{addListener:vi.fn(),removeListener:vi.fn()},
      sendMessage:(_id:any,msg:any,cb:any)=>cb(msg.type==='GET_CONTEXT'?{type:'CONTEXT_RESPONSE',context:{isSupported:true,arxivId:'a',version:'v1',pageType:'HTML'}}:{type:'ANALYZE_RESPONSE',paper:{title:'a',arxivId:'a',version:'v1',canonicalUrl:'url',sections:[],paragraphs:[]}})}});
    function Harness(){hook=usePaper(client);return null;}
    const root=createRoot(document.createElement('div'));
    await act(async()=>root.render(React.createElement(Harness)));
    await act(async()=>hook.grantConsent());
    let pending!:Promise<void>;
    await act(async()=>{pending=hook.analyze();});
    await act(async()=>activated());
    await act(async()=>{delayed.resolve({paper_id:'stale'});await pending;});
    expect(hook.paperId).toBeNull();expect(hook.consentGranted).toBe(false);
    expect(status).not.toHaveBeenCalled();
    await act(async()=>root.unmount());vi.unstubAllGlobals();
  });
});

describe('research refusal lifecycle', () => {
  it.each(['post', 'poll', 'stream'])('finishes a refused request via %s without adding it to research history', async (transport) => {
    const client = new ApiClient({ token: 'test' });
    const refused: any = { run_id: 'refused', paper_id: 'p', status: 'refused', evidence: [],
      answer_blocks: [{ text: 'PaperLens only supports scientific research.', evidence_ids: [] }] };
    vi.spyOn(client, 'createAgentRun').mockResolvedValue(transport === 'post' ? refused : { ...refused, status: 'queued' });
    const poll = vi.spyOn(client, 'getAgentRun').mockResolvedValue(refused);
    vi.spyOn(client, 'streamAgentRunEvents').mockImplementation(async (_run, onEvent) => {
      if (transport === 'stream') onEvent({ type: 'done', ...refused });
    });
    let hook: any;
    function Harness() { hook = useAgentRun({ client, paperId: 'p' }); return null; }
    const root = createRoot(document.createElement('div'));
    await act(async () => root.render(React.createElement(Harness)));
    await act(async () => hook.startRun('What is the weather?'));
    expect(hook.status).toBe('refused');
    expect(hook.polling).toBe(false);
    expect(hook.messages.at(-1).isStreaming).toBe(false);
    expect(hook.messages.at(-1).content).toContain('scientific research');
    expect(hook.history).toEqual([]);
    expect(poll).toHaveBeenCalledTimes(transport === 'poll' ? 1 : 0);
    await act(async () => root.unmount());
  });

  it('shows the backend quota recovery message without serializing its metadata', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 429, json: async () => ({ detail: {
      code: 'DAILY_QUOTA_EXCEEDED', message: 'Daily limit reached. Resets at 00:00 UTC.', quota: 'agent_turns',
    } }) }));
    const client = new ApiClient({ token: 'test' });
    await expect(client.createAgentRun({ request_id: 'q', paper_id: 'p', question: 'Research?' }))
      .rejects.toThrow('Daily limit reached. Resets at 00:00 UTC.');
    vi.unstubAllGlobals();
  });
});

describe('chat token accounting and image payloads', () => {
  it('persists the backend chat id across turns, sends image bytes and level, and resets for a new chat', async () => {
    const client = new ApiClient({token:'test'});
    const create = vi.spyOn(client,'createAgentRun').mockImplementation(async req => ({run_id:req.request_id,paper_id:'p',status:'completed',
      answer_blocks:[{text:'Cited response.',evidence_ids:['p1']}], follow_ups:['How can we test this mechanism?'],
      chat_id:req.chat_id || 'chat-new',tokens_used:req.chat_id?2400:1200,token_limit:50000,chat_exhausted:false}));
    let hook:any;
    function Harness(){hook=useAgentRun({client,paperId:'p'});return null;}
    const root=createRoot(document.createElement('div'));
    await act(async()=>root.render(React.createElement(Harness)));
    await act(async()=>hook.startRun('Analyze figure','A2',[{id:'i',name:'figure.png',size:100,type:'image/png',dataUrl:'data:image/png;base64,ABC'}],undefined,'medium'));
    expect(create.mock.calls[0][0].images?.[0].data_url).toBe('data:image/png;base64,ABC');
    expect(create.mock.calls[0][0].level).toBe('medium');
    expect(hook.budget.tokens_used).toBe(1200);
    expect(hook.messages.at(-1).followUps).toEqual(['How can we test this mechanism?']);
    await act(async()=>hook.startRun('Explain more'));
    expect(create.mock.calls[1][0].chat_id).toBe('chat-new');
    expect(hook.budget.tokens_used).toBe(2400);
    await act(async()=>hook.resetConversation());
    expect(hook.budget.tokens_used).toBe(0);
    await act(async()=>hook.startRun('A new topic'));
    expect(create.mock.calls[2][0].chat_id).toBeUndefined();
    await act(async()=>root.unmount());
  });

  it('blocks another turn after the backend marks the chat exhausted',async()=>{
    const client=new ApiClient({token:'test'});
    const create=vi.spyOn(client,'createAgentRun').mockResolvedValue({run_id:'r',paper_id:'p',status:'completed',chat_id:'c',tokens_used:50000,chat_exhausted:true});
    let hook:any;function Harness(){hook=useAgentRun({client,paperId:'p'});return null;}
    const root=createRoot(document.createElement('div'));
    await act(async()=>root.render(React.createElement(Harness)));
    await act(async()=>hook.startRun('First'));
    await act(async()=>hook.startRun('Blocked'));
    expect(create).toHaveBeenCalledTimes(1);
    expect(hook.budget.chat_exhausted).toBe(true);
    await act(async()=>root.unmount());
  });
});

it('restores authoritative budget even if indexing assigns a paper id while usage is loading',async()=>{
  const delayed=deferred();const client=new ApiClient({token:'test'});
  vi.spyOn(client,'getChatState').mockReturnValue(delayed.promise);
  const stored={messages:[{id:'a',role:'assistant',content:'Saved response',status:'completed'}],history:[],budget:{chat_id:'saved',tokens_used:1000,token_limit:50000}};
  vi.stubGlobal('chrome',{storage:{local:{get:async()=>({'paperlens_chat_url':stored}),set:async()=>{},remove:async()=>{}},session:{get:async()=>({}),remove:async()=>{}}}});
  let hook:any;let paperId:string|null=null;
  function Harness(){hook=useAgentRun({client,paperId,canonicalUrl:'url'});return null;}
  const root=createRoot(document.createElement('div'));
  await act(async()=>root.render(React.createElement(Harness)));
  expect(hook.budget.tokens_used).toBe(1000);
  await act(async()=>{paperId='indexed';root.render(React.createElement(Harness));});
  await act(async()=>delayed.resolve({chat_id:'saved',tokens_used:50000,token_limit:50000,chat_exhausted:true}));
  expect(hook.budget.tokens_used).toBe(50000);
  expect(hook.budget.chat_exhausted).toBe(true);
  await act(async()=>root.unmount());vi.unstubAllGlobals();
});
