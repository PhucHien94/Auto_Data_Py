# -*- coding: utf-8 -*-
"""Crawl lại catalog NSG từ API production As-Is, khi không có quyền vào ES trực tiếp.

Bối cảnh: bộ dump v1/v1.1 trong data/ được crawl thẳng từ Elasticsearch legacy
bằng scripts/crawl_legacy_es.py của repo services/search-service. Repo đó KHÔNG
có trên máy này, và tài khoản PROD_ES_* cũng nằm trong .env của nó - nên không
crawl lại ES trực tiếp được. Script này đi đường vòng: gọi chính API search của
production (www.lottemart.vn/v1/p/mart/es/{lang}_nsg/products/search), vốn là
một lớp mỏng phủ lên đúng cụm ES đó.

KHÁC BIỆT SO VỚI DUMP ES TRỰC TIẾP - đọc kỹ trước khi dùng:

  1. Phạm vi hẹp hơn. API chỉ trả sản phẩm ĐANG HIỂN THỊ TRONG TÌM KIẾM
     (~15.038), còn dump thô có cả sản phẩm bị ẩn (18.122). Cụ thể, sản phẩm
     giá 0đ/1đ KHÔNG xuất hiện qua API - tức bộ lọc isZeroOrOneDongItem của
     search_engine.js sẽ thành vô tác dụng trên catalog này.

  2. Thiếu 4 trường mà dump thô có:
       best_sellings.30days (sold30)  - engine dùng tính popularity, nhưng
                                        99,9% SKU đang bằng 0 nên mất không đáng kể
       ec_status                      - engine không dùng
       substitute_product_sku         - engine không dùng
       cross_sell_product_sku         - engine không dùng
     rating_summary cũng không có, nhưng dump thô cũng đang rỗng 100%.

Vì hai điểm trên, script ghi ra tệp RIÊNG, KHÔNG đè lên dump v1.1. So sánh hai
bên rồi mới quyết định có sinh lại Expected hay không.

CÁCH VƯỢT GIỚI HẠN PHÂN TRANG: ES chặn ở 10.000 bản ghi (limit*offset), trong
khi catalog 15.038. offset là SỐ TRANG chứ không phải số bản ghi. Giải pháp là
chia theo category_ids - mỗi danh mục đều dưới 10.000, và facet_filters cho
phép kết hợp category_ids với in_stock để chẻ nhỏ thêm nếu cần. Chạy tham lam:
danh mục lớn trước, dừng ngay khi gom đủ số SKU mà API báo.
"""
import argparse
import collections
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]

URL = "https://www.lottemart.vn/v1/p/mart/es/{lang}_nsg/products/search"
HEADERS = {
    "Content-Type": "application/json",
    "origin": "https://dev-console.martonline.lotte.vn",
    "referer": "https://dev-console.martonline.lotte.vn/",
}
PAGE_CAP = 10000       # trần ES: limit * offset không vượt được mốc này
PAGE_SIZE = 2000       # đo thực tế: 2000 nhanh hơn hẳn 100, vẫn ổn định

FIELDS_FULL = ["sku", "name", "price", "stock_qty", "in_stock", "status",
               "visibility_search", "visibility_catalog", "category_full_path",
               "category_ids", "custom_attribute", "ext_viewed",
               "description", "short_description", "type_id"]
FIELDS_NAME = ["sku", "name", "category_ids"]


def call(lang, ff, offset, limit, fields, retries=4):
    body = {"where": {"query": ""}, "limit": limit, "offset": offset,
            "facet_filters": ff, "fields": fields}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(URL.format(lang=lang), data=data, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))["data"]
        except Exception as e:  # noqa: BLE001 - gateway thỉnh thoảng 5xx, lùi rồi thử lại
            if attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def crawl_bucket(lang, ff, fields, out, stats):
    """Lấy hết một nhánh lọc. Nếu nhánh vượt trần thì chẻ tiếp theo in_stock."""
    head = call(lang, ff, 1, 1, ["sku"])
    total = head.get("total_items") or 0
    stats["requests"] += 1
    if total == 0:
        return
    if total > PAGE_CAP and "in_stock" not in ff:
        for v in ("1", "0"):
            sub = dict(ff)
            sub["in_stock"] = [v]
            crawl_bucket(lang, sub, fields, out, stats)
        return
    pages = min((total + PAGE_SIZE - 1) // PAGE_SIZE, PAGE_CAP // PAGE_SIZE)
    for page in range(1, pages + 1):
        d = call(lang, ff, page, PAGE_SIZE, fields)
        stats["requests"] += 1
        for it in d.get("items") or []:
            out.setdefault(str(it.get("sku")), it)


def discover_categories(lang):
    """Tập danh mục + độ lớn, lấy từ mẫu 10.000 bản ghi mỗi nhánh tồn kho."""
    cats = collections.Counter()
    seeded = {}
    for v in ("1", "0"):
        d = call(lang, {"in_stock": [v]}, 1, PAGE_CAP, ["sku", "category_ids"])
        for it in d.get("items") or []:
            seeded[str(it["sku"])] = it
            for c in it.get("category_ids") or []:
                cats[c] += 1
    return cats, seeded


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out-dir", default="data/ProductInfo_api_20260917")
    ap.add_argument("--langs", default="vi,en,kr")
    ap.add_argument("--store", default="nsg")
    args = ap.parse_args()

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    for lang in [x.strip() for x in args.langs.split(",") if x.strip()]:
        t0 = time.time()
        fields = FIELDS_FULL if lang == "vi" else FIELDS_NAME
        target = call(lang, {}, 1, 1, ["sku"])["total_items"]
        print(f"\n=== {lang}_{args.store}: API báo {target:,} sản phẩm ===")

        cats, seed = discover_categories(lang)
        print(f"  mẫu đầu   : {len(seed):,} SKU, thấy {len(cats)} danh mục")

        # Mẫu trên chỉ có sku/category_ids nên không dùng làm dữ liệu được -
        # thứ duy nhất giữ lại là TẬP DANH MỤC để chia nhỏ.
        out = {}
        stats = {"requests": 0}
        done_cats = set()
        pending = [c for c, _ in cats.most_common()]
        rounds = 0

        while pending and len(out) < target:
            rounds += 1
            idle = 0
            for i, cid in enumerate(pending, start=1):
                if cid in done_cats:
                    continue
                before = len(out)
                crawl_bucket(lang, {"category_ids": [cid]}, fields, out, stats)
                done_cats.add(cid)
                idle = idle + 1 if len(out) == before else 0
                if i % 25 == 0:
                    print(f"  vòng {rounds} | {i}/{len(pending)} danh mục | "
                          f"{len(out):,}/{target:,} SKU | {stats['requests']} request | "
                          f"{time.time()-t0:.0f}s")
                if len(out) >= target:
                    break
                # 20 danh mục liên tiếp không thêm SKU nào nghĩa là phần còn
                # lại nằm ở danh mục CHƯA BIẾT - quét tiếp chỉ tốn request.
                # Dừng để đi sang bước mở rộng tập danh mục.
                if idle >= 20:
                    print(f"  vòng {rounds} | 20 danh mục liên tiếp không thêm gì, "
                          f"chuyển sang mở rộng tập danh mục")
                    break

            if len(out) >= target:
                break
            # Mở rộng: lấy category_ids từ CHÍNH dữ liệu vừa crawl. Mẫu ban đầu
            # bị trần 10.000 chặn nên không thấy hết danh mục; các bản ghi mới
            # crawl được thường lộ ra danh mục chưa từng xuất hiện.
            fresh = collections.Counter()
            for src in out.values():
                for c in src.get("category_ids") or []:
                    if c not in done_cats:
                        fresh[c] += 1
            if not fresh:
                print(f"  vòng {rounds} | không còn danh mục mới để thử - dừng")
                break
            pending = [c for c, _ in fresh.most_common()]
            print(f"  vòng {rounds} | tìm thêm {len(pending)} danh mục chưa quét, "
                  f"đang có {len(out):,}/{target:,}")

        path = out_dir / f"mart_{lang}_{args.store}_product.ndjson"
        with open(path, "w", encoding="utf-8") as f:
            for sku, src in out.items():
                # Giữ đúng hình dạng {_id,_index,_source} của dump ES, để
                # export_full_store_catalog.py dùng lại được mà không phải sửa.
                f.write(json.dumps({
                    "_id": src.get("id"),
                    "_index": f"mart_{lang}_{args.store}_product",
                    "_source": src,
                }, ensure_ascii=False) + "\n")
        print(f"  XONG      : {len(out):,}/{target:,} SKU "
              f"({len(out)/target*100:.1f}%), {stats['requests']} request, "
              f"{time.time()-t0:.0f}s")
        print(f"  -> {path}")


if __name__ == "__main__":
    main()
