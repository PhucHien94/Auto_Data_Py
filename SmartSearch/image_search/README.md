# Image Search Eval

So sánh các cơ chế image search trên [dev console playground](https://dev-console.martonline.lotte.vn/#/search-service/playground?q=&size=100).

Bốn cơ chế đang so (sửa trong `scripts/config.mjs`):

| Giá trị | Mô tả trên UI |
|---|---|
| `vector` | ảnh chính của sản phẩm |
| `vector_titan` | Titan G1 (Sydney), trường `image_vector_titan_v1`, chỉ ảnh chính |
| `vector_titan_multi` | Titan G1 trên **nhiều ảnh** của sản phẩm (thêm 2026-09-22) |
| `caption` | Nova Lite đọc ảnh ra câu tìm kiếm |

Backend còn nhận `vector_multi` (3 ảnh đầu gallery) — đã đo trả HTTP 200. Thêm vào mảng
`MODES` là nó tự chạy; Excel, dashboard và audit đều suy ra số cơ chế từ mảng đó, không
chỗ nào hard-code con số.

## Chạy

```bash
npm install
npx playwright install chromium

npm run auth      # đăng nhập dev console 1 lần, lưu session
npm test          # xác minh selector còn đúng với UI
npm run check     # validate bộ ảnh + ground truth
npm run smoke     # 3 ảnh đầu, hiện browser
npm run run       # chạy full
npm run score     # metric + so cặp
```

`run.mjs` bỏ qua ảnh đã có kết quả, nên đứt giữa chừng thì chạy lại là chạy tiếp.
Muốn chạy lại từ đầu thì thêm `--force`.

## Hai phần tách biệt trong repo này

| Phần | Chạy bằng | Vai trò |
|---|---|---|
| `scripts/` | `node`, thư viện `playwright` | Chạy eval thật — vòng lặp 150 ảnh × 3 cơ chế |
| `tests/` | `@playwright/test` | Chỉ để xác minh selector + phục vụ recorder |

Eval **không** chạy bằng `playwright test`. Vòng lặp qua bộ ảnh với ghi kết quả thô
và resume-khi-đứt không hợp với test runner, nên nó là script Node thường.

`tests/` tồn tại vì hai lý do: `npm test` biến câu hỏi "selector còn đúng không"
thành đỏ/xanh cụ thể ở từng bước, và VS Code Testing panel cần `playwright.config.js`
mới chịu hiện nút **Record new** / **Pick locator**.

## Xác nhận selector trước khi chạy full

Selector trong `scripts/config.mjs` suy ra từ screenshot UI, chưa chạy thật lần nào.
`npm test` sẽ chỉ đúng chỗ sai:

| Test đỏ | Nghĩa là |
|---|---|
| đã đăng nhập thật | Có call `/api/` trả 401 → session hỏng, chạy lại `npm run auth` |
| nút camera mở được modal | `SELECTORS.cameraButton` sai |
| có `input[type=file]` | Upload là drag-drop thuần, không có input ẩn → cần mô phỏng `DataTransfer` |
| dropdown hiện đủ option | Không phải `<select>` thật → xem mục dưới |
| `resolvedImageMode` khớp | Đổi cơ chế không trigger search, hoặc UI không đổi model thật |

Lấy selector đúng: `npm run record` (mở Inspector, bấm **Pick locator**), hoặc
`npm run codegen`, hoặc nút **Record new** trong Testing panel của VS Code.

Hai chỗ nhiều khả năng phải sửa:

**Nút camera** — `button:near(input[placeholder="Tìm kiếm"])` là selector đoán.
Chạy `npm run codegen`, click nút camera, copy selector Playwright sinh ra.

**Dropdown "Cơ chế ảnh"** — code đang dùng `page.selectOption()`, chỉ chạy nếu đó là
`<select>` thật. Nếu là combobox custom (React Select, Ant Design…) thì đổi trong
`run.mjs` thành:

```js
await page.click(SELECTORS.modeSelect);
await page.click(`text=${mode}`);   // hoặc role=option[name=...]
```

**Nếu đổi cơ chế không tự search lại** — test `resolvedImageMode` sẽ timeout.
Lúc đó set `SELECTORS.submitButton` trỏ vào nút tìm kiếm.

Sửa xong chạy lại `npm test` tới khi xanh hết rồi mới `npm run run`.

Upload dùng `setInputFiles()` bắn thẳng vào `<input type="file">` ẩn sau link
"Chọn ảnh từ máy", nên không cần mô phỏng drag-drop hay paste.

## Nhánh Excel: ảnh nhúng trong file keyword → top-40 mỗi cơ chế

Nhánh chạy riêng, độc lập với `manifest.csv`: đầu vào là các ảnh **nhúng thẳng
vào cột J** của sheet `Top100_Keywords` trong `ImageSearch_TopKeywords_100_*.xlsx`,
đầu ra đổ ngược lại chính file đó.

```bash
npm run excel:extract    # trích ảnh nhúng ra images/excel_keywords/ + manifest.json
npm run excel:run        # mỗi ảnh x 3 cơ chế -> results/excel_top40/<mode>/<id>.json
npm run excel:images     # tải ảnh sản phẩm của top-40 về result_images/<sku>.webp
npm run excel:write      # đổ kết quả vào Excel (3 sheet)
```

Bốn bước đều chạy lại được: `excel:run` bỏ qua ảnh đã có kết quả (`--force` để chạy
lại, `--only kw011,kw012` để lọc), `excel:images` bỏ qua SKU đã tải.

#### Độ phủ ngành hàng

```bash
npm run cattree                              # (1 lần) dựng cache cây ngành từ ProductInfo
npm run coverage -- --level 3                # đo độ phủ
npm run coverage -- --level 3 --suggest 2    # kèm đề xuất keyword lấp chỗ trống
```

**Cây ngành lấy từ `data/ProductInfo_v1.1/.../mart_vi_nsg_product.ndjson`, trường
`category_full_path` — 451 ngành, tới 5 cấp.** Đừng dùng trường `cat` của
`full_store_catalog/nsg.json`: nó chỉ là chuỗi 2 cấp, 48 nhánh, và đo độ phủ trên đó là
đo trên bản đồ thu nhỏ. Lần đầu tôi đo nhầm như vậy và báo "phủ 99,5%", trong khi ở cấp 3
thật thì mới 54%. Riêng rượu: trường `cat` chỉ thấy 26 sản phẩm, cây thật có **216 sp
ngành Đồ Uống/Rượu** + 48 sp vang/bia — tức bản đồ thu nhỏ còn gán nhãn sai.

| Cấp | Số ngành (≥10 sp) | Ý nghĩa |
|---|---|---|
| 2 | 30 | ngành lớn: Bánh Kẹo, Đồ Uống, Chăm Sóc Cá Nhân |
| **3** | **85** | **ngành hàng thực dụng: Văn Phòng Phẩm, Rượu, Trang Điểm — mức nên chốt** |
| 4 | 133 | chi tiết: Hạt Trái Cây Sấy, Vang Đỏ |

Cách đo: mỗi keyword → top-10 kết quả `vector` → ngành (ở cấp đang xét) của từng sản phẩm
→ ngành xuất hiện nhiều nhất là ngành keyword đó **thực sự** kiểm tra. Ngành chỉ thấp
thoáng 1-2 sản phẩm tính là "chạm", không tính là phủ.

Đề xuất keyword: lấy n-gram 1–3 từ trong **tên sản phẩm của chính ngành đó**, chấm điểm
bằng lượt tìm thật trong log 6 tháng, chỉ giữ cụm mà phần lớn sản phẩm chứa nó nằm đúng
ngành (độ chính xác ≥ 0.6). Không có ngưỡng đó thì "hộp", "gói" thắng mọi ngành. Cụm nào
log không có thì lùi về chính tên ngành — nhưng **phải đọc lại bằng mắt**: tên ngành kiểu
"Món Ăn Nhanh Khác" hay "Sửa Chữa Nhà Cửa" không ai gõ vào ô tìm kiếm, phải mở ngành đó ra
xem bán gì rồi đặt lại ("salad", "mũi khoan").

#### Soát lệch

```bash
npm run audit
```

11 phép kiểm, mỗi cái ứng với một kiểu lệch đã xảy ra hoặc có thể xảy ra: cột No liên tục,
ảnh nhúng ↔ manifest, keyword Excel khớp keyword đã chạy, kết quả có phải của đúng tấm ảnh
hiện tại không (so `sha256` với `imageRef`), đủ 3 cơ chế, không lượt lỗi, không kết quả mồ côi,
ô Top-40 khớp kết quả thô, `top40_flat.csv` đủ dòng và đúng vị trí, và mọi SKU có `imageUrl`
đều đã tải ảnh. Thoát khác 0 nếu có FAIL, nên gắn vào script/CI được.

Phép kiểm cuối tách riêng hai chuyện dễ lẫn: **SKU backend trả về không kèm `imageUrl`**
(lỗ hổng dữ liệu bên họ, dashboard hiện ô `n/a`) khác hẳn **có URL mà mình chưa tải**
(lỗi phía mình, chạy lại `excel:images`).

#### image_id neo vào nội dung ảnh, không phải cột No

`images/excel_keywords/id_map.json` giữ `sha256(ảnh) -> image_id`. Nhờ vậy sửa cột No
(thêm dòng, xoá dòng, đánh số lại) không đụng gì tới id, và kết quả đã chạy vẫn đúng chủ.

Trước đây `image_id = 'kw%03d' % STT`, tức buộc định danh vào **một cột người dùng sửa** —
đánh lại số là đổi id cả bộ, mọi kết quả thành mồ côi và phải chạy lại từ đầu.

```bash
npm run renumber -- --dry-run    # xem trước
npm run renumber                 # đánh lại cột No thành 1..N liên tục
```

`renumber_keywords.py` từ chối chạy nếu chưa có `id_map.json`, đúng vì lý do trên.
Ảnh mới dán vào nhận id ở slot số còn trống (kw002, kw016, …), nên id không liên tục —
không sao, id chỉ là khoá nội bộ; thứ người đọc nhìn là cột No và keyword.

Đổi ảnh cho một keyword đã chạy = ảnh mới, hash mới, **id mới**: nó được chạy như một ca
mới và kết quả của ảnh cũ thành mồ côi (script in ra danh sách, không ghi vào Excel/dashboard).

**Luôn chạy `excel:extract` trước `excel:write` và trước khi sinh dashboard.**
Kết quả thô có ghi `excel_row`, nhưng đó là số dòng **lúc chạy** — chèn hay xoá dòng
trong Excel sau đó là nó sai ngay. Cả `write_excel_results.py` lẫn
`build_image_dashboard.py` giờ lấy vị trí từ `images/excel_keywords/manifest.json`
(do `excel:extract` đọc anchor thật của file hiện tại), không đụng tới `excel_row` nữa.

Đã dính một lần ngày 2026-09-22: một dòng ở giữa bị xoá (STT 52), khối 13 keyword thủ công
tụt từ dòng 58–70 lên 57–69, nhưng script vẫn ghi theo số cũ nên **toàn bộ kết quả từ
dòng 58 trở xuống lệch một dòng** — nhìn ra vì "hộp bánh gival" hiện ở hai dòng liền nhau.
Hai chốt chặn thêm vào sau đó:

- `write_excel_results.py` **xoá sạch vùng cột kết quả** trước khi ghi, nên dòng không còn
  kết quả (keyword bị xoá, ảnh bị gỡ) không giữ lại số cũ.
- Nó đối chiếu keyword ở dòng sắp ghi với keyword của lượt chạy; lệch thì in cảnh báo
  `dòng LỆCH keyword`, và in danh sách kết quả "mồ côi" (image_id không còn dòng nào trong sheet).
**Đóng Excel trước khi chạy `excel:write`** — file đang mở thì script không ghi đè
được, nó ghi ra bản `_results.xlsx` bên cạnh.

Excel nhận thêm:

| Nơi | Nội dung |
|---|---|
| `Top100_Keywords` cột L–AB | imageRef + tổng KQ / số KQ trả về / tookMs của từng cơ chế, query NovaLite sinh ra, và **một ô top-40 cho mỗi cơ chế nằm ngay trong dòng của keyword** — mỗi dòng trong ô là `No \| SKU \| Tên sản phẩm \| Tồn` |
| `Run_Info` | endpoint, params đã ghim, và các bẫy khi đọc số |
| `results/excel_top40/top40_flat.csv` | bảng dài cho dashboard: 1 dòng = 1 sản phẩm, đủ cột để pivot |

Ô top-40 để font 8 và dòng cao kịch trần Excel (409.5pt) nên vẫn hụt vài dòng cuối:
bấm vào ô để xem đủ trên thanh công thức, hoặc mở `top40_flat.csv`. Excel không cho
dòng cao hơn mức đó, nên đây là giới hạn của định dạng chứ không phải của dữ liệu.

Ảnh nhúng trong Excel được giữ nguyên qua vòng ghi (openpyxl đọc và ghi lại
`twoCellAnchor`), nhưng vẫn nên backup file trước khi chạy lần đầu.

### Dashboard so sánh + chấm "cơ chế nào OK"

```bash
npm run dashboard                       # sinh rồi mở luôn
npm run dashboard:apply -- <export.json>   # nạp phán quyết đã xuất, sinh lại
```

`dashboard/image_search_dashboard.html` xếp 3 cơ chế thành 3 cột cạnh nhau cho từng
ảnh, kèm ảnh sản phẩm thật lấy từ `result_images/`. Phần đầu trang là tổng KQ và
thời gian phản hồi p50/p95 của từng cơ chế; mỗi cột còn lặp lại tổng KQ + tookMs
của chính ảnh đó.

Thanh công cụ: lọc **chưa/đã đánh giá**, **Mở tất cả / Thu tất cả**, xem **cả 3 cơ chế
hay chỉ một**, và sắp xếp theo STT / NovaLite ít kết quả nhất / chậm nhất.

#### Mở / thu từng keyword

Card mặc định thu gọn — bấm vào đầu card (hoặc Enter khi focus) để mở ra **đủ 40 sản
phẩm của cả 3 cơ chế**; bấm lại, hoặc bấm thanh "▲ Thu gọn" ở cuối card, để thu lại.
Bấm vào dropdown phán quyết thì không mở/thu card.

Lý do mặc định thu: mở hết 27 ảnh cùng lúc là ~3.200 dòng sản phẩm kèm ảnh, cuộn tìm
một keyword thành cực hình. Danh sách sản phẩm chỉ được dựng khi card mở ra, thu lại
là trả luôn DOM đó về — "Mở tất cả" vẫn dùng được khi cần Ctrl+F toàn trang.

Lúc thu gọn vẫn đọc được ngay cơ chế nào hơn: mỗi cơ chế một dòng tóm tắt gồm tổng KQ,
thời gian phản hồi và tên sản phẩm hạng 1.

#### Phán quyết sống ở đâu

Mỗi ảnh có **hai dropdown chọn nhiều** và **một ô ghi chú**:

| Ô | Ý nghĩa |
|---|---|
| **Kết quả** | những cơ chế trả kết quả đạt — chọn được nhiều cơ chế cùng lúc |
| **Hiệu năng** | những cơ chế đạt về tốc độ — cũng chọn nhiều |
| **Ghi chú** | nhận xét tự do của người đánh giá |

Dropdown là `<details>` + checkbox chứ không phải `<select multiple>`, nên không phải
ctrl+click. Mở một cái thì cái kia tự đóng, bấm ra ngoài đóng hết — panel bung ra che
mất dòng bên dưới nên nếu không làm vậy thì dropdown thứ hai bấm không trúng.

"Không cái nào đạt" loại trừ lẫn nhau với các cơ chế: tick nó thì bỏ hết cơ chế đã chọn,
và ngược lại. Giữ nó làm một lựa chọn riêng vì **"không cơ chế nào đạt" khác hẳn
"chưa ai đánh giá"** — bỏ đi thì hai ca đó nhìn giống nhau.

Một keyword có thể chọn nhiều cơ chế, nên tổng các cột trong thanh tóm tắt sẽ lớn hơn
số keyword đã đánh giá — đó là đúng, không phải lỗi đếm.

File export mang ba nhánh: `verdicts` (kết quả), `performance` (hiệu năng), `notes` (ghi chú),
mỗi nhánh là `{image_id: [cơ chế...]}`. File export cũ (mỗi ảnh một chuỗi) vẫn nạp được —
`apply_export` tự quy về list.

Lựa chọn đi theo đường này:

```
dropdown -> localStorage (chỉ máy đó, hiện "chưa xuất")
   -> nút "Xuất kết quả đánh giá" -> file JSON
   -> npm run dashboard:apply -- <file>  -> dashboard/verdict_state.json
   -> sinh lại HTML -> phán quyết nằm trong chính báo cáo ("đã lưu trong báo cáo")
```

Đây là cùng cơ chế với `compare_report.html` của repo, và cùng một cái bẫy:
**dashboard là bản chụp — nó đọc `verdict_state.json` lúc SINH, không phải lúc mở.**
Nạp state xong mà quên sinh lại thì báo cáo vẫn hiện số cũ. `--apply` đã gộp sẵn hai
bước nên đừng chạy tay từng bước.

Phán quyết rỗng trong file export = xoá phán quyết cũ, quay về "chưa đánh giá" —
chọn nhầm thì gỡ được, không phải sửa tay `verdict_state.json`.

#### Chạy lại sau khi dev fix bug: đánh giá theo từng lần chạy

Từ 2026-09-24, mỗi **lần chạy** (ngày `ran_at` của `results/excel_top40`) là một vòng đánh giá riêng:

- **Dashboard:** panel top-40 luôn là dữ liệu mới nhất. Hàng dropdown **Lần dd/mm** đầu tiên
  dùng để đánh giá lần chạy này. Bên dưới là hàng dropdown của các lần trước, giữ nguyên lựa
  chọn cũ, chỉ để xem, không sửa được.
- **`verdict_state.json`:** có dạng `{"rounds": {"2026-09-22": {"verdicts": …}, "2026-09-24": …}}`.
  File export có trường `round`, nên `--apply` nạp đúng vòng. File export cũ không có
  `round` thì được tính là lần 22/09.
- **Lựa chọn cũ chưa xuất:** mỗi vòng lưu localStorage dưới khoá riêng. Nếu trình duyệt còn
  lựa chọn 22/09 chưa xuất (khoá cũ không có ngày), hàng 22/09 hiện chúng kèm nhãn
  "chưa xuất", và có thêm nút **Xuất đánh giá 22/09 chưa xuất** để xuất riêng.
- **Excel:** `write_excel_results.py` ghi mỗi lần chạy thành một khối cột, tiêu đề có tiền tố
  `[dd/mm]`. Lần mới thêm khối mới bên phải, các khối cũ giữ nguyên. Chạy lại cùng ngày thì
  chỉ ghi đè khối của ngày đó.
- **Bản `_view`:** mỗi lần build sinh thêm `image_search_dashboard_view.html` để trình chiếu,
  đã ẩn nút xuất và dòng chú thích trần top-K 200.
- **Lưu kết quả cũ:** `run-excel-top40.mjs --force` ghi đè `results/excel_top40`. Muốn giữ
  kết quả thô của lần trước thì copy sang `results/_archive/` trước khi chạy.

#### Đọc biểu đồ thời gian phản hồi

Vẽ dải phân bố chứ không phải 3 cột p50 cạnh nhau: chấm = p50, khối đậm = p50→p95,
vạch mảnh = nhanh nhất→chậm nhất. Ba cơ chế chênh nhau vài chục ms trên nền dao động
hàng trăm ms, nên ba dải chồng lên nhau gần hết — **đó mới là kết luận**: về tốc độ
thì ba cơ chế như nhau, đừng chọn cơ chế dựa vào cột p50 trông cao thấp.

HTML cần hai thư mục cạnh nó (`../result_images/`, `../images/`) mới có ảnh, nên copy
riêng file HTML đi nơi khác là mất ảnh.

### Gọi thẳng API thay vì bấm dropdown

`run-excel-top40.mjs` không thao tác UI như `run.mjs`. Nó mở playground để mượn
phiên đăng nhập rồi `fetch` thẳng vào endpoint từ page context — cùng origin,
cùng cookie, nhưng chủ động được `params` và không dính 3 request trùng của UI:

```
POST /api/v2/{lang}/{store}/products/search-by-image
multipart/form-data:
  image  = <file>
  params = {"imageMode":"vector","sort":"relevance","storeId":"nsg",
            "lang":"vi","page":1,"pageSize":100,"filters":{}}
```

Hợp đồng này lấy bằng `node scripts/inspect-formdata.mjs` (hook `fetch`/`XHR`
trong page rồi in ra tên field FormData thật).

### imageRef dùng lại được — nhưng chỉ trong đúng cơ chế đã upload

`imageRef` là `sha256:` của **chính file ảnh** — upload cùng một ảnh bao nhiêu lần
cũng ra đúng một ref. Backend cache embedding theo cặp **(hash ảnh, imageMode)**,
nên ref dùng lại được hay không phụ thuộc cơ chế đang hỏi, không phụ thuộc thời gian.

Đo bằng `node scripts/inspect-imageref-fresh.mjs` — mỗi cơ chế một ảnh hash mới tinh
để không nhờ được cache của lượt trước:

| upload bằng \ hỏi bằng ref | `vector` | `vector_titan` | `caption` |
|---|---|---|---|
| `vector` | **200** | 410 | 410 |
| `vector_titan` | 410 | **200** | 410 |
| `caption` | 410 | 410 | **200** |

Hai điều rút ra:

- **Dán lại imageRef để gọi API là đúng và chạy được** — miễn giữ nguyên `imageMode`
  của lượt upload gốc. Ref phải nằm **trong `params`**; để thành field riêng của
  form thì nhận `400 INVALID_QUERY`. Gọi lại cùng cơ chế sau 30s và 90s vẫn 200
  (`scripts/inspect-imageref.mjs`), nên đây không phải chuyện hết hạn nhanh.
  Rất hợp để phân trang, đổi `sort`/`filters`, hay chạy lại một lượt mà không upload lại.
- **Nhưng không gộp được 3 cơ chế vào một lần upload.** Mỗi cơ chế vẫn phải upload
  riêng, nên runner giữ nguyên 3 lượt cho mỗi ảnh.

Tên lỗi `IMAGE_REF_EXPIRED` và câu *"imageRef is expired or unknown"* gây hiểu nhầm:
ca này luôn là **unknown** (chưa có embedding loại đó cho hash này), không phải expired.
Đáng báo dev đổi thành mã lỗi riêng — nhìn `EXPIRED` rất dễ kết luận sai là ref sống
vài giây, đó đúng là kết luận sai mà repo này từng ghi vào tài liệu.

### `totalHits` của cơ chế vector là trần, không phải tổng

Đo trên cả 9 ảnh đợt đầu: `vector` và `vector_titan` trả `totalHits` = **đúng 200**
ở mọi ảnh, `pageCeiling` = 2. Đó là trần top-K của truy vấn vector, không phải số
sản phẩm khớp. Chỉ `caption` (search text) mới cho tổng thật, và số của nó nhảy
theo ảnh: 25, 31, 56, 177, 225, 236, 290, 326.

Nên **không so "tổng kết quả" giữa vector và caption** — hai con số khác bản chất.
Cái so được là thứ hạng và chất lượng top-N.

## manifest.csv

Nguồn sự thật duy nhất. Mỗi dòng một ảnh:

| Cột | Ý nghĩa |
|---|---|
| `image_id` | Định danh, dùng làm tên file kết quả |
| `file` | Đường dẫn tương đối trong `images/` |
| `source` | `ugc` / `marketplace` / `aigen` |
| `keyword` | Keyword khách hay dùng, dẫn tới việc chọn SKU này |
| `exact_skus` | SKU đúng, nhiều SKU ngăn bằng `\|` |
| `variant_skus` | Cùng sản phẩm khác size/màu — vẫn tính là đúng |
| `category_ids` | Ngành hàng đúng, dùng chấm ảnh `aigen` |
| `difficulty` | `clean` / `cluttered` / `multi_product` / `angled` / `partial` / `lowlight` |

Cột dạng danh sách dùng `|` chứ không phải dấu phẩy, tránh đụng phân cách CSV.

Ảnh `aigen` để trống `exact_skus` — script tự loại khỏi metric SKU và chỉ chấm
ở mức ngành hàng. Ảnh "một cái chảo" chung chung không ứng với SKU nào thật,
ép vào Top-1 SKU là chấm sai bản chất.

## Trạng thái backend (đo ngày 2026-09-21)

Endpoint: `POST /api/v2/{lang}/{store}/products/search-by-image` — ngôn ngữ và cửa hàng
nằm trong đường dẫn, nên hai tham số đó ảnh hưởng trực tiếp tới kết quả.

| Cơ chế | Kết quả đo | |
|---|---|---|
| `vector` | HTTP 200, 100 sản phẩm, ~90ms | Ổn định |
| `vector_titan` | Lúc `503 EMBEDDING_UNAVAILABLE`, lúc 200 | **Chập chờn** |
| `caption` | HTTP 200, `resolvedImageMode: caption` | Ổn định |

**`vector_titan` không ổn định.** Cùng một buổi: lượt đầu trả `410 IMAGE_REF_EXPIRED`
→ retry → `503 EMBEDDING_UNAVAILABLE`; khoảng 20 phút sau chạy lại thì 200 bình thường.
Dịch vụ embedding của Titan lúc có lúc không.

Ảnh hưởng tới cách đọc kết quả: nếu `vector_titan` rụng vài chục lượt giữa chừng thì
số của nó tính trên tập ảnh nhỏ hơn hai cơ chế kia, so sánh trực tiếp là lệch.
`score.mjs` tách riêng lượt lỗi và đếm theo từng cơ chế — **đọc mục "LƯỢT LỖI BACKEND"
trước khi tin bảng metric**. Rụng đáng kể thì chạy lại riêng các ảnh đó bằng
`npm run run -- --only <id1>,<id2> --force`, đừng so bằng dữ liệu khuyết.

### `410 IMAGE_REF_EXPIRED` không phải là hết hạn

*(Sửa lại ngày 2026-09-21. Mục này trước đây ghi "imageRef hết hạn sau vài giây" —
đo lại thấy sai, nguyên nhân thật xem mục [imageRef dùng lại được — nhưng chỉ trong
đúng cơ chế đã upload](#imageref-dùng-lại-được--nhưng-chỉ-trong-đúng-cơ-chế-đã-upload).)*

Backend trả `410 IMAGE_REF_EXPIRED` — *"imageRef is expired or unknown; send the image
again"* — khi ref chưa có embedding **của cơ chế đang hỏi**, chứ không phải khi ref cũ.
Cùng cơ chế thì ref sống ít nhất 90 giây (đo bằng `scripts/inspect-imageref.mjs`).

Hệ quả thực tế vẫn như cũ: **không gộp một lượt upload cho nhiều cơ chế được**, mỗi cặp
(ảnh, cơ chế) là một lượt upload riêng — 150 ảnh × 3 cơ chế = **450 lượt upload**.
Runner gặp 410 thì gửi lại ảnh đúng một lần theo hướng dẫn của chính thông báo lỗi.

### UI bắn request trùng

Mỗi lần upload, UI gửi **3 request giống nhau**, và có nút "Thử lại sau 1s" tự retry.
Vì vậy runner không chờ "response kế tiếp" mà chờ response có `resolvedImageMode`
đúng bằng cơ chế đang hỏi, hoặc một lỗi 4xx/5xx — tự miễn nhiễm với request trùng.

### Chẩn đoán của cơ chế caption

`caption` mode trả kèm thông tin của Nova Lite, rất đáng lưu vào kết quả:

```json
"caption": { "query": null, "outcome": "no_product", "reason": "not_product",
             "modelId": "amazon.nova-lite-v1:0", "promptVersion": "cap-712c24252506" }
```

Nhờ đó phân biệt được **"model bảo đây không phải sản phẩm"** với **"model đọc được
ảnh nhưng search không ra gì"** — hai ca hoàn toàn khác nhau mà nếu chỉ nhìn
`totalHits: 0` thì trông y hệt. `scores.csv` có 3 cột `caption_query`,
`caption_outcome`, `caption_reason`.

## Biến gây nhiễu phải ghim

Trang có 6 `<select>`, không cái nào có `id` hay `name` — chỉ có class Angular sinh ra.
Selector định danh từng cái bằng một option value chỉ nó mới có (`select:has(option[value="vector_titan"])`),
bền hơn `nth-child` vì không gãy khi dev chèn thêm control.

| Select | Mặc định | Xử lý |
|---|---|---|
| Cửa hàng | `nsg` (Nam Sài Gòn) | **Ghim** — store khác thì tồn kho khác, tập sản phẩm khác |
| **Cơ chế ảnh** | `vector` | Biến đang đo — runner lặp qua `MODES` |
| Ngôn ngữ | `vi` | **Ghim** — ảnh hưởng `caption` mode rõ nhất |
| Chế độ | *(trống)* | Để nguyên mặc định |
| Hiển thị | `100` | Đã set qua `?size=100` trên URL |
| Sắp xếp | `relevance` | **Ghim** — khác `relevance` thì thứ hạng do giá quyết định, mọi metric vô nghĩa |

Giá trị ghim nằm ở `FIXED_PARAMS` trong `scripts/config.mjs`, được set lại trước mỗi
ảnh và ghi vào từng file kết quả (`fixed_params`) để sau này đối chiếu được.

Option value của cơ chế ảnh là chuỗi thường (`vector_titan`). Riêng select "Hiển thị"
dùng định dạng `ngValue` của Angular (`3: 100`) — nếu sau này cần đụng tới nó thì phải
truyền đúng chuỗi đó, không phải `100`.

## Script chẩn đoán

Dùng khi UI đổi và selector không còn khớp:

| Lệnh | Việc |
|---|---|
| `node scripts/inspect-health.mjs` | Trang đang ở trạng thái nào, API trả gì, lỗi console — kèm `health.png` |
| `node scripts/inspect-ui.mjs` | Dump mọi `<select>` + option value thật → `ui-selects.json` |
| `node scripts/inspect-flow.mjs` | Trace XHR theo từng giai đoạn + liệt kê button hiển thị |
| `node scripts/inspect-response.mjs` | Status + hình dạng response của `search-by-image` cho từng cơ chế |

Cả ba chạy một lần rồi thoát, không retry — tránh dội request vào dev console.

## Metric

| Metric | Định nghĩa |
|---|---|
| `strict@1` | SKU trong `exact_skus` đứng đầu |
| `relaxed@1` / `relaxed@5` | `exact ∪ variant` trong top 1 / top 5 — **metric chính** |
| `category@5` | Có sản phẩm đúng ngành hàng trong top 5 |
| `MRR` | 1/thứ hạng kết quả đúng đầu tiên |
| `no_result` | Tỉ lệ `totalHits == 0` |
| `p50/p95 ms` | Độ trễ từ `tookMs` |

`relaxed` là metric để chốt, không phải `strict`: khách chụp chảo 24cm mà ra chảo
26cm cùng dòng thì trong ngữ cảnh e-commerce không phải fail.

Kết quả cắt theo `source` và `difficulty`. Nhiều khả năng các cơ chế hoà nhau ở ảnh
sạch và tách hẳn ở `cluttered` / `multi_product` — đó mới là kết luận dùng được.

So cặp bằng McNemar exact test trên `relaxed_hit@5`, ngưỡng hiệu chỉnh Holm cho 3
phép so. "Chưa đủ bằng chứng" nghĩa là chênh lệch nằm trong nhiễu của cỡ mẫu,
**không** phải "hai bên như nhau".

## Hai chốt chặn

**`resolvedImageMode` phải khớp cơ chế đã chọn.** Runner assert mỗi lượt, `score.mjs`
in cảnh báo nếu lệch. Không có kiểm tra này, bạn hoàn toàn có thể chạy cả bộ ảnh qua
cùng một model ba lần rồi kết luận "ba cơ chế như nhau".

**`imageRef` phải giống nhau giữa các cơ chế** của cùng một ảnh, vì chỉ upload một lần.
Lệch nghĩa là ảnh bị xử lý lại khác đi giữa các lượt.

## Session và OIDC

Dev console là app Angular đăng nhập bằng Magento SSO qua OIDC.

**`storageState` không dùng được với app này.** Nó chỉ chụp cookie + localStorage,
trong khi access token nằm ở `sessionStorage` và sống vài phút. Kể cả khôi phục cả
`sessionStorage`, app vẫn không silent-refresh được vì thiếu phiên gốc với IdP.
Triệu chứng đã gặp: chạy được khoảng 15 phút, sau đó mọi call `/api/` trả 401 và
trang bị đá về `#/auth/login` — trong khi cookie vẫn còn hạn tới cuối ngày.

Vì vậy mọi thứ chạy trên **profile Chromium cố định** ở `.auth/profile`:

```js
const context = await openProfile({ headless: true });   // scripts/lib/session.mjs
```

Đăng nhập một lần bằng `npm run auth`, app tự gia hạn token như trình duyệt bình thường.

`npm run auth` tự kiểm chứng: sau khi bạn đăng nhập xong nó đóng browser, mở lại
profile ở chế độ headless đúng như runner sẽ dùng, rồi xem `/api/v1/auth/userinfo`
trả 200 hay 401. Xanh mới chạy tiếp.

**Profile khoá theo tiến trình** — không mở hai Chromium cùng profile cùng lúc.
Đó là lý do `workers: 1` trong `playwright.config.js`, và là lý do không chạy
`npm test` song song với `npm run run`.

**Phiên SSO vẫn có thể hết hạn** khi chạy full vài giờ. `run.mjs` bắt 401 và dừng
ngay kèm thông báo thay vì ghi ra hàng trăm kết quả rỗng. Gặp thì `npm run auth`
rồi `npm run run` — ảnh đã xong được bỏ qua, chạy tiếp từ chỗ dừng.

## Dữ liệu khách hàng

`images/ugc/` chứa ảnh review của khách đã mua. Loại ảnh này hay dính mặt người,
nhà cửa, đôi khi cả nhãn giao hàng có tên và địa chỉ.

Trước khi copy ra máy hoặc chia sẻ kết quả, cần xác nhận với phía data owner / pháp chế
là được dùng cho mục đích test, và crop/che phần nhận dạng được. `.gitignore` đã chặn
sẵn toàn bộ `images/` và `.auth/`, nhưng đó chỉ chặn việc commit nhầm — không thay
được bước xin phép.

`results/*.json` chứa tên sản phẩm và SKU, không chứa dữ liệu cá nhân. Riêng cột
`caption` của cơ chế `caption` là do model sinh ra từ ảnh — nếu ảnh có chữ hoặc người
thì caption có thể mô tả lại, nên soát qua trước khi đưa kết quả ra ngoài team.

## Giới hạn upload

UI chỉ nhận PNG / JPEG / WebP / GIF, tối đa 5 MB. Ảnh chụp từ điện thoại thường
3–8 MB nên sẽ có file vượt ngưỡng — `npm run check` liệt kê ra trước khi chạy.
Nén bằng gì cũng được, miễn đừng hạ độ phân giải quá tay vì chính nó là biến đang đo.

## Bàn giao test data cho dev

```bash
python scripts/export_dev_testdata.py                  # vòng duyệt tay mới nhất
python scripts/export_dev_testdata.py --round 2026-09-22
```

Sinh `dev_handoff/ImageSearch_DevTestData_NSG_<ngày>/`: thư mục `images/` (ảnh test gốc, tên ASCII
`<image_id>_<keyword>`), file Excel (README · TestData có thumbnail · Summary · Actual_Top40), file JSON
cùng nội dung kèm lịch sử các vòng duyệt, và README.md cho dev. Kết quả duyệt tay lấy từ
`dashboard/verdict_state.json` nên **phải `dashboard:apply` export mới nhất trước khi chạy**; vị trí
dòng/lượt tìm lấy theo `manifest.json` nên cũng chạy `excel:extract` trước nếu Excel vừa sửa.
`dev_handoff/` nằm trong `.gitignore` vì chứa bản sao ảnh test.
