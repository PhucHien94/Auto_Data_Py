# -*- coding: utf-8 -*-
"""Xuất danh sách sản phẩm & keyword ĐẶC BIỆT theo hai cờ hiển thị của catalog.

Vì sao cần file này: catalog có hai cờ quyết định sản phẩm được nhìn thấy ở đâu,
nhưng search_engine.js hiện KHÔNG đọc cờ nào cả. Hệ quả là bộ Expected có thể
trả về sản phẩm mà hệ thống thật không bao giờ hiện - khi so với Actual thì đếm
thành mismatch, trong khi thực chất là engine mô phỏng sai. File xuất ra giúp
QA khoanh vùng đúng những keyword đó thay vì đi soát tay từng cái.

Chạy:
  python scripts/testdata/export_visibility_special.py
"""
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]

CATALOG = ROOT / "SmartSearch/full_store_catalog_desc/nsg.json"
EXPECTED = ROOT / "SmartSearch/test_data/json/batches/NSG_ExpectedData_all_20260916c.json"
OUT = ROOT / "SmartSearch/test_data/exports/visibility_special_keywords_20260917.json"

GIAI_THICH = {
    "visibility_search": {
        "kieu": "boolean",
        "nghia": "Sản phẩm có được TÌM THẤY QUA Ô TÌM KIẾM hay không. "
                 "true = gõ tên ra được. false = dù gõ đúng nguyên tên sản phẩm "
                 "cũng KHÔNG bao giờ hiện trong kết quả tìm kiếm.",
        "kiem_chung": "Ngày 17/09/2026 đã thử trực tiếp trên production "
                      "(www.lottemart.vn/v1/p/mart/es/vi_nsg/products/search): lấy 6 SKU "
                      "có visibility_search=false, gõ ĐÚNG NGUYÊN TÊN từng cái - 6/6 đều "
                      "không xuất hiện, trong khi truy vấn vẫn trả về các sản phẩm khác "
                      "(tức không phải lỗi truy vấn). Đối chứng 3 SKU có "
                      "visibility_search=true thì 3/3 đều ra.",
    },
    "visibility_catalog": {
        "kieu": "boolean",
        "nghia": "Sản phẩm có hiện khi NGƯỜI DÙNG DUYỆT THEO DANH MỤC hay không "
                 "(bấm vào cây danh mục để xem hàng, không gõ tìm kiếm). "
                 "true = có nằm trong trang danh mục. false = không bày ra trong "
                 "danh mục, muốn tới được thì phải đi đường khác (tìm kiếm, link "
                 "trực tiếp, hoặc gợi ý sản phẩm liên quan).",
    },
    "hai_co_doc_lap": "Hai cờ này ĐỘC LẬP với nhau, không phải một cái là phủ định "
                      "của cái kia. Một sản phẩm có thể tìm ra được nhưng không nằm "
                      "trong danh mục, và ngược lại.",
    "khac_voi_status": "Đừng nhầm với 'status'. status nói sản phẩm CÒN KINH DOANH "
                       "hay không (status=1 là còn). Hai cờ visibility_* nói sản phẩm "
                       "còn kinh doanh đó được BÀY RA Ở ĐÂU. Một sản phẩm status=1 "
                       "vẫn có thể bị ẩn khỏi cả tìm kiếm lẫn danh mục.",
    "khac_voi_stock": "Cũng đừng nhầm với tồn kho. Hết hàng (stock=0) thì sản phẩm "
                      "VẪN HIỆN, chỉ bị engine đẩy xuống cuối danh sách. Còn "
                      "visibility_search=false thì không hiện ra chút nào.",
}


def load():
    cat = {str(p["sku"]): p for p in json.loads(CATALOG.read_text(encoding="utf-8"))}
    exp = json.loads(EXPECTED.read_text(encoding="utf-8"))["scenarios"]
    return cat, exp


def in_engine_index(p):
    """Đúng bộ lọc buildIndex() của search_engine.js đang chạy."""
    if not (p.get("status") == 1 or p.get("status") is None):
        return False
    price = p.get("price")
    if price not in (None, "") and float(price) <= 1:
        return False
    return True


def main():
    cat, exp = load()

    groups = {
        "an_hoan_toan": {
            "dieu_kien": "visibility_search = false VÀ visibility_catalog = false",
            "nghia": "Không hiện ở bất cứ đâu - không tìm ra, cũng không có trong "
                     "danh mục. Đây là nhóm ĐÁNG NGỜ NHẤT nếu Expected trả về chúng.",
            "test": lambda p: p.get("visibility_search") is False
                              and p.get("visibility_catalog") is False,
        },
        "chi_tim_kiem_duoc": {
            "dieu_kien": "visibility_search = true VÀ visibility_catalog = false",
            "nghia": "Tìm kiếm ra được nhưng KHÔNG bày trong danh mục. Không phải "
                     "lỗi - Expected trả về nhóm này là hợp lệ. Ghi lại để phân biệt "
                     "với nhóm trên. Lưu ý: nhóm này đông (2.585 SKU) nhưng hầu hết "
                     "KHÔNG lọt vào engine index, vì 2.555/2.585 là hàng giá 0đ/1đ đã "
                     "bị luật lọc 0đ/1đ loại từ trước, thêm 17 SKU status khác 1 - chỉ "
                     "còn 30 SKU thật sự đi vào index. Nói cách khác, 'chỉ tìm kiếm ra "
                     "được, không bày danh mục' gần như đồng nghĩa với 'hàng khuyến "
                     "mãi 0đ/1đ' trong catalog này.",
            "test": lambda p: p.get("visibility_search") is True
                              and p.get("visibility_catalog") is False,
        },
        "chi_duyet_danh_muc": {
            "dieu_kien": "visibility_search = false VÀ visibility_catalog = true",
            "nghia": "Chỉ thấy khi duyệt danh mục, tìm kiếm không ra. Trên catalog "
                     "28/08 nhóm này RỖNG - giữ lại để lần sau chạy còn phát hiện "
                     "nếu production bắt đầu có.",
            "test": lambda p: p.get("visibility_search") is False
                              and p.get("visibility_catalog") is True,
        },
    }

    # keyword nào trong bộ test đang trả về từng SKU
    sku_to_queries = defaultdict(list)
    total_rows = 0
    for s in exp:
        for r in s.get("search_results") or []:
            total_rows += 1
            sku_to_queries[str(r["sku"])].append(s["query"])

    payload = {
        "generated": "2026-09-17",
        "store": "nsg",
        "muc_dich": "Khoanh vùng sản phẩm & keyword bị ảnh hưởng bởi hai cờ hiển thị "
                    "của catalog, do search_engine.js hiện không đọc hai cờ này.",
        "nguon": {
            "catalog": "SmartSearch/full_store_catalog_desc/nsg.json "
                       "(dựng từ data/ProductInfo_v1.1/v1.1, ảnh chụp production 28/08/2026)",
            "expected": "SmartSearch/test_data/json/batches/NSG_ExpectedData_all_20260916c.json",
            "tong_sku_catalog": len(cat),
            "tong_dong_ket_qua_trong_expected": total_rows,
        },
        "giai_thich_hai_bien": GIAI_THICH,
        "canh_bao_quan_trong": (
            "search_engine.js CHƯA đọc visibility_search / visibility_catalog. Nó chỉ "
            "lọc theo status (còn kinh doanh) và giá 0đ/1đ. Vì vậy Expected vẫn có thể "
            "trả về sản phẩm thuộc nhóm 'an_hoan_toan' - hệ thống thật không bao giờ "
            "hiện chúng, nên khi so Expected với Actual sẽ ra mismatch GIẢ. Đây là câu "
            "hỏi luật cần BA chốt (hệ thống mới có tôn trọng visibility_search như hệ "
            "thống cũ không?), cùng loại với QnA-69 về status vs ec_status - chưa tự sửa."
        ),
        "nhom": {},
    }

    for name, g in groups.items():
        skus = [s for s, p in cat.items() if g["test"](p)]
        items, kw = [], set()
        for s in sorted(skus):
            p = cat[s]
            qs = sorted(set(sku_to_queries.get(s, [])))
            kw.update(qs)
            items.append({
                "sku": s,
                "name": p.get("name"),
                "cat": p.get("cat"),
                "price": p.get("price"),
                "stock": p.get("stock"),
                "status": p.get("status"),
                "visibility_search": p.get("visibility_search"),
                "visibility_catalog": p.get("visibility_catalog"),
                "trong_engine_index": in_engine_index(p),
                "so_keyword_tra_ve_no": len(qs),
                "keyword_tra_ve_no": qs,
            })
        rows = sum(i["so_keyword_tra_ve_no"] for i in items)
        payload["nhom"][name] = {
            "dieu_kien": g["dieu_kien"],
            "nghia": g["nghia"],
            "so_sku": len(items),
            "so_sku_lot_vao_engine_index": sum(1 for i in items if i["trong_engine_index"]),
            "so_keyword_bi_anh_huong": len(kw),
            "so_dong_ket_qua_bi_anh_huong": rows,
            "keyword_bi_anh_huong": sorted(kw),
            "san_pham": items,
        }
        print(f"{name:22} {len(items):>6,} SKU | "
              f"{payload['nhom'][name]['so_sku_lot_vao_engine_index']:>5,} lọt vào index | "
              f"{len(kw):>4} keyword | {rows:>5,} dòng")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> {OUT}")
    print(f"   {OUT.stat().st_size/1024:.0f} KB")


if __name__ == "__main__":
    main()
