// Phép thử quyết định: imageRef là "vé vào cửa cho mọi cơ chế", hay chỉ là
// khoá cache của MỘT cơ chế?
//
//   node scripts/inspect-imageref-fresh.mjs
//
// imageRef = 'sha256:<hash nội dung ảnh>', nên mọi lượt upload cùng một ảnh đều
// nhận về đúng một ref. Hệ quả: ma trận chạy trên ảnh đã từng gọi API là ma trận
// chạy trên cache đã hâm nóng — "200" ở đó không phân biệt được "ref dùng được cho
// cơ chế này" với "ảnh này từng chạy cơ chế đó rồi nên embedding có sẵn".
//
// Script này sửa 1 pixel để ra một hash chưa ai thấy, upload đúng MỘT lần bằng
// cơ chế đầu tiên, rồi hỏi hai cơ chế còn lại bằng ref. Không còn cache cũ để nhờ:
//   cả 3 cùng 200  -> 1 ảnh = 1 upload, runner bớt được 2/3 số lượt
//   chỉ cơ chế đã upload 200, còn lại 410 -> cache theo cặp (hash, cơ chế)

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { PLAYGROUND_URL, MODES, FIXED_PARAMS } from './config.mjs';
import { openProfile, firstPage } from './lib/session.mjs';

const LANG = FIXED_PARAMS.langSelect, STORE = FIXED_PARAMS.storeSelect;
const API = `https://dev-gateway.martonline.lotte.vn/api/v2/${LANG}/${STORE}/products/search-by-image`;
const SRC = path.resolve(process.argv[2] ?? 'images/excel_keywords/kw009_kem-danh-rang.png');
const baseParams = { sort: 'relevance', storeId: STORE, lang: LANG, page: 1, pageSize: 100, filters: {} };

// Ảnh mới = ảnh cũ + vài byte rác sau IEND. Trình giải mã PNG bỏ qua phần đuôi
// (ảnh hiện ra y hệt) nhưng sha256 thì khác -> backend coi là ảnh chưa từng thấy.
function freshCopy() {
  const buf = Buffer.concat([fs.readFileSync(SRC), crypto.randomBytes(16)]);
  const out = path.resolve('.fresh-probe.png');
  fs.writeFileSync(out, buf);
  return { file: out, sha: crypto.createHash('sha256').update(buf).digest('hex') };
}

const context = await openProfile({ headless: true });
const page = await firstPage(context);
await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });
await page.waitForSelector('input[placeholder="Tìm kiếm"]', { timeout: 90_000 });

const call = (mode, { b64 = null, ref = null } = {}) =>
  page.evaluate(async ({ API, b64, ref, mode, baseParams }) => {
    const fd = new FormData();
    const params = { imageMode: mode, ...baseParams };
    if (b64) {
      const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      fd.append('image', new File([bin], 'probe.png', { type: 'image/png' }));
    } else {
      params.imageRef = ref;
    }
    fd.append('params', JSON.stringify(params));
    const r = await fetch(API, { method: 'POST', body: fd });
    const t = await r.text();
    try { return { status: r.status, body: JSON.parse(t) }; }
    catch { return { status: r.status, text: t.slice(0, 200) }; }
  }, { API, b64, ref, mode, baseParams });

const line = (tag, r) => {
  const b = r.body ?? {};
  const code = b?.downstream?.error?.code ?? b?.title ?? r.text ?? '';
  console.log(`  ${tag.padEnd(42)} ${r.status}  ${r.status === 200
    ? `${b.resolvedImageMode} · ${b.totalHits} hits`
    : String(code).slice(0, 50)}`);
  return r.status;
};

const table = [];
// Mỗi cơ chế một ảnh mới tinh: upload bằng chính nó, rồi hỏi hai cơ chế kia bằng ref.
for (const uploadMode of MODES) {
  const { file, sha } = freshCopy();
  const b64 = fs.readFileSync(file).toString('base64');
  console.log(`\n=== ảnh mới (sha256:${sha.slice(0, 12)}…), upload bằng ${uploadMode} ===`);
  const up = await call(uploadMode, { b64 });
  line(`upload file, imageMode=${uploadMode}`, up);
  const ref = up.body?.imageRef;
  if (!ref) { console.log('  không có imageRef, bỏ qua ảnh này'); continue; }
  console.log(`  ref khớp hash file? ${ref === 'sha256:' + sha ? 'CÓ' : 'KHÔNG (' + ref.slice(0, 20) + '…)'}`);
  for (const askMode of MODES) {
    const st = line(`  ref -> ${askMode}`, await call(askMode, { ref }));
    table.push({ upload: uploadMode, ask: askMode, status: st });
  }
  fs.rmSync(file, { force: true });
}

console.log('\n=== TỔNG HỢP (dòng = cơ chế đã upload, cột = cơ chế hỏi bằng ref) ===');
console.log('upload \\ hỏi'.padEnd(18) + MODES.map((m) => m.padEnd(14)).join(''));
for (const up of MODES) {
  const cells = MODES.map((ask) => {
    const hit = table.find((t) => t.upload === up && t.ask === ask);
    return String(hit ? hit.status : '-').padEnd(14);
  });
  console.log(up.padEnd(18) + cells.join(''));
}
fs.writeFileSync('imageref-fresh-matrix.json', JSON.stringify(table, null, 2));
await context.close();
