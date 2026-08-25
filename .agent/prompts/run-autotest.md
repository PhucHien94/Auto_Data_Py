---
description: Chạy bộ test data (batch) thật đối với Smart Search API và xuất dashboard
model: claude-3-7-sonnet
---
Tiền điều kiện: người dùng đã đăng nhập thủ công (qua trình duyệt/dev-console) và đã set biến
môi trường `DEV_SEARCH_COOKIE` với cookie session mới nhất - KHÔNG tự động hoá bước đăng nhập,
KHÔNG lưu giá trị cookie vào bất kỳ file nào trong repo. Nếu chưa có `DEV_SEARCH_COOKIE`, dừng lại
và nhắc người dùng đăng nhập lại trước.

Bộ test data là các batch JSON 1000 dòng/batch tại `SmartSearch/test_data/json/batches/`
(`NSG_ExpectedData_<start>-<end>_<date>.json`). Hãy:
1. Hỏi người dùng muốn chạy batch nào (một range cụ thể, nhiều range, hay toàn bộ `all`).
2. Chạy `python scripts/automation/run_batch_test.py --env dev --batch <đã chọn>` (thêm `--limit N`
   nếu muốn smoke-test trước khi chạy full; `--sleep-ms` nếu nghi ngờ bị WAF rate-limit).
3. Script tự làm: preflight kiểm tra đăng nhập trước khi chạy cả batch; gọi Search + Autocomplete
   thật cho mỗi scenario; đo response time; so khớp kết quả actual với `search_results`/
   `autocomplete_suggestions` đã có sẵn trong batch (expected); tự dừng sớm nếu phát hiện session
   bị degrade (nhiều query khác nhau trả về y hệt kết quả - dấu hiệu WAF throttle, không phải search
   thật bị lỗi).
4. Kết quả: `report.xlsx` (sheet Dashboard có chart + Detail theo scenario) và `dashboard.html`
   (trang xem nhanh, mở bằng browser) trong `SmartSearch/runs/batch_<batch>_<timestamp>/`.
5. Tóm tắt lại trong chat: response time (avg/p95), recall trung bình (search/autocomplete), %
   khớp hoàn toàn, số lỗi - không chỉ báo "đã chạy xong".

Nếu script báo dừng do session degrade: KHÔNG coi số liệu thu được là finding thật về search -
nhắc người dùng đăng nhập lại rồi chạy lại.
