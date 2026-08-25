# Smoke test — 10 keyword

Bộ dữ liệu nhỏ (10 scenario) dùng để chạy nhanh `run_batch_test.py` hết-đầu-đến-cuối (login,
preflight, gọi API thật, so khớp expected/actual, dashboard) mà không phải chờ 1 batch 1000 dòng.
Cùng schema và cùng độ tin cậy với các batch thật trong `SmartSearch/test_data/json/batches/` —
`search_results`/`autocomplete_suggestions` được tính bằng chính `search_engine.js` +
catalog NSG thật (`SmartSearch/full_store_catalog_desc/nsg.json`), không phải dữ liệu bịa.

## Chạy

```powershell
$env:DEV_SEARCH_COOKIE = "..."   # đăng nhập tay trước, xem SmartSearch/README.md
python scripts\automation\run_batch_test.py --env dev --batches-dir SmartSearch\smoke_test --batch 0-10
```

## 10 query (tự chọn để phủ đủ các dimension chính của bộ dataset thật)

| test_id | dimension | query | ý nghĩa |
|---|---|---|---|
| SMOKE-0001 | exact | (tên sản phẩm thật, lấy trực tiếp từ catalog) | khớp chính xác tên |
| SMOKE-0002 | typo | (tên sản phẩm thật, đảo 2 ký tự liền kề) | gõ sai chính tả |
| SMOKE-0003 | no_diacritics | (tên sản phẩm thật, bỏ dấu) | gõ không dấu |
| SMOKE-0004 | multilang | (tên tiếng Anh của 1 sản phẩm thật) | đa ngôn ngữ |
| SMOKE-0005 | synonym | mua thịt lợn | từ đồng nghĩa (lợn ↔ heo) |
| SMOKE-0006 | regional | quả thơm | phương ngữ (thơm ↔ dứa/khóm) |
| SMOKE-0007 | intent | đi mưa | ngữ cảnh sử dụng |
| SMOKE-0008 | category | đồ ăn vặt | duyệt theo ngành hàng |
| SMOKE-0009 | generic | sữa | từ khoá phổ thông 1 âm tiết |
| SMOKE-0010 | partial | mua đồ biển | last-resort, từ không liền kề trong tên SP |

Xem field `note` trong file JSON để biết SKU/tên sản phẩm tham chiếu cụ thể cho từng dòng, và tier
thực tế mà engine đã chọn cho query đó (không phải lúc nào cũng đúng như tên dimension dự kiến —
đó là hành vi thật của engine, không phải bug của bộ smoke test này; xem `AI_CONTEXT.md` mục 3d).

## Sinh lại / mở rộng

Script sinh file này (`gen_smoke_test.js`) chỉ sống trong session scratchpad, không commit vào
repo (theo đúng convention của `generate_batch.js`/`compute_batch.js` — xem `AI_CONTEXT.md` mục
3b). Cần sinh lại (đổi query, thêm dòng) thì viết lại script tương tự: load
`SmartSearch/test_data/json/_source/search_engine.js` + `SmartSearch/full_store_catalog_desc/nsg.json`
qua Node, gọi `SE.buildIndex()`, rồi `SE.search()`/`SE.autocomplete()`/`SE.routeFor()` cho từng query,
đóng gói đúng shape `{generatedDate, store, batchRange, totalScenarios, scenarios}` như file batch thật.
