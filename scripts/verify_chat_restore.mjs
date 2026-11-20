/** Verify full-chat restoration and reset in Chrome without spending model tokens. */
import puppeteer from '../extension/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js';
import fs from 'node:fs';import path from 'node:path';import assert from 'node:assert/strict';import {execFileSync} from 'node:child_process';
const dir=process.env.PAPERLENS_CHECK_DIR; if(!dir)throw new Error('Set PAPERLENS_CHECK_DIR');
const root=path.resolve(import.meta.dirname,'..');
const browser=await puppeteer.launch({executablePath:path.join(root,'chrome/linux-158.0.8127.36/chrome-linux64/chrome'),headless:false,ignoreDefaultArgs:['--disable-extensions'],args:['--no-sandbox',`--load-extension=${dir}/extension`,`--disable-extensions-except=${dir}/extension`]});
try{
 const page=await browser.newPage();await page.goto('https://arxiv.org/html/2504.01346v4',{waitUntil:'networkidle2'});
 await page.waitForFunction(()=>document.querySelector('#paperlens-agent-host')?.shadowRoot?.querySelector('.paperlens-fab'));
 await page.evaluate(()=>document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-fab').click());
 let frame=await page.waitForFrame(f=>f.url().includes('/sidepanel/index.html'));await frame.waitForSelector('textarea');
 await frame.waitForFunction(()=>document.querySelector('.status-text')?.textContent.includes('Ready'),{timeout:30000});
 const context=await frame.evaluate(async()=>{
  const entries=Object.entries(await chrome.storage.local.get(null));const token=entries.find(([k])=>k.startsWith('paperlens_session:'))[1];
  const owner=(await(await fetch('http://127.0.0.1:8765/api/v1/session',{headers:{Authorization:'Bearer '+token}})).json()).user_id;
  const [paperKey,paper]=entries.find(([k])=>k.startsWith('paperlens_paper_'));
  return {owner,paperId:paper.paperId,key:'paperlens_chat_'+paperKey.slice('paperlens_paper_'.length)};
 });
 const chatId='restore-'+Date.now();
 execFileSync('python',['-c','import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("INSERT INTO conversations(chat_id,owner_id,paper_id,tokens_used) VALUES (?,?,?,500000)",tuple(sys.argv[2:5])); c.commit()',path.join(dir,'check.db'),chatId,context.owner,context.paperId]);
 await frame.evaluate(async({key,chatId})=>chrome.storage.local.set({[key]:{messages:[{id:'smoke',role:'assistant',status:'completed',content:'Restored chat budget check.',answerBlocks:[{text:'Restored chat budget check.',evidence_ids:[]}]}],history:[],budget:{chat_id:chatId,tokens_used:1000,token_limit:50000,usage_estimated:false,chat_exhausted:false}}}),{key:context.key,chatId});
 await frame.goto(frame.url());await frame.waitForFunction(()=>document.querySelector('[role=meter]')?.getAttribute('aria-valuenow')==='500000'&&document.querySelector('textarea')?.disabled,{timeout:20000});
 assert.equal(await frame.$eval('[role=meter]',el=>el.getAttribute('aria-valuemax')),'500000');
 await frame.click('[aria-label="Start new conversation"]');await frame.waitForFunction(()=>document.querySelector('[role=meter]')?.getAttribute('aria-valuenow')==='0'&&!document.querySelector('textarea')?.disabled);
 await page.evaluate(()=>{document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-modal').style.width='340px';});
 await frame.waitForFunction(()=>document.documentElement.clientWidth<=340,{timeout:5000});
 const size=await frame.evaluate(()=>({width:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));
 assert(size.scroll<=size.width+2,JSON.stringify(size));
 const file=path.join(root,'reports/chat_restore_500k_20261120.json');const report={kind:'500k full-chat restoration; no LLM requests',checks:{}};
 report.checks.exhaustionRestoredAndNewChatResets=true;report.checks.narrowNoHorizontalOverflow=size;report.restoreCheck='Separate current-build Chrome run, with a seeded full chat and stale local budget; no additional model inference.';
 report.ok=true;
 fs.writeFileSync(file,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({ok:report.ok,checks:report.checks}));
}finally{await browser.close();}
