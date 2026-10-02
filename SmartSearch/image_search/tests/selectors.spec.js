// Xác minh selector trong scripts/config.mjs còn đúng với UI hiện tại.
// Chạy cái này trước khi tốn cả buổi chạy eval — test đỏ ở bước nào thì
// sửa đúng selector đó, khỏi phải đoán qua log của runner.
//
//   npm test
//   npx playwright test --ui      (chạy từng bước, xem screenshot)

import { test, expect } from './fixtures.js';
import fs from 'node:fs';
import path from 'node:path';
import { PLAYGROUND_URL, MODES, SELECTORS, PATHS, UPLOAD_LIMITS } from '../scripts/config.mjs';

// Ghi lại status của mọi call /api/ để phân biệt "trang render được"
// với "thật sự đã đăng nhập" — hai thứ này khác nhau và từng làm test
// xanh giả trên cái vỏ trang chưa auth.
const apiCalls = new Map();

// Ảnh thật trong images/ nếu có, không thì dùng fixture tổng hợp.
// Fixture chỉ để test cơ chế upload — không dùng để đánh giá chất lượng model.
function findSampleImage() {
  const root = path.resolve(PATHS.images);
  if (fs.existsSync(root)) {
    for (const dir of fs.readdirSync(root)) {
      const sub = path.join(root, dir);
      if (!fs.statSync(sub).isDirectory()) continue;
      for (const f of fs.readdirSync(sub)) {
        if (UPLOAD_LIMITS.extensions.includes(path.extname(f).toLowerCase())) {
          return path.join(sub, f);
        }
      }
    }
  }
  const fixture = path.resolve('tests/fixtures/synthetic-pan.png');
  return fs.existsSync(fixture) ? fixture : null;
}

const sample = findSampleImage();

test.beforeEach(async ({ page }) => {
  apiCalls.set(page, []);
  page.on('response', (res) => {
    if (res.url().includes('/api/')) {
      apiCalls.get(page).push({ url: res.url(), status: res.status() });
    }
  });
  await page.goto(PLAYGROUND_URL, { waitUntil: 'domcontentloaded' });
  // App Angular hydrate chậm; không fail ở đây để test 1 báo đúng nguyên nhân
  await page.waitForSelector('input[placeholder="Tìm kiếm"]', { timeout: 60_000 }).catch(() => {});
});

test('đã đăng nhập thật, không phải chỉ render được vỏ trang', async ({ page }) => {
  await page.waitForTimeout(8_000);
  const calls = apiCalls.get(page);
  const unauthorized = calls.filter((c) => c.status === 401);

  // Đây là assertion quan trọng nhất của cả file. Không có nó, ba test selector
  // phía dưới vẫn xanh trên trang chưa đăng nhập và cho cảm giác an toàn giả.
  expect(
    unauthorized.map((c) => c.url),
    'Có call API trả 401 -> session hỏng, chạy lại `npm run auth`'
  ).toEqual([]);

  expect(calls.length, 'Không có call /api/ nào — trang chưa kịp khởi động').toBeGreaterThan(0);
  await expect(page.locator('input[placeholder="Tìm kiếm"]')).toBeVisible();
});

test('nút camera mở được modal tìm bằng hình ảnh', async ({ page }) => {
  await page.click(SELECTORS.cameraButton);
  await expect(page.getByText('Tìm sản phẩm bằng hình ảnh')).toBeVisible();
});

test('có input[type=file] để setInputFiles bắn vào', async ({ page }) => {
  await page.click(SELECTORS.cameraButton);
  // Input thường bị ẩn sau link "Chọn ảnh từ máy" — chỉ cần tồn tại trong DOM,
  // setInputFiles() không yêu cầu nó visible.
  await expect(page.locator(SELECTORS.fileInput)).toHaveCount(1);
});

test('upload xong thì dropdown cơ chế hiện đủ option cần test', async ({ page }) => {
  test.skip(!sample, 'Chưa có ảnh nào trong images/ — bỏ qua phần upload');

  await page.click(SELECTORS.cameraButton);
  await page.setInputFiles(SELECTORS.fileInput, sample);

  const select = page.locator(SELECTORS.modeSelect);
  await expect(select).toBeVisible({ timeout: 20_000 });

  // Nếu assertion này đỏ: dropdown là combobox custom chứ không phải <select>,
  // phải đổi selectOption() sang click + click option trong scripts/run.mjs
  const values = await select.locator('option').evaluateAll(
    (opts) => opts.map((o) => o.value)
  );
  for (const mode of MODES) {
    expect(values, `dropdown thiếu option "${mode}"`).toContain(mode);
  }
});

test('đổi cơ chế thì API trả về resolvedImageMode khớp', async ({ page }) => {
  test.skip(!sample, 'Chưa có ảnh nào trong images/ — bỏ qua phần upload');

  await page.click(SELECTORS.cameraButton);
  await page.setInputFiles(SELECTORS.fileInput, sample);
  await page.waitForSelector(SELECTORS.modeSelect, { timeout: 20_000 });

  for (const mode of MODES) {
    // UI bắn nhiều request trùng mỗi lần upload, nên chờ response ĐÚNG cơ chế
    // đang hỏi hoặc một lỗi 4xx/5xx — giống hệt logic trong scripts/run.mjs.
    const waitForSearch = page.waitForResponse(async (res) => {
      if (!res.url().includes('search-by-image')) return false;
      if (res.status() >= 400) return true;
      try {
        const body = await res.json();
        return body?.resolvedImageMode === mode;
      } catch { return false; }
    }, { timeout: 60_000 });

    await page.selectOption(SELECTORS.modeSelect, mode);
    if (SELECTORS.submitButton) await page.click(SELECTORS.submitButton);

    // Timeout ở đây = đổi cơ chế không tự trigger search lại
    // -> phải set SELECTORS.submitButton trong scripts/config.mjs
    const res = await waitForSearch;
    const body = await res.json();

    // Lỗi backend thì nói thẳng là backend lỗi, đừng để nó hiện ra như lỗi
    // selector — hai thứ này cần hành động hoàn toàn khác nhau.
    const code = body?.downstream?.error?.code ?? body?.title ?? '?';
    expect(
      res.status(),
      `Cơ chế "${mode}": backend trả HTTP ${res.status()} ${code} `
      + `— "${body?.detail ?? ''}". Lỗi dịch vụ, không phải lỗi selector.`
    ).toBe(200);

    // Chốt chặn quan trọng nhất của cả bộ eval: lệch nghĩa là UI không thật sự
    // đổi model, và mọi so sánh phía sau đều vô nghĩa.
    expect(body.resolvedImageMode, `chọn "${mode}" nhưng API trả về khác`).toBe(mode);
  }
});
