// Thu thập ảnh sản phẩm từ công cụ tìm kiếm ảnh trên web.
//
//   node scripts/collect-web-images.mjs --dry-run          chỉ liệt kê URL
//   node scripts/collect-web-images.mjs --target 60        tải tới khi đủ 60 ảnh
//   node scripts/collect-web-images.mjs --per-product 2
//
// Đường đi: keyword -> search API (dev gateway) -> sku + categoryIds + tên sản phẩm
//           -> tìm ảnh theo tên -> tải về.
//
// ====================== ĐỌC TRƯỚC KHI DÙNG KẾT QUẢ ======================
// Ground truth ở đây là GIẢ ĐỊNH, không phải sự thật. Script gán exact_skus
// bằng SKU của sản phẩm đã dùng tên để tìm, nhưng ảnh trả về có thể là:
//   - đúng sản phẩm, khác bao bì / khác phiên bản năm
//   - sản phẩm cùng dòng nhưng khác dung tích  -> phải chuyển sang variant_skus
//   - sản phẩm hoàn toàn khác, hoặc ảnh quảng cáo ghép nhiều sản phẩm
// Vì vậy mọi dòng sinh ra đều có verified=0. PHẢI xem từng ảnh và sửa tay
// trước khi gộp vào manifest.csv, nếu không toàn bộ metric sẽ sai.
//
// Ảnh tải về thuộc bản quyền của trang gốc (cột source_page ghi lại nơi lấy).
// Dùng nội bộ để đánh giá model; không phân phối lại.
// ========================================================================

import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { openProfile, firstPage } from './lib/session.mjs';
import { PLAYGROUND_URL, PATHS, UPLOAD_LIMITS } from './config.mjs';

const args = process.argv.slice(2);
const flag = (n) => args.includes(n);
const val = (n) => { const i = args.indexOf(n); return i === -1 ? null : args[i + 1]; };

const DRY = flag('--dry-run');
const TARGET = Number(val('--target') ?? 60);
const PER_PRODUCT = Number(val('--per-product') ?? 2);
const PER_KEYWORD = Number(val('--per-keyword') ?? 8);
const DELAY_MS = 800;   // chậm tay với công cụ tìm kiếm, tránh bị chặn

const kwFile = val('--keywords');
const KEYWORDS = kwFile
  ? fs.readFileSync(kwFile, 'utf8').split('\n').map((s) => s.trim()).filter(Boolean)
  : ['chảo chống dính', 'nồi inox', 'bình giữ nhiệt', 'hộp đựng thực phẩm',
     'sữa tươi', 'mì gói', 'nước giặt', 'dầu gội', 'bánh quy', 'cà phê hoà tan'];

const outDir = path.resolve(PATHS.images, 'marketplace');
const manifestOut = path.resolve('manifest.web.csv');

fs.mkdirSync(outDir, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const cell = (v) => /[",\n]/.test(String(v ?? '')) ? `"${String(v).replace(/"/g, '""')}"` : String(v ?? '');

// --------------------------------------------------- lấy sản phẩm từ search API
const authCtx = await openProfile({ headless: true });
const authPage = await firstPage(authCtx);
await authPage.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });
await authPage.waitForSelector('input[placeholder="Tìm kiếm"]', { timeout: 90_000 });

const products = [];
for (const kw of KEYWORDS) {
  const found = await authPage.evaluate(async ({ kw, n }) => {
    try {
      const r = await fetch('https://dev-gateway.martonline.lotte.vn/api/v2/vi/nsg/products/search', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ query: kw, page: 1, pageSize: n }),
      });
      const b = await r.json();
      return (b.products || []).map((p) => ({
        productId: p.productId, sku: p.sku, name: p.name,
        categoryIds: p.categoryIds || [], brand: p.brand,
      }));
    } catch { return []; }
  }, { kw, n: PER_KEYWORD });
  for (const p of found) products.push({ ...p, keyword: kw });
}
await authCtx.close();
console.log(`${products.length} sản phẩm từ ${KEYWORDS.length} keyword\n`);

// --------------------------------------------------- tìm ảnh trên web
const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  locale: 'vi-VN',
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
           + '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
});
const page = await ctx.newPage();

const rows = [];
const seenUrls = new Set();
let blocked = 0;

for (const p of products) {
  if (rows.length >= TARGET) break;

  const q = p.name;
  const url = 'https://www.bing.com/images/search?q=' + encodeURIComponent(q);

  let hits = [];
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45_000 });
    await page.waitForTimeout(2500);
    // metadata ảnh thật nằm trong thuộc tính m (JSON) của a.iusc
    hits = await page.evaluate(() =>
      [...document.querySelectorAll('a.iusc')].map((a) => {
        try {
          const m = JSON.parse(a.getAttribute('m'));
          return { murl: m.murl, purl: m.purl };
        } catch { return null; }
      }).filter((x) => x && x.murl)
    );
  } catch {
    blocked++;
    console.log(`  ! không tải được kết quả cho "${q.slice(0, 40)}"`);
    await sleep(DELAY_MS * 3);
    continue;
  }

  let taken = 0;
  for (const h of hits) {
    if (taken >= PER_PRODUCT || rows.length >= TARGET) break;
    if (seenUrls.has(h.murl)) continue;
    seenUrls.add(h.murl);

    const ext = (path.extname(new URL(h.murl).pathname).split('?')[0] || '.jpg').toLowerCase();
    if (!UPLOAD_LIMITS.extensions.includes(ext)) continue;

    const imageId = `web_${p.productId}_${taken}`;
    const file = `${imageId}${ext}`;

    if (!DRY) {
      try {
        const r = await fetch(h.murl, {
          headers: { 'User-Agent': 'Mozilla/5.0' },
          signal: AbortSignal.timeout(20_000),
        });
        if (!r.ok) continue;
        const buf = Buffer.from(await r.arrayBuffer());
        if (buf.length > UPLOAD_LIMITS.maxBytes) continue;
        if (buf.length < 5000) continue;          // bỏ thumbnail quá nhỏ
        fs.writeFileSync(path.join(outDir, file), buf);
      } catch { continue; }
    }

    rows.push({
      image_id: imageId,
      file: `marketplace/${file}`,
      source: 'marketplace',
      keyword: p.keyword,
      exact_skus: p.sku,           // GIẢ ĐỊNH — phải xác minh bằng mắt
      variant_skus: '',
      category_ids: p.categoryIds.join('|'),
      difficulty: '',
      verified: 0,                 // 1 sau khi bạn đã xem và xác nhận
      source_page: h.purl ?? '',
      note: `${p.name.slice(0, 45)}`,
    });
    taken++;
  }

  console.log(`  ${String(taken).padStart(2)} ảnh | ${String(hits.length).padStart(3)} kết quả | ${q.slice(0, 50)}`);
  await sleep(DELAY_MS);
}

await browser.close();

const cols = ['image_id', 'file', 'source', 'keyword', 'exact_skus', 'variant_skus',
              'category_ids', 'difficulty', 'verified', 'source_page', 'note'];
if (!DRY) {
  fs.writeFileSync(manifestOut,
    [cols.join(','), ...rows.map((r) => cols.map((c) => cell(r[c])).join(','))].join('\n'));
}

console.log(`\n=== KẾT QUẢ ===`);
console.log(`Sản phẩm đã tìm : ${products.length}`);
console.log(`Ảnh thu được    : ${rows.length}`);
if (blocked) console.log(`Truy vấn bị chặn: ${blocked}`);
if (!DRY) {
  console.log(`Đã tải          : ${outDir}`);
  console.log(`Manifest        : ${manifestOut}`);
}
console.log(`
CÒN PHẢI LÀM TAY — bỏ qua là mọi metric sai:
  1. Xem từng ảnh, kiểm exact_skus có đúng sản phẩm đó không
     - khác dung tích/màu  -> chuyển SKU sang cột variant_skus
     - sai sản phẩm        -> xoá dòng và xoá file
     - ảnh ghép nhiều sản phẩm -> xoá
  2. Gán cột difficulty
  3. Đặt verified=1 cho dòng đã xác minh
  4. Chỉ gộp dòng verified=1 vào manifest.csv`);
