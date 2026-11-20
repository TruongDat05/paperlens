/** Two live Low turns on the real paper, proving automatic memory across new chats. */
import puppeteer from '../extension/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'..'),dir=process.env.PAPERLENS_CHECK_DIR;
if(!dir)throw new Error('Set PAPERLENS_CHECK_DIR to the disposable live build/database directory.');
const report={kind:'Live automatic long-term research memory across two new chats',turns:[],checks:{},errors:[]};
const browser=await puppeteer.launch({executablePath:path.join(root,'chrome/linux-158.0.8127.36/chrome-linux64/chrome'),headless:false,
  ignoreDefaultArgs:['--disable-extensions'],args:['--no-sandbox',`--load-extension=${dir}/live-extension`,`--disable-extensions-except=${dir}/live-extension`,'--window-size=1500,1050']});
try{
  const page=await browser.newPage();await page.setViewport({width:1500,height:1050});page.on('pageerror',e=>report.errors.push(e.message));
  await page.goto('https://arxiv.org/html/2504.01346v4',{waitUntil:'networkidle2',timeout:45000});
  await page.waitForFunction(()=>document.querySelector('#paperlens-agent-host')?.shadowRoot?.querySelector('.paperlens-fab'));
  await page.evaluate(()=>document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-fab').click());
  const frame=await page.waitForFrame(f=>f.url().includes('/sidepanel/index.html'));
  await frame.waitForSelector('.onboarding-panel');
  await frame.type('input[autocomplete=name]','Memory Verification');
  await frame.type('.profile-form textarea','Table retrieval and personalized PageRank');
  await frame.type('input[autocomplete=country-name]','Test profile');
  await frame.click('.profile-form button[type=submit]');
  await frame.waitForFunction(()=>document.querySelector('.status-text')?.textContent.includes('Ready'),{timeout:30000});
  async function api(endpoint){return frame.evaluate(async endpoint=>{
    const entries=Object.entries(await chrome.storage.local.get(null));const token=entries.find(([key])=>key.startsWith('paperlens_session:'))[1];
    const r=await fetch('http://127.0.0.1:8766/api/v1/'+endpoint,{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw new Error('API '+r.status);return r.json();
  },endpoint);}
  async function ask(question){
    const count=await frame.$$eval('.message-assistant-wrapper',els=>els.length),started=Date.now();
    await frame.type('.composer-textarea',question);await frame.click('.composer-btn-send');
    await frame.waitForFunction(n=>document.querySelectorAll('.message-assistant-wrapper').length>n,{},count);
    await frame.waitForFunction(()=>!document.querySelector('.composer-btn-stop'),{timeout:140000});
    const account=await api('account');
    const state=await frame.evaluate(async owner=>Object.entries(await chrome.storage.local.get(null))
      .filter(([key])=>key.startsWith('paperlens_chat_'+owner+':')).map(([,value])=>value).sort((a,b)=>b.updatedAt-a.updatedAt)[0],account.owner_id);
    const message=state.messages.at(-1);assert(message.answerBlocks?.length,JSON.stringify({status:message.status,error:message.error,limitations:message.limitations}));
    const turn={question,seconds:(Date.now()-started)/1000,budget:state.budget,...message};report.turns.push(turn);
    console.log(JSON.stringify({status:message.status,seconds:turn.seconds,chars:message.answerBlocks.reduce((n,b)=>n+b.text.length,0)}));return turn;
  }
  const first=await ask('Trong thí nghiệm giả định Orion của tôi, tôi chọn alpha=0.375. Hãy ghi nhớ thiết lập nghiên cứu riêng này cho các session sau. Giải thích ngắn gọn nó liên hệ với damping factor trong Personalized PageRank của paper như thế nào, và phân biệt thiết lập của tôi với kết quả bài báo.');
  report.memories=await api('account/memories');
  assert(report.memories.some(memory=>memory.kind==='user_context'&&memory.text.includes('0.375')),'The explicit research setting must be saved automatically');
  report.checks.automaticGroundedMemory=true;
  await frame.click('[aria-label="Start new conversation"]');
  const second=await ask('Trong session trước tôi đã chọn alpha bằng bao nhiêu cho thí nghiệm Orion? Phân biệt rõ thiết lập riêng của tôi với giá trị được paper báo cáo.');
  assert.notEqual(first.budget.chat_id,second.budget.chat_id);
  const text=second.answerBlocks.map(block=>block.text).join('\n\n');assert(/0[.,]375/.test(text));
  assert(second.evidence.some(ev=>ev.passage_id.startsWith('mem_')&&ev.text.includes('0.375')));
  assert(second.answerBlocks.some(block=>block.evidence_ids.some(id=>id.startsWith('mem_'))));
  report.checks.newChatRecalledCitableMemory=true;
  await frame.click('[aria-label="Chat history"]');await frame.waitForSelector('.chat-history-open');
  assert.equal(await frame.$$eval('.chat-history-open',els=>els.length),2);report.checks.twoDurableChats=true;
  await page.screenshot({path:path.join(root,'reports/account_memory_live_20261120.png')});
  assert(!report.errors.length);report.ok=true;
}catch(error){report.ok=false;report.failure=error.stack;}
finally{fs.writeFileSync(path.join(root,'reports/account_memory_live_20261120.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
console.log(JSON.stringify({ok:report.ok,checks:report.checks,failure:report.failure}));if(!report.ok)process.exitCode=1;
