// Chạy bộ ảnh nhúng trong ImageSearch_TopKeywords_100_*.xlsx qua 3 cơ chế,
// lưu response thô + top-40 đã rút gọn để đổ vào Excel.
//
//   node scripts/run-excel-top40.mjs                 chạy tất cả
//   node scripts/run-excel-top40.mjs --only kw001    lọc theo image_id
//   node scripts/run-excel-top40.mjs --force         chạy lại ảnh đã có kết quả
//   node scripts/run-excel-top40.mjs --only kw128 --round 2026-09-28
//        ảnh BỔ SUNG cho vòng đánh giá cũ: ghi round = ngày đó để dashboard/Excel
//        không mở vòng mới; ran_at vẫn là giờ chạy thật (user 2026-09-29)
//
// Gọi thẳng API bằng fetch trong page context thay vì bấm dropdown: cùng origin,
// cùng cookie, nhưng chủ động được params và không dính 3 request trùng của UI.
// imageRef KHÔNG tái dùng được giữa các cơ chế (backend trả 410 IMAGE_REF_EXPIRED
// ngay lập tức - đã đo), nên mỗi cặp (ảnh, cơ chế) vẫn là một lượt upload riêng.

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { PLAYGROUND_URL, MODES, FIXED_PARAMS, PACING } from './config.mjs';
import { openProfile, firstPage } from './lib/session.mjs';

const args = process.argv.slice(2);
const flag = (n) => args.includes(n);
const val = (n) => { const i = args.indexOf(n); return i === -1 ? null : args[i + 1]; };

// --lang en|ko|... (user 2026-09-29): chạy lại cùng bộ ảnh với ngôn ngữ payload khác để so với vi.
// Ngôn ngữ nằm cả trong đường dẫn API lẫn params. Kết quả khác vi thì PHẢI ghi ra --out riêng,
// không thì đè mất kết quả vi mà dashboard/Excel đang dùng.
const LANG = val('--lang') ?? FIXED_PARAMS.langSelect;      // mặc định vi
const STORE = FIXED_PARAMS.storeSelect;    // nsg
const API = `https://dev-gateway.martonline.lotte.vn/api/v2/${LANG}/${STORE}/products/search-by-image`;
const PAGE_SIZE = 100;     // giữ đúng mặc định UI; top-40 cắt ra khi xuất Excel
const TOP_N = 40;
const OUT = path.resolve(val('--out') ?? 'results/excel_top40');
if (LANG !== FIXED_PARAMS.langSelect && !val('--out')) {
  console.error(`--lang ${LANG} phải đi kèm --out <thư mục riêng> để không đè kết quả ${FIXED_PARAMS.langSelect}.`);
  process.exit(1);
}
const MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif' };

let manifest = JSON.parse(fs.readFileSync(path.resolve('images/excel_keywords/manifest.json'), 'utf8'));
if (val('--only')) {
  const ids = val('--only').split(',').map((s) => s.trim());
  manifest = manifest.filter((r) => ids.includes(r.image_id));
}
if (!manifest.length) { console.error('Không còn ảnh nào sau khi lọc.'); process.exit(1); }

for (const m of MODES) fs.mkdirSync(path.join(OUT, m), { recursive: true });

const context = await openProfile({ headless: !flag('--headed') });
const page = await firstPage(context);
await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('input[placeholder="Tìm kiếm"]', { timeout: 90_000 });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function call(mode, file) {
  const b64 = fs.readFileSync(file).toString('base64');
  const mime = MIME[path.extname(file).toLowerCase()] ?? 'image/png';
  return page.evaluate(async ({ API, b64, mime, mode, name, PAGE_SIZE, STORE, LANG }) => {
    const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const fd = new FormData();
    fd.append('image', new File([bin], name, { type: mime }));
    fd.append('params', JSON.stringify({
      imageMode: mode, sort: 'relevance', storeId: STORE, lang: LANG,
      page: 1, pageSize: PAGE_SIZE, filters: {},
    }));
    const t0 = performance.now();
    const r = await fetch(API, { method: 'POST', body: fd });
    const text = await r.text();
    const clientMs = Math.round(performance.now() - t0);
    try { return { status: r.status, clientMs, body: JSON.parse(text) }; }
    catch { return { status: r.status, clientMs, text: text.slice(0, 500) }; }
  }, { API, b64, mime, mode, name: path.basename(file), PAGE_SIZE, STORE, LANG });
}

const issues = [];
const total = manifest.length * MODES.length;
let done = 0;

for (const row of manifest) {
  const file = path.resolve('images', row.file);
  for (const mode of MODES) {
    done++;
    const outFile = path.join(OUT, mode, `${row.image_id}.json`);
    // Bỏ qua chỉ khi kết quả cũ chạy trên ĐÚNG file ảnh này. imageRef backend
    // trả về là sha256 của chính file, nên so nó với hash file hiện tại là biết
    // ảnh trong Excel có bị thay hay không — thay ảnh mà vẫn giữ tên keyword cũ
    // thì phải chạy lại, không thì báo cáo hiện kết quả của ảnh đã bị xoá.
    if (fs.existsSync(outFile) && !flag('--force')) {
      const prev = JSON.parse(fs.readFileSync(outFile, 'utf8'));
      const sha = 'sha256:' + crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
      if (prev.ok && prev.image_ref === sha) {
        console.log(`[${done}/${total}] ${row.image_id} / ${mode} — đã có, bỏ qua`);
        continue;
      }
      console.log(`[${done}/${total}] ${row.image_id} / ${mode} — ${prev.ok ? 'ẢNH ĐÃ ĐỔI' : 'lượt cũ lỗi'}, chạy lại`);
    }
    process.stdout.write(`[${done}/${total}] ${row.image_id} "${row.keyword}" / ${mode} ... `);

    let res = null;
    // vector_titan chập chờn (503 EMBEDDING_UNAVAILABLE) -> thử lại tối đa 3 lần
    for (let attempt = 1; attempt <= 3; attempt++) {
      res = await call(mode, file);
      if (res.status === 200) break;
      const code = res.body?.downstream?.error?.code ?? res.body?.title ?? res.text ?? '?';
      process.stdout.write(`${res.status} ${String(code).slice(0, 40)}, thử lại... `);
      await sleep(3000 * attempt);
    }

    const ok = res.status === 200 && res.body?.resolvedImageMode === mode;
    const b = res.body ?? {};
    const products = Array.isArray(b.products) ? b.products : [];

    fs.writeFileSync(outFile, JSON.stringify({
      image_id: row.image_id, excel_row: row.excel_row, keyword: row.keyword, lang: row.lang,
      image_file: row.file, mode_requested: mode, ran_at: new Date().toISOString(),
      round: val('--round') ?? new Date().toISOString().slice(0, 10),
      api: API, params: { imageMode: mode, sort: 'relevance', storeId: STORE, lang: LANG, page: 1, pageSize: PAGE_SIZE },
      http_status: res.status, ok,
      image_ref: b.imageRef ?? null,
      resolved_image_mode: b.resolvedImageMode ?? null,
      total_hits: b.totalHits ?? null,
      returned: products.length,
      took_ms: b.tookMs ?? null, client_ms: res.clientMs,
      caption: b.caption ?? null,
      top: products.slice(0, TOP_N).map((p, i) => ({
        no: i + 1, sku: p.sku, product_id: p.productId, name: p.name,
        in_stock: p.inStock, stock_qty: p.stockQty, price: p.price, original_price: p.originalPrice,
        brand: p.brand, category: p.category, category_ids: p.categoryIds,
        image_url: p.imageUrl, url_key: p.urlKey, promotion: p.promotion,
        sponsored: p.sponsored, pinned: p.pinned,
      })),
      response: res.body ?? { text: res.text },
    }, null, 2));

    if (ok) {
      const cap = b.caption?.outcome ? ` caption=${b.caption.outcome}/${b.caption.query ?? '-'}` : '';
      console.log(`${b.totalHits} total, ${products.length} trả về, ${b.tookMs}ms${cap}`);
    } else {
      const code = b?.downstream?.error?.code ?? b?.title ?? res.text ?? '?';
      console.log(`LỖI ${res.status} ${String(code).slice(0, 60)}`);
      issues.push(`${row.image_id}/${mode}: HTTP ${res.status} ${String(code).slice(0, 80)}`);
    }
    await sleep(PACING.delayBetweenSearchesMs);
  }
}

await context.close();
if (issues.length) {
  fs.writeFileSync(path.join(OUT, 'run-issues.txt'), issues.join('\n'));
  console.log(`\n${issues.length} lượt lỗi:`); issues.forEach((i) => console.log('  ! ' + i));
}
console.log(`\nKết quả thô: ${OUT}/<mode>/<image_id>.json`);
