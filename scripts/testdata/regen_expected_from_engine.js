// Sinh lại search_results / autocomplete_suggestions cho một file Expected
// bằng search_engine.js HIỆN TẠI, sau khi engine được chỉnh theo
// MART_Search_Mechanism_and_Rules_Specification_v1.pdf (2026-09-16).
//
// Vì sao cần script này: export_smartsearch_testdata.py chỉ ĐÓNG GÓI dataset
// có sẵn sang định dạng cho dev, KHÔNG chạy lại engine. Mỗi lần luật engine
// đổi thì Expected phải sinh lại, nếu không báo cáo compare sẽ đối chiếu
// Actual mới với Expected cũ - so sai gốc.
//
// GIỮ NGUYÊN mọi trường khác của scenario (test_id, query, dimension, note,
// các trường real_search_*). Chỉ ghi đè đúng phần engine sinh ra.
//
// Cách chạy:
//   node scripts/testdata/regen_expected_from_engine.js \
//        --in  SmartSearch/test_data/json/batches/NSG_ExpectedData_all_20260907.json \
//        --out SmartSearch/test_data/json/batches/NSG_ExpectedData_all_20260916.json \
//        --catalog SmartSearch/full_store_catalog_desc/nsg.json

const fs = require("fs");
const path = require("path");

function arg(name, def) {
  const i = process.argv.indexOf("--" + name);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : def;
}

const ROOT = path.resolve(__dirname, "..", "..");
const inPath = path.resolve(ROOT, arg("in"));
const outPath = path.resolve(ROOT, arg("out"));
const catPath = path.resolve(ROOT, arg("catalog", "SmartSearch/full_store_catalog_desc/nsg.json"));
const SEARCH_CAP = parseInt(arg("cap", "50"), 10);   // số SKU lưu lại mỗi scenario
const AC_LIMIT = parseInt(arg("ac-limit", "30"), 10); // số gợi ý autocomplete

const E = require(path.resolve(ROOT, "SmartSearch/test_data/json/_source/search_engine.js"));

console.log("Catalog :", catPath);
const products = JSON.parse(fs.readFileSync(catPath, "utf8"));
console.log("          " + products.length.toLocaleString() + " sản phẩm");

const t0 = Date.now();
const index = E.buildIndex(products);
console.log("Index    : dựng xong trong " + ((Date.now() - t0) / 1000).toFixed(1) + "s\n");

const data = JSON.parse(fs.readFileSync(inPath, "utf8"));
let scenarios = data.scenarios || [];
// --limit: chạy thử vài scenario để bắt lỗi trước khi cam kết cả bộ.
const LIMIT = parseInt(arg("limit", "0"), 10);
if (LIMIT > 0) scenarios = scenarios.slice(0, LIMIT);
// --only-empty: chỉ sinh cho scenario CHƯA có search_results. Dùng khi vừa
// thêm keyword mới vào một bộ đã sinh xong - khỏi chạy lại cả bộ 40 phút.
// Các scenario cũ vẫn nằm nguyên trong data.scenarios nên file ra vẫn đủ.
if (process.argv.includes("--only-empty")) {
  scenarios = scenarios.filter((s) => !(s.search_results && s.search_results.length));
  console.log("--only-empty: chỉ xử lý " + scenarios.length + " scenario chưa có kết quả");
}
console.log("Expected : " + inPath);
console.log("           " + scenarios.length + " scenario\n");

let changedSearch = 0, changedAC = 0, changedRoute = 0, zeroResult = 0, n = 0;
const tStart = Date.now();

for (const sc of scenarios) {
  const q = sc.query || "";
  // ---- search results -------------------------------------------------
  const all = E.search(index, q, Infinity);
  const top = all.slice(0, SEARCH_CAP).map((r) => ({
    sku: String(r.product.sku),
    score: r.score,
    tier: r.tier,
  }));
  const before = JSON.stringify((sc.search_results || []).map((x) => x.sku));
  sc.search_results = top;
  sc.search_results_total_before_cap = all.length;
  if (JSON.stringify(top.map((x) => x.sku)) !== before) changedSearch++;
  if (all.length === 0) zeroResult++;

  // ---- route / confidence (Adaptive Gate, spec trang 10) --------------
  // BM25 chạy trước; đủ chắc chắn thì dừng (keyword), không thì leo thang
  // gọi nhánh vector (keyword_ai). Hai trường này phải sinh lại cùng lúc,
  // nếu không route sẽ mô tả một bảng kết quả không còn tồn tại.
  if (typeof E.routeFor === "function") {
    const rt = E.routeFor(all);
    if (sc.route !== rt.route) changedRoute++;
    sc.route = rt.route;
    sc.confidence = rt.confidence;
  }
  if (typeof E.isSingleExactMatch === "function") {
    try { sc.is_single_exact_match = E.isSingleExactMatch(all); } catch (e) { /* giữ giá trị cũ */ }
  }

  // ---- autocomplete ---------------------------------------------------
  if (typeof E.autocomplete === "function") {
    try {
      const acBefore = JSON.stringify((sc.autocomplete_suggestions || []).map((x) => x.keyword));
      const ac = E.autocomplete(index, q, AC_LIMIT) || [];
      sc.autocomplete_suggestions = ac;
      if (JSON.stringify(ac.map((x) => x.keyword)) !== acBefore) changedAC++;
    } catch (err) {
      // autocomplete hỏng ở 1 query không được làm chết cả batch - ghi lại rồi đi tiếp
      console.error("  [autocomplete lỗi] " + q + " :: " + err.message);
    }
  }

  if (++n % 250 === 0) {
    const el = (Date.now() - tStart) / 1000;
    console.log("  ... " + n + "/" + scenarios.length + ", " + el.toFixed(0) + "s, " +
                (n / el).toFixed(1) + " scenario/s");
  }
}

const today = new Date().toISOString().slice(0, 10);
data.expectedRegeneratedDate = today;
data.engineRulesVersion = "MART_Search_Mechanism_and_Rules_Specification_v1 (2026-09-16)";
data.engineChangeLog = [
  "Ưu Tiên 1 (spec trang 4 & 8): in_stock DESC - hàng còn tồn xếp trước 100%, hết tồn dồn xuống đáy (OOS Demote). Áp ở bước NGOÀI CÙNG, sau cả diversifyByBrand.",
  "Ưu Tiên 5 (spec trang 4 & 8): tie-break theo sku để ổn định thứ tự khi hoà điểm.",
  "Nhóm 2 (spec trang 6): bổ sung 3 cặp đồng nghĩa vùng miền spec nêu đích danh - thịt lợn/thịt heo, dưa chuột/dưa leo, bột canh/bột nêm.",
  "KHÔNG cài Campaign Pin (spec ghi rõ chưa test, thử nghiệm chưa chốt) và Category Dial (pipeline chưa phục vụ Search Serving).",
];

fs.writeFileSync(outPath, JSON.stringify(data, null, 1), "utf8");

console.log("\n=== KẾT QUẢ ===");
console.log("  scenario xử lý          : " + scenarios.length);
console.log("  đổi danh sách SKU search: " + changedSearch +
            " (" + (changedSearch / scenarios.length * 100).toFixed(1) + "%)");
console.log("  đổi gợi ý autocomplete  : " + changedAC +
            " (" + (changedAC / scenarios.length * 100).toFixed(1) + "%)");
console.log("  đổi route keyword/AI    : " + changedRoute);
console.log("  query ra 0 kết quả      : " + zeroResult);
console.log("  thời gian               : " + ((Date.now() - tStart) / 1000).toFixed(0) + "s");
console.log("-> " + outPath);
