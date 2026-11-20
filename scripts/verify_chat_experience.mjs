/** Live MV3 UI check. Point at an isolated :8765 backend and temporary extension build. */
import puppeteer from '../extension/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';
const root=path.resolve(import.meta.dirname,'..');
const dir=process.env.PAPERLENS_CHECK_DIR;
if(!dir) throw new Error('Set PAPERLENS_CHECK_DIR to the disposable backend/build directory');
const report={kind:'live-models-and-vision-ui-check',paper:'https://arxiv.org/html/2504.01346v4',turns:[],checks:{},errors:[]};
const browser=await puppeteer.launch({executablePath:path.join(root,'chrome/linux-158.0.8127.36/chrome-linux64/chrome'),headless:false,
 ignoreDefaultArgs:['--disable-extensions'],args:['--no-sandbox',`--load-extension=${dir}/extension`,`--disable-extensions-except=${dir}/extension`,'--window-size=1440,1000']});
try {
 const page=await browser.newPage();await page.setViewport({width:1440,height:1000});page.on('pageerror',e=>report.errors.push(e.message));
 async function open(){
  await page.goto(report.paper,{waitUntil:'networkidle2',timeout:45000});
  await page.waitForFunction(()=>document.querySelector('#paperlens-agent-host')?.shadowRoot?.querySelector('.paperlens-fab'),{timeout:10000});
  await page.evaluate(()=>{const s=document.querySelector('#paperlens-agent-host').shadowRoot;s.querySelector('.paperlens-fab').click();const m=s.querySelector('.paperlens-modal');m.style.width='580px';m.style.height='850px';});
  const frame=await page.waitForFrame(f=>f.url().includes('/sidepanel/index.html'));
  await frame.waitForSelector('textarea');return frame;
 }
 let frame=await open();
 assert.equal(await frame.$('.starter-chip'),null);
 assert.equal(await frame.$('[aria-label="Upload document or research file"]'),null);
 assert.deepEqual(await frame.$$eval('.mode-chip',nodes=>nodes.map(n=>n.textContent)),['Low','Medium','High']);
 report.checks.levelsAndImageOnly=true;
 async function saved(){return frame.evaluate(async()=>Object.entries(await chrome.storage.local.get(null)).filter(([k])=>k.startsWith('paperlens_chat_')).map(([,v])=>v).sort((a,b)=>b.updatedAt-a.updatedAt)[0]);}
 async function ask(question,level,image){
  await frame.$eval('textarea',el=>el.focus());
  const levels=await frame.$$('.mode-chip');await levels[{low:0,medium:1,high:2}[level]].click();
  if(image){const upload=await frame.$('input[type=file]');await upload.uploadFile(image);await frame.waitForSelector('.attachment-thumb');}
  await frame.type('textarea',question);
  assert.equal(await frame.$eval('textarea',el=>el.value),question);
  const count=await frame.$$eval('.message-assistant-wrapper',nodes=>nodes.length);const started=Date.now();
  await frame.click('.composer-btn-send');
  await frame.waitForFunction(n=>document.querySelectorAll('.message-assistant-wrapper').length>n,{timeout:30000},count);
  await frame.waitForFunction(()=>!document.querySelector('.composer-btn-stop')&&!!document.querySelector('.message-assistant-wrapper:last-child .answer-card,.message-assistant-wrapper:last-child .message-error'),{timeout:140000});
  const text=await frame.$eval('.message-assistant-wrapper:last-child',el=>el.innerText);
  assert(!await frame.$('.message-assistant-wrapper:last-child .message-error'),text);
  assert(!text.includes('semantic support for synthesized claims is unverified'));
  await frame.waitForFunction(()=>document.querySelectorAll('.message-assistant-wrapper:last-child .follow-up-question').length>=2,{timeout:8000});
  const state=await saved();const message=state.messages.at(-1);
  const turn={level,question,text,seconds:(Date.now()-started)/1000,model:message.servingModel,followUps:message.followUps,budget:state.budget};
  report.turns.push(turn);console.log(JSON.stringify({level,seconds:turn.seconds,model:turn.model,tokens:turn.budget.tokens_used,chars:text.length}));
  assert.equal(turn.model,{low:'ag/gemini-3.8-flash-medium',medium:'ag/gemini-3.8-flash-high',high:'ag/claude-sonnet-4-6'}[level]);
  return turn;
 }
 const first=await ask('Explain T-RAG’s retrieval pipeline step by step, why each stage is needed, and a worked example. Distinguish the paper’s mechanism from your illustration.','low');
 assert(first.text.length>1000,'The technical answer must develop its explanation');
 const second=await ask('Read this synthetic research chart: give both bar values and their difference. Explain how to design a similar comparison for T-RAG; these are not results reported by the paper.','medium',path.join(root,'extension/tests/fixtures/research_chart.png'));
 assert(second.text.includes('73')&&second.text.includes('17')&&second.text.includes('56'));
 const third=await ask('Using that same image and the paper, explain the 73 versus 17 comparison and propose a concrete ablation plan for T-RAG. Separate hypothetical metrics from reported findings.','high');
 assert(third.text.includes('73')&&third.text.includes('17'));
 assert(third.budget.tokens_used>second.budget.tokens_used&&second.budget.tokens_used>first.budget.tokens_used);
 report.checks.visionAndBudget=true;
 await frame.evaluate(()=>{const el=document.querySelector('.conversation-scroll-area');el.scrollTop=0;el.dispatchEvent(new Event('scroll'));});
 await frame.waitForSelector('.jump-to-bottom-btn');
 const layout=await frame.evaluate(()=>{const a=document.querySelector('.conversation-scroll-area').getBoundingClientRect();const b=document.querySelector('.conversation-scroll-controls').getBoundingClientRect();return {answerBottom:a.bottom,controlsTop:b.top};});
 assert(layout.answerBottom<=layout.controlsTop+1,'Jump control must occupy a separate row');
 report.checks.jumpDoesNotOverlap=true;
 await page.screenshot({path:path.join(root,'reports/chat_experience_20261120.png')});
 execFileSync('python',['-c','import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute("UPDATE conversations SET tokens_used=50000 WHERE chat_id=?",(sys.argv[2],)); c.commit()',path.join(dir,'check.db'),third.budget.chat_id]);
 frame=await open();await frame.waitForFunction(()=>document.querySelector('textarea')?.disabled,{timeout:15000});
 assert.equal(await frame.$eval('[role=meter]',el=>el.getAttribute('aria-valuenow')),'50000');
 await frame.click('[aria-label="Start new conversation"]');
 await frame.waitForFunction(()=>!document.querySelector('textarea')?.disabled&&document.querySelector('[role=meter]')?.getAttribute('aria-valuenow')==='0');
 report.checks.exhaustionRestoredAndNewChatResets=true;
 report.ok=report.errors.length===0;
} catch(error){report.ok=false;report.failure=error.stack;console.error(error.message);}
finally {fs.writeFileSync(path.join(root,'reports/chat_experience_20261120.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
console.log(JSON.stringify({ok:report.ok,checks:report.checks,failure:report.failure}));if(!report.ok)process.exitCode=1;
