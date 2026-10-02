# Smart Search QnA – Part 1 · Danh sách cần hỏi tiếp

_Rà soát ngày 07/09/2026 – dựa trên file `MART_PART1_SmartSearch_QnA_Log_v1.0_07092026.xlsx`. Cập nhật thêm 10/09/2026 (mục E)._

**Đã xử lý:** 39/69 QnA có câu trả lời dùng được → đã cập nhật test case tương ứng (cả file VI + EN,
sheet Functional + Integration), đổi `Trạng thái = Resolved`, bỏ màu cam (giữ nguyên QnA ID để track).
Trong đó **9 QnA** kết luận **Out of scope v1** (giữ nguyên nội dung TC, chỉ đánh dấu OOS):
QnA-04, 07, 17, 26, 30, 31, 44, 46, 58.

**Còn 30 QnA giữ màu cam** – chi tiết bên dưới.

---

## A. BA chưa điền câu trả lời (ô "Câu trả lời" trống) – cần nhắc BA

| QnA | Vấn đề | TC bị chặn |
|-----|--------|------------|
| QnA-03 | Ngưỡng debounce / fuzzy-match (Levenshtein) / confidence nhận diện ảnh | SS-SCR-002-SC5-TC2, SS-SCR-015-SC1-TC3, INT-03-SC2, INT-06-SC1, INT-09-SC1 |
| QnA-05 | Nhãn nút trên Toast "Đã thêm giỏ": giữ "Đóng" hay đổi "Xem giỏ" | (bổ sung TC nếu đổi) |
| QnA-09 | Có bổ sung khung hướng dẫn canh giữa sản phẩm ở Camera v1 không | SS-SCR-013-SC1-TC3 |
| QnA-11 | SS-SCR-007 không có trong bản storyboard export – bị thiếu hay gộp vào SS-SCR-008 | SS-SCR-005-SC1-TC1 |
| QnA-16 | Cơ chế Toast khi bấm (+) dồn dập / nhiều SKU liên tiếp | SS-SCR-011-SC2/SC3 (parent giờ OOS theo QnA-07) |
| QnA-19 | Thu hồi quyền Camera **giữa phiên** – UI xử lý ra sao khi quay lại foreground | SS-SCR-013-SC3-TC1 |
| QnA-20 | Badge giỏ khi >99: rút gọn "99+" hay số đầy đủ | SS-SCR-001-SC6-TC2 |
| QnA-21 | Mất mạng ngay khi tải Pre-search (skeleton / lỗi cục bộ theo khối / ẩn khối) | SS-SCR-001-SC9-TC1 |
| QnA-27 | Tách FR-GD-01 vs FR-GD-03; **thiếu hẳn nhóm TC cho Graceful Degradation thực tế** | toàn bộ SS-SCR-004 |
| QnA-39 | Khi **tất cả** SKU khớp trực tiếp đều hết hàng → ở lại SS-SCR-005 hay chuyển Zero Result | SS-SCR-012-SC4-TC2 |
| QnA-59 | Định nghĩa cụ thể trọng số Margin / Promotion / Trending trong Scorecard | SS-SCR-008-SC1-TC3 |
| QnA-64 | **Phạm vi store trong AI Search**: 1 index/store hay index gộp + filter; autocomplete/trending/best-seller tính theo store nào; đổi Serving Store khi đang xem kết quả | ảnh hưởng giả định nền toàn bộ golden test set |
| QnA-65 | BRD nói synonym "tự động", kiến trúc thật (OVERVIEW-FLOW-VI_Phase1.pdf) là **thủ công + nút Áp dụng** – chốt lại văn bản REQ; và có 2 bộ synonym (search-service vs indexer-service) | giả định nền Test Strategy Artifact Phần 0 |
| QnA-68 | Tồn kho về 0 do khách thêm giỏ hết – còn hiển thị khi search lại không (cùng khách / khách khác), có nhất quán qua Search Index dùng chung không | liên quan INT-08-SC1, INT-09-SC1 |
| QnA-69 | Field nào định nghĩa **"Active"** cho rule lọc Elasticsearch: `status` / `ec_status` / `visibility_search` / `visibility_catalog` (hay kết hợp). Data/engine đang **tạm dùng `status`** | SS-SCR-005-SC12-TC1, INT-09-SC5-TC1 |

---

## B. BA đã đẩy sang TD / Data Analytics – cần đòi câu trả lời từ bên tương ứng

| QnA | Cần ai trả lời | Nội dung |
|-----|----------------|----------|
| QnA-25 | TD | Ngưỡng Loading UI đa kênh; voice P95 = 4.000ms (NFR-005) hay 6.000ms (FR-VS-08) |
| QnA-32 | TD | Định nghĩa + quy tắc tie-break của 7 sort cũ ("logic hệ thống cũ": Lượt mua = Order Count hay Quantity? Được quan tâm = PDP view hay impression? Sao TB có Bayesian không? Tie-break trùng giá?) |
| QnA-33 | TD | Công thức Information Gain sinh chip Nhãn + ngưỡng tối thiểu + thứ tự hiển thị |
| QnA-38 | TD | Ngưỡng SLA ở chế độ fallback Keyword search (BA chỉ expect "vài giây đổ lại") |
| QnA-40 | TD | Thuật toán Cross-sell / Basket Analysis (Apriori? co-occurrence? ngưỡng support/confidence? cá nhân hoá hay tổng hợp? khung thời gian?) |
| QnA-49 | Data Analytics | Công thức đo KPI-04 (Search→Cart), KPI-06 (Query Refinement), KPI-07 (Search Retry) |
| QnA-56 | TD / Data Eng | Chu kỳ chạy Data Pipeline synonym + ai kiểm duyệt chất lượng cặp từ tự sinh |
| QnA-57 | TD | Trọng số Scorecard (40/20/15/15/10) lưu ở đâu: hardcode / config file / feature flag / DB |
| QnA-63 | TD | Relevance 40% có tích hợp 6 cơ chế match FR-SM-01→07 không, Matching–Ranking là 2 tầng nối tiếp hay blend. _(BA đã xác nhận **ý định nghiệp vụ** = CÓ; chỉ còn phần kiến trúc.)_ |
| QnA-66 | TD | Thứ tự áp 3 override (Out-of-stock / Guest PA=0 / Sponsored) **trước hay sau** bước tính blend. _(BA đã chốt: mô hình là **blend trọng số duy nhất**, KHÔNG phải chuỗi "tầng ưu tiên".)_ |
| QnA-55 | TD / BA | Thứ tự ưu tiên hiển thị giữa các loại gợi ý autocomplete (khớp trực tiếp / đồng nghĩa / đa ngôn ngữ / không dấu). BA nói "đã có trong BRD" nhưng chưa chỉ rõ mục nào. _(Phần "gõ không dấu → gợi ý có dấu" đã được xác nhận, đã áp vào TC.)_ |
| QnA-52 (đuôi) | TD | Event tracking hiện có phân biệt được 3 nguồn đếm lượt tìm kiếm (Enter / nút Search / tap Autocomplete) không |

---

## C. Câu trả lời chưa rõ / BA hỏi ngược – cần làm rõ lại với BA

| QnA | Tình trạng |
|-----|------------|
| QnA-06 | BA ghi **"Done"** + trỏ tới "bảng mapping đầy đủ ở QnA-06" nhưng ô câu trả lời chỉ có chữ "Done". **Cần BA gửi bảng mapping REQ ID ↔ Screen ID đầy đủ** để áp phần còn lại (FR-SP-03, FR-PR-03, FR-SF-02/03, FR-AC-01, FR-IS-01..04, FR-VS-01..03). Phần QnA-48 chỉ đích danh (FR-SP-02 → FR-PS-01/02/03/04; FR-ZR-01 → FR-SM-07) **đã áp** vào toàn bộ SS-SCR-001 + SS-SCR-012. |
| QnA-08 | BA ghi **"Done"** – NFR ID chính thức áp cho Loading UI (SS-SCR-004) là gì? NFR-001? NFR-004/005? hay đã thêm NFR-SS-01 vào BRD? |
| QnA-15 | BA hỏi ngược: _"Lý do vì sao phiên đăng nhập hết hạn ngay lúc thao tác?"_ → cần giải thích ngữ cảnh (token TTL ngắn, admin revoke, đổi mật khẩu ở thiết bị khác…) rồi hỏi lại hành vi UI mong muốn. |
| QnA-35 | BA trả lời chung ("dùng Scorecard Ranking mới nếu chọn 'Liên quan nhất'") – **chưa định nghĩa "từ liên quan"** (co-purchase / category-sibling / complementary) để curate `data/glossary/related_terms.csv`. |
| QnA-46 | BA trả lời **theo trí nhớ** ("em nhớ TD từng nói vậy") – cần **TD xác nhận chính thức**: voice = voice-to-text thuần rồi chạy text search, không có banner confidence riêng. _(Đã tạm đánh OOS v1.)_ |

---

## D. Câu trả lời kéo theo REWORK test case – cần QC quyết cách xử lý

| QnA | Hệ quả |
|-----|--------|
| **QnA-34** | BA chốt "về UI ưu tiên Figma" → nút **"Bộ lọc" KHÔNG có badge tổng**. SS-SCR-009-SC1-TC1 và **toàn bộ SS-SCR-010-SC1/SC2/SC3** hiện viết theo giả định "badge tổng = n / badge giảm dần" → **cần viết lại** theo cơ chế chip filter active. Hiện mới ghi chú cảnh báo vào cột Comments, **chưa sửa Expected Result**. |
| **QnA-66** | INT-01-SC1-TC2 ("Business rule > Relevance thuần") dựa trên giả định "tầng ưu tiên" đã bị BA bác (mô hình là blend). Đã đánh dấu **"CẦN VIẾT LẠI"** ở Expected; scenario INT-01-SC1 đã sửa mô tả sang mô hình blend + 3 override. |
| **QnA-07** | "Thêm giỏ hàng ngoài scope Smart Search" → đã đánh **OOS toàn bộ**: SS-SCR-011-SC1-TC1…SC4-TC1 (7 TC) + SS-SCR-006-SC5-TC1 + INT-08-SC1-TC1/TC2. **Mất coverage đáng kể** – xác nhận lại đúng ý BA. |
| QnA-42 | Phần v1 đã rõ (Xu hướng = auto; Từ điển cấm = bộ AI tạo sẵn). Phần **config tay qua CMS** vẫn chờ Mart confirm – cần theo dõi với Mart. |

---

## E. Phát hiện mới khi đối chiếu REQ (10/09/2026) – CHƯA raise thành QnA chính thức, CHƯA sửa test case

_Phát sinh khi trả lời câu hỏi trực tiếp của QC, chưa đưa vào file QnA log. Ghi lại đây để confirm hướng xử lý trước khi sửa TC hoặc gửi BA/TD._

| # | Vấn đề | Bằng chứng REQ | Cần quyết |
|---|--------|-----------------|-----------|
| E1 | **Autocomplete có áp dụng từ đồng nghĩa (FR-SM-04) không?** | FR-SP-01 (REQ duy nhất định nghĩa Autocomplete) chỉ nói "đếm keyword khớp tên sản phẩm". Toàn bộ nhóm FR-SM-01→07 (đồng nghĩa, đa ngôn ngữ, phương ngữ, không dấu, ngữ nghĩa) chỉ được BRD đặt dưới mục **"Search Results Page"**, không có trong mục Autocomplete — kể cả bảng thành phần UI (dòng "Autocomplete List" chỉ gắn FR-SP-01, không có FR-SM-04). | Hỏi BA/TD: Autocomplete có kế thừa FR-SM-01→07 không, hay chỉ literal match theo tên sản phẩm? Nếu có, cần REQ ID chính thức nối 2 mục lại. |
| E1b | Ghi chú cũ tại `SS-SCR-002-SC1-TC1` (theo QnA-55) trích "gõ không dấu → gợi ý có dấu — **theo BRD FR-SM-06**" — nhưng FR-SM-06 cũng chỉ scope Search Results Page như E1, không có dòng nào nói áp dụng Autocomplete. | (như trên) | Sửa lại trích dẫn cho chính xác: đây là theo **câu trả lời BA (QnA-55)**, không phải theo REQ literal — chờ cùng lúc với E1. |
| E2 | **Gõ sai chính tả, Autocomplete hiển thị gì?** `SS-SCR-002-SC1-TC4` đang test: danh sách gợi ý **tự fuzzy-match** (gõ "vinamild" → list tự hiện "vinamilk"), trích dẫn FR-SP-01 — nhưng FR-SP-01 không hề nhắc fuzzy-match. Cơ chế REQ chính thức duy nhất cho lỗi chính tả là **FR-AC-01**: input **giữ nguyên** chữ sai, chỉ có **Banner** gợi ý, khách phải chủ động tap mới đổi. TC4 còn hiểu sai thời điểm Banner (ghi "sau khi submit" — nhưng FR-AC-01 + `SS-SCR-003-SC1-TC1` xác nhận Banner hiện **ngay lúc đang gõ**, cùng màn Autocomplete). | FR-AC-01, FR-SP-01, đối chiếu `SS-SCR-003-SC1-TC1` | Quyết 1 trong 2: (a) sửa `SS-SCR-002-SC1-TC4` theo đúng cơ chế Banner (bỏ giả định fuzzy-match ngầm trong list), hoặc (b) ghi QnA mới hỏi BA/TD có tồn tại song song cơ chế fuzzy-match-trong-list không. Liên quan QnA-03 (ngưỡng fuzzy-match vẫn chưa có câu trả lời). |
