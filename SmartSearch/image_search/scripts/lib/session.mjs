// Phiên đăng nhập dev console.
//
// Không dùng storageState: nó chỉ chụp cookie + localStorage, trong khi access
// token OIDC của app nằm ở sessionStorage và sống vài phút. Khôi phục ảnh chụp
// tĩnh thì app không silent-refresh được (thiếu phiên gốc với IdP) nên 401 sau
// ít phút — đã kiểm chứng: chạy được lúc đầu rồi bị đá về /#/auth/login.
//
// Profile trình duyệt cố định giữ nguyên mọi thứ, app tự gia hạn như bình thường.

import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { PATHS } from '../config.mjs';

export const PROFILE_DIR = path.resolve(PATHS.profile);

export async function openProfile({ headless = true } = {}) {
  if (!fs.existsSync(PROFILE_DIR)) {
    throw new Error('Chưa có profile đăng nhập. Chạy trước: npm run auth');
  }
  return chromium.launchPersistentContext(PROFILE_DIR, {
    headless,
    viewport: { width: 1440, height: 900 },
  });
}

// launchPersistentContext luôn mở sẵn 1 tab — dùng lại thay vì mở thêm
export const firstPage = async (context) => context.pages()[0] ?? context.newPage();

// Phiên SSO hết hạn giữa chừng thì phải dừng ngay, không để runner chạy tiếp
// rồi ghi ra cả trăm kết quả rỗng.
export function watchForAuthFailure(page, onFailure) {
  page.on('response', (res) => {
    if (res.status() === 401 && res.url().includes('/api/')) onFailure(res.url());
  });
}
