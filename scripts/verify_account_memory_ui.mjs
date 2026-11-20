/** Native Chrome acceptance with a disposable backend and explicitly mocked inference. */
import puppeteer from '../extension/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';

const root=path.resolve(import.meta.dirname,'..'),dir=process.env.PAPERLENS_CHECK_DIR;
if(!dir)throw new Error('Set PAPERLENS_CHECK_DIR to the disposable build/database directory.');
const report={kind:'Native Chrome account/history/memory/resize acceptance; mocked inference and HTML fixture',checks:{},errors:[]};
const browser=await puppeteer.launch({executablePath:path.join(root,'chrome/linux-158.0.8127.36/chrome-linux64/chrome'),
  headless:false,ignoreDefaultArgs:['--disable-extensions'],args:['--no-sandbox',`--load-extension=${dir}/extension`,
    `--disable-extensions-except=${dir}/extension`,'--window-size=1500,1050']});
try {
  const page=await browser.newPage();await page.setViewport({width:1500,height:1050});
  page.on('pageerror',error=>report.errors.push(error.message));
  await page.setRequestInterception(true);
  page.on('request',request=>{
    if(request.isNavigationRequest() && request.url()==='https://arxiv.org/html/2504.01346v4')void request.respond({status:200,contentType:'text/html',body:
      '<!doctype html><html><head><title>Research memory UI fixture</title></head><body><article class="ltx_document"><h1 class="ltx_title_document">Research memory UI fixture</h1><section class="ltx_section" id="S1"><h2>1 Method</h2><div class="ltx_para" id="S1.p1"><p class="ltx_p">The Transformer uses self-attention in place of recurrence. This is a deterministic test fixture for account and chat interactions.</p></div></section></article></body></html>'});
    else void request.continue();
  });
  await page.goto('https://arxiv.org/html/2504.01346v4',{waitUntil:'networkidle2'});
  await page.waitForFunction(()=>document.querySelector('#paperlens-agent-host')?.shadowRoot?.querySelector('.paperlens-fab'));
  await page.evaluate(()=>document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-fab').click());
  const frame=await page.waitForFrame(f=>f.url().includes('/sidepanel/index.html'));
  await frame.waitForSelector('.onboarding-panel');
  await page.screenshot({path:path.join(root,'reports/account_onboarding_20261120.png')});
  await frame.type('input[autocomplete=name]','Research Tester');
  await frame.type('.profile-form textarea','Graph retrieval and research agents');
  await frame.type('input[autocomplete=country-name]','Vietnamese');
  await frame.click('.profile-form button[type=submit]');
  await frame.waitForSelector('.composer-textarea');
  await frame.waitForFunction(()=>document.querySelector('.status-text')?.textContent.includes('Ready'));
  report.checks.onboarding=true;
  const owner=await frame.evaluate(async()=>{
    const entries=Object.entries(await chrome.storage.local.get(null));
    const token=entries.find(([key])=>key.startsWith('paperlens_session:'))[1];
    return (await(await fetch('http://127.0.0.1:8765/api/v1/account',{headers:{Authorization:'Bearer '+token}})).json()).owner_id;
  });
  async function saved(){return frame.evaluate(async owner=>Object.entries(await chrome.storage.local.get(null))
    .filter(([key])=>key.startsWith('paperlens_chat_'+owner+':')).map(([,value])=>value).sort((a,b)=>b.updatedAt-a.updatedAt)[0],owner);}
  async function ask(question){
    const count=await frame.$$eval('.message-assistant-wrapper',els=>els.length);
    await frame.type('.composer-textarea',question);await frame.click('.composer-btn-send');
    await frame.waitForFunction(n=>document.querySelectorAll('.message-assistant-wrapper').length>n,{},count);
    await frame.waitForFunction(()=>!document.querySelector('.composer-btn-stop'));
    const state=await saved();assert(state.messages.at(-1).answerBlocks?.length);return state;
  }
  const first=await ask('Explain this paper.');
  assert.equal(await frame.$eval('[role=meter]',el=>el.getAttribute('aria-valuemax')),'500000');
  assert.equal(await frame.$$eval('.token-count',els=>els.length),0);
  await frame.click('[aria-label="Start new conversation"]');
  const second=await ask('What does the method replace?');assert.notEqual(first.budget.chat_id,second.budget.chat_id);
  await frame.click('[aria-label="Chat history"]');await frame.waitForSelector('.chat-history-open');
  assert.equal(await frame.$$eval('.chat-history-open',els=>els.length),2);
  await page.screenshot({path:path.join(root,'reports/account_history_20261120.png')});
  const old=(await frame.$$('.chat-history-open'))[1];await old.click();
  await frame.waitForSelector('.composer-textarea');
  await frame.waitForFunction(()=>document.querySelector('.message-user-wrapper .message-text')?.textContent==='Explain this paper.');
  assert.equal((await saved()).budget.chat_id,first.budget.chat_id);
  report.checks.historyRestoresOwnSession=true;
  await frame.click('[aria-label="Settings and memory"]');await frame.waitForSelector('#memory-note');
  await frame.type('#memory-note','Our Orion experiment uses alpha=0.375.');await frame.click('.memory-add button');
  await frame.waitForSelector('.memory-item');
  assert((await frame.$eval('.memory-item',el=>el.textContent)).includes('0.375'));
  await frame.click('.memory-item .text-action');await frame.waitForSelector('.memory-item textarea');
  await frame.$eval('.memory-item textarea',el=>{el.select();});
  await frame.type('.memory-item textarea','Our Orion experiment now uses alpha=0.5.');
  await frame.click('.memory-item form button');
  await frame.waitForFunction(()=>!document.querySelector('.memory-item textarea') && document.querySelector('.memory-item')?.textContent.includes('0.5'));
  await page.screenshot({path:path.join(root,'reports/account_settings_20261120.png')});
  await frame.click('.memory-item .danger-action');await frame.waitForFunction(()=>!document.querySelector('.memory-item'));
  report.checks.memoryAddEditForget=true;
  await frame.click('.page-toolbar button');
  execFileSync('python',['-c','import sqlite3,sys; c=sqlite3.connect(sys.argv[1]);c.execute("UPDATE conversations SET tokens_used=460000 WHERE chat_id=?",(sys.argv[2],));c.commit()',path.join(dir,'check.db'),first.budget.chat_id]);
  await frame.goto(frame.url());await frame.waitForSelector('.context-notice');
  assert((await frame.$eval('.context-notice',el=>el.textContent)).includes('Context sắp hết'));
  assert.equal(await frame.$$eval('.token-count',els=>els.length),0);
  report.checks.contextRingAndWarning=true;
  await page.screenshot({path:path.join(root,'reports/account_context_warning_20261120.png')});
  await page.evaluate(()=>document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.btn-transform').click());
  const rect=()=>page.evaluate(()=>{const r=document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-modal').getBoundingClientRect();return {left:r.left,top:r.top,width:r.width,height:r.height,right:r.right,bottom:r.bottom};});
  const before=await rect();
  assert.equal(await page.evaluate(()=>document.querySelector('#paperlens-agent-host').shadowRoot.querySelectorAll('.resizer').length),8);
  await page.mouse.move(before.left+4,before.top+4);await page.mouse.down();await page.mouse.move(before.left-86,before.top-46,{steps:8});await page.mouse.up();
  const after=await rect();assert(after.width>=before.width+70 && after.height>=before.height+35,JSON.stringify({before,after}));
  await page.evaluate(()=>document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.resizer.e').focus());
  await page.keyboard.press('ArrowLeft');const keyboard=await rect();assert(keyboard.width<after.width);
  await page.evaluate(()=>document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('[data-size="width:40"]').click());
  assert((await rect()).width>keyboard.width);
  await page.screenshot({path:path.join(root,'reports/account_free_transform_20261120.png')});
  await page.setViewport({width:900,height:700});
  await page.waitForFunction(()=>{const r=document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-modal').getBoundingClientRect();return r.left>=11&&r.top>=11&&r.right<=innerWidth-11&&r.bottom<=innerHeight-11;});
  report.checks.eightHandlesKeyboardButtonsAndBounds=true;
  const geometry=await rect();report.geometry=geometry;
  await page.evaluate(()=>{const shadow=document.querySelector('#paperlens-agent-host').shadowRoot;
    shadow.querySelector('[data-size=done]').click();shadow.querySelector('.paperlens-modal').style.width='340px';});
  await frame.waitForFunction(()=>document.documentElement.clientWidth<=340);
  const narrow=await frame.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,
    controlsRight:document.querySelector('.header-controls').getBoundingClientRect().right}));
  assert(narrow.scroll<=narrow.width+1 && narrow.controlsRight<=narrow.width,JSON.stringify(narrow));
  report.checks.narrowPanel=narrow;
  await page.evaluate(()=>document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.btn-maximize').click());
  const expanded=await rect();assert(expanded.left>=15 && expanded.right<=900-15 && expanded.bottom<=700-15);
  await page.evaluate(()=>document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.btn-transform').click());
  assert(await page.evaluate(()=>{const m=document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-modal');return !m.classList.contains('maximized')&&m.classList.contains('transform-active');}));
  report.checks.expandRestoreAndTransform=true;
  await page.reload({waitUntil:'networkidle2'});
  await page.waitForFunction(()=>document.querySelector('#paperlens-agent-host')?.shadowRoot?.querySelector('.paperlens-fab'));
  await page.evaluate(()=>document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-fab').click());
  const restored=await page.waitForFrame(f=>f.url().includes('/sidepanel/index.html'));
  await restored.waitForSelector('.composer-textarea');assert.equal(await restored.$$eval('.onboarding-panel',els=>els.length),0);
  report.checks.profileAndWindowPersist=true;
  assert.equal(report.errors.length,0);report.ok=true;
} catch(error){report.ok=false;report.failure=error.stack;}
finally{fs.writeFileSync(path.join(root,'reports/account_memory_ui_20261120.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
console.log(JSON.stringify(report));if(!report.ok)process.exitCode=1;
