# Runbook: Data & Compare (Smart Search)

Ghi lại đầy đủ từng bước để **tự chạy tay** 2 việc hay làm nhất trong dự án Smart Search — (1) tạo/lấy **Data** (Expected, Actual), (2) chạy **file Compare** (`compare_results.py`) — phòng trường hợp không có AI hỗ trợ. Toàn bộ lệnh chạy **từ thư mục gốc repo** (`Auto_Data_Py/`), dùng PowerShell.

Xem thêm: [`SmartSearch/README.md`](README.md) (tổng quan toàn bộ pipeline), [`SmartSearch/AI_CONTEXT.md`](AI_CONTEXT.md) (bối cảnh/quyết định thiết kế đầy đủ).

---

## 0. Chuẩn bị môi trường (chỉ cần làm 1 lần)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Nếu không muốn activate venv mỗi lần, gọi thẳng `.\.venv\Scripts\python.exe <script>` như các ví dụ bên dưới.

---

## 1. Auth — bắt buộc chọn trước khi gọi API thật

**Quy tắc đứng: LUÔN xác định rõ auth mode trước khi chạy bất kỳ lệnh nào gọi API thật (Actual hoặc As-Is), không đoán/không mặc định.** Có 3 cách:

| Cách | Khi dùng | Cách bật |
|---|---|---|
| `--no-auth` | Nhanh nhất, gọi thẳng không kèm cookie/token | Chỉ cần thêm flag `--no-auth` vào lệnh |
| Cookie thủ công | Đã có sẵn session cookie từ trình duyệt | Xem bước 1a bên dưới |
| `--headed-login` | Cookie hết hạn / chưa từng đăng nhập | Xem bước 1b bên dưới |

### 1a. Cookie thủ công
1. Đăng nhập `https://dev-console.martonline.lotte.vn/` bằng trình duyệt thường.
2. Mở DevTools → tab Network → tìm 1 request `products/search` hoặc `/autocomplete` → Request Headers → copy nguyên giá trị header `Cookie`.
3. Gán vào biến môi trường (chỉ có hiệu lực trong cửa sổ PowerShell hiện tại):
   ```powershell
   $env:DEV_SEARCH_COOKIE = "visid_incap_XXX=...; incap_ses_XXX=..."
   ```
4. Chạy lệnh với `--env dev` (không cần thêm `--no-auth` hay `--headed-login`).

### 1b. `--headed-login` (trình duyệt thật, tự đăng nhập tay)
Thêm flag `--headed-login` vào lệnh `export_actual_search_results.py` hoặc `run_batch_test.py`. Một cửa sổ Chromium thật sẽ mở ra, đăng nhập tay (username/password + mã 2FA), tool tự phát hiện đăng nhập xong và tự lấy cookie — không cần làm gì thêm. Cần cài 1 lần:
```powershell
pip install playwright
playwright install chromium
```

---

## 2. DATA

### 2a. Tạo 1 batch Expected MỚI (thủ công — cách hay dùng nhất)

Batch nằm ở `SmartSearch/test_data/json/batches/<PREFIX>_ExpectedData_<range_hoặc_tên>_<yyyymmdd>.json` (PREFIX = `NSG` hoặc `WLE` tuỳ store). Cấu trúc JSON:

```json
{
  "generatedDate": "2026-09-04",
  "store": "nsg",
  "batchRange": "ten_dat_tuy_y",
  "totalScenarios": 2,
  "scenarios": [
    {
      "test_id": "NSG-XXX-0001",
      "query": "từ khoá cần test",
      "dimension": "loại query (typo/synonym/regional/manual_demo_...)",
      "note": "ghi chú lý do có query này"
    }
  ]
}
```

- Nếu **biết trước đáp án đúng** (SKU nào phải ra), thêm `search_results` (mảng `{sku, rank}`) và/hoặc `autocomplete_suggestions` vào từng scenario — compare sẽ so Actual với đúng field này.
- Nếu **KHÔNG có đáp án trước** (kiểu file demo, chỉ muốn xem As-Is vs Actual khác nhau thế nào) — bỏ hẳn field `search_results`, để trống. Panel Expected trong report sẽ hiện trống/TBD, không sao cả.
- Muốn thêm query vào 1 batch đã có: mở đúng file JSON đó, append thêm object vào mảng `scenarios`, tăng `totalScenarios` cho khớp — **không tạo file mới cho cùng 1 mục đích**.

### 2b. Tạo batch bằng generator tự động (golden-set, ít dùng hơn trong luồng Compare)

```powershell
python scripts\testdata\generate_master_testset.py --store nsg --out-dir SmartSearch\golden_testsets\nsg
python scripts\testdata\generate_master_testset.py --all-stores --out-dir SmartSearch\golden_testsets
```
Sinh theo 8 dimension (exact/lowercase/partial/typo/no_diacritics/synonym/regional/related), lấy mẫu ≤300 sản phẩm/store từ `data/ProductInfo/`.

### 2c. Lấy ACTUAL (gọi API thật, môi trường dev-gateway)

```powershell
# 1 batch cụ thể, không cần đăng nhập
python scripts\automation\export_actual_search_results.py --env dev --batch <ten_batch> --no-auth

# 1 batch, dùng cookie đã export ở bước 1a
python scripts\automation\export_actual_search_results.py --env dev --batch <ten_batch>

# 1 batch, tự đăng nhập bằng trình duyệt
python scripts\automation\export_actual_search_results.py --env dev --batch <ten_batch> --headed-login

# chạy TẤT CẢ batch có sẵn dưới SmartSearch/test_data/json/batches/
python scripts\automation\export_actual_search_results.py --env dev --batch all --no-auth

# chạy thử vài dòng đầu trước khi chạy hết (smoke test)
python scripts\automation\export_actual_search_results.py --env dev --batch <ten_batch> --no-auth --limit 20
```

`<ten_batch>` = phần `batchRange` trong tên file (ví dụ file `NSG_ExpectedData_0-1000_20260821.json` → `--batch 0-1000`; file `NSG_ExpectedData_demo_asis_vs_actual_20260831.json` → `--batch demo_asis_vs_actual`). Nếu batch là của store WLE, thêm `--store-prefix WLE`.

Kết quả ghi ra `SmartSearch/test_data/json/actual/<PREFIX>_ActualData_<batchRange>_<timestamp>.json` — dùng đúng đường dẫn này làm `--actual` ở bước Compare.

**Lưu ý an toàn:** script sẽ tự dừng (`--stuck-streak-limit`, mặc định 8) nếu nhiều query liên tiếp trả về y hệt cùng 1 kết quả nhỏ/generic — dấu hiệu session bị WAF chặn/degraded, không phải do search thật sự tệ. Nếu gặp, đăng nhập lại rồi chạy lại.

### 2d. As-Is (hệ thống cũ, lottemart.vn)

**Không phải bước riêng** — As-Is được lấy tự động ngay trong lúc chạy `compare_results.py` (xem Phần 3), có cache-first (`AsIs_NSG_cache.json` / `AsIs_WLE_cache.json` dưới `SmartSearch/test_data/json/actual/`) để không gọi lại query đã từng lấy.

---

## 3. FILE COMPARE (`compare_results.py`)

### 3a. Lệnh cơ bản

```powershell
python scripts\automation\compare_results.py --expected <đường dẫn file Expected> --actual <đường dẫn file Actual>
```

Ví dụ thật:
```powershell
python scripts\automation\compare_results.py `
  --expected SmartSearch\test_data\json\batches\NSG_ExpectedData_0-1000_20260821.json `
  --actual SmartSearch\test_data\json\actual\NSG_ActualData_0-1000_20260904_101500.json
```

Output ghi vào **thư mục mới** `SmartSearch/test_data/compare/run_<batchRange>_<timestamp>/`, gồm:
- `compare_report.html` — mở trực tiếp bằng trình duyệt (không cần server/internet), có dropdown đổi kiểu so sánh (As-Is↔Actual hoặc Expected↔Actual), toggle ẩn/hiện panel Expected, KPI card, filter theo tier match.
- `matched_100_percent.json`, `mismatched_keywords.json`, `summary_stats.json` — dữ liệu thô để phân tích thêm.

### 3b. Điều khiển việc gọi As-Is

| Flag | Hành vi |
|---|---|
| (không truyền gì) | Mặc định: lấy từ cache nếu có; nếu chưa có VÀ scenario khớp ≤50% thì **tự gọi hệ thống As-Is thật** để lấy (tốn 1 call thật/query mới) |
| `--no-asis-fetch` | Chỉ dùng cache có sẵn, **không bao giờ gọi** hệ thống As-Is thật kể cả khi thiếu — dùng khi muốn so sánh mà không rủi ro gọi production |
| `--no-asis` | Bỏ hẳn panel As-Is, chỉ so Expected vs Actual kiểu offline thông thường |

**Ngoại lệ riêng cho file demo** (`NSG_ExpectedData_demo_*.json`): vì file này không có Expected nên MỌI scenario đều "≤50%" → mặc định (không truyền gì) sẽ tự động gọi As-Is thật cho toàn bộ query chưa có cache, không cần hỏi lại mỗi lần — khác với batch thật lớn (luôn phải cân nhắc `--no-asis-fetch` / hỏi trước vì tốn call thật quy mô lớn).

### 3c. Build lại report từ 1 lần chạy trước (không cần gõ lại đường dẫn Expected/Actual)

```powershell
python scripts\automation\compare_results.py --report-dir SmartSearch\test_data\compare\run_0-1000_20260904_101530
```

### 3d. Áp lại đánh giá đã export từ report (Đánh giá lại / Xuất Bug / Xuất cải thiện Engine)

```powershell
python scripts\automation\compare_results.py `
  --report-dir SmartSearch\test_data\compare\run_0-1000_20260904_101530 `
  --apply-overrides pass_fail_overrides_nsg_2026-09-04.json `
  --apply-bug-notes bug_notes_nsg_2026-09-04.json `
  --apply-engine-notes engine_improvement_notes_nsg_2026-09-04.json
```
Ghi đè vĩnh viễn vào `pass_fail_state_<store>.json` / `bug_notes_<store>.json` / `engine_notes_<store>.json`, đồng thời build lại report mới có đủ chú thích.

---

## 4. Quy tắc đứng cần nhớ (đã thống nhất trong quá trình làm việc)

1. **Luôn hỏi/xác nhận auth mode** (`--no-auth` / cookie / `--headed-login`) trước MỌI lần gọi API thật — không tự chọn mặc định.
2. **Không tự xoá** thư mục `SmartSearch/test_data/compare/run_*/` cũ khi có report mới thay thế — luôn hỏi trước, trừ khi đó là output rác từ 1 lần chạy bị lỗi/crash ngay trong cùng phiên.
3. **File demo** (`*_demo_*.json`) là ngoại lệ duy nhất được tự động gọi As-Is thật không cần hỏi lại mỗi lần.
4. Trước khi ghi vào bất kỳ file `.xlsx` nào, kiểm tra không có file khoá `~$*.xlsx` cùng thư mục (nghĩa là Excel đang mở file đó) — nếu có, phải đóng Excel trước.
5. Batch lớn (500-1000+ query) tốn call thật đáng kể — luôn cân nhắc `--no-asis-fetch` hoặc chạy `--limit` nhỏ để smoke test trước khi chạy hết.

---

## 5. Bảng tra nhanh (cheat sheet)

```powershell
# --- DATA ---
# Lấy Actual (không đăng nhập)
python scripts\automation\export_actual_search_results.py --env dev --batch <range> --no-auth

# Lấy Actual (cookie đã export)
$env:DEV_SEARCH_COOKIE = "<cookie>"
python scripts\automation\export_actual_search_results.py --env dev --batch <range>

# Lấy Actual (tự đăng nhập trình duyệt)
python scripts\automation\export_actual_search_results.py --env dev --batch <range> --headed-login

# --- COMPARE ---
# So sánh cơ bản
python scripts\automation\compare_results.py --expected <expected.json> --actual <actual.json>

# So sánh, không gọi As-Is thật (chỉ dùng cache)
python scripts\automation\compare_results.py --expected <expected.json> --actual <actual.json> --no-asis-fetch

# Build lại report từ lần chạy trước
python scripts\automation\compare_results.py --report-dir <thư mục run cũ>
```
