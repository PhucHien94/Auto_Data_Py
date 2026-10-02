// Dump status + hình dạng response của endpoint search-by-image.
// Trả lời: predicate trong runner sai chỗ nào, hay request đang lỗi thật.
//   node scripts/inspect-response.mjs

import path from 'node:path';
import { PLAYGROUND_URL, SELECTORS, FIXED_PARAMS, MODES } from './config.mjs';
import { openProfile, firstPage } from './lib/session.mjs';

const sample = path.resolve('tests/fixtures/synthetic-pan.png');

const context = await openProfile({ headless: true });
const page = await firstPage(context);

const hits = [];
page.on('response', async (res) => {
  if (!res.url().includes('search-by-image')) return;
  const rec = {
    phase: globalThis.__phase,
    status: res.status(),
    contentType: res.headers()['content-type'] || '(none)',
  };
  try {
    const body = await res.json();
    rec.topLevelKeys = Object.keys(body);
    rec.hasProducts = Array.isArray(body.products);
    rec.productCount = Array.isArray(body.products) ? body.products.length : null;
    rec.resolvedImageMode = body.resolvedImageMode ?? '(không có field này)';
    rec.totalHits = body.totalHits;
    rec.caption = body.caption;
    rec.tookMs = body.tookMs;
    rec.sample = JSON.stringify(body).slice(0, 500);
  } catch (e) {
    rec.jsonError = String(e).slice(0, 120);
    rec.text = (await res.text().catch(() => '')).slice(0, 300);
  }
  hits.push(rec);
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
await page.waitForTimeout(8000);

for (const mode of MODES) {
  globalThis.__phase = `mode:${mode}`;
  await page.selectOption(SELECTORS.modeSelect, mode);
  await page.waitForTimeout(8000);
}

console.log(`\n=== ${hits.length} response từ search-by-image ===`);
for (const h of hits) {
  console.log(`\n[${h.phase}]  HTTP ${h.status}   ${h.contentType.split(';')[0]}`);
  if (h.jsonError) {
    console.log(`   không parse được JSON: ${h.jsonError}`);
    console.log(`   body: ${h.text}`);
  } else {
    if (h.status !== 200) {
      // problem+json: in nguyên để còn báo dev
      console.log(`   ${h.sample}`);
    } else {
      console.log(`   keys            : ${h.topLevelKeys?.join(', ')}`);
      console.log(`   products[]      : ${h.hasProducts} (${h.productCount})`);
      console.log(`   resolvedImageMode: ${h.resolvedImageMode}`);
      console.log(`   totalHits       : ${h.totalHits}`);
      console.log(`   caption         : ${JSON.stringify(h.caption)}`);
      console.log(`   tookMs          : ${h.tookMs}`);
    }
  }
}

import('node:fs').then(fs=>fs.writeFileSync('response-shapes.json', JSON.stringify(hits,null,2)));
await context.close();
