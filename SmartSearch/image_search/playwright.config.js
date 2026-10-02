import { defineConfig } from '@playwright/test';

// Config này KHÔNG phục vụ việc chạy eval — eval chạy bằng `npm run run`.
// Nó tồn tại để:
//   1. VS Code Testing panel nhận ra project -> hiện nút Record new / Pick locator
//   2. `npm test` xác minh selector trong scripts/config.mjs còn đúng
//
// Context/page do tests/fixtures.js cung cấp (profile cố định), nên ở đây
// không đặt storageState hay viewport — đặt cũng không có tác dụng.
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,            // profile Chromium khoá theo tiến trình
  reporter: 'list',
  timeout: 120_000,      // app Angular hydrate chậm
  use: {
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
