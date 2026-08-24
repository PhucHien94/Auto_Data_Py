# AI Context Prompt — MART Smart Search Test Automation (Auto_Data_Py)

> File này viết theo dạng "prompt" để một AI khác (Claude, GPT, v.v.) đọc 1 lần là nắm được bối cảnh project, tránh phải hỏi lại hoặc suy diễn sai. Nếu bạn là AI đang đọc file này: hãy coi nội dung dưới đây là ground truth tại thời điểm viết (2026-08-21), nhưng luôn verify lại code/data thực tế trước khi khẳng định điều gì đã thay đổi.

## 1. Bối cảnh & mục tiêu

Đây là workspace **QA/test automation** cho tính năng **Smart Search & Autocomplete** của hệ thống **MART** (dự án `2026_MartRenew`, thuộc Lotte). Người dùng chính là **QA/test-strategy lead**, làm việc bằng tiếng Việt, thao tác trực tiếp trên các workbook Excel test case/QnA song song với AI.

Mục tiêu tổng thể: xây dựng một pipeline để
1. Sinh **golden-set test data** (input query + expected output) từ catalog sản phẩm thật (20 store × EN/VI/KR NDJSON trong `data/ProductInfo/`).
2. Chạy test đó chống lại API search/autocomplete thật (khi có), chấm điểm theo mô hình 4 tier, xuất report.
3. Sinh tài sản test thủ công (Postman/k6) từ cùng dataset.
4. Quản lý workbook test case / QnA log giao cho dev/QA (VI + EN song song).
5. (Nhánh phụ, quy mô lớn) Xây một **JS relevance-search engine mô phỏng** + dataset 3000+ scenario cho riêng store NSG, publish dưới dạng Claude Artifact để QA có thể tự tra cứu/so sánh expected vs actual.

Chưa có API search thật nào được cấp — mọi số liệu "relevance thật" hiện tại đều **chưa verify với hệ thống production**.

## 2. Cấu trúc thư mục (đã reorganize 2026-08-19 → 2026-08-21; refactor đa-module 2026-08-24)

**2026-08-24: toàn bộ artifact riêng của feature Smart Search đã dọn vào folder `SmartSearch/`** (bỏ lớp `output/` bọc ngoài), để chuẩn bị cho các module/feature khác sau này cũng có folder riêng ngang hàng, cùng dùng chung `scripts/`, `data/`, `config/` ở root. Nếu thấy tài liệu/memory cũ còn ghi path kiểu `output/test_cases/testcases/...` hoặc `output/REQ/...` — đó là path CŨ, đã stale, quy đổi sang `SmartSearch/testcases/...` / `SmartSearch/REQ/...` theo mapping dưới đây.

```
Auto_Data_Py/
├── scripts/                        # SHARED — giữ nguyên vị trí, dùng chung cho mọi module
│   ├── testcase/       # tooling cho workbook test case/QnA: combine REQ+TC, preview, search keyword, translate EN/VI
│   ├── testdata/       # generators: golden testset, text/image testdata, multilang query, export catalog, export smartsearch testdata
│   ├── automation/     # run_autoscript (gọi API + scoring), lib_scoring, lib_search_client, runner_text_search
│   └── performance/    # export Postman/k6 assets từ dataset có sẵn (export_manual_qc_assets.py, k6_search_test.js)
├── data/                            # SHARED
│   ├── ProductInfo/    # NDJSON catalog gốc (EN/VI/KR) theo store — nguồn sự thật duy nhất
│   └── glossary/       # synonyms/regional_terms/related_terms.csv — dùng để sinh keyword variant
├── config/environments.yaml         # SHARED — endpoint search/autocomplete theo env (staging/production) — hiện đang null, CHƯA có URL thật
├── docs/                            # SHARED — tài liệu phụ (ví dụ image test data)
├── README.md                       # SHARED — README ngắn ở root, trỏ vào từng module
└── SmartSearch/                     # MODULE — mọi thứ đặc thù cho riêng feature Smart Search
    ├── golden_testsets/<store>/     # output của generate_master_testset.py
    ├── runs/                         # report.xlsx + raw NDJSON từ run_autoscript.py
    ├── manual_qc/<store>/            # Postman collection/env/CSV
    ├── text_testdata/, full_store_catalog*/  # nhánh phụ khác
    ├── image_test_data_sets.csv      # image-search test set
    ├── REQ/                          # tài liệu BRD/flow gốc (PDF/docx)
    ├── qna/          # QnA log workbook (VI + EN, PHẢI sửa đồng thời cả 2)
    ├── testcases/    # Combined_TestCases (VI + EN + CSV auto)
    ├── test_data/
    │   ├── excel/    # bản Excel cho dev/QA (regenerate khi được yêu cầu, không tự động)
    │   └── json/
    │       ├── batches/   # NSG_ExpectedData_<start>-<end>_<date>.json — batch query mới, không trùng key cũ
    │       ├── for_dev/   # bản denormalized (join tên/giá/category) giao dev, 1 file/nguồn
    │       └── _source/   # dataset_2000.json, queries_2000.json, search_engine.js — snapshot pipeline gốc
    ├── README.md          # hướng dẫn sử dụng chi tiết từng script (nguồn tham khảo song song với file này)
    ├── SKILL.md           # skill "review testcase" — luồng review coverage BRD ↔ testcase (tiếng Việt)
    └── AI_CONTEXT.md      # (chính là file này)
```

`SmartSearch/README.md` có hướng dẫn command-line chi tiết cho pipeline chính (mục 3) — đọc file đó để lấy cú pháp CLI, file này chỉ tóm tắt kiến trúc + các quyết định/rule đã thống nhất mà README không có. Mọi lệnh script vẫn chạy **từ root repo** (`Auto_Data_Py/`), không phải từ trong `SmartSearch/`, vì `scripts/`/`data/`/`config/` nằm ở root.

## 3. Hai nhánh công việc chính

### 3a. Golden-set pipeline đa store (chính thức, cho toàn bộ 20 store)
- `generate_master_testset.py` → sample ≤300 SKU/store, sinh keyword variant theo 8 dimension (exact/lowercase/partial/typo/no_diacritics/synonym/regional/related), tách `search_result_expected.ndjson` (theo SKU, có `acceptable_set`) và `autocomplete_expected.ndjson` (theo keyword).
- `run_autoscript.py` + `lib_scoring.py`: gọi Search và Autocomplete **như 2 API độc lập hoàn toàn** (không share request/response schema), hỗ trợ `--repeat N` để chấm `matching_ratio` vì kết quả AI search không deterministic. Chấm theo 4 tier: exact Top-1 / trong Top-N / recall≥threshold / cần review tay. Xuất `report.xlsx`.
- `export_manual_qc_assets.py`: sinh Postman + k6 từ golden dataset có sẵn, dùng cho spot-check/load test tay.
- `data/glossary/regional_terms.csv` và `related_terms.csv` **chỉ có dữ liệu mẫu/placeholder**, chưa được QA/BA curate — không coi là ground truth.
- `config/environments.yaml`: chưa có URL API thật.

### 3b. Engine mô phỏng search + dataset lớn cho riêng NSG (nhánh sâu, chạy trên Claude Artifact)
Xây từ 2026-08-20, đã qua **11 vòng chỉnh sửa** trong 1 phiên dài — không nằm trong `scripts/` chính thức, phần lớn toolchain **chỉ sống trong session scratchpad** (không commit vào repo), trừ snapshot cuối cùng ở `SmartSearch/test_data/json/_source/`.

- **Mục đích**: mô phỏng hành vi search/autocomplete thật (BM25-first + AI fallback theo đúng flow doc `SmartSearch/REQ/OVERVIEW-FLOW-VI_Phase1.pdf`) để sinh ra "expected data" hàng nghìn scenario mà QA dùng làm baseline so sánh với hệ thống thật khi nó sẵn sàng.
- **2 Artifact đang live**:
  - "NSG Expected data" (favicon 🔍) — embed catalog NSG (16,340 SKU) + engine JS, cho phép query trực tiếp + import batch JSON qua drag-and-drop (không còn embed dataset tĩnh, để không phải republish mỗi khi có batch mới).
  - "Search Result Comparator" (favicon 🎯) — tool so sánh expected vs actual (upload 2 file, parser dung nạp nhiều format: JSON/markdown table/fenced JSON).
  - "Ranking Scorecard — NSG" và "Ranking Scorecard — WLE" (favicon 🎛️) — full catalog browser riêng biệt, không liên quan search-testing (xem mục full-catalog artifact).
- **Quy trình sinh batch mới (standing rule)**: mỗi lần user yêu cầu "gen 1 bộ data set" → `generate_batch.js <start> <target>` rồi `compute_batch.js <start> <end> <date>` (scratchpad), loại trừ toàn bộ query đã có ở các batch trước, ghi thẳng ra `NSG_ExpectedData_<start>-<end>_<date>.json` vào `batches/`, **sau đó BẮT BUỘC** chạy `export_smartsearch_testdata.py --source <file batch>` để sinh bản denormalized cho dev vào `for_dev/`. KHÔNG chạm `dataset_2000.json` và KHÔNG republish artifact cho một batch mới thuần túy.
- **Khi sửa engine/glossary** (không phải batch mới): phải re-run `compute_dataset.js` cho 2000 query gốc, re-split lại 2 file batch 0-1000/1000-2000, reassemble + republish artifact, và re-run export cho dev. Các batch >2000 (sinh bằng `generate_batch.js`) KHÔNG tự động được refresh — phải chạy lại `compute_batch.js` riêng nếu cần.
- **Các lớp bug đã phát hiện & sửa trong engine** (quan trọng nếu mở rộng sang store khác): xem chi tiết trong `[[project-search-testdata-engine]]` (memory). Tóm tắt: collision dấu tiếng Việt khi strip diacritics ở single-token glossary source (tã/ta, chó/cho, nồi/nói); nhập nhằng ngữ nghĩa thật trong tiếng Việt (tập=vở vs tập=yoga) không có fix sạch; typo-tier chỉ được chạy làm fallback khi tier chính = 0 kết quả (theo yêu cầu thật của user dựa trên UI production); có thêm brand-tier (dựa `custom_attribute.brand/sub_brand`) và partial-tier (last-resort, single-token match) để giảm zero-result về 0/2000.
- **Nếu cần làm lại cho store khác (dng/gvp/wle/tbh)**: phải dựng lại toolchain scratchpad từ đầu (nó không nằm trong repo), chạy `export_full_store_catalog.py --desc-keywords` cho store đó, rồi audit lại glossary trước khi generate.

## 4. Quy tắc bắt buộc (đã bị vi phạm 1 lần → user sửa gắt, đừng lặp lại)

1. **Không bao giờ sửa test case ngoài phạm vi được liệt kê rõ ràng**, dù thấy mâu thuẫn — không có git history cho các workbook Excel, sửa "hộ" có thể phá dữ liệu user tự tay chỉnh mà không có cách khôi phục. Thấy mâu thuẫn → nêu ra và hỏi, không tự sửa.
2. **Kiểm tra file lock trước khi ghi Excel** — user hay mở file trong Excel song song khi chat. `PermissionError` / có file `~$*.xlsx` = đang mở, phải dừng và báo, không ép ghi.
3. **openpyxl gotcha**: `ws.cell(row, col, value=None)` KHÔNG xóa cell (đó là sentinel "chỉ fetch"). Muốn xóa phải gán `ws.cell(row, col).value = None` (2 bước).
4. **QnA log và Combined TestCases đều tồn tại dưới dạng cặp song ngữ VI/EN cùng cấu trúc dòng** — sửa 1 bên phải sửa cả 2, không được chỉ sửa bản đang mở/không bị lock.
5. Khi ghi nội dung tiếng Việt ra file: file write luôn UTF-8-safe, đừng bỏ dấu để né lỗi in console (`UnicodeEncodeError`) — lỗi đó là ở console print, không phải ở nội dung file, đừng đánh đổi nội dung thật để né lỗi hiển thị.
6. Trước khi khẳng định "store X không có mặt hàng Y" — phải broaden search (bare token, partial match), một lần grep hẹp trượt không phải bằng chứng caterogy không tồn tại (từng bị user bắt lỗi vụ "quần jean").

## 5. 3 câu lệnh tắt (standing trigger phrases) người dùng hay dùng

| User nói | Hành động ngay, không cần hỏi lại |
|---|---|
| "tạo data set" | chạy `scripts/testdata/generate_master_testset.py` cho store được nêu (hoặc `--all-stores`) |
| "run autoscript" (+ URL) | chạy `scripts/automation/run_autoscript.py --dataset-dir ... --search-api ... --autocomplete-api ...`, rồi **báo lại tóm tắt kết quả chấm điểm trong chat** (Precision@1, tier breakdown, MRR, zero-result rate, p95 latency, số cần review tay) — không chỉ báo "done" |
| "test tay" / manual QC (k6, Postman) | chạy `scripts/performance/export_manual_qc_assets.py` từ dataset có sẵn, không tự viết Postman/k6 tay |
| "gen 1 bộ data set" (trong ngữ cảnh NSG search-testdata engine) | sinh batch mới không trùng query cũ theo quy trình mục 3b, đặt tên `NSG_ExpectedData_<start>-<end>_<date>.json` |

## 6. Ngôn ngữ & phong cách làm việc

- Trả lời chat bằng **tiếng Việt**; giữ thuật ngữ kỹ thuật/tên sản phẩm ở nguyên tiếng Anh.
- Người dùng chấp nhận làm việc lâu, nhiều vòng lặp nhỏ trong 1 phiên (đã có phiên với 11+ vòng sửa liên tiếp) — ưu tiên sửa đúng, verify bằng script/test thật trước khi báo "đã sửa xong", không đoán.
- Khi không chắc regex/grep đã đủ rộng, hoặc chưa có API thật để verify — nói rõ giới hạn, đừng khẳng định chắc như đã kiểm chứng.

## 7. Việc còn thiếu / đang chờ (tại 2026-08-21)

- Chưa có URL API search/autocomplete thật (`config/environments.yaml` vẫn null) — mọi số liệu relevance hiện tại đều mô phỏng, chưa chạy trên hệ thống production.
- `data/glossary/regional_terms.csv` và `related_terms.csv` chưa được QA/BA curate chính thức (chỉ có vài dòng nháp do AI đề xuất, đánh dấu rõ là draft).
- "Nói lái" (chơi chữ kiểu Việt Nam) được yêu cầu cho engine NSG nhưng chưa implement — biết là gap, chưa làm.
- Dimension "intent" trong batch generator đã cạn glossary từ batch 3000-4000 trở đi — coverage intent sẽ gần 0 ở batch mới trừ khi mở rộng thêm `INTENT`/`SYNONYMS`/`REGIONAL`/`CATEGORY`.
- 2 sản phẩm có lỗi data thật ở nguồn (`(__EMPTY__VALUE__)` leak vào tên SKU 4550516703545/552) — đã note để báo BA/data team, chưa fix (không thuộc phạm vi pipeline này).

## 8. Nguồn tham khảo bổ sung

- Chi tiết đầy đủ, theo timeline từng vòng chỉnh sửa: xem hệ thống memory của AI hỗ trợ project này (`project_smart-search-test-pipeline.md`, `project_search-testdata-engine.md`, `project_full-catalog-artifacts.md`, `feedback_standing-commands.md`, `feedback_testcase-scope-discipline.md`). File này (`AI_CONTEXT.md`) là bản tóm tắt tĩnh tại một thời điểm — memory có thể có cập nhật mới hơn, và có thể còn ghi path cũ theo `output/...` từ trước ngày 2026-08-24 (xem mục 2 để quy đổi sang `SmartSearch/...`).
- `SmartSearch/README.md` — cú pháp CLI chi tiết từng script.
- `SmartSearch/SKILL.md` — quy trình review testcase coverage vs BRD (tiếng Việt).
- `README.md` (root) — điểm vào ngắn gọn, danh sách các module hiện có.
