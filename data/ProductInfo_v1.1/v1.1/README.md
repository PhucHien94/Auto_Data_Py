# v1.1 — Bản làm mới dữ liệu gốc production (Store NSG, 3 ngôn ngữ)

**Đơn vị:** Store `nsg` (Nam Sài Gòn) · Crawl lại từ **Elasticsearch v1 legacy production** ngày **2026-08-28**.

v1.1 **không phải bộ dữ liệu mới**, mà là **v1 được refresh**: cùng nguồn, cùng schema,
cùng script — chỉ khác thời điểm chụp. v1 chụp ngày **2026-07-27**, đã lệch so với
production. v1.1 chỉ chụp lại **3 ngôn ngữ của riêng store `nsg`**; 20 store còn lại vẫn
dùng bản v1 (xem [`../v1/README.md`](../v1/README.md)).

---

## 1. Danh sách Tệp Dữ liệu

| Tệp | Số dòng | Kích thước | Mô tả |
|---|---:|---:|---|
| `mart_vi_nsg_product.ndjson` | 18.122 | 215 MB | Sản phẩm thô tiếng Việt (VI) |
| `mart_en_nsg_product.ndjson` | 18.117 | 185 MB | Sản phẩm thô tiếng Anh (EN) |
| `mart_kr_nsg_product.ndjson` | 18.083 | 166 MB | Sản phẩm thô tiếng Hàn (KO) |
| `mart_{lang}_nsg_product.schema.json` | — | ~68 KB mỗi tệp | `_mapping` + `_settings` của index nguồn (54 trường top-level) |

Mỗi dòng NDJSON là một object `{"_id", "_index", "_source"}`, `_source` giữ nguyên
**56 trường** như v1 — **không transform gì cả**. Phase 2 (`scripts/seed_products.py`)
đọc các tệp này offline.

---

## 2. Nguồn & Lệnh tái lập

Alias được crawl (alias trỏ index hiện hành, các index rebuild cũ bị bỏ qua):

| Alias | Index thật |
|---|---|
| `mart_vi_nsg_product` | `mart_vi_nsg_product-2024-05-28-20-05-38` |
| `mart_en_nsg_product` | `mart_en_nsg_product-2024-05-28-20-06-08` |
| `mart_kr_nsg_product` | `mart_kr_nsg_product-2024-05-28-20-06-09` |

> Tên index gắn timestamp **2024-05-28** là ngày *tạo* index, không phải ngày dữ liệu.
> v1 cũng crawl đúng ba index này — dữ liệu bên trong vẫn được ghi tiếp qua alias.

```bash
cd services/search-service
ES_BASIC="$(grep '^PROD_ES_USERNAME=' .env | cut -d= -f2-):$(grep '^PROD_ES_PASSWORD=' .env | cut -d= -f2-)" \
python3 scripts/crawl_legacy_es.py \
  --old-es https://search-latg-es-production-nqejr4j2apkk6p2gzdm566gixu.ap-southeast-1.es.amazonaws.com \
  --data-dir docs/data/v1.1 \
  --only 'mart_vi_nsg_product' --only 'mart_en_nsg_product' --only 'mart_kr_nsg_product'
```

Transport là **REST trực tiếp** vào domain AWS OpenSearch bằng basic-auth
`PROD_ES_USERNAME` / `PROD_ES_PASSWORD` trong `.env`. Đường Kibana proxy
(`KIBANA_URL` / `KIBANA_COOKIE`, `.env:74-75`) đang comment và cookie rỗng — **không cần
tới**, chỉ là fallback khi REST trực tiếp bị chặn.

Crawl là **read-only, tuần tự, có throttle** (0,25 s giữa các trang scroll). Toàn bộ 3
index mất ~9 phút, `crawled 3, skipped 0, failed 0`. Số dòng mỗi tệp khớp **chính xác**
`_count` của alias tại thời điểm crawl.

---

## 3. Đã thay đổi gì so với v1

Gôm union theo `id` trên cả 3 ngôn ngữ:

| Chỉ số | v1 (2026-07-27) | v1.1 (2026-08-28) | Δ |
|---|---:|---:|---:|
| Tổng sản phẩm (union 3 ngôn ngữ) | 16.374 | **18.171** | **+1.797** |
| Sản phẩm Active (`status=1`) | 16.151 | **17.767** | **+1.616** |

Phân rã thay đổi:

- **2.201 sản phẩm mới** xuất hiện trong v1.1 (không có trong v1).
- **404 sản phẩm biến mất** khỏi production (có trong v1, không còn trong v1.1).
- **15.970 sản phẩm chung**, trong đó **142 sản phẩm đổi `status`**.

Nghĩa là ~13,4% catalog đã đổi trong một tháng — **v1 không dùng để đo lường được nữa**.

### Độ bao phủ theo từng tệp ngôn ngữ

| Ngôn ngữ | Docs | Active | `name` | `short_description` | category path |
|---|---:|---:|---:|---:|---:|
| VI | 18.122 | 17.761 | 18.122 (100%) | 15.435 (85,2%) | 18.075 (99,7%) |
| EN | 18.117 | 17.737 | 18.117 (100%) | 14.780 (81,6%) | 18.070 (99,7%) |
| KO | 18.083 | 17.742 | 18.083 (100%) | 11.006 (60,9%) | 18.036 (99,7%) |

### Sản phẩm chưa dịch tiếng Hàn

**1.845 sản phẩm Active** có `name` trong tệp KO **hoàn toàn không chứa ký tự Hangul**
(tức vẫn là fallback VI/EN) — cùng tiêu chí đã dùng cho `untranslated-products.*` của v1
(1.934 sản phẩm). Con số **giảm 89** dù catalog **tăng 1.797** sản phẩm.

---

## 4. Chưa có trong v1.1

v1.1 chỉ chứa **dữ liệu thô 3 ngôn ngữ**. Các tệp phái sinh của v1 **chưa được dựng lại**
cho ảnh chụp này:

- `missing-translation.ndjson` — bộ gôm union 3 ngôn ngữ.
- `untranslated-products.ndjson` / `.csv` — bộ lọc Active chưa dịch KO.
- `categories_*_3_languages.{csv,json}` — cây danh mục 3 ngôn ngữ.
- `nsg.ndjson` — bộ đã transform.
- Dữ liệu 20 store khác (`bdg`, `bdh`, `bgg`, …).

Cần cái nào thì chạy lại pipeline phái sinh trên `--data-dir docs/data/v1.1`.

---

## 5. Tài liệu Tham chiếu

- Ảnh chụp trước đó và mô tả các tệp phái sinh: [`../v1/README.md`](../v1/README.md)
- Schema và lệnh kiểm tra: [`../../ops/localization/missing-translation-schema.md`](../../ops/localization/missing-translation-schema.md)
- Quy trình localization tiếng Hàn: [`../../ops/localization/kr-localization-into-opensearch.md`](../../ops/localization/kr-localization-into-opensearch.md)
- Script crawl: [`../../../scripts/crawl_legacy_es.py`](../../../scripts/crawl_legacy_es.py)
