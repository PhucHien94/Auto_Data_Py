# Skill: review testcase

Mục đích
- Hướng dẫn quy trình kiểm tra xem các testcase hiện có có bao phủ BRD/REQ không, và đánh giá tính chính xác của từng testcase.
- Cung cấp luồng tương tác: hỏi người dùng một `tính năng` hoặc `màn hình` (hoặc `Requirement ID`) cần review, sau đó tự động tìm REQ và testcases, báo cáo coverage và các testcase cần sửa hoặc thêm.

Phạm vi
- Áp dụng cho mọi module/epic được mô tả trong BRD/REQ.
- Dành cho team QA, BA, hoặc kỹ sư kiểm thử chịu trách nhiệm review testcase.

Kết quả mong muốn
- Bảng mapping giữa `Requirement ID` và `Testcase ID`.
- Danh sách các requirement chưa có testcase (gaps).
- Danh sách testcase không chính xác hoặc cần chỉnh sửa (issues).
- Đề xuất testcase mới hoặc cập nhật.

Tiền điều kiện
- Có bản BRD/REQ (phiên bản rõ ràng, có `Requirement ID`).
- Có repository testcase (file, test management tool) truy cập được.
- Người review có quyền đọc BRD và testcases.

Luồng tương tác (Interactive flow)
- Bước 0 — Hỏi người dùng: "Bạn muốn review tính năng hay màn hình nào?" (có thể cung cấp `Requirement ID`, tên feature, hoặc đường dẫn BRD).
- Bước 1 — Tự động tìm nguồn:
   - Đọc REQ từ folder `SmartSearch/REQ`.
   - Đọc testcases từ folder `SmartSearch/testcases` (nếu có file combined, dùng `Combined_TestCases_auto.csv`).
- Bước 2 — Lọc & mapping:
   - Sử dụng rule-based matching (tên feature, Requirement ID, từ khoá) để tìm testcase liên quan.
   - Nếu mapping tự động không rõ ràng, liệt kê các ứng viên để người dùng duyệt.
- Bước 3 — Kiểm tra tính đúng/đủ:
   - Báo cáo: có bao nhiêu testcase liên quan, có requirement tương ứng không, và đánh dấu các testcase có `expected` không rõ hoặc không khớp.
- Bước 4 — Kết quả và hành động tiếp theo:
   - Xuất báo cáo ngắn (mapping, gaps, issues).
   - Gợi ý tạo testcase mới hoặc sửa testcase hiện có, có thể xuất template CSV để người dùng chỉnh sửa.


Bước thực hiện (Workflow)
1. Chuẩn bị
   - Lấy BRD/REQ (phiên bản mới nhất). Ghi chú phiên bản và ngày.
   - Lấy danh sách testcase hiện có (file excel, tms, ndjson, v.v.).
2. Chuẩn hóa dữ liệu
   - Chuẩn hoá định danh: đảm bảo mọi `Requirement` có `Requirement ID` và testcases có `Testcase ID`.
   - Đưa BRD và testcases về dạng dễ mapping (CSV/Excel/NDJSON).
3. Lập mapping sơ bộ
   - Với mỗi `Testcase`, xác định `Requirement ID` liên quan.
   - Tạo bảng mapping: `Requirement ID` → [Testcase ID...].
4. Kiểm tra bao phủ
   - Đánh dấu các `Requirement` chưa có testcase (gap).
   - Đánh dấu các testcase dư thừa (không liên quan đến bất kỳ requirement nào).
5. Đánh giá tính chính xác của testcase
   - Kiểm tra mỗi testcase mapping có: đầu vào, bước thực hiện, dữ liệu test, expected result rõ ràng và phù hợp requirement không.
   - Phân loại vấn đề: thiếu thông tin, expected không đúng, kịch bản không khớp, dữ liệu không phù hợp.
6. Quyết định và phân loại
   - Nếu requirement chưa có testcase → thêm vào danh sách `Needs Testcase`.
   - Nếu testcase không đúng → đánh dấu `Needs Fix` kèm gợi ý sửa.
   - Nếu testcase trùng lặp hoặc không cần thiết → đánh dấu `Review/Remove`.
7. Đề xuất hành động
   - Lập danh sách testcase cần viết/cập nhật với mô tả ngắn.
   - Gán ưu tiên (High/Medium/Low) và owner.
8. Tổng kết
   - Chuẩn bị báo cáo: mapping, gaps, issues, recommended actions.
   - Chạy review/meeting với BA/DEV/QA để xác nhận.

Decision points (Những điểm cần quyết định)
- Nếu một requirement có nhiều testcase: giữ tất cả hay gộp? (quy tắc: gộp nếu nội dung chồng chéo >70%).
- Nếu testcase thiếu dữ liệu nhưng ý định rõ ràng: sửa nhẹ hay viết lại hoàn toàn?
- Ngưỡng coverage chấp nhận được (ví dụ: 100% cho critical, ≥90% cho major).

Tiêu chí chất lượng (Quality Criteria)
- Coverage: Tất cả `Critical` requirement phải có ít nhất 1 testcase.
- Clarity: Mỗi testcase phải có bước thực hiện rõ ràng và expected result cụ thể.
- Traceability: Mỗi testcase phải trace tới ít nhất 1 `Requirement ID`.
- Non-redundancy: Tránh trùng lặp bước/expected giữa testcases tương tự.

Kết quả đầu ra (Artifacts)
- Bảng mapping (`Requirement ID` ↔ `Testcase ID`) dưới dạng CSV/Excel.
- File issues list (requirement/testcase, loại issue, mô tả, owner, priority).
- Đề xuất testcases mới (mẫu template).

Ví dụ prompt để chạy skill
- "Review testcases cho module X so với BRD phiên bản v2 và xuất báo cáo gaps." 
- "Mapping testcases hiện có với yêu cầu trong file `BRD_ModuleX.docx`." 

Gợi ý cải tiến tiếp theo
- Tạo script tự động map bằng rule-based NLP (dùng tên requirement và tiêu đề testcase).
- Thêm checklist tự động hoá để validate expected result định dạng.

Hướng dẫn ngắn để sử dụng
1. Chuẩn bị file BRD và export testcases sang CSV/Excel.  
2. Chạy theo các bước từ 1 → 8.  
3. Xuất artifacts và mở review meeting.

Ngôn ngữ: Tiếng Việt.  

Liên hệ tác giả: QA Lead / BA Lead để xác thực kết luận và phân công hành động.
