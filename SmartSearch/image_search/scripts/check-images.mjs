// Kiểm tra bộ ảnh trước khi chạy: file tồn tại, đúng định dạng, dưới 5 MB,
// ground truth hợp lệ. Chạy cái này trước khi tốn cả buổi chạy runner.
//   node scripts/check-images.mjs

import fs from 'node:fs';
import path from 'node:path';
import { readManifest, splitList } from './lib/csv.mjs';
import { PATHS, UPLOAD_LIMITS } from './config.mjs';

const manifest = readManifest(fs.readFileSync(path.resolve(PATHS.manifest), 'utf8'));
const problems = [];
const warnings = [];
const seenIds = new Set();

const mb = (n) => (n / 1024 / 1024).toFixed(2) + ' MB';

for (const row of manifest) {
  const id = row.image_id;

  if (!id) { problems.push('Có dòng thiếu image_id'); continue; }
  if (seenIds.has(id)) problems.push(`${id}: image_id bị trùng`);
  seenIds.add(id);

  const file = path.resolve(PATHS.images, row.file);
  if (!fs.existsSync(file)) { problems.push(`${id}: không tìm thấy file ${row.file}`); continue; }

  const ext = path.extname(file).toLowerCase();
  if (!UPLOAD_LIMITS.extensions.includes(ext)) {
    problems.push(`${id}: định dạng ${ext} không được UI chấp nhận (chỉ PNG/JPEG/WebP/GIF)`);
  }

  const size = fs.statSync(file).size;
  if (size > UPLOAD_LIMITS.maxBytes) {
    problems.push(`${id}: ${mb(size)} vượt giới hạn 5 MB — cần nén hoặc giảm kích thước`);
  }

  const exact = splitList(row.exact_skus);
  const variant = splitList(row.variant_skus);
  const cats = splitList(row.category_ids);

  if (row.source === 'aigen') {
    if (exact.length) {
      warnings.push(`${id}: ảnh aigen mà có exact_skus — sẽ bị loại khỏi metric SKU, cân nhắc đổi source`);
    }
    if (!cats.length) problems.push(`${id}: ảnh aigen bắt buộc phải có category_ids để chấm được`);
  } else if (!exact.length) {
    problems.push(`${id}: source=${row.source || '(trống)'} nhưng không có exact_skus`);
  }

  const overlap = exact.filter((s) => variant.includes(s));
  if (overlap.length) warnings.push(`${id}: SKU ${overlap.join(', ')} nằm ở cả exact và variant`);
}

const bySource = {};
const byDifficulty = {};
for (const r of manifest) {
  bySource[r.source || '(trống)'] = (bySource[r.source || '(trống)'] || 0) + 1;
  byDifficulty[r.difficulty || '(trống)'] = (byDifficulty[r.difficulty || '(trống)'] || 0) + 1;
}

console.log(`\nTổng: ${manifest.length} ảnh`);
console.log('Theo nguồn:     ', bySource);
console.log('Theo độ khó:    ', byDifficulty);

if (warnings.length) {
  console.log(`\n${warnings.length} cảnh báo:`);
  warnings.forEach((w) => console.log('  ! ' + w));
}

if (problems.length) {
  console.log(`\n${problems.length} lỗi phải sửa trước khi chạy:`);
  problems.forEach((p) => console.log('  x ' + p));
  process.exit(1);
}

console.log('\nBộ ảnh hợp lệ, chạy được.');
