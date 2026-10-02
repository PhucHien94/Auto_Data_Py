// Hook fetch/XHR trong page để đọc tên field FormData mà UI gửi lên search-by-image.
// Đây là nguồn của hợp đồng API dùng trong run-excel-top40.mjs:
//   image=<file> + params={"imageMode","sort","storeId","lang","page","pageSize","filters"}
import path from 'node:path';
import { PLAYGROUND_URL, SELECTORS } from './config.mjs';
import { openProfile, firstPage } from './lib/session.mjs';

const img = path.resolve('images/excel_keywords/kw009_kem-danh-rang.png');
const context = await openProfile({ headless: true });
const page = await firstPage(context);

await page.addInitScript(() => {
  window.__cap = [];
  const describe = (body) => {
    if (body instanceof FormData) {
      const out = [];
      for (const [k, v] of body.entries()) {
        out.push(v instanceof File || v instanceof Blob
          ? `${k}=<file ${v.name ?? ''} ${v.type ?? ''} ${v.size}b>`
          : `${k}=${String(v).slice(0, 120)}`);
      }
      return { type: 'FormData', entries: out };
    }
    if (typeof body === 'string') return { type: 'string', body: body.slice(0, 600) };
    return { type: typeof body };
  };
  const of = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : input?.url;
    if (url && url.includes('search-by-image')) {
      window.__cap.push({ via: 'fetch', url, method: init?.method,
        headers: init?.headers ? JSON.parse(JSON.stringify(init.headers)) : null,
        body: describe(init?.body) });
    }
    return of.apply(this, arguments);
  };
  const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; this.__m = m; return oo.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (b) {
    if (this.__u && String(this.__u).includes('search-by-image')) {
      window.__cap.push({ via: 'xhr', url: this.__u, method: this.__m, body: describe(b) });
    }
    return os.apply(this, arguments);
  };
});

await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('input[placeholder="Tìm kiếm"]', { timeout: 90_000 });
await page.click(SELECTORS.cameraButton, { timeout: 60_000 });
await page.setInputFiles(SELECTORS.fileInput, img);
await page.waitForTimeout(8000);
console.log(JSON.stringify(await page.evaluate(() => window.__cap), null, 2));
await context.close();
