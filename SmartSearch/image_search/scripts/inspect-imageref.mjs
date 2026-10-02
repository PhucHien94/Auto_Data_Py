// imageRef tái dùng được tới đâu? Chạy ma trận rồi in bảng.
//   node scripts/inspect-imageref.mjs
//
// Lần đo trước chỉ thử ĐÚNG MỘT ca — lấy ref từ lượt `vector` rồi hỏi
// `vector_titan` / `caption` — thấy 410 rồi kết luận "ref không tái dùng được".
// Kết luận đó rộng hơn bằng chứng. Các ca cần tách bạch:
//
//   - cùng cơ chế với lượt đã tạo ra ref  (ref có thể gắn theo loại embedding)
//   - khác cơ chế
//   - ref đặt trong params vs đặt thành field riêng của form
//   - sau 30s / 120s  (TTL thật là bao lâu)
//
// Chạy xong đọc cột "kết quả": 200 = dùng lại được, 410 = backend từ chối.

import fs from 'node:fs';
import path from 'node:path';
import { PLAYGROUND_URL, FIXED_PARAMS } from './config.mjs';
import { openProfile, firstPage } from './lib/session.mjs';

const LANG = FIXED_PARAMS.langSelect, STORE = FIXED_PARAMS.storeSelect;
const API = `https://dev-gateway.martonline.lotte.vn/api/v2/${LANG}/${STORE}/products/search-by-image`;
const FILE = path.resolve(process.argv[2] ?? 'images/excel_keywords/kw009_kem-danh-rang.png');
const b64 = fs.readFileSync(FILE).toString('base64');
const baseParams = { sort: 'relevance', storeId: STORE, lang: LANG, page: 1, pageSize: 100, filters: {} };

const context = await openProfile({ headless: true });
const page = await firstPage(context);
await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('input[placeholder="Tìm kiếm"]', { timeout: 90_000 });

// where: 'file' | 'params' | 'field'  — ref nằm trong params hay là field riêng
const call = (mode, { where = 'file', ref = null } = {}) =>
  page.evaluate(async ({ API, b64, mode, where, ref, name, baseParams }) => {
    const fd = new FormData();
    const params = { imageMode: mode, ...baseParams };
    if (where === 'file') {
      const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      fd.append('image', new File([bin], name, { type: 'image/png' }));
    } else if (where === 'params') {
      params.imageRef = ref;
    } else if (where === 'field') {
      fd.append('imageRef', ref);
    }
    fd.append('params', JSON.stringify(params));
    const r = await fetch(API, { method: 'POST', body: fd });
    const t = await r.text();
    try { return { status: r.status, body: JSON.parse(t) }; }
    catch { return { status: r.status, text: t.slice(0, 200) }; }
  }, { API, b64, mode, where, ref, name: path.basename(FILE), baseParams });

const rows = [];
const note = (ca, r) => {
  const b = r.body ?? {};
  const code = b?.downstream?.error?.code ?? b?.title ?? b?.detail ?? r.text ?? '';
  rows.push({
    ca,
    kq: r.status,
    mode: b.resolvedImageMode ?? '-',
    hits: b.totalHits ?? '-',
    ghichu: r.status === 200 ? '' : String(code).slice(0, 60),
  });
  console.log(`  ${ca.padEnd(46)} ${r.status}  ${b.resolvedImageMode ?? ''} ${b.totalHits ?? String(code).slice(0, 50)}`);
};

console.log(`Ảnh: ${path.basename(FILE)}\n`);
console.log('— upload thật để lấy ref —');
const up = await call('vector');
note('upload file, imageMode=vector', up);
const ref = up.body?.imageRef;
if (!ref) { console.log('Không lấy được imageRef, dừng.'); await context.close(); process.exit(1); }
console.log(`  ref = ${ref}\n`);

console.log('— dùng lại ref, ref nằm trong params —');
note('ref + vector (CÙNG cơ chế đã tạo ref)', await call('vector', { where: 'params', ref }));
note('ref + vector_titan (khác cơ chế)', await call('vector_titan', { where: 'params', ref }));
note('ref + caption (khác cơ chế)', await call('caption', { where: 'params', ref }));

console.log('\n— dùng lại ref, ref là field riêng của form —');
note('field imageRef + vector', await call('vector', { where: 'field', ref }));
note('field imageRef + vector_titan', await call('vector_titan', { where: 'field', ref }));

console.log('\n— ref lấy từ lượt vector_titan, dùng lại cho chính vector_titan —');
const upT = await call('vector_titan');
note('upload file, imageMode=vector_titan', upT);
if (upT.body?.imageRef) {
  note('ref(titan) + vector_titan', await call('vector_titan', { where: 'params', ref: upT.body.imageRef }));
  note('ref(titan) + vector', await call('vector', { where: 'params', ref: upT.body.imageRef }));
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
console.log('\n— TTL: chờ rồi dùng lại chính ref ban đầu, cùng cơ chế vector —');
for (const s of [30, 90]) {
  await sleep(s * 1000);
  note(`ref + vector sau ${s}s`, await call('vector', { where: 'params', ref }));
}

fs.writeFileSync('imageref-matrix.json', JSON.stringify(rows, null, 2));
console.log('\nBảng đầy đủ: imageref-matrix.json');
await context.close();
