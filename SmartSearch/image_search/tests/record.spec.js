// Mở playground rồi dừng lại để bạn dùng Pick locator / Record.
// Gắn tag @record nên `npm test` bỏ qua, chỉ chạy khi gọi thẳng:
//
//   npm run record
//
// Inspector mở ra -> bấm "Pick locator" -> click nút camera / dropdown cơ chế
// -> copy selector -> dán vào scripts/config.mjs

import { test } from '@playwright/test';
import { PLAYGROUND_URL } from '../scripts/config.mjs';

test('mở playground để lấy selector @record', async ({ page }) => {
  await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });
  await page.pause();
});
