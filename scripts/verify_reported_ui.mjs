/** Replay live answers to verify citation navigation without regenerating them. */
import puppeteer from '../extension/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import katex from '../extension/node_modules/katex/dist/katex.mjs';

const root = path.resolve(import.meta.dirname, '..');
const dir = process.env.PAPERLENS_CHECK_DIR;
if (!dir) throw new Error('Set PAPERLENS_CHECK_DIR to the disposable build/database directory');
const live = JSON.parse(fs.readFileSync(path.join(root, 'reports/reported_fixes_20261120.json')));
assert.equal(live.turns.length, 3, 'Replay requires three saved live answers');
const uiOnly = process.env.PAPERLENS_UI_ONLY === '1';
if (uiOnly) {
  const {mathTurn} = JSON.parse(fs.readFileSync(path.join(root, 'reports/reported_fixes_ui_20261120.json')));
  live.turns[2] = {...mathTurn, sources:mathTurn.evidence};
}
const blocks = JSON.parse(execFileSync('python', ['-c', `import sqlite3,json,sys
c=sqlite3.connect(sys.argv[1])
print(json.dumps([json.loads(c.execute("SELECT answer_blocks FROM runs WHERE question=? AND status IN ('completed','partial') ORDER BY created_at DESC LIMIT 1",(q,)).fetchone()[0]) for q in json.loads(sys.argv[2])]))`,
  path.join(dir, 'check.db'), JSON.stringify(live.turns.map(turn => turn.question))], {encoding:'utf8'}));
const report = {kind:uiOnly ? 'UI replay only; no LLM requests' : 'Chrome replay of saved live answers, followed by live older-context recall', checks:{}};
const browser = await puppeteer.launch({
  executablePath:path.join(root, 'chrome/linux-158.0.8127.36/chrome-linux64/chrome'), headless:false,
  ignoreDefaultArgs:['--disable-extensions'], args:['--no-sandbox', `--load-extension=${dir}/extension`,
    `--disable-extensions-except=${dir}/extension`, '--window-size=1500,1050'],
});
try {
  const page = await browser.newPage();
  await page.setViewport({width:1500, height:1050});
  await page.goto('https://arxiv.org/html/2504.01346v4', {waitUntil:'networkidle2'});
  await page.waitForFunction(() => document.querySelector('#paperlens-agent-host')?.shadowRoot);
  await page.evaluate(() => {
    const shadow = document.querySelector('#paperlens-agent-host').shadowRoot;
    shadow.querySelector('.paperlens-fab').click();
    Object.assign(shadow.querySelector('.paperlens-modal').style, {width:'570px', height:'880px'});
  });
  const frame = await page.waitForFrame(f => f.url().includes('/sidepanel/index.html'));
  await frame.waitForFunction(() => document.querySelector('.status-text')?.textContent.includes('Ready'), {timeout:30000});
  const context = await frame.evaluate(async () => {
    const entries = Object.entries(await chrome.storage.local.get(null));
    const token = entries.find(([key]) => key.startsWith('paperlens_session:'))[1];
    const owner = (await (await fetch('http://127.0.0.1:8765/api/v1/session', {headers:{Authorization:'Bearer '+token}})).json()).user_id;
    const [paperKey, paper] = entries.find(([key]) => key.startsWith('paperlens_paper_'));
    return {owner, paperId:paper.paperId, key:'paperlens_chat_'+paperKey.slice('paperlens_paper_'.length)};
  });
  const chatId = 'replay-'+Date.now();
  execFileSync('python', ['-c', `import sqlite3,sys
c=sqlite3.connect(sys.argv[1]);c.execute("INSERT INTO conversations(chat_id,owner_id,paper_id) VALUES (?,?,?)",tuple(sys.argv[2:]));c.commit()`,
    path.join(dir, 'check.db'), chatId, context.owner, context.paperId]);
  const messages = live.turns.flatMap((turn, index) => [
    {id:`q${index}`, role:'user', content:turn.question},
    {id:`a${index}`, role:'assistant', status:'completed', content:'', answerBlocks:blocks[index],
      evidence:turn.sources, followUps:turn.followUps},
  ]);
  await frame.evaluate(async ({key, chatId, messages}) => chrome.storage.local.set({[key]:{
    messages, history:[], budget:{chat_id:chatId, tokens_used:0, token_limit:500000, usage_estimated:false, chat_exhausted:false},
  }}), {key:context.key, chatId, messages});
  await frame.goto(frame.url());
  await frame.waitForSelector('.message-assistant-wrapper:nth-last-child(1) .katex');
  report.math = await frame.$$eval('.message-assistant-wrapper:last-child .katex annotation', elements => elements.map(el => el.textContent));
  assert.equal(await frame.$$eval('.katex-error', elements => elements.length), 0);
  report.checks.mathRendered = true;
  if (uiOnly) {
    for (const source of report.math) katex.renderToString(source, {throwOnError:true, trust:false, strict:'ignore'});
    report.checks.strictlyValidMathExpressions = report.math.length;
  }

  for (const index of [0, 2]) {
    const wrapper = (await frame.$$('.message-assistant-wrapper'))[index];
    const buttons = await wrapper.$$('.citation-link');
    let target;
    for (const button of buttons) {
      const label = await button.evaluate(el => el.getAttribute('aria-label'));
      const id = label.replace('View citation for evidence ', '');
      const source = live.turns[index].sources.find(ev => ev.passage_id === id);
      if (source && !/^(img_|chat_|ext_)/.test(id)) {target = {button, source}; break;}
    }
    assert(target);
    const probe = await page.evaluate(async source => {
      const el = document.getElementById(source.locator.element_id);
      const data = new TextEncoder().encode((el?.textContent || '').replace(/\s+/g,' ').trim());
      const actual = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', data)), b => b.toString(16).padStart(2,'0')).join('');
      return {exists:!!el, actual, expected:source.fingerprint, selector:source.locator.selector,
        nativeSelector:'#'+CSS.escape(source.locator.element_id)};
    }, target.source);
    report[`source${index}`] = probe;
    // Wait until the overlay's entrance animation has finished before clicking.
    await page.waitForFunction(() => getComputedStyle(document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-modal')).opacity === '1');
    await target.button.evaluate(el => el.click());
    await page.waitForFunction(() => !document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-modal').classList.contains('visible'), {timeout:10000});
    await page.waitForFunction(id => {
      const el = document.getElementById(id), rect = el?.getBoundingClientRect();
      return el?.classList.contains('paperlens-highlight') && rect.top >= 0 && rect.top < innerHeight;
    }, {timeout:10000}, target.source.locator.element_id);
    report.checks[index === 0 ? 'oldCitation' : 'latestCitation'] = target.source.passage_id;
    await page.screenshot({path:path.join(root, `reports/v3_jump_${index}_20261120.png`)});
    await page.evaluate(() => document.querySelector('#paperlens-agent-host').shadowRoot.querySelector('.paperlens-fab').click());
  }
  async function ask(question, level, image) {
    const chip = (await frame.$$('.mode-chip'))[{low:0,medium:1,high:2}[level]];
    await chip.evaluate(el => el.click());
    if (image) await (await frame.$('input[type=file]')).uploadFile(image);
    await frame.type('textarea', question);
    const count = await frame.$$eval('.message-assistant-wrapper', els => els.length);
    const started = Date.now();
    await frame.click('.composer-btn-send');
    await frame.waitForFunction(n => document.querySelectorAll('.message-assistant-wrapper').length > n, {}, count);
    await frame.waitForFunction(() => !document.querySelector('.composer-btn-stop'), {timeout:140000});
    const state = await frame.evaluate(async () => Object.entries(await chrome.storage.local.get(null))
      .filter(([key]) => key.startsWith('paperlens_chat_')).map(([,value]) => value).sort((a,b) => b.updatedAt-a.updatedAt)[0]);
    const message = state.messages.at(-1);
    assert(message.answerBlocks?.length, JSON.stringify({status:message.status,error:message.error,limitations:message.limitations}));
    return {question, level, seconds:(Date.now()-started)/1000, ...message, budget:state.budget};
  }
  if (!uiOnly) {
  report.mathTurn = await ask('Kết hợp hình với paper để kiểm tra công thức Personalized PageRank. Với P_ij là xác suất đi từ i đến j và r là vector cột, cần P r hay P^T r? Kiểm tra bằng ví dụ bất đối xứng P=[[0.9,0.1],[0.4,0.6]], r=[1,0]^T. Đối chiếu chính xác với công thức paper, giải thích nếu có xung đột ký hiệu; phân biệt nội dung paper và ví dụ của tôi.', 'high', path.join(dir,'paper-figure.png'));
  assert.equal(report.mathTurn.servingModel, 'ag/claude-sonnet-4-6');
  const mathText = report.mathTurn.answerBlocks.map(block => block.text).join('\n\n');
  assert(/0[.,]9/.test(mathText) && /0[.,]1/.test(mathText));
  assert.equal(await frame.$$eval('.message-assistant-wrapper:last-child .katex-error', els => els.length), 0);
  const math = await frame.$$eval('.message-assistant-wrapper:last-child .katex annotation', els => els.map(el => el.textContent));
  assert(math.length > 4);
  for (const source of math) katex.renderToString(source, {throwOnError:true, trust:false, strict:'ignore'});
  report.checks.strictlyValidMathExpressions = math.length;
  assert(!math.some(text => /\\n[rSh]_/.test(text)), 'Literal escaped newlines must not become TeX commands');
  report.checks.mathNumericalExample = true;
  await (await frame.$('.message-assistant-wrapper:last-child .md-math-display')).evaluate(el => el.scrollIntoView({block:'center'}));
  await page.screenshot({path:path.join(root, 'reports/v3_answer_20261120.png')});
  execFileSync('python',['-c',`import sqlite3,json,sys
c=sqlite3.connect(sys.argv[1]);chat=c.execute('SELECT owner_id,paper_id FROM conversations WHERE chat_id=?',(sys.argv[2],)).fetchone()
for i in range(14):
 q='For our hypothetical Orion experiment, set alpha=0.375. This is not the paper setting.' if i==0 else f'Ancillary research note {i} about an unrelated pilot.'
 c.execute("INSERT INTO runs(run_id,owner_id,paper_id,request_id,request_fingerprint,status,created_at,updated_at,deadline,chat_id,question,answer_blocks) VALUES (?,?,?,?,'seed','completed',?,'now','later',?,?,?)",('recall'+str(i)+sys.argv[2],chat[0],chat[1],'recall'+str(i)+sys.argv[2],f'2026-11-01T00:{i:02}:00',sys.argv[2],q,json.dumps([{'text':'Recorded the user-provided pilot setting.','evidence_ids':[]}])))
c.commit()`,path.join(dir,'check.db'),chatId]);
  report.recall = await ask('Bạn nhớ alpha mà tôi đã đặt trước đây cho thí nghiệm Orion là bao nhiêu? Phân biệt rõ tham số giả định của tôi với thiết lập được báo cáo trong paper.', 'low');
  assert(/0[.,]375/.test(report.recall.answerBlocks.map(block => block.text).join(' ')));
  report.checks.olderContextRecalled = true;
  }
  report.ok = true;
} catch (error) {
  report.ok = false; report.failure = error.stack;
} finally {
  fs.writeFileSync(path.join(root, uiOnly ? 'reports/reported_fixes_ui_replay_20261120.json' : 'reports/reported_fixes_ui_20261120.json'), JSON.stringify(report,null,2)+'\n');
  await browser.close();
}
console.log(JSON.stringify({ok:report.ok,checks:report.checks,failure:report.failure}));
if (!report.ok) process.exitCode=1;
