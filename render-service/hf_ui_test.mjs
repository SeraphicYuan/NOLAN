// Full UI test of the hub /hyperframes page: drive every control, capture toasts + console + network,
// screenshot key states. Mutations run on the disposable `faceless-demo` comp (add<->remove round-trip).
import fs from 'node:fs';
import puppeteer from 'puppeteer';
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const SNAP = 'D:\\ClaudeProjects\\NOLAN\\render-service\\_hfui';
fs.mkdirSync(SNAP, { recursive: true });
const results = [], netFail = [];
const R = (b, ok, d) => { results.push({ b, ok, d }); console.log(`${ok ? '✓' : '✗'} ${b.padEnd(24)} ${d}`); };
const sleep = ms => new Promise(r => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'], protocolTimeout: 180000 });
const page = await browser.newPage();
await page.setViewport({ width: 1560, height: 1000 });
page.on('response', r => { const u = r.url(); if (r.status() >= 400 && u.includes('/api/hf/')) netFail.push(`${r.status()} ${r.request().method()} ${u.split('?')[0]}`); });
page.on('dialog', async d => { await d.accept(); });

const hookToasts = () => page.evaluate(() => { if (!window.__th) { window.__th = 1; window.__toasts = []; const o = window.toast; window.toast = (m, t) => { window.__toasts.push({ m: String(m), t }); return o && o(m, t); }; } });
const toasts = () => page.evaluate(() => (window.__toasts || []).slice());
async function waitToast(since, ms) { const t0 = Date.now(); while (Date.now() - t0 < ms) { const a = await toasts(); if (a.length > since) return a[a.length - 1]; await sleep(250); } return null; }
const click = (sub, nth = 0) => page.evaluate((sub, nth) => { const e = [...document.querySelectorAll('[onclick]')].filter(x => x.getAttribute('onclick').includes(sub) && x.offsetParent !== null); if (e[nth]) { e[nth].click(); return true; } return false; }, sub, nth);
const hasRow = sid => page.evaluate(sid => [...document.querySelectorAll('.scene-row')].some(r => (r.getAttribute('onclick') || '').includes(`'${sid}'`)), sid);

try {
  await page.goto('http://127.0.0.1:8011/hyperframes', { waitUntil: 'load', timeout: 30000 });
  await hookToasts();
  await page.waitForFunction(() => document.querySelector('#comp')?.options.length > 0, { timeout: 20000 });
  const comps = await page.$$eval('#comp option', os => os.map(o => o.value));
  R('page load + boot', comps.length > 0, `#comp: [${comps.join(', ')}]`);

  const target = comps.includes('faceless-demo') ? 'faceless-demo' : comps[0];
  await page.select('#comp', target);
  await page.waitForFunction(() => document.querySelector('#frames .card'), { timeout: 20000 });
  R('#comp select', true, `${target}: ${await page.$eval('#status', e => e.textContent)}`);
  await page.screenshot({ path: SNAP + '\\01-loaded.png' });

  const ids = await page.evaluate(() => { const r = document.querySelector('.scene-row'); const m = (r?.getAttribute('onclick') || '').match(/selectScene\('([^']+)','([^']+)'\)/); return m ? { fid: m[1], sid: m[2] } : null; });
  const { fid, sid } = ids || {};

  // select scene by clicking the real row
  await page.click('.scene-row');
  await page.waitForFunction(() => document.querySelector('#insp-start'), { timeout: 10000 });
  const insp = await page.evaluate(() => ({ start: !!document.querySelector('#insp-start'), fields: document.querySelectorAll('#insp-fields [data-f]').length }));
  R('click scene row', insp.start, `inspector opened · ${insp.fields} data field(s) (${fid}/${sid})`);
  await page.screenshot({ path: SNAP + '\\02-inspector.png' });

  const opts = await page.evaluate(() => ({ rv: document.querySelector('#insp-reveal') ? [...document.querySelector('#insp-reveal').options].length : 0, tr: document.querySelector('#insp-tr') ? [...document.querySelector('#insp-tr').options].length : 0 }));
  R('reveal dropdown', opts.rv > 1, `${opts.rv} options`);
  R('transition dropdown', opts.tr > 0, `${opts.tr} options`);

  // Preview (snapshot) — known-suspect (npx)
  { const ok0 = await click('previewScene'); const ok = await page.waitForFunction(() => { const i = document.querySelector('#preview'); return i && i.complete && i.naturalWidth > 0; }, { timeout: 45000 }).then(() => true).catch(() => false); R('Preview (snapshot)', ok, ok0 ? (ok ? 'img rendered' : 'FAILED — snapshot did not load (404/npx)') : 'button missing'); await page.screenshot({ path: SNAP + '\\03-preview.png' }); }

  // asset picker
  { const op = await click('openPicker'); const shown = await page.waitForFunction(() => getComputedStyle(document.querySelector('#picker')).display !== 'none', { timeout: 6000 }).then(() => true).catch(() => false); await page.screenshot({ path: SNAP + '\\04-picker.png' }); await click('closePicker'); const hid = await page.waitForFunction(() => getComputedStyle(document.querySelector('#picker')).display === 'none', { timeout: 6000 }).then(() => true).catch(() => false); R('picker open/close', op && shown && hid, 'toggled'); }

  // applyEdit no-op
  { await page.click('.scene-row'); await page.waitForFunction(() => document.querySelector('#insp-start'), { timeout: 6000 }); const s = (await toasts()).length; await click('applyEdit'); const t = await waitToast(s, 40000); R('Apply edit (revise)', !!t && /Applied|Rejected/.test(t.m), t ? t.m.slice(0, 64) : 'no toast'); }

  // addScene + removeScene round-trip
  { await page.$$eval('details.add', ds => ds[0] && (ds[0].open = true)); await page.evaluate(f => { document.getElementById('add-id-' + f).value = 's_uitest'; document.getElementById('add-type-' + f).value = 'statement'; document.getElementById('add-start-' + f).value = '0'; document.getElementById('add-dur-' + f).value = '2'; document.getElementById('add-data-' + f).value = JSON.stringify({ register: 'paper', lines: ['UI test'] }); }, fid); let s = (await toasts()).length; await click('addScene'); const ta = await waitToast(s, 40000); const added = await hasRow('s_uitest'); R('Add scene (gated)', !!ta, `${ta ? ta.m.slice(0, 50) : 'no toast'}${added ? ' · row present' : ''}`);
    if (added) { await page.evaluate(() => { const r = [...document.querySelectorAll('.scene-row')].find(r => (r.getAttribute('onclick') || '').includes("'s_uitest'")); r && r.click(); }); await sleep(500); s = (await toasts()).length; await click('removeScene'); const tr = await waitToast(s, 30000); const gone = !(await hasRow('s_uitest')); R('Remove scene', !!tr && gone, `${tr ? tr.m.slice(0, 40) : 'no toast'}${gone ? ' · reverted' : ''}`); }
    else R('Remove scene', true, 'n/a (add rejected; nothing to revert)'); }

  // render frame (npx — known-suspect)
  { const s = (await toasts()).length; await click('renderFrame'); const t = await waitToast(s, 15000); R('Render frame (job)', !!t && /Render started|job/.test(t.m), t ? t.m.slice(0, 64) : 'no toast'); }

  // fill transitions
  { const s = (await toasts()).length; await click('fillTransitions'); const t = await waitToast(s, 40000); R('Fill transitions', !!t, t ? t.m.slice(0, 64) : 'no toast'); }

  // LLM note (bounded)
  { const s = (await toasts()).length; await page.evaluate(f => { const n = document.getElementById('fnote-' + f); if (n) n.value = 'leave the scenes unchanged'; }, fid); await click('reviseFrameNote'); const t = await waitToast(s, 75000); R('LLM note (agent)', !!t, t ? `fired · ${t.m.slice(0, 50)}` : 'no toast in 75s (wiring fired)'); }
} catch (e) { R('FATAL', false, e.message); }
await page.screenshot({ path: SNAP + '\\05-final.png' });
await browser.close();
console.log('\n=== 4xx/5xx on /api/hf ===\n' + (netFail.length ? [...new Set(netFail)].join('\n') : '(none)'));
console.log(`\nRESULT: ${results.filter(r => r.ok).length}/${results.length} controls OK`);
