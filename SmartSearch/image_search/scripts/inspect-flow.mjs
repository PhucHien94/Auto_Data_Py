// Upload ảnh, đổi cơ chế, rồi dump MỌI request/response + mọi button trên trang.
// Dùng để phân biệt "không có request nào bắn ra" với "có bắn nhưng predicate sai".
//   node scripts/inspect-flow.mjs


import path from 'node:path';
import { PLAYGROUND_URL, SELECTORS, FIXED_PARAMS } from './config.mjs';
import { openProfile, firstPage } from './lib/session.mjs';

const sample = path.resolve('tests/fixtures/synthetic-pan.png');

const context = await openProfile({ headless: true });

const page = await firstPage(context);

const seen = [];
page.on('request', (r) => {
  if (['xhr', 'fetch'].includes(r.resourceType())) {
    seen.push({ phase: globalThis.__phase, method: r.method(), url: r.url() });
  }
});

globalThis.__phase = 'load';
await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('input[placeholder="Tìm kiếm"]', { timeout: 90_000 });

globalThis.__phase = 'upload';
await page.click(SELECTORS.cameraButton, { timeout: 60_000 });
await page.setInputFiles(SELECTORS.fileInput, sample);
await page.waitForSelector(SELECTORS.modeSelect, { timeout: 30_000 });
for (const [k, v] of Object.entries(FIXED_PARAMS)) {
  await page.selectOption(SELECTORS[k], v).catch(() => {});
}
await page.waitForTimeout(6000);

globalThis.__phase = 'selectMode';
await page.selectOption(SELECTORS.modeSelect, 'vector_titan');
await page.waitForTimeout(10000);

console.log('\n=== XHR/fetch theo từng giai đoạn ===');
for (const phase of ['load', 'upload', 'selectMode']) {
  const rows = seen.filter((s) => s.phase === phase);
  console.log(`\n[${phase}]  ${rows.length} request`);
  for (const r of rows) console.log(`   ${r.method} ${r.url.slice(0, 130)}`);
}

console.log('\n=== Button hiển thị trên trang ===');
const buttons = await page.locator('button:visible').evaluateAll((els) =>
  els.map((e, i) => ({
    i,
    text: (e.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 45),
    title: e.getAttribute('title'),
    type: e.getAttribute('type'),
    cls: (e.className || '').slice(0, 45),
  }))
);
for (const b of buttons) {
  console.log(`   [${b.i}] "${b.text}"  type=${b.type} title=${b.title} class=${b.cls}`);
}

await context.close();
