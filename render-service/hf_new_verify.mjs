import fs from 'node:fs';
import puppeteer from 'puppeteer';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const SNAP = 'D:\\ClaudeProjects\\NOLAN\\render-service\\_hfui';
const errs = [];
const b = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'], protocolTimeout: 60000 });
const p = await b.newPage();
await p.setViewport({ width: 1560, height: 1040 });
p.on('pageerror', e => errs.push(e.message));
await p.goto('http://127.0.0.1:8011/hyperframes', { waitUntil: 'load', timeout: 30000 });
await p.waitForFunction(() => document.querySelector('#comp'), { timeout: 15000 });
await p.evaluate(() => { if (!window.__th){window.__th=1;window.__toasts=[];const o=window.toast;window.toast=(m,t)=>{window.__toasts.push(String(m));return o&&o(m,t);};} });
// open modal
await p.evaluate(() => [...document.querySelectorAll('button')].find(x => x.textContent.includes('New essay')).click());
const modalShown = await p.waitForFunction(() => getComputedStyle(document.querySelector('#newModal')).display !== 'none', { timeout: 6000 }).then(() => true).catch(() => false);
await new Promise(r => setTimeout(r, 400));
const agentOpts = await p.$$eval('#new-session option', o => o.map(x => x.value));
await p.screenshot({ path: SNAP + '\\new1-modal.png' });
// fill + create (session left empty -> scaffold only, no live dispatch)
const NAME = 'ui new verify';
await p.type('#new-name', NAME);
await p.type('#new-script', 'A quick explainer about compound interest.');
const since = await p.evaluate(() => window.__toasts.length);
await p.evaluate(() => [...document.querySelectorAll('#newModal button')].find(x => x.textContent.includes('Create')).click());
const t0 = Date.now(); let toast = null;
while (Date.now() - t0 < 15000) { const a = await p.evaluate(() => window.__toasts.slice()); if (a.length > since) { toast = a[a.length - 1]; break; } await new Promise(r => setTimeout(r, 250)); }
const modalClosed = await p.evaluate(() => getComputedStyle(document.querySelector('#newModal')).display === 'none');
await b.close();
console.log(`modal opened: ${modalShown}`);
console.log(`agent options: [${agentOpts.join(', ')}]`);
console.log(`create toast: ${toast}`);
console.log(`modal closed after create: ${modalClosed}`);
console.log(`scaffold on disk: ${fs.existsSync('D:\\ClaudeProjects\\NOLAN\\render-service\\_lab_hyperframes\\videos\\ui-new-verify')}`);
console.log(`page errors: ${errs.length ? errs.join(' | ') : '(none)'}`);
