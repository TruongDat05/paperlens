/** Live regression checks for image answers, old citations, math and 500k chat memory. */
import puppeteer from '../extension/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js';
import fs from 'node:fs';import path from 'node:path';import assert from 'node:assert/strict';import {execFileSync} from 'node:child_process';
const root=path.resolve(import.meta.dirname,'..'), dir=process.env.PAPERLENS_CHECK_DIR;
if(!dir)throw new Error('Set PAPERLENS_CHECK_DIR to a disposable backend/build directory');
const report={kind:'live reported-bug regression',turns:[],checks:{},errors:[]};
const browser=await puppeteer.launch({executablePath:path.join(root,'chrome/linux-158.0.8127.36/chrome-linux64/chrome'),headless:false,ignoreDefaultArgs:['--disable-extensions'],args:['--no-sandbox',`--load-extension=${dir}/extension`,`--disable-extensions-except=${dir}/extension`,'--window-size=1500,1050']});
try{
 const page=await browser.newPage();await page.setViewport({width:1500,height:1050});page.on('pageerror',e=>report.errors.push(e.message));
 await page.goto('https://arxiv.org/html/2504.01346v4',{waitUntil:'networkidle2',timeout:45000});
 const figures=await page.$$eval('figure.ltx_figure',els=>els.map(el=>({id:el.id,caption:el.querySelector('figcaption')?.textContent?.trim()})));
 const figure=figures.find(f=>/framework|overview/i.test(f.caption||''))||figures[0];
 assert(figure,'A real paper figure must be available');
 const figurePath=path.join(dir,'paper-figure.png');
 await(await page.$(`[id="${figure.id}"]`)).screenshot({path:figurePath});
 report.image={kind:'real full-paper figure',...figure};
 await page.evaluate(()=>{const s=document.querySelector('#paperlens-agent-host').shadowRoot;s.querySelector('.paperlens-fab').click();s.querySelector('.paperlens-modal').style.width='570px';s.querySelector('.paperlens-modal').style.height='880px';});
 let frame=await page.waitForFrame(f=>f.url().includes('/sidepanel/index.html'));await frame.waitForSelector('textarea');
 await frame.waitForFunction(()=>document.querySelector('.status-text')?.textContent.includes('Ready'),{timeout:30000});
 async function saved(){return frame.evaluate(async()=>Object.entries(await chrome.storage.local.get(null)).filter(([key])=>key.startsWith('paperlens_chat_')).map(([,value])=>value).sort((a,b)=>b.updatedAt-a.updatedAt)[0]);}
 async function ask(question,level,image,minChars=450){
  const levels=await frame.$$('.mode-chip');await levels[{low:0,medium:1,high:2}[level]].evaluate(el=>el.click());
  await frame.waitForFunction(expected=>document.querySelector('.mode-chip[aria-pressed=true]')?.textContent.toLowerCase()===expected,{},level);
  if(image){await(await frame.$('input[type=file]')).uploadFile(image);await frame.waitForSelector('.attachment-thumb');}
  await frame.type('textarea',question);assert.equal(await frame.$eval('textarea',el=>el.value),question);
  const n=await frame.$$eval('.message-assistant-wrapper',els=>els.length),start=Date.now();
  await frame.click('.composer-btn-send');
  await frame.waitForFunction(count=>document.querySelectorAll('.message-assistant-wrapper').length>count,{timeout:30000},n);
  await frame.waitForFunction(()=>!document.querySelector('.composer-btn-stop'),{timeout:140000});
  const state=await saved(), message=state.messages.at(-1);
  assert(message.answerBlocks?.length,JSON.stringify({status:message.status,error:message.error,limitations:message.limitations}));
  const text=message.answerBlocks.map(b=>b.text).join('\n\n');
  const turn={level,question,seconds:(Date.now()-start)/1000,text,servingModel:message.servingModel,sources:message.evidence,followUps:message.followUps,budget:state.budget};report.turns.push(turn);
  assert.equal(turn.budget.token_limit,500000);assert(text.length>minChars);
  assert(turn.followUps?.length>=2);
  console.log(JSON.stringify({level,seconds:turn.seconds,chars:text.length,tokens:turn.budget.tokens_used}));return turn;
 }
 const first=await ask('Giải thích chi tiết sơ đồ này trong paper: đầu vào, từng bước xử lý, quan hệ giữa các thành phần và đầu ra. Cho một ví dụ cụ thể; phân biệt điều thể hiện trên hình với phần suy luận của bạn.','medium',figurePath);
 report.checks.realImageAnswered=true;
 const second=await ask('Phân tích phương pháp trong paper kỹ hơn: xây dựng đồ thị, truy xuất thô và truy xuất tinh khác nhau thế nào? Nêu cơ chế, một ví dụ có giải thích, các giả định và hạn chế.','low');
 const third=await ask('Kết hợp hình ở trên với paper để giải thích Personalized PageRank. Minh hoạ công thức LaTeX \\[r_{t+1}=\\alpha P^{\\top}r_t+(1-\\alpha)q\\], định nghĩa từng ký hiệu, giải thích trực giác và quy ước chuyển vị; nêu phần nào là minh hoạ thay vì chép công thức paper.','high');
 await frame.waitForSelector('.message-assistant-wrapper:last-child .katex .msupsub');
 assert.equal(await frame.$$eval('.message-assistant-wrapper:last-child .katex-error',els=>els.length),0);
 assert(await frame.evaluate(async()=>{await document.fonts.ready;return document.fonts.check('12px KaTeX_Main');}));
 report.checks.mathRendered=true;
 async function jumpFromAnswer(index){
  const wrappers=await frame.$$('.message-assistant-wrapper');
  const buttons=await wrappers[index].$$('.citation-link');let target;
  for(const button of buttons){const label=await button.evaluate(el=>el.getAttribute('aria-label'));const id=label?.replace('View citation for evidence ','');const ev=report.turns[index].sources?.find(e=>e.passage_id===id);if(ev&&!/^(img_|chat_|ext_)/.test(id)){target={button,ev};break;}}
  assert(target,'Answer needs an in-paper citation');
  const style=await target.button.evaluate(el=>({label:el.textContent,width:el.getBoundingClientRect().width,font:parseFloat(getComputedStyle(el).fontSize)}));assert(/^\d{1,2}$/.test(style.label));assert(style.width<26&&style.font<=11);
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-modal')).opacity==='1');
  await target.button.evaluate(el=>el.click());
  await page.waitForFunction(()=>document.querySelector('.paperlens-highlight'),{timeout:10000});
  await page.waitForFunction(()=>!document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-modal').classList.contains('visible'));
  await page.waitForFunction(()=>{const r=document.querySelector('.paperlens-highlight')?.getBoundingClientRect();return r&&r.top>=0&&r.top<innerHeight;},{timeout:10000});
  const selector=target.ev.locator.selector;const elementId=target.ev.locator.element_id;
  assert(await page.evaluate(({selector,elementId})=>{const el=elementId?document.getElementById(elementId):document.querySelector(selector);return !!el?.classList.contains('paperlens-highlight');},{selector,elementId}));
  await page.screenshot({path:path.join(root,`reports/v3_jump_${index}_20261120.png`)});
  await page.evaluate(()=>document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-fab').click());
  return {sourceId:target.ev.passage_id,selector,...style};
 }
 report.checks.oldCitation=await jumpFromAnswer(0);report.checks.latestCitation=await jumpFromAnswer(2);
 // Seed an older user parameter among unrelated turns; no model usage is fabricated.
 const state=await saved(), chatId=state.budget.chat_id;
 execFileSync('python',['-c',`import sqlite3,json,sys
c=sqlite3.connect(sys.argv[1]); chat=c.execute('SELECT owner_id,paper_id FROM conversations WHERE chat_id=?',(sys.argv[2],)).fetchone()
for i in range(14):
 q='For our hypothetical Orion experiment, set alpha=0.375. This is not the paper setting.' if i==0 else f'Ancillary research note {i} about an unrelated pilot.'
 c.execute("INSERT INTO runs(run_id,owner_id,paper_id,request_id,request_fingerprint,status,created_at,updated_at,deadline,chat_id,question,answer_blocks) VALUES (?,?,?,?,'seed','completed',?,'now','later',?,?,?)",('recall'+str(i)+sys.argv[2],chat[0],chat[1],'recall'+str(i)+sys.argv[2],f'2026-11-01T00:{i:02}:00',sys.argv[2],q,json.dumps([{'text':'Recorded the user-provided pilot setting.','evidence_ids':[]}])))
c.commit()`,path.join(dir,'check.db'),chatId]);
 const recall=await ask('Bạn nhớ alpha mà tôi đã đặt trước đây cho thí nghiệm Orion là bao nhiêu? Phân biệt rõ tham số giả định của tôi với thiết lập được báo cáo trong paper.','low',null,80);
 assert(recall.text.includes('0.375'));
 report.checks.olderContextRecalled=true;
 await page.screenshot({path:path.join(root,'reports/v3_answer_20261120.png')});
 assert(report.errors.length===0);report.ok=true;
}catch(error){report.ok=false;report.failure=error.stack;console.error(error.message);}
finally{fs.writeFileSync(path.join(root,'reports/reported_fixes_20261120.json'),JSON.stringify(report,null,2)+'\n');await browser.close();}
console.log(JSON.stringify({ok:report.ok,checks:report.checks,failure:report.failure}));if(!report.ok)process.exitCode=1;
