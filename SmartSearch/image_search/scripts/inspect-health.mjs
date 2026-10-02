// Một lần chẩn đoán: trang đang ở trạng thái nào, API trả gì, lỗi console ra sao.
// Không retry, không vòng lặp — tránh dội request vào dev console.
//   node scripts/inspect-health.mjs


import { PLAYGROUND_URL } from './config.mjs';
import { openProfile, firstPage } from './lib/session.mjs';

const context = await openProfile({ headless: true });

const page = await firstPage(context);

const api = [];
const errors = [];
page.on('response', (r) => {
  if (r.url().includes('/api/')) api.push({ status: r.status(), url: r.url().slice(0, 110) });
});
page.on('pageerror', (e) => errors.push(String(e).slice(0, 160)));
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(m.text().slice(0, 160));
});

const t0 = Date.now();
await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });
console.log(`domcontentloaded sau ${Date.now() - t0}ms`);

await page.waitForTimeout(30_000);

console.log('\nURL  :', page.url());
console.log('Title:', await page.title());

const dom = await page.evaluate(() => ({
  inputs: document.querySelectorAll('input').length,
  selects: document.querySelectorAll('select').length,
  buttons: document.querySelectorAll('button').length,
  placeholders: [...document.querySelectorAll('input')].map((i) => i.placeholder).filter(Boolean),
  text: (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 300),
}));

console.log('\nDOM:', { inputs: dom.inputs, selects: dom.selects, buttons: dom.buttons });
console.log('Placeholder:', dom.placeholders);
console.log('\nText đầu trang:\n  ' + dom.text);

console.log(`\nCall /api/ (${api.length}):`);
for (const a of api.slice(0, 15)) console.log(`  ${a.status}  ${a.url}`);

console.log(`\nLỗi console (${errors.length}):`);
for (const e of [...new Set(errors)].slice(0, 10)) console.log('  ' + e);

await page.screenshot({ path: 'health.png' });
console.log('\nẢnh màn hình -> health.png');
await context.close();
