import puppeteer from 'puppeteer';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const SNAP = 'D:\\ClaudeProjects\\NOLAN\\render-service\\_hfui';
const errs = [];
const b = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'], protocolTimeout: 60000 });
const p = await b.newPage();
await p.setViewport({ width: 1560, height: 1040 });
p.on('pageerror', e => errs.push(e.message));
await p.goto('http://127.0.0.1:8011/hyperframes', { waitUntil: 'load', timeout: 30000 });
await p.waitForFunction(() => document.querySelector('#comp')?.options.length > 0, { timeout: 15000 });
await p.select('#comp', 'faceless-demo');
await p.waitForFunction(() => document.querySelector('#frames .card'), { timeout: 15000 });
await new Promise(r => setTimeout(r, 500));
// #2: frame video + badge
const vid = await p.evaluate(() => { const v = document.querySelector('.frame-vid'); return v ? { present: true, hasSrc: /frame-video/.test(v.src) } : { present: false }; });
const mp4Badge = await p.evaluate(() => !!document.querySelector('.badge.mp4'));
// #4: build-pool button (frame panel) + modal checkbox
const buildPoolBtn = await p.evaluate(() => [...document.querySelectorAll('#framePanel button')].some(x => /Build asset pool/.test(x.textContent)));
await p.evaluate(() => [...document.querySelectorAll('button')].find(x => x.textContent.includes('New essay')).click());
await p.waitForFunction(() => getComputedStyle(document.querySelector('#newModal')).display !== 'none', { timeout: 6000 }).catch(() => {});
const poolCheckbox = await p.evaluate(() => !!document.querySelector('#new-pool'));
await new Promise(r => setTimeout(r, 300));
await p.screenshot({ path: SNAP + '\\v23.png' });
await b.close();
console.log(`#2 frame <video> present: ${vid.present} (src->frame-video: ${vid.hasSrc})`);
console.log(`#2 "rendered" badge: ${mp4Badge}`);
console.log(`#4 "Build asset pool" button (panel): ${buildPoolBtn}`);
console.log(`#4 pool checkbox in New-essay modal: ${poolCheckbox}`);
console.log(`page errors: ${errs.length ? errs.join(' | ') : '(none)'}`);
