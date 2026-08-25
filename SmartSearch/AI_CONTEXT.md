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
    └── AI_CONTEXT.md      # (chính là file này)
```

`SmartSearch/README.md` có hướng dẫn command-line chi tiết cho pipeline chính (mục 3) — đọc file đó để lấy cú pháp CLI, file này chỉ tóm tắt kiến trúc + các quyết định/rule đã thống nhất mà README không có. Mọi lệnh script vẫn chạy **từ root repo** (`Auto_Data_Py/`), không phải từ trong `SmartSearch/`, vì `scripts/`/`data/`/`config/` nằm ở root.

## 3. Hai nhánh công việc chính

### 3a. Golden-set pipeline đa store (chính thức, cho toàn bộ 20 store)
- `generate_master_testset.py` → sample ≤300 SKU/store, sinh keyword variant theo 8 dimension (exact/lowercase/partial/typo/no_diacritics/synonym/regional/related), tách `search_result_expected.ndjson` (theo SKU, có `acceptable_set`) và `autocomplete_expected.ndjson` (theo keyword).
- `run_autoscript.py` + `lib_scoring.py`: gọi Search và Autocomplete **như 2 API độc lập hoàn toàn** (không share request/response schema), hỗ trợ `--repeat N` để chấm `matching_ratio` vì kết quả AI search không deterministic. Chấm theo 4 tier: exact Top-1 / trong Top-N / recall≥threshold / cần review tay. Xuất `report.xlsx`.
- `export_manual_qc_assets.py`: sinh Postman + k6 từ golden dataset có sẵn, dùng cho spot-check/load test tay.
- `data/glossary/regional_terms.csv` và `related_terms.csv` **chỉ có dữ liệu mẫu/placeholder**, chưa được QA/BA curate — không coi là ground truth.

**2026-08-24: API dev thật đã có, `config/environments.yaml` không còn null.** User dán 2 curl thật (autocomplete GET, search POST) từ dev-gateway (`dev-gateway.martonline.lotte.vn/api/v2/{lang}/{store}/products/{search|autocomplete}`) — đã test-call trực tiếp (transient, không lưu cookie vào file nào) để xác nhận response shape thật, rồi nâng cấp toàn bộ contract:
  - `lang`/`store` nằm trong **URL path**, không phải query param — `run_autoscript.py` giờ tự điền `{store}` (= tên folder `--dataset-dir`) và `{lang}` (`--lang`, default `vi`) vào URL và vào `search_extra_params`/`autocomplete_extra_params`.
  - Autocomplete = GET, `q` + `limit`; response `{"suggestions":[{"text":...}], "products":[...]}` → `autocomplete_result_path: suggestions`, field `text` (đã có trong default list).
  - Search = POST JSON, field `query` + extra field tĩnh (`storeId`, `page`, `pageSize`, `sort`, `filters`, `lang`, `trace`) + header riêng `x-search-mode: adaptive`; response `{"products":[{"sku":...,"productId":...,"name":...}], "resolvedMode": "lexical"|"hybrid", ...}` → `search_result_path: products`, ưu tiên field `sku` (không phải `productId`) vì golden dataset key theo SKU thật (barcode), không theo `productId` nội bộ.
  - Code (`lib_search_client.call_api`, `run_autoscript.py`) đã refactor để hỗ trợ: method riêng theo endpoint (`search_method`/`autocomplete_method`), extra static params/body riêng theo endpoint (`search_extra_params`/`autocomplete_extra_params`, có template `{store}`/`{lang}`), header riêng theo endpoint (`search_headers`/`autocomplete_headers`), và `auth_header_name` để route giá trị `auth_header_env` vào bất kỳ header nào (không chỉ `Authorization`).
  - **Auth = cookie session sau WAF Incapsula** (`visid_incap_*`, `incap_ses_*`), KHÔNG phải Bearer token — cookie hết hạn/đổi theo session, **không lưu cứng vào file nào trong repo** (đã cố tình không đưa cookie thật vào `config/environments.yaml`). Trước mỗi lần chạy `--env dev`, phải copy cookie tươi từ DevTools (Network tab, request `products/search` hoặc `/autocomplete` → Request Headers → Cookie) vào biến môi trường `DEV_SEARCH_COOKIE` (chỉ giá trị, không có tiền tố `Cookie:`), xem comment chi tiết trong `config/environments.yaml`.
  - Đã smoke-test end-to-end (`--env dev --limit 15`, cookie set tạm qua env var, không lưu) — pipeline chạy đúng cơ chế (request/response/parse đều OK), nhưng **kết quả chấm điểm mẫu nhỏ này rất tệ (P@1=0%, cả 15 dòng search rơi vào Tier4)** — kể cả với query là tên sản phẩm tiếng Việt chính xác 100% (`resolvedMode` trả về `hybrid`, sản phẩm mong đợi không nằm trong top 20). Đây **có thể** là finding thật về relevance của hệ thống dev hiện tại, nhưng mẫu quá nhỏ (15/2934 dòng) để kết luận chắc — cần chạy full dataset (bỏ `--limit`) rồi báo BA/dev team, đừng vội kết luận "search dev bị hỏng" chỉ từ smoke test này.

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

**2026-08-24 — audit toàn bộ 4 batch (4000 scenario) so với REQ, cả JSON và Excel:** user yêu cầu kiểm tra expected result đã match REQ hiện có chưa. Trích xuất text từ toàn bộ REQ (`BRD_AI_Search_VI_v0.0.3_20260812.docx`, 2 pptx storyboard/SRS, 2 pdf test-plan/flow-overview — dùng `python-docx`/`python-pptx`/`pypdf`, không có sẵn công cụ render PDF trong môi trường này) rồi đối chiếu với dữ liệu thật trong cả 4 file batch + Excel deliverable. Kết quả:

- ✅ **`route` field khớp HOÀN HẢO với top-tier của `search_results`** (0/1000 mismatch ở cả 4 batch) và khớp đúng ví dụ minh họa trong `OVERVIEW-FLOW-VI_Phase1.pdf` (bảng "câu tìm nào đi đường nào": "coca cola"/"thịt heo"/"bia" → chỉ từ khoá; "mua bia các loại"/"bia các loại" (category, mô tả nhu cầu chung) → keyword_ai) — verify trực tiếp: "Thịt Heo" (typo dimension) trong batch có `route:"keyword", confidence:100` đúng như REQ.
- ✅ Zero-result rate cực thấp ở cả search (0.0%/0.0%/0.1%/0.2%) và autocomplete (0.0%/0.0%/0.0%/0.2%) — khớp với REQ's FR-SM-07 (không bao giờ trả trang trống) và với việc engine đã groundedness-validate autocomplete.
- ✅ Điểm số theo tier đúng 100% với bảng tier→score đã biết (brand 95, exact 100, no_diacritics 92, multilang 88, typo 80, description 65, synonym 60, category 35, partial 20) — **trừ một chi tiết chưa từng ghi lại**: tier `intent` có 2 giá trị score, 45 (đa số) VÀ 40 (413/4000 item) — không phải bug (nội bộ tự nhất quán), chỉ là nuance chưa document trước đây, cần xem lại script gốc (`search_engine.js`, scratchpad) nếu muốn biết chính xác điều kiện nào cho ra 40 thay vì 45.
- ⚠️ **Phát hiện thật, cần BA/PO xác nhận — thứ tự sắp xếp autocomplete không khớp literal với storyboard**: `MART-DE03-Smart Search Storyboard` (SS-SCR-002, dòng "2 | Dòng gợi ý") ghi rõ **"Sắp xếp theo search volume giảm dần"** (sort theo popularity/search-volume descending, không nhắc đến relevance). Nhưng dữ liệu thật (check tay 1 scenario, `NSG-TD-0003` "gym") cho thấy thứ tự thực tế là **`best_score` giảm dần TRƯỚC, `popularity` giảm dần trong từng nhóm best_score SAU** (ví dụ: nhóm best_score=65 có popularity 7.6 xếp trước nhóm best_score=35 có popularity 22.6 cao hơn nhiều) — tức sort 2 cấp (relevance rồi mới đến volume), không phải sort 1 cấp theo volume như storyboard viết. Cách hiện tại hợp lý hơn về UX (không để 1 từ khoá phổ biến nhưng không liên quan lên đầu), nhưng **về câu chữ thì trái với storyboard hiện có** — đây là quyết định sản phẩm, không tự sửa, cần hỏi lại BA/PO xem storyboard cần update hay data cần sửa theo đúng "chỉ sort theo popularity".
- 🔴 **File Excel deliverable đã CŨ (stale), không còn khớp JSON hiện tại**: `SmartSearch/test_data/excel/MART_SmartSearch_AutocompleteSearch_TestData_v1.0_20260821.xlsx` (tạo lúc 09:31 ngày 20260821) chỉ phản ánh dataset TRƯỚC các fix cuối ngày đó (banned-words, typo-fallback-chỉ-khi-0-kết-quả, brand-tier, và quan trọng nhất là **partial-tier** — cái làm zero-result giảm về ~0 và tăng số search_results trung bình lên tới cap 80). Verify cụ thể: scenario `NSG-TD-1627` ("Coca-Cola 제로 탄산음료") trong Excel ghi "Số kết quả hiển thị / tổng thật: 29 / 29", nhưng JSON hiện tại (cả batch file và `for_dev/MART_SmartSearch_AutocompleteSearch_TestData_v1.0_20260821.json`, file này ĐÃ được refresh đúng) cho `80 / 125`. **File `for_dev/*.json` là đáng tin (đã refresh đúng theo engine cuối cùng); riêng Excel trong `test_data/excel/` thì KHÔNG** — đây đúng như quy tắc đã ghi ("Excel chỉ là template, không tự động regenerate") nhưng user cần biết nó đang stale trước khi dùng để review/demo. Nếu cần Excel mới: `python scripts/testdata/export_smartsearch_testdata.py --with-excel` (mặc định export theo `dataset_2000.json`/main set; dùng `--source <tên file batch>` cho batch cụ thể).
- Không kiểm tra được đầy đủ nội dung banned-words (`BANNED_WORDS` rỗng, chưa có wordlist thật — biết trước, không phải finding mới) và không kiểm tra được toàn bộ 4000×2 nội dung câu chữ so với REQ (chỉ audit được ở mức field/logic/structure, không đọc từng scenario).

### 3c. Batch test runner — chạy các batch (mục 3b) chống lại API thật (2026-08-24)

`scripts/automation/run_batch_test.py` (+ `lib_dashboard.py`): khác với `run_autoscript.py` (đọc `golden_testsets`, chấm theo 4-tier model của `lib_scoring.py`), script này đọc trực tiếp các batch `SmartSearch/test_data/json/batches/NSG_ExpectedData_<range>_<date>.json` (mục 3b) và dùng **so khớp theo rank** (cùng triết lý với Artifact "Search Result Comparator": mỗi item trong `search_results` precomputed được coi là "expected", kiểm tra rank của nó trong response thật — `matched`/`outside_top`/`missing`; item trong response thật không có trong expected → `extras`).

- **Tiền điều kiện: người dùng phải đăng nhập tay trước** (theo yêu cầu 2026-08-24) — script KHÔNG tự động login. Chỉ cần set `$env:DEV_SEARCH_COOKIE` với cookie mới copy từ DevTools trước mỗi lần chạy. Không được lưu cookie thật vào bất kỳ file nào trong repo (đã tuân thủ suốt phiên này).
- **Chọn batch**: `--batch 0-1000` (1 batch), `--batch 0-1000,2000-3000` (nhiều batch cụ thể), hoặc `--batch all` (tất cả batch tìm thấy trong `--batches-dir`, default `SmartSearch/test_data/json/batches/`) — theo yêu cầu "chạy batch nào / chạy all batch". Khi `all`, xuất **1 report tổng hợp duy nhất** (theo lựa chọn của user 2026-08-24), không tách report riêng mỗi batch.
- **Output** (`SmartSearch/runs/batch_<selection>_<timestamp>/`): `report.xlsx` (sheet `Dashboard` có openpyxl chart latency/recall theo dimension + KPI, cộng `Search_Detail`/`Autocomplete_Detail`) VÀ `dashboard.html` (trang HTML tự chứa, SVG chart nội tuyến, không CDN — mở offline được) — theo yêu cầu "cả 2" format của user. Cả hai dùng cùng `stats.json`, màu categorical theo palette chuẩn của skill `dataviz` (search=slot1 xanh, autocomplete=slot2 cam, cố định thứ tự).
- **Preflight + phát hiện session bị degrade**: 1 request kiểm tra trước khi chạy cả batch (bắt lỗi chưa đăng nhập/hết hạn ngay, không để burn hết 1000 dòng). Trong lúc chạy, có `StuckResultGuard`: nếu N query khác nhau liên tiếp (default 8, `--stuck-streak-limit`) trả về **y hệt** một kết quả nhỏ → dừng ngay, báo lỗi rõ ràng, KHÔNG xuất report — vì đây là dấu hiệu WAF/session bị throttle/degrade (server vẫn trả HTTP 200 hợp lệ nhưng nội dung là fallback chung), không phải search thật đang trả kết quả đó.
  - **Đã thực sự gặp lỗi này khi smoke-test hôm nay**: sau một số lượng request trong phiên (dùng lại 1 cookie nhiều lần để test cả 2 script), API bắt đầu trả về **y hệt 2 SKU không liên quan** (`Cá He Kho Riệu...`, `Sáp Ngăn Mùi...`) cho MỌI query khác nhau ("gym", "sữa", "Coca Cola", "1 túi quả cam"...), `resolvedMode:"hybrid"`, `totalHits:2`. Đã verify kỹ đây không phải bug code (request/encoding gửi đúng, `originalQuery` echo lại đúng) — là session bị degrade. `StuckResultGuard` được viết ra chính vì phát hiện này, đã test xác nhận nó dừng đúng và không xuất report sai lệch.
- **Chưa verify được đường "match thành công" thật** (session bị degrade trước khi kịp thấy 1 scenario match) — logic rank/so khớp đã verify đúng qua debug thủ công (request/response đúng cho từng scenario), nhưng chưa có 1 lần full run thành công với session khoẻ để xem dashboard thật trông ra sao trên số liệu match tốt. Khi user chạy lần đầu với cookie mới, nên xem qua `dashboard.html` một lượt để bắt lỗi hiển thị nếu có.

### 3d. Smoke-test folder (10 query) — chạy nhanh trước khi chạy full batch (2026-08-24)

`SmartSearch/smoke_test/NSG_ExpectedData_0-10_20260824.json` — 10 scenario, **tính bằng chính `search_engine.js` + catalog NSG thật** (`SmartSearch/full_store_catalog_desc/nsg.json`, qua Node), KHÔNG phải data bịa tay — cùng schema, cùng độ tin cậy với batch thật, chỉ khác là đặt tên `0-10` để `run_batch_test.py`'s `discover_batches()` tự nhận diện được qua regex filename (đã test: `discover_batches`/`select_batches`/`load_batch` đọc đúng file này). Chạy: `--env dev --batches-dir SmartSearch/smoke_test --batch 0-10`. Xem `SmartSearch/smoke_test/README.md` cho danh sách 10 query + ý nghĩa từng dimension. Script sinh file này (Node, dùng trực tiếp `SE.buildIndex/search/autocomplete/routeFor`) chỉ sống trong scratchpad, không commit — cùng convention với `generate_batch.js`.

Vài query không rơi đúng vào tier "sạch" như tên dimension gợi ý (VD: query typo lại rơi vào tier `partial` vì bản thân 2 từ đầu của tên sản phẩm đã đủ khớp qua tier khác trước khi typo-fallback có cơ hội chạy) — đây là hành vi THẬT của engine (đã ghi rõ trong field `note` của từng scenario), không phải lỗi của bộ smoke test, không cần "sửa" lại data cho đẹp.

**2026-08-24 — `--headed-login` (Playwright): thất bại 2 lần đầu (giả thuyết WAF fingerprint SAI), rồi thành công hoàn toàn sau khi user cung cấp đúng flow login thật.** User yêu cầu "chạy lại smoke test (headed mode)" — hiểu là: mở browser Playwright thật (không headless) để user login tay, script tự capture cookie sau đó. Vòng đầu tiên (dùng URL console gốc + tự "probe" domain gateway bằng `fetch()`/`page.goto()`) không lấy được cookie WAF nào dù user xác nhận đã login xong, dẫn tới giả thuyết SAI rằng Incapsula fingerprint được `navigator.webdriver` và luôn degrade browser tự động hoá — **giả thuyết này đã bị bác bỏ hoàn toàn ở vòng sau, xoá khỏi kết luận.**

**Flow login THẬT** (do user cung cấp chi tiết, xem ảnh chụp Playground thật): `dev-console.martonline.lotte.vn/#/auth/login` → nút duy nhất "Sign in with Magento" → redirect OAuth2/OIDC thật tới `dev.admin.martonline.lotte.vn/lottemartbos/oidc/authorize/...` (`redirect_uri` trỏ THẲNG về `dev-gateway.martonline.lotte.vn/login/oauth2/code/lotte` — đây chính là domain cần cookie, tự nhiên có được qua redirect chain thật, không cần "probe" giả) → form Magento SSO (Username/Password/Sign in) → **Google Authenticator 2FA** (`.../tfa/google/auth/`, user tự nhập mã) → về lại `dev-console.martonline.lotte.vn/#/dashboard`. Sau khi login: menu sidebar "Search Service" → "Playground" (dashboard có tile "Search Playground") → trang Playground có `<select>` "Chế độ" (native HTML select, option value thật gồm `lexical`/`semantic`/`hybrid`/`adaptive`...) và search box pre-fill query demo "thit heo".

**Kỹ thuật automation đúng, đã verify chạy thành công toàn bộ:**
- Login-detection: poll theo **nội dung trang** (text marker "Search Playground"/"Welcome to..."), KHÔNG dùng URL matching (URL không đổi ổn định qua nhiều bước redirect) — robust hơn nhiều.
- Không thể dùng `input()` chờ Enter (Bash tool của harness này không nối tới stdin người dùng thật) → phải poll theo thời gian cố định + text-marker detection thay vì chờ tín hiệu "đã xong".
- Click menu sidebar "Playground" bị 1 `<div class="menu-area">` che (PrimeNG/Angular overlay animation) → **click(force=True)** giải quyết được, nhưng ưu tiên hơn: click trực tiếp tile "Search Playground" trên Dashboard (text unique, không dính overlay sidebar).
- Dropdown "Chế độ" là **native `<select>` HTML** (không phải overlay component) → text-click vào option luôn fail ("Element is not visible", vì browser render option list ở tầng OS-native, ngoài luồng DOM thường) → phải dùng **`select.select_option(value="adaptive")`**, tìm đúng `<select>` bằng cách check `option[value='adaptive']` tồn tại (trang có 5 `<select>` khác nhau, không đoán bằng label text).
- Sau khi set mode, còn 1 bước **clear query demo mặc định** (pre-fill sẵn khi mở trang, VD "thit heo") — quan trọng vì theo user, để nguyên query demo đó là lý do khiến backend "trông như" đang mock/kẹt ở 1 kết quả cố định. Lúc đầu code chọn sai input (khớp vào ô "Search menu..." của sidebar — luôn rỗng — vì dùng `.first` trên input rỗng đầu tiên tìm thấy, không phải ô search box thật đang có giá trị) → đã sửa: quét TẤT CẢ input, chỉ clear cái ĐẦU TIÊN có value không rỗng (không dừng ở `.first` mù quáng).
- **Nguyên tắc thiết kế quan trọng nhất**: mọi bước UI sau khi login (Playground/Chế độ/clear search box) đều best-effort, KHÔNG được làm mất cookie đã capture nếu fail — cookie hợp lệ ngay khi login xong, độc lập với các bước UI sau đó.

**Về "2 SKU degrade" xuất hiện xuyên suốt session — đã đính chính LẦN 2, hiện tại: KHÔNG phải WAF, KHÔNG phải chưa login, và CŨNG KHÔNG phải "backend cố định mock toàn hệ thống" như ghi nhận trước.** User giải thích lại (2026-08-24, cùng ngày): hiện tượng "2 SKU cố định" nhiều khả năng chỉ là do **query demo mặc định chưa được clear** (xem điểm phía trên) — nếu clear đúng trước khi search thì backend không còn ở trạng thái đó. Nhưng **tại thời điểm này chưa verify được giả thuyết đó vì hệ thống dev đang tạm chết** ("hệ thống hiện tại tạm chết, nên chưa thể test" — lời user) — tức là hiện KHÔNG THỂ chạy bất kỳ test thật nào để xác nhận, không phải do code/automation. `StuckResultGuard` (mục 3c) vẫn đúng về mặt phát hiện hiện tượng; nguyên nhân gốc thật sự (query demo sót lại, hay backend outage, hay cả hai) **chưa được xác nhận dứt điểm** — đừng vội kết luận theo bất kỳ hướng nào ở trên cho tới khi chạy được 1 lần thật, sau khi (a) hệ thống dev hết "tạm chết" VÀ (b) bước clear-query-demo đã chạy đúng (code đã sửa, chưa có cơ hội test lại).

**Việc cần làm khi hệ thống dev sống lại**: chạy `run_batch_test.py --env dev --headed-login --batches-dir SmartSearch/smoke_test --batch 0-10`, xác nhận bước "clear query demo" trong `login_flow_debug.log`/warnings không báo lỗi, rồi mới đánh giá số liệu thật. Không tự chạy lại nhiều lần liên tục nếu hệ thống báo lỗi/degrade — hỏi lại user trước, vì đã có tiền lệ nhầm 2 lần (WAF, rồi mock) trong chính session này.

### 3e. Business rules chính thức — từ meeting BA, 2026-08-24

**Nguồn**: user tổng hợp lại verbatim sau 1 buổi meeting (2026-08-24), chưa có văn bản BRD/storyboard chính thức nào cập nhật theo — coi đây là **ground truth mới nhất**; nếu thấy mâu thuẫn với BRD/Storyboard cũ trong `SmartSearch/REQ/`, báo lại cho BA để xác nhận bản nào đúng, không tự quyết định.

**A. Indexing / data pipeline (backend, OMS → OpenSearch — không do search_engine.js mô phỏng trực tiếp)**
1. Sau khi lên tính năng: **Full sync** (đồng bộ toàn bộ dữ liệu OMS → OpenSearch) chạy 1 lần, kèm đánh index (chuẩn hoá dữ liệu, gắn tag). Về sau, nếu OMS có sản phẩm mới hoặc **update Tên/Short Description**, chỉ **sync lại đúng (các) sản phẩm tương ứng** — incremental theo sản phẩm bị đổi, không full-sync lại toàn bộ mỗi lần.
2. **OpenSearch + Elasticsearch phối hợp** quyết định sản phẩm nào hiển thị ở Search Result/Autocomplete — **Elasticsearch chỉ cho hiển thị sản phẩm đang Active** (kể cả OpenSearch/keyword-match ra sản phẩm không Active, tầng Elasticsearch sẽ chặn, không hiển thị ra ngoài).
3. Batch sync chia theo lô **50 sản phẩm/batch**. Nếu 1 batch lỗi → **toàn bộ batch đó (50 sản phẩm) không được reflect** — all-or-nothing theo batch, không phải partial-success trong 1 batch.
4. Quy trình index hiện tại: **chuẩn hoá dữ liệu (name, short description) → translate → gắn tag ở level category của sản phẩm → Enrichment** (không dấu, ngữ nghĩa, ...).

**B. Ranking / hiển thị kết quả (frontend-facing — ảnh hưởng trực tiếp expected data của search_engine.js)**
5. **Rule ưu tiên bổ sung**: sản phẩm match được **nhiều từ trong keyword nhất** → hiển thị lên đầu. Cơ chế: khi nhập keyword, AI phân tách keyword thành từ (word segmentation), sản phẩm nào match nhiều từ hơn được đánh dấu ưu tiên cao hơn.
6. **Search đúng tên (100% matching)**: nếu search result ra **đúng 1 sản phẩm** khớp 100% (matching toàn bộ từ trong tên) → trang kết quả **CHỈ hiển thị đúng sản phẩm đó** + section **"Có thể bạn sẽ thích"** (không hiển thị thêm sản phẩm nào khác trong khối kết quả chính).
7. **Matching tên < 100%** → trang kết quả hiển thị **sản phẩm matching + các sản phẩm liên quan** (không giới hạn về 1 sản phẩm như rule 6).

**Đã triển khai vào `search_engine.js` + catalog + dataset (2026-08-24, sau khi 3 điểm mơ hồ dưới đây được xác nhận trực tiếp với user):**
- **Rule 2 (Active-only filter)**: catalog export (`scripts/testdata/export_full_store_catalog.py`) đã thêm field `status`, `ec_status`, `visibility_search`, `visibility_catalog`, `substitute_product_sku`, `cross_sell_product_sku` từ `data/ProductInfo/*.ndjson` gốc. `search_engine.js` dùng `isActiveProduct(p)` (`status === 1` hoặc undefined) để loại sản phẩm không Active NGAY TỪ `buildIndex()` — 208/16340 SKU bị loại (status=2). **TBC**: field `status` chỉ là lựa chọn TẠM theo chỉ định user — CHƯA được BA/Dev xác nhận chính thức (có 3 field khác cùng ứng viên: `ec_status`, `visibility_search`, `visibility_catalog`, cho ra tập loại trừ khác nhau). Đã mở **QnA-69** để chốt việc này; nếu câu trả lời đổi field, phải rebuild lại `isActiveProduct()` + catalog + rescore toàn bộ dataset.
- **Rule 5 (matching nhiều từ nhất)**: user xác nhận đây là **1 tiêu chí ranking MỚI, đứng ngang/trên hệ thống tier** — không phải chỉ tie-break trong cùng 1 tier. Implement: `matchedWordCount(entry, qTokens)` tính số từ khoá query (unique) match được với tên/tên EN/tên KR/category của sản phẩm; sort cuối cùng đổi thành `matchedWords > score (tier) > popularity` — nghĩa là matchedWords được so sánh TRƯỚC score, đúng như "đứng trên" tier. Việc này đã trả lời **QnA-54** (BRD FR-SP-01 "khớp tên nhiều nhất" thắng Storyboard SS-SCR-002 "search volume") — QnA-54 đã set Resolved. Có liên quan (nhưng chưa đóng) QnA-66/QnA-67 (thứ tự 4-tầng ưu tiên & tie-break Scorecard) — đã ghi note cross-reference, còn Open.
- **Rule 6 + 7 (1 sản phẩm khớp 100% → "Có thể bạn sẽ thích"; <100% → sản phẩm matching + liên quan)**: user xác nhận nguồn recommendation là **kết hợp** đúng thuật toán đã có ở Zero Result (FR-ZR-02/Storyboard slide 17, SS-SCR-012), KHÔNG phải thiết kế mới — 3 tầng: **Substitute** (field `substitute_product_sku`, phổ biến 82% SKU) → **Cross-sell** (field `cross_sell_product_sku`, **luôn rỗng 0% trong data NSG thật** — tầng này trên thực tế không bao giờ có dữ liệu ở NSG) → **Best-seller** (cùng category, sort theo `popularity`, luôn có kết quả — tầng fallback sâu nhất, không bao giờ trả rỗng). Implement: `isSingleExactMatch(results)` (top1 tier=exact/score=100 VÀ (chỉ có 1 kết quả HOẶC kết quả thứ 2 không cùng tier exact) — định nghĩa "đúng 1 sản phẩm, không đồng hạng"), `pickYouMightLike(index, product, topN=10)` dùng đúng 3 tầng trên. Dataset schema thêm 2 field mới per-scenario: `is_single_exact_match` (bool) và `you_might_like` (array, chỉ có khi `is_single_exact_match=true`) — không đổi field `search_results` cũ.
- **Rule 1, 3, 4 (Full sync/incremental sync, batch-50 all-or-nothing, thứ tự pipeline index)**: thuộc backend/vận hành, không mô phỏng trong `search_engine.js`/dataset — đã ghi test case Integration mới (INT-09-SC2-TC1/TC2, INT-09-SC3-TC1, INT-09-SC4-TC1) mô tả kỳ vọng hành vi, không cần sửa engine.

**Test case & QnA đã cập nhật** (`SmartSearch/testcases/MART_SmartSearch_Combined_TestCases_v3.0_20260818_{VI,EN}.xlsx`, `SmartSearch/qna/MART_SmartSearch_QnA_Log_v1.1_20260817{,_en}.xlsx`, append-only, không sửa dòng cũ ngoài note/Resolved nêu trên):
- Functional (SS-SCR-005): SC10-TC1, SC10-TC2, SC11-TC1, SC12-TC1.
- Integration: INT-01-SC3-TC1 (rule 5), INT-09-SC2-TC1/TC2 (rule 1), INT-09-SC3-TC1 (rule 3), INT-09-SC4-TC1 (rule 4), INT-09-SC5-TC1 (rule 2), INT-10-SC4-TC1 (rule 6).
- QnA: QnA-69 mới (rule 2 field TBC); QnA-54 → Resolved (rule 5); QnA-66, QnA-67 → note cross-reference, vẫn Open.

### 3f. Real search-history data — `data/searchistory/` (bổ sung 2026-08-25)

User bổ sung 2 file thật: `nsg_search_terms_6m.merged.ndjson` (356.049 dòng log search 6 tháng thật của production, mỗi dòng `{q, variants, score, latest_hits, hits_avg, hits_max, last, all_zero?, barcode?}`) và `lotte_tags_vi_en_ko_description_v2.csv` (761 tag dev DỰ ĐỊNH làm — chưa có mapping tag↔SKU thật, chỉ là taxonomy, KHÔNG được tự chế logic tag). Chi tiết đầy đủ ở memory `project_real-search-history-data.md`.

**Phát hiện quan trọng**: 81% (≈280k) truy vấn text thật (loại bỏ barcode) trả về 0 kết quả trong hệ thống production HIỆN TẠI/CŨ — xác nhận qua grep trực tiếp catalog KHÔNG phải do thiếu hàng (VD "mật ong", "coca cola", "rượu vang" đều có hàng trăm SKU thật) mà do search cũ quá yếu — đây chính là lý do dự án Smart Search này tồn tại. Coi file này là **bộ regression/validation**, không phải bộ lỗi cần fix từng dòng.

**Đã chạy diagnostic** (top 10.000 truy vấn theo `score` thật, loại barcode) qua engine hiện tại: 5.226 truy vấn từng zero ở hệ cũ nay engine mới đã tìm ra kết quả; chỉ 17 regression (hệ cũ có hàng, engine mới về 0 — toàn bộ là query 1 ký tự nhiễu hoặc "bàn ủi" đã xác nhận catalog thật sự không có từ trước); chỉ 25 còn zero ở cả 2 bên (đã grep xác nhận từng case — quần áo thời trang tổng quát/brand nhỏ NSG không bán, KHÔNG phải lỗi engine).

**3 lỗi engine thật đã fix** (xem chi tiết + bài học trong memory):
1. `normalize()`/`tokensCaseFold()` thêm xử lý `/` dính liền (giống `&` đã fix từ trước cho P&G) → fix "p/s" (kem đánh răng P/S, top-search, từng 0 kết quả).
2. **Tự bắt được 1 regression khi đang fix #1**: bản đầu tiên (xoá cả khoảng trắng quanh `&`/`/`) làm hỏng tokenize category path (`"... / Sức Khỏe..."` dính chữ) VÀ có nguy cơ làm hỏng 188 sản phẩm có " & " thật trong tên (VD "Xương Ống & Tủy"). Đã revert về bản chỉ dính khi KHÔNG có khoảng trắng xung quanh (lookbehind/lookahead).
3. Thêm SYNONYMS: `bi bi`→`bibigo`, `heniken`→`heineken` (lỗi chính tả vượt edit-distance-1), `sô cô la`→`socola`; CATEGORY: `mỹ phẩm`→`Sức Khỏe, Làm Đẹp`; special-case raw-string cho `m & m`→`m&m` (mỗi bên chỉ 1 ký tự, không qua được filter token length≥2).

**Bộ data mới**: `SmartSearch/test_data/json/batches/NSG_ExpectedData_realsearch_top1000_20260825.json` — top 1.000 truy vấn thật theo lượng search (dimension `real_search_history`, test_id `NSG-RS-0001..1000`), có thêm field `real_search_score/rank/variants`, `real_history_all_zero`, `real_history_hits_max` để QA thấy ngay dòng nào "từng fail ở production". Kết quả: 0/1000 zero-result, 228/1000 được fix so với hệ cũ, 0 regression. KHÔNG dedupe với các batch dimension tổng hợp khác (nguồn dữ liệu khác bản chất, trùng vài query là bình thường).

**Việc còn treo**: bộ tag CSV (761 tag) chưa actionable — cần dev cung cấp mapping tag↔SKU thật trước khi build được 1 "tag tier" thật trong engine; hiện chỉ dùng để double-check tên category (VD xác nhận "mỹ phẩm" là khái niệm thật, không phải bịa).

## 4. Quy tắc bắt buộc (đã bị vi phạm 1 lần → user sửa gắt, đừng lặp lại)

1. **Không bao giờ sửa test case ngoài phạm vi được liệt kê rõ ràng**, dù thấy mâu thuẫn — không có git history cho các workbook Excel, sửa "hộ" có thể phá dữ liệu user tự tay chỉnh mà không có cách khôi phục. Thấy mâu thuẫn → nêu ra và hỏi, không tự sửa.
2. **Kiểm tra file lock trước khi ghi Excel** — user hay mở file trong Excel song song khi chat. `PermissionError` / có file `~$*.xlsx` = đang mở, phải dừng và báo, không ép ghi.
3. **openpyxl gotcha**: `ws.cell(row, col, value=None)` KHÔNG xóa cell (đó là sentinel "chỉ fetch"). Muốn xóa phải gán `ws.cell(row, col).value = None` (2 bước).
4. **QnA log và Combined TestCases đều tồn tại dưới dạng cặp song ngữ VI/EN cùng cấu trúc dòng** — sửa 1 bên phải sửa cả 2, không được chỉ sửa bản đang mở/không bị lock.
5. Khi ghi nội dung tiếng Việt ra file: file write luôn UTF-8-safe, đừng bỏ dấu để né lỗi in console (`UnicodeEncodeError`) — lỗi đó là ở console print, không phải ở nội dung file, đừng đánh đổi nội dung thật để né lỗi hiển thị.
6. Trước khi khẳng định "store X không có mặt hàng Y" — phải broaden search (bare token, partial match), một lần grep hẹp trượt không phải bằng chứng caterogy không tồn tại (từng bị user bắt lỗi vụ "quần jean").
7. **Không tự động hoá việc đăng nhập vào dev-gateway** — luôn giả định user đã login tay và set `DEV_SEARCH_COOKIE`; nếu thiếu/hết hạn, báo lỗi rõ và dừng, không tìm cách "tự lấy cookie" bằng cách khác.
8. **Trước khi tin số liệu response-time/matching từ một lần chạy API thật** — kiểm tra xem có bị "session degrade" không (nhiều query khác nhau trả về y hệt kết quả — xem mục 3c). `run_batch_test.py` đã tự check việc này (`StuckResultGuard`); nếu tự viết script gọi API mới, nhớ mang theo check tương tự, đừng báo cáo relevance dựa trên 1 session có thể đã bị throttle.

## 5. Standing trigger phrases người dùng hay dùng

| User nói | Hành động ngay, không cần hỏi lại |
|---|---|
| "tạo data set" | chạy `scripts/testdata/generate_master_testset.py` cho store được nêu (hoặc `--all-stores`) |
| "run autoscript" (+ URL, hoặc `--env dev`) | chạy `scripts/automation/run_autoscript.py --dataset-dir ... --env dev` (hoặc URL trực tiếp), rồi **báo lại tóm tắt kết quả chấm điểm trong chat** (Precision@1, tier breakdown, MRR, zero-result rate, p95 latency, số cần review tay) — không chỉ báo "done" |
| "test tay" / manual QC (k6, Postman) | chạy `scripts/performance/export_manual_qc_assets.py` từ dataset có sẵn, không tự viết Postman/k6 tay |
| "gen 1 bộ data set" (trong ngữ cảnh NSG search-testdata engine, mục 3b) | sinh batch mới không trùng query cũ theo quy trình mục 3b, đặt tên `NSG_ExpectedData_<start>-<end>_<date>.json` |
| "chạy batch X" / "chạy all batch" (2026-08-24, mục 3c) | nhắc user đã set `DEV_SEARCH_COOKIE` chưa, rồi chạy `scripts/automation/run_batch_test.py --env dev --batch <X hoặc all>`, báo tóm tắt latency (avg/p95) + recall trung bình + % lỗi trong chat, dẫn link `dashboard.html`/`report.xlsx` |

## 6. Ngôn ngữ & phong cách làm việc

- Trả lời chat bằng **tiếng Việt**; giữ thuật ngữ kỹ thuật/tên sản phẩm ở nguyên tiếng Anh.
- Người dùng chấp nhận làm việc lâu, nhiều vòng lặp nhỏ trong 1 phiên (đã có phiên với 11+ vòng sửa liên tiếp) — ưu tiên sửa đúng, verify bằng script/test thật trước khi báo "đã sửa xong", không đoán.
- Khi không chắc regex/grep đã đủ rộng, hoặc chưa có API thật để verify — nói rõ giới hạn, đừng khẳng định chắc như đã kiểm chứng.

## 7. Việc còn thiếu / đang chờ (tại 2026-08-24)

- **Đã có URL API search/autocomplete thật của dev-gateway** (từ 2026-08-24, xem mục 3a) — `config/environments.yaml` mục `dev` không còn null. Vẫn thiếu: URL của môi trường **staging/production** thật (mục `staging` vẫn null); cookie auth của dev phải refresh tay mỗi lần chạy (không có cơ chế lấy cookie tự động).
- **Smoke test 15 dòng đầu tiên (golden_testsets, mục 3a) cho P@1=0%** — CHƯA kết luận được đây là finding thật hay do session degrade (xem mục 3c — cùng session đó sau đó được xác nhận bị degrade khi test `run_batch_test.py`), vì smoke test đó chạy TRƯỚC khi phát hiện ra vấn đề session degrade và trước khi có `StuckResultGuard`. **Việc cần làm tiếp theo, quan trọng**: chạy lại `run_autoscript.py --env dev` (không `--limit`) với cookie MỚI để có số liệu đáng tin, đừng dùng lại số 15 dòng đó làm bằng chứng.
- **`run_batch_test.py` (mục 3c) chưa từng chạy full/thành công với 1 session khoẻ** — mọi lần test trong phiên 2026-08-24 đều bị `StuckResultGuard` chặn do session degrade trước khi hoàn tất. Logic so khớp/rank đã verify đúng qua debug thủ công, nhưng dashboard thật (Excel + HTML) với số liệu match tốt chưa được người dùng xem qua lần nào — cần chạy lại với cookie mới và xem qua 1 lượt.
- `data/glossary/regional_terms.csv` và `related_terms.csv` chưa được QA/BA curate chính thức (chỉ có vài dòng nháp do AI đề xuất, đánh dấu rõ là draft).
- "Nói lái" (chơi chữ kiểu Việt Nam) được yêu cầu cho engine NSG nhưng chưa implement — biết là gap, chưa làm.
- Dimension "intent" trong batch generator đã cạn glossary từ batch 3000-4000 trở đi — coverage intent sẽ gần 0 ở batch mới trừ khi mở rộng thêm `INTENT`/`SYNONYMS`/`REGIONAL`/`CATEGORY`.
- 2 sản phẩm có lỗi data thật ở nguồn (`(__EMPTY__VALUE__)` leak vào tên SKU 4550516703545/552) — đã note để báo BA/data team, chưa fix (không thuộc phạm vi pipeline này).

## 8. Nguồn tham khảo bổ sung

- Chi tiết đầy đủ, theo timeline từng vòng chỉnh sửa: xem hệ thống memory của AI hỗ trợ project này (`project_smart-search-test-pipeline.md`, `project_search-testdata-engine.md`, `project_full-catalog-artifacts.md`, `feedback_standing-commands.md`, `feedback_testcase-scope-discipline.md`). File này (`AI_CONTEXT.md`) là bản tóm tắt tĩnh tại một thời điểm — memory có thể có cập nhật mới hơn, và có thể còn ghi path cũ theo `output/...` từ trước ngày 2026-08-24 (xem mục 2 để quy đổi sang `SmartSearch/...`).
- `SmartSearch/README.md` — cú pháp CLI chi tiết từng script.
- `README.md` (root) — điểm vào ngắn gọn, danh sách các module hiện có.
