// Đăng nhập dev console mà KHÔNG cần terminal tương tác.
//   node scripts/auth-wait.mjs [--minutes 10]
//
// `npm run auth` chờ bạn bấm Enter ở terminal nên chỉ chạy được khi gõ tay;
// chạy qua tool thì stdin không phải TTY và nó thoát ngay. Script này thay chỗ
// đó: mở đúng profile Chromium mà runner dùng (.auth/profile), rồi tự dò tới
// khi `/api/v1/auth/userinfo` trả 200 — đăng nhập xong là nó tự đóng.
//
// Lưu ý: đăng nhập trong Chrome thường của bạn KHÔNG có tác dụng ở đây.
// Runner chạy bằng profile riêng, phải đăng nhập trong chính cửa sổ này.

import { chromium } from 'playwright';
import fs from 'node:fs';
import { PLAYGROUND_URL } from './config.mjs';
import { PROFILE_DIR, firstPage } from './lib/session.mjs';

const args = process.argv.slice(2);
const minutes = Number(args[args.indexOf('--minutes') + 1]) || 10;

fs.mkdirSync(PROFILE_DIR, { recursive: true });
const context = await chromium.launchPersistentContext(PROFILE_DIR, {
  headless: false,
  viewport: { width: 1440, height: 900 },
});
const page = await firstPage(context);
await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' }).catch(() => {});

console.log('Cửa sổ Chromium vừa mở là profile của runner.');
console.log('Đăng nhập Magento SSO trong ĐÚNG cửa sổ đó (Chrome thường không tính).');
console.log(`Script tự nhận ra khi xong, tối đa ${minutes} phút.\n`);

const deadline = Date.now() + minutes * 60_000;
const check = () => page.evaluate(async () => {
  try {
    const r = await fetch('/api/v1/auth/userinfo', { headers: { accept: 'application/json' } });
    return r.status;
  } catch { return 0; }
}).catch(() => 0);

let ok = false;
while (Date.now() < deadline) {
  const status = await check();
  if (status === 200) { ok = true; break; }
  process.stdout.write(`  chưa đăng nhập (userinfo ${status})...\r`);
  await page.waitForTimeout(3000);
}

if (ok) {
  // Kiểm chứng đúng cách runner sẽ dùng: playground phải render được ô tìm kiếm
  await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' }).catch(() => {});
  const box = await page.waitForSelector('input[placeholder="Tìm kiếm"]', { timeout: 60_000 })
    .then(() => true).catch(() => false);
  console.log(box ? '\nĐăng nhập OK, playground render được. Đóng cửa sổ, chạy tiếp được rồi.'
                  : '\nuserinfo 200 nhưng playground không render — xem lại quyền tài khoản.');
  await context.close();
  process.exit(box ? 0 : 1);
}

console.log('\nHết giờ chờ, vẫn chưa đăng nhập. Cửa sổ vẫn mở, đăng nhập rồi chạy lại script này.');
process.exit(1);
