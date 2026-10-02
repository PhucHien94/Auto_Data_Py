// Dump mọi <select> trên trang sau khi upload ảnh, kèm option value thật.
// Dùng khi UI đổi và selector trong config.mjs không còn khớp.
//   node scripts/inspect-ui.mjs

import fs from 'node:fs';
import path from 'node:path';
import { PLAYGROUND_URL, SELECTORS } from './config.mjs';
import { openProfile, firstPage } from './lib/session.mjs';

const sample = path.resolve('tests/fixtures/synthetic-pan.png');

// openProfile đặt sẵn viewport 1440x900: hẹp hơn thì layout responsive
// giấu ô tìm kiếm và nút camera không tồn tại trong DOM
const context = await openProfile({ headless: true });
const page = await firstPage(context);

await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });
// App Angular hydrate chậm, phải chờ ô tìm kiếm render xong mới có nút camera
await page.waitForSelector('input[placeholder="Tìm kiếm"]', { timeout: 90_000 });
await page.click(SELECTORS.cameraButton, { timeout: 60_000 });
await page.setInputFiles(SELECTORS.fileInput, sample);
await page.waitForSelector('select', { timeout: 20_000 });
await page.waitForTimeout(2000);

const selects = await page.locator('select').evaluateAll((nodes) =>
  nodes.map((el, i) => ({
    index: i,
    id: el.id || null,
    name: el.getAttribute('name') || null,
    className: el.className || null,
    labelText: el.closest('label')?.innerText?.trim().slice(0, 60)
      || el.previousElementSibling?.innerText?.trim().slice(0, 60)
      || el.parentElement?.innerText?.trim().slice(0, 60)
      || null,
    value: el.value,
    options: [...el.options].map((o) => ({ value: o.value, text: o.text.trim().slice(0, 70) })),
  }))
);

console.log(JSON.stringify(selects, null, 2));
fs.writeFileSync('ui-selects.json', JSON.stringify(selects, null, 2));
console.log('\n-> ui-selects.json');

await browser.close();
