// Đọc manifest + results/ -> metric từng cơ chế, cắt lát, so cặp.
//   node scripts/score.mjs

import fs from 'node:fs';
import path from 'node:path';
import { readManifest, splitList, toCsv } from './lib/csv.mjs';
import { MODES, PATHS } from './config.mjs';

const K = [1, 5, 10];

const manifest = readManifest(fs.readFileSync(path.resolve(PATHS.manifest), 'utf8'));
const byId = new Map(manifest.map((r) => [r.image_id, r]));

// ---------------------------------------------------------------- chấm từng lượt
const rows = [];
const errors = [];

for (const mode of MODES) {
  const dir = path.resolve(PATHS.results, mode);
  if (!fs.existsSync(dir)) continue;

  for (const file of fs.readdirSync(dir).filter((f) => f.endsWith('.json'))) {
    const raw = JSON.parse(fs.readFileSync(path.join(dir, file), 'utf8'));
    const gt = byId.get(raw.image_id);
    if (!gt) continue;

    // Lượt lỗi backend (410/503) KHÔNG phải "tìm không ra" — gộp hai cái này
    // là bịa ra tỉ lệ trượt cho một cơ chế thật ra chưa chạy lần nào.
    if (raw.ok === false) {
      errors.push({
        image_id: raw.image_id,
        mode,
        http_status: raw.http_status,
        code: raw.response?.downstream?.error?.code ?? raw.response?.title ?? '?',
      });
      continue;
    }

    const products = raw.response.products || [];
    const exact = new Set(splitList(gt.exact_skus));
    const relaxed = new Set([...exact, ...splitList(gt.variant_skus)]);
    const cats = new Set(splitList(gt.category_ids));

    const rankOf = (matches) => {
      const i = products.findIndex(matches);
      return i === -1 ? null : i + 1;
    };

    const strictRank = exact.size ? rankOf((p) => exact.has(p.sku)) : null;
    const relaxedRank = relaxed.size ? rankOf((p) => relaxed.has(p.sku)) : null;
    const catRank = cats.size
      ? rankOf((p) => (p.categoryIds || []).some((c) => cats.has(c)))
      : null;

    const hit = (rank, k) => (rank !== null && rank <= k ? 1 : 0);

    const row = {
      image_id: raw.image_id,
      mode,
      source: gt.source,
      difficulty: gt.difficulty,
      keyword: gt.keyword,
      // ảnh aigen không có SKU đích -> loại khỏi metric SKU, chỉ tính category
      scorable_sku: exact.size ? 1 : 0,
      strict_rank: strictRank,
      relaxed_rank: relaxedRank,
      category_rank: catRank,
      mrr: relaxedRank ? +(1 / relaxedRank).toFixed(4) : 0,
      no_result: products.length === 0 ? 1 : 0,
      total_hits: raw.response.totalHits ?? 0,
      took_ms: raw.response.tookMs ?? null,
      mode_resolved: raw.response.resolvedImageMode ?? '',
      mode_mismatch: raw.response.resolvedImageMode !== mode ? 1 : 0,
      // Cơ chế caption trả kèm chẩn đoán của Nova Lite: phân biệt được
      // "model bảo đây không phải sản phẩm" với "model đọc được nhưng search rỗng"
      caption_query: raw.response.caption?.query ?? '',
      caption_outcome: raw.response.caption?.outcome ?? '',
      caption_reason: raw.response.caption?.reason ?? '',
      top1_sku: products[0]?.sku ?? '',
      top1_name: products[0]?.name ?? '',
    };
    for (const k of K) {
      row[`strict_hit@${k}`] = hit(strictRank, k);
      row[`relaxed_hit@${k}`] = hit(relaxedRank, k);
      row[`category_hit@${k}`] = hit(catRank, k);
    }
    rows.push(row);
  }
}

// ---------------------------------------------------------------- lỗi backend
if (errors.length) {
  const byMode = new Map();
  for (const e of errors) {
    const key = `${e.mode}  HTTP ${e.http_status} ${e.code}`;
    byMode.set(key, (byMode.get(key) || 0) + 1);
  }
  console.log('\n!! LƯỢT LỖI BACKEND — đã loại khỏi mọi metric phía dưới');
  console.log('─'.repeat(70));
  for (const [key, n] of [...byMode].sort()) console.log(`  ${String(n).padStart(4)}x  ${key}`);

  const dead = MODES.filter((m) => {
    const errN = errors.filter((e) => e.mode === m).length;
    const okN = rows.filter((r) => r.mode === m).length;
    return errN > 0 && okN === 0;
  });
  if (dead.length) {
    console.log(`\n  Cơ chế ${dead.join(', ')} không có lượt nào thành công.`);
    console.log('  Không so sánh được — cần backend sửa trước khi chạy lại.');
  }
}

if (!rows.length) { console.error('\nChưa có kết quả hợp lệ nào trong results/.'); process.exit(1); }

// ---------------------------------------------------------------- tổng hợp
const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0);
const pct = (x) => (x * 100).toFixed(1) + '%';

function percentile(xs, p) {
  const v = xs.filter((x) => typeof x === 'number').sort((a, b) => a - b);
  if (!v.length) return null;
  return v[Math.min(v.length - 1, Math.floor((p / 100) * v.length))];
}

function summarise(subset) {
  const sku = subset.filter((r) => r.scorable_sku);
  return {
    n: subset.length,
    n_sku: sku.length,
    'strict@1': mean(sku.map((r) => r['strict_hit@1'])),
    'relaxed@1': mean(sku.map((r) => r['relaxed_hit@1'])),
    'relaxed@5': mean(sku.map((r) => r['relaxed_hit@5'])),
    'category@5': mean(subset.map((r) => r['category_hit@5'])),
    mrr: mean(sku.map((r) => r.mrr)),
    no_result: mean(subset.map((r) => r.no_result)),
    p50_ms: percentile(subset.map((r) => r.took_ms), 50),
    p95_ms: percentile(subset.map((r) => r.took_ms), 95),
    mismatch: subset.reduce((a, r) => a + r.mode_mismatch, 0),
  };
}

const table = (title, groups) => {
  // n = tổng ảnh (dùng cho cat@5, trống, latency)
  // nSKU = ảnh có SKU đích (dùng cho strict/relax/MRR — ảnh aigen bị loại)
  console.log(`\n${title}`);
  console.log('─'.repeat(104));
  console.log(
    'nhóm'.padEnd(26) + 'n/nSKU'.padStart(9) + 'strict@1'.padStart(10) +
    'relax@1'.padStart(9) + 'relax@5'.padStart(9) + 'cat@5'.padStart(8) +
    'MRR'.padStart(8) + 'trống'.padStart(8) + 'p50ms'.padStart(8) + 'p95ms'.padStart(8)
  );
  for (const [label, subset] of groups) {
    if (!subset.length) continue;
    const s = summarise(subset);
    console.log(
      label.padEnd(26) + `${s.n}/${s.n_sku}`.padStart(9) + pct(s['strict@1']).padStart(10) +
      pct(s['relaxed@1']).padStart(9) + pct(s['relaxed@5']).padStart(9) +
      pct(s['category@5']).padStart(8) + s.mrr.toFixed(3).padStart(8) +
      pct(s.no_result).padStart(8) + String(s.p50_ms ?? '-').padStart(8) +
      String(s.p95_ms ?? '-').padStart(8)
    );
  }
};

const groupBy = (subset, key) => {
  const m = new Map();
  for (const r of subset) {
    const v = r[key] || '(trống)';
    if (!m.has(v)) m.set(v, []);
    m.get(v).push(r);
  }
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
};

table('TỔNG THỂ THEO CƠ CHẾ', MODES.map((m) => [m, rows.filter((r) => r.mode === m)]));

for (const key of ['source', 'difficulty']) {
  for (const [val, subset] of groupBy(rows, key)) {
    table(`${key.toUpperCase()} = ${val}`, MODES.map((m) => [m, subset.filter((r) => r.mode === m)]));
  }
}

// ---------------------------------------------------------------- so cặp
// McNemar exact: chỉ những ảnh mà 2 cơ chế cho kết quả khác nhau mới mang
// thông tin. b, c là số ca lệch theo mỗi chiều.
function logChoose(n, k) {
  let s = 0;
  for (let i = 0; i < k; i++) s += Math.log(n - i) - Math.log(i + 1);
  return s;
}
function mcnemarExactP(b, c) {
  const n = b + c;
  if (n === 0) return 1;
  const lo = Math.min(b, c);
  let tail = 0;
  for (let i = 0; i <= lo; i++) tail += Math.exp(logChoose(n, i) - n * Math.LN2);
  return Math.min(1, 2 * tail);
}

console.log('\n\nSO CẶP — relaxed_hit@5, chỉ trên ảnh có SKU đích');
console.log('─'.repeat(104));
console.log('cặp'.padEnd(34) + 'A thắng'.padStart(10) + 'B thắng'.padStart(10) +
            'hoà'.padStart(8) + 'p (McNemar)'.padStart(14) + '  kết luận');

const pairs = [];
for (let i = 0; i < MODES.length; i++) {
  for (let j = i + 1; j < MODES.length; j++) {
    const [A, B] = [MODES[i], MODES[j]];
    const idx = (m) => new Map(rows.filter((r) => r.mode === m && r.scorable_sku).map((r) => [r.image_id, r]));
    const a = idx(A), b = idx(B);
    let aw = 0, bw = 0, tie = 0;
    for (const [id, ra] of a) {
      const rb = b.get(id);
      if (!rb) continue;
      const x = ra['relaxed_hit@5'], y = rb['relaxed_hit@5'];
      if (x === y) tie++; else if (x > y) aw++; else bw++;
    }
    pairs.push({ A, B, aw, bw, tie, p: mcnemarExactP(aw, bw) });
  }
}

// Holm: 3 cặp so cùng lúc thì ngưỡng 0.05 cho từng cặp là quá dễ dãi
const sorted = [...pairs].sort((x, y) => x.p - y.p);
sorted.forEach((p, i) => { p.alpha = 0.05 / (sorted.length - i); });

for (const p of pairs) {
  const verdict = p.p < p.alpha
    ? (p.aw > p.bw ? `${p.A} tốt hơn` : `${p.B} tốt hơn`)
    : 'chưa đủ bằng chứng';
  console.log(
    `${p.A} vs ${p.B}`.padEnd(34) + String(p.aw).padStart(10) + String(p.bw).padStart(10) +
    String(p.tie).padStart(8) + p.p.toFixed(4).padStart(14) + '  ' + verdict
  );
}
console.log('\nNgưỡng đã hiệu chỉnh Holm cho 3 phép so. "chưa đủ bằng chứng" nghĩa là');
console.log('chênh lệch nằm trong nhiễu của cỡ mẫu này — không phải "hai bên như nhau".');

// ---------------------------------------------------------------- cảnh báo
const mismatches = rows.filter((r) => r.mode_mismatch);
if (mismatches.length) {
  console.log(`\n!! ${mismatches.length} lượt có resolvedImageMode lệch với cơ chế đã chọn.`);
  console.log('   Mọi con số phía trên không đáng tin cho tới khi giải thích được chỗ này.');
  for (const r of mismatches.slice(0, 10)) {
    console.log(`   ${r.image_id}: chọn ${r.mode} -> trả về ${r.mode_resolved || '(trống)'}`);
  }
}

// ---------------------------------------------------------------- xuất file
const columns = [
  'image_id', 'mode', 'source', 'difficulty', 'keyword', 'scorable_sku',
  ...K.flatMap((k) => [`strict_hit@${k}`, `relaxed_hit@${k}`, `category_hit@${k}`]),
  'strict_rank', 'relaxed_rank', 'category_rank', 'mrr', 'no_result',
  'total_hits', 'took_ms', 'mode_resolved', 'mode_mismatch', 'top1_sku', 'top1_name',
  'caption_query', 'caption_outcome', 'caption_reason',
];
const out = path.resolve(PATHS.results, 'scores.csv');
fs.writeFileSync(out, toCsv(rows, columns));
console.log(`\nChi tiết từng lượt -> ${out}`);
console.log('Lọc relaxed_hit@5 = 0 trong file này để xem model trượt ở đâu.');
