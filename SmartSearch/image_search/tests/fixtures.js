// Test phải chạy trên đúng profile mà runner dùng. Nếu để @playwright/test
// tự tạo context sạch, test sẽ chạy trên trang chưa đăng nhập và mấy assertion
// thuần UI vẫn xanh — đúng cái bẫy đã gặp một lần.
//
// workers = 1 trong playwright.config.js là bắt buộc: profile Chromium khoá
// theo tiến trình, hai worker mở cùng lúc sẽ đụng nhau.

import { test as base, expect } from '@playwright/test';
import { openProfile, firstPage } from '../scripts/lib/session.mjs';

export const test = base.extend({
  context: async ({}, use) => {
    const context = await openProfile({ headless: !process.env.HEADED });
    await use(context);
    await context.close();
  },
  page: async ({ context }, use) => {
    await use(await firstPage(context));
  },
});

export { expect };
