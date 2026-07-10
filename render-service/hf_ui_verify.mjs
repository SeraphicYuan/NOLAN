import fs from 'node:fs';
import puppeteer from 'puppeteer';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const SNAP = 'D:\\ClaudeProjects\\NOLAN\\render-service\\_hfui';
fs.mkdirSync(SNAP, { recursive: true });
const errs = [];
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'], protocolTimeout: 60000 });
const page = await browser.newPage();
await page.setViewport({ width: 1560, height: 1040 });
page.on('pageerror', e => errs.push(e.message));
await page.goto('http://127.0.0.1:8011/hyperframes', { waitUntil: 'load', timeout: 30000 });
await page.waitForFunction(() => document.querySelector('#comp')?.options.length > 0, { timeout: 20000 });
const comps = await page.$$eval('#comp option', o => o.map(x => x.value));
// prefer a multi-frame comp
let target = comps[0];
for (const c of comps) { await page.select('#comp', c); await page.waitForFunction(() => document.querySelector('#frames .card'), { timeout: 15000 }); const n = await page.$$eval('#frames .card', c => c.length); if (n > 1) { target = c; break; } }
await page.select('#comp', target);
await page.waitForFunction(() => document.querySelector('#frames .card'), { timeout: 15000 });
await new Promise(r => setTimeout(r, 400));
const frameCards = await page.$$eval('#frames .card', c => c.length);
const fillBtns = await page.evaluate(() => [...document.querySelectorAll('button')].filter(b => /Fill transitions/.test(b.textContent)).length);
const addInCards = await page.$$eval('#frames', f => f[0].querySelectorAll('details.add, textarea').length);
const panelHasActions = await page.evaluate(() => !!document.querySelector('#framePanel .fp-actions'));
await page.screenshot({ path: SNAP + '\\v1-layout.png' });

// switch active frame by clicking the 2nd frame header
let switched = 'n/a';
if (frameCards > 1) {
  const before = await page.$eval('#framePanel .id', e => e.textContent);
  await page.evaluate(() => document.querySelectorAll('#frames .frame-head.clickable')[1].click());
  await new Promise(r => setTimeout(r, 250));
  const after = await page.$eval('#framePanel .id', e => e.textContent);
  switched = `${before} -> ${after} (${before !== after ? 'OK' : 'SAME'})`;
}

// mention autocomplete
await page.focus('#fnote');
await page.type('#fnote', 'try @');
await new Promise(r => setTimeout(r, 250));
const popShown = await page.evaluate(() => { const p = document.querySelector('.mention-pop'); return p && p.style.display !== 'none' ? p.querySelectorAll('.mention-item').length : 0; });
const firstItems = await page.evaluate(() => [...document.querySelectorAll('.mention-pop .mention-item b')].slice(0, 6).map(b => b.textContent));
await page.screenshot({ path: SNAP + '\\v2-mention.png' });
// filter to reveals
await page.type('#fnote', 'reveal:sc');
await new Promise(r => setTimeout(r, 250));
const revItems = await page.evaluate(() => [...document.querySelectorAll('.mention-pop .mention-item b')].map(b => b.textContent));

await browser.close();
console.log(`comp: ${target}  frames(cards): ${frameCards}`);
console.log(`"Fill transitions" buttons in DOM: ${fillBtns}  (expect 1, was = #frames)`);
console.log(`add-form/textarea INSIDE frame cards: ${addInCards}  (expect 0 — moved to panel)`);
console.log(`framePanel has actions: ${panelHasActions}`);
console.log(`active-frame switch on header click: ${switched}`);
console.log(`@ autocomplete items: ${popShown}  first: [${firstItems.join(', ')}]`);
console.log(`@reveal:sc filtered -> [${revItems.join(', ')}]`);
console.log(`page errors: ${errs.length ? errs.join(' | ') : '(none)'}`);
