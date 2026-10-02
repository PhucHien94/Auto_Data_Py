// Xác nhận dứt điểm: storefront lottemart.vn có review kèm ảnh khách không.
//   node scripts/inspect-review-api.mjs [url-san-pham]

import { chromium } from 'playwright';

const PRODUCT = process.argv[2]
  ?? 'https://www.lottemart.vn/vi-nsg/product/trung-vit-vfood-hop-10-qua-8936013680040-p8066';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

const xhr = [];
page.on('response', async (r) => {
  const u = r.url();
  if (/google|doubleclick|facebook|analytics|gtm|clarity|gstatic|fonts/i.test(u)) return;
  if (!['xhr', 'fetch'].includes(r.request().resourceType())) return;
  xhr.push({ status: r.status(), line: `${r.request().method()} ${u}` });
});

console.log('=== ' + PRODUCT + ' ===\n');
await page.goto(PRODUCT, { waitUntil: 'domcontentloaded', timeout: 60_000 });
await page.waitForTimeout(8000);

// Review thường lazy-load khi cuộn tới
for (let i = 0; i < 6; i++) {
  await page.evaluate(() => window.scrollBy(0, window.innerHeight));
  await page.waitForTimeout(2500);
}
await page.waitForTimeout(4000);

console.log('Title:', await page.title());
console.log('URL cuoi:', page.url());

const dom = await page.evaluate(() => {
  const text = document.body.innerText || '';
  const m = text.match(/.{0,80}(đánh giá|nhận xét|review|bình luận).{0,80}/gi) || [];
  return {
    hasReviewWord: m.slice(0, 6),
    // ảnh không thuộc CDN catalog -> nghi là ảnh khách upload
    imgs: [...document.querySelectorAll('img')].map((i) => i.src)
      .filter((s) => s && s.startsWith('http')),
    starEls: document.querySelectorAll('[class*="star" i],[class*="rating" i],[class*="review" i]').length,
  };
});

console.log('\n--- Cum tu lien quan review tren trang ---');
console.log(dom.hasReviewWord.length ? dom.hasReviewWord.join('\n') : '  (khong co)');
console.log(`\n--- Element co class star/rating/review: ${dom.starEls}`);

const catalog = dom.imgs.filter((s) => s.includes('/media/catalog/'));
const other = [...new Set(dom.imgs.filter((s) => !s.includes('/media/catalog/')))];
console.log(`\n--- Anh: ${dom.imgs.length} tong | catalog: ${catalog.length} | khac: ${other.length}`);
for (const s of other.slice(0, 12)) console.log('    ' + s.slice(0, 130));

const uniq = [...new Map(xhr.map((x) => [x.line, x])).values()];
const review = uniq.filter((x) => /review|rating|comment|feedback|ugc/i.test(x.line));
console.log(`\n--- XHR lien quan review: ${review.length}`);
for (const x of review) console.log(`    ${x.status}  ${x.line.slice(0, 160)}`);

console.log(`\n--- Toan bo API storefront (${uniq.length}) ---`);
for (const x of uniq.filter((x) => x.line.includes('/v1/p/mart/'))) {
  console.log(`    ${x.status}  ${x.line.slice(0, 160)}`);
}

await browser.close();
