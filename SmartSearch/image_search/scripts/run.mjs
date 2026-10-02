// Chạy toàn bộ bộ ảnh qua từng cơ chế, lưu response thô.
//   node scripts/run.mjs                 chạy tất cả
//   node scripts/run.mjs --limit 5       chạy 5 ảnh đầu (smoke test)
//   node scripts/run.mjs --headed        hiện browser để nhìn nó làm gì
//   node scripts/run.mjs --only img_001,img_007
//   node scripts/run.mjs --force         chạy lại cả ảnh đã có kết quả
//
// Mỗi cặp (ảnh, cơ chế) là một lượt upload riêng. Không tái dùng imageRef:
// backend trả 410 IMAGE_REF_EXPIRED ("send the image again") chỉ sau vài giây,
// nên tối ưu "upload một lần rồi đổi cơ chế" không dùng được.

import fs from 'node:fs';
import path from 'node:path';
import { readManifest } from './lib/csv.mjs';
import { openProfile, firstPage, watchForAuthFailure } from './lib/session.mjs';
import { PLAYGROUND_URL, MODES, SELECTORS, FIXED_PARAMS, PATHS, PACING } from './config.mjs';

const args = process.argv.slice(2);
const flag = (name) => args.includes(name);
const value = (name) => { const i = args.indexOf(name); return i === -1 ? null : args[i + 1]; };

const limit = value('--limit') ? Number(value('--limit')) : null;
const only = value('--only') ? value('--only').split(',').map((s) => s.trim()) : null;

let manifest = readManifest(fs.readFileSync(path.resolve(PATHS.manifest), 'utf8'));
if (only) manifest = manifest.filter((r) => only.includes(r.image_id));
if (limit) manifest = manifest.slice(0, limit);
if (!manifest.length) { console.error('Manifest rỗng sau khi lọc.'); process.exit(1); }

for (const mode of MODES) fs.mkdirSync(path.resolve(PATHS.results, mode), { recursive: true });

const total = manifest.length * MODES.length;
console.log(`${manifest.length} ảnh x ${MODES.length} cơ chế = ${total} lượt upload\n`);

const context = await openProfile({ headless: !flag('--headed') });
const page = await firstPage(context);

let authFailedAt = null;
watchForAuthFailure(page, (url) => { authFailedAt ??= url; });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// UI bắn 3 request trùng nhau mỗi lần upload, và có nút "Thử lại sau 1s" tự retry.
// Nên không chờ "response tiếp theo" mà chờ response ĐÚNG cơ chế đang hỏi,
// hoặc một lỗi 4xx/5xx. Cách này tự miễn nhiễm với request trùng.
function waitForModeResponse(mode) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      page.off('response', handler);
      reject(new Error(`Không có response cho cơ chế ${mode} trong ${PACING.responseTimeoutMs}ms`));
    }, PACING.responseTimeoutMs);

    async function handler(res) {
      if (!res.url().includes('search-by-image')) return;
      let body = null;
      try { body = await res.json(); } catch { return; }

      const isMatch = res.status() === 200 && body?.resolvedImageMode === mode;
      const isError = res.status() >= 400;
      if (!isMatch && !isError) return;

      clearTimeout(timer);
      page.off('response', handler);
      resolve({ status: res.status(), body });
    }
    page.on('response', handler);
  });
}

// Một lượt: nạp trang sạch, upload ảnh, chọn cơ chế, lấy response.
async function runOnce(imageFile, mode) {
  await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('input[placeholder="Tìm kiếm"]', { timeout: 90_000 });

  if (authFailedAt) throw new Error(`Session hết hạn (401 tại ${authFailedAt}). Chạy lại: npm run auth`);

  await page.click(SELECTORS.cameraButton, { timeout: 60_000 });
  await page.setInputFiles(SELECTORS.fileInput, imageFile);
  await page.waitForSelector(SELECTORS.modeSelect, { timeout: 30_000 });

  // Ghim biến gây nhiễu: store, ngôn ngữ, sắp xếp
  for (const [key, val] of Object.entries(FIXED_PARAMS)) {
    await page.selectOption(SELECTORS[key], val).catch(() => {});
  }

  // Đổi cơ chế NGAY, đừng chờ — imageRef hết hạn rất nhanh
  const waiter = waitForModeResponse(mode);
  await page.selectOption(SELECTORS.modeSelect, mode);
  if (SELECTORS.submitButton) await page.click(SELECTORS.submitButton);
  return waiter;
}

const issues = [];
let done = 0;
let stop = false;

for (const row of manifest) {
  if (stop) break;
  const imageFile = path.resolve(PATHS.images, row.file);

  for (const mode of MODES) {
    const outFile = path.resolve(PATHS.results, mode, `${row.image_id}.json`);
    done++;
    if (fs.existsSync(outFile) && !flag('--force')) continue;

    process.stdout.write(`[${done}/${total}] ${row.image_id} / ${mode} ... `);

    let result = null;
    // 410 IMAGE_REF_EXPIRED thì backend bảo gửi lại ảnh -> thử lại đúng 1 lần.
    // 503 EMBEDDING_UNAVAILABLE là dịch vụ chết, thử lại cũng vậy, ghi nhận rồi đi tiếp.
    for (let attempt = 1; attempt <= 2; attempt++) {
      try {
        result = await runOnce(imageFile, mode);
      } catch (err) {
        issues.push(`${row.image_id}/${mode}: ${err.message}`);
        if (authFailedAt) stop = true;
        break;
      }
      if (result.status === 200) break;
      const code = result.body?.downstream?.error?.code ?? result.body?.title ?? '?';
      if (attempt === 1 && result.status === 410) {
        process.stdout.write(`410 ${code}, gửi lại ảnh... `);
        await sleep(1000);
        continue;
      }
      break;
    }

    if (!result) { process.stdout.write('BỎ QUA\n'); if (stop) break; continue; }

    const ok = result.status === 200;
    fs.writeFileSync(outFile, JSON.stringify({
      image_id: row.image_id,
      mode_requested: mode,
      ran_at: new Date().toISOString(),
      fixed_params: FIXED_PARAMS,
      http_status: result.status,
      ok,
      response: result.body,
    }, null, 2));

    if (ok) {
      const cap = result.body.caption;
      const note = cap?.outcome ? ` caption=${cap.outcome}/${cap.reason ?? '-'}` : '';
      process.stdout.write(`${result.body.totalHits} hits, ${result.body.tookMs}ms${note}\n`);
    } else {
      const code = result.body?.downstream?.error?.code ?? result.body?.title ?? '?';
      process.stdout.write(`LỖI ${result.status} ${code}\n`);
      issues.push(`${row.image_id}/${mode}: HTTP ${result.status} ${code}`);
    }

    await sleep(PACING.delayBetweenSearchesMs);
  }
}

await context.close();

if (issues.length) {
  console.log(`\n${issues.length} vấn đề:`);
  for (const i of issues.slice(0, 20)) console.log('  ! ' + i);
  if (issues.length > 20) console.log(`  ... còn ${issues.length - 20} dòng trong run-issues.txt`);
  fs.writeFileSync(path.resolve(PATHS.results, 'run-issues.txt'), issues.join('\n'));
}

if (authFailedAt) {
  console.log('\nDừng sớm: session hết hạn. Chạy `npm run auth` rồi `npm run run` để chạy tiếp.');
}

console.log(`\nKết quả thô trong ${PATHS.results}/<mode>/`);
console.log('Chấm điểm: npm run score');
