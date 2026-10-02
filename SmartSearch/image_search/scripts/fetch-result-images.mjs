// Tải ảnh sản phẩm của top-40 (cả 3 cơ chế) về một thư mục phẳng theo SKU,
// để dashboard trỏ ảnh bằng SKU mà không cần gọi CDN mỗi lần render.
//   node scripts/fetch-result-images.mjs [--force] [--concurrency 6]
import fs from 'node:fs';
import path from 'node:path';

const args = process.argv.slice(2);
const FORCE = args.includes('--force');
const CONC = Number(args[args.indexOf('--concurrency') + 1]) || 6;
const OUT = path.resolve('result_images');
fs.mkdirSync(OUT, { recursive: true });
// Nguồn: kết quả vi + mọi ngôn ngữ khác ở results/excel_top40_lang/<lang>/ (2026-09-29).
// index.csv được GHI LẠI TOÀN BỘ mỗi lần chạy, nên phải gom đủ mọi nguồn, sót 1 nguồn là
// dashboard của nguồn đó mất bảng tra ảnh.
const LANG_ROOT = path.resolve('results/excel_top40_lang');
const SRCS = [path.resolve('results/excel_top40'),
  ...(fs.existsSync(LANG_ROOT) ? fs.readdirSync(LANG_ROOT).map((d) => path.join(LANG_ROOT, d)).filter((d) => fs.statSync(d).isDirectory()) : [])];

// Gom SKU duy nhất + nơi nó xuất hiện (ảnh nào / cơ chế nào / hạng mấy)
const bySku = new Map();
for (const SRC of SRCS) for (const mode of fs.readdirSync(SRC).filter((d) => fs.statSync(path.join(SRC, d)).isDirectory())) {
  for (const f of fs.readdirSync(path.join(SRC, mode)).filter((f) => f.endsWith('.json'))) {
    const d = JSON.parse(fs.readFileSync(path.join(SRC, mode, f), 'utf8'));
    for (const p of d.top) {
      if (!p.image_url) continue;
      const e = bySku.get(p.sku) ?? { sku: p.sku, name: p.name, url: p.image_url, seen: [] };
      e.seen.push(`${d.image_id}:${mode}:#${p.no}`);
      bySku.set(p.sku, e);
    }
  }
}
const items = [...bySku.values()];
console.log(`${items.length} SKU duy nhất trong top-40 (${SRCS.length} nguồn: ${SRCS.map((d) => path.basename(d)).join(', ')})`);

const EXT = { 'image/webp': '.webp', 'image/jpeg': '.jpg', 'image/png': '.png', 'image/gif': '.gif' };
const results = [];
let done = 0, downloaded = 0, skipped = 0, failed = 0;

async function one(it) {
  const existing = ['.webp', '.jpg', '.png', '.gif'].map((e) => path.join(OUT, it.sku + e)).find(fs.existsSync);
  if (existing && !FORCE) { skipped++; results.push({ ...it, file: path.basename(existing), status: 'cached' }); return; }
  try {
    const r = await fetch(it.url, { headers: { referer: 'https://www.lottemart.vn/' } });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const ct = (r.headers.get('content-type') ?? '').split(';')[0];
    const file = it.sku + (EXT[ct] ?? path.extname(new URL(it.url).pathname) ?? '.jpg');
    fs.writeFileSync(path.join(OUT, file), Buffer.from(await r.arrayBuffer()));
    downloaded++;
    results.push({ ...it, file, status: 'ok' });
  } catch (e) {
    failed++;
    results.push({ ...it, file: '', status: 'FAIL: ' + e.message });
  } finally {
    if (++done % 100 === 0) process.stdout.write(`  ${done}/${items.length}\n`);
  }
}

const queue = [...items];
await Promise.all(Array.from({ length: CONC }, async () => { let it; while ((it = queue.shift())) await one(it); }));

const cell = (v) => /[",\n]/.test(String(v ?? '')) ? `"${String(v).replace(/"/g, '""')}"` : String(v ?? '');
fs.writeFileSync(path.join(OUT, 'index.csv'),
  ['sku,file,product_name,image_url,status,seen_in',
   ...results.sort((a, b) => a.sku.localeCompare(b.sku))
     .map((r) => [r.sku, r.file, r.name, r.url, r.status, r.seen.join('|')].map(cell).join(','))].join('\n'));

console.log(`tải mới ${downloaded}, có sẵn ${skipped}, lỗi ${failed}`);
console.log(`Ảnh: ${OUT}/<sku>.<ext>   Bảng tra: ${path.join(OUT, 'index.csv')}`);
