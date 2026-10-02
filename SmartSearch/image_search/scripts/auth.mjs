// Đăng nhập dev console một lần vào profile cố định.
//   npm run auth
// Browser mở ra -> bạn đăng nhập Magento SSO -> quay lại terminal bấm Enter.
//
// Dùng profile thật chứ không phải storageState: access token OIDC nằm trong
// sessionStorage và sống vài phút, ảnh chụp tĩnh không silent-refresh được.
// Profile giữ nguyên mọi thứ nên app tự gia hạn như trình duyệt bình thường.

import { chromium } from 'playwright';
import fs from 'node:fs';
import readline from 'node:readline/promises';
import { PLAYGROUND_URL } from './config.mjs';
import { PROFILE_DIR, firstPage } from './lib/session.mjs';

// Phải chạy trong terminal thật: nó mở browser và chờ bạn đăng nhập tay.
// Chạy qua tool/CI (stdin không phải TTY) thì readline nhận EOF ngay và
// script đi thẳng xuống khi bạn còn chưa kịp đăng nhập.
if (!process.stdin.isTTY) {
  console.error('npm run auth cần terminal tương tác — stdin hiện không phải TTY.');
  console.error('Mở terminal và chạy trực tiếp, đừng chạy qua tool hay script khác.');
  process.exit(1);
}

fs.mkdirSync(PROFILE_DIR, { recursive: true });

const context = await chromium.launchPersistentContext(PROFILE_DIR, {
  headless: false,
  viewport: { width: 1440, height: 900 },
});
const page = await firstPage(context);
await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });

console.log('\nDang nhap Magento SSO tren cua so vua mo.');
console.log('Khi da vao duoc trang playground, quay lai day va bam Enter.\n');

const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
await rl.question('Enter khi da dang nhap xong... ');
rl.close();
await context.close();

console.log(`\nProfile da luu -> ${PROFILE_DIR}`);
console.log('Thu muc nay chua phien dang nhap cua ban: khong commit, khong gui cho ai.\n');

// ---------------------------------------------------------------- kiem chung
// Mo lai profile o tien trinh khac - dung cach runner se dung.
console.log('Dang kiem chung: mo lai profile headless...');

const verify = await chromium.launchPersistentContext(PROFILE_DIR, {
  headless: true,
  viewport: { width: 1440, height: 900 },
});
const vp = await firstPage(verify);

let unauthorized = null;
let authorized = false;
vp.on('response', (res) => {
  if (!res.url().includes('/api/')) return;
  if (res.status() === 401) unauthorized ??= res.url();
  if (res.ok() && res.url().includes('userinfo')) authorized = true;
});

await vp.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });
const searchBox = await vp.waitForSelector('input[placeholder="Tìm kiếm"]', { timeout: 60_000 })
  .then(() => true).catch(() => false);
const url = vp.url();
await verify.close();

if (authorized && !unauthorized && searchBox) {
  console.log('\nOK - profile dung duoc headless. Chay tiep: npm test');
} else {
  console.log('\nPROFILE CHUA DUNG DUOC.');
  if (unauthorized) console.log(`  401 tai: ${unauthorized}`);
  if (!searchBox) console.log('  O tim kiem khong render.');
  if (url.includes('/auth/login')) console.log(`  Bi da ve man dang nhap: ${url}`);
  console.log('\nNeu app chan headless, chay runner kem --headed: npm run run -- --headed');
  process.exitCode = 1;
}
