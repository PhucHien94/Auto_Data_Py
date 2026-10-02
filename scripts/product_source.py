# -*- coding: utf-8 -*-
"""Nơi DUY NHẤT quyết định dữ liệu sản phẩm thô được lấy từ đâu.

Bối cảnh (2026-09-17): repo có HAI ảnh chụp catalog production, và trước đây
mỗi script tự ghi cứng đường dẫn của mình, nên rất dễ hai script cùng nói về
"catalog NSG" mà thực ra đang đọc hai bộ số khác nhau:

    data/ProductInfo_v1.1/v1.1   ảnh chụp 2026-08-28, CHỈ có store nsg (3 ngôn ngữ)
                                 18.122 SKU - đây là bản dùng cho nsg.
    data/ProductInfo             ảnh chụp 2026-07-27, có 21 store
                                 nsg ở đây chỉ 16.340 SKU - đã cũ, chỉ còn
                                 dùng cho 20 store KHÔNG phải nsg.

Hai bản không bao nhau: v1.1 thêm 2.201 sản phẩm, bỏ 404 sản phẩm, và 142 sản
phẩm đổi status - tức ~13,4% catalog đã đổi trong một tháng. Vì vậy KHÔNG được
coi bản nào là superset của bản kia.

Quy tắc: xét theo thứ tự trong SOURCES, store nào có dữ liệu ở thư mục nào
trước thì lấy thư mục đó. Đổi nguồn thì sửa đúng danh sách này, không sửa rải
rác trong từng script.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Theo THỨ TỰ ƯU TIÊN. Bản mới nhất đứng trước.
SOURCES = [
    ROOT / "data" / "ProductInfo_v1.1" / "v1.1",
    ROOT / "data" / "ProductInfo",
]

SNAPSHOT_DATE = {
    "data/ProductInfo_v1.1/v1.1": "2026-08-28",
    "data/ProductInfo": "2026-07-27",
}


def rel(path):
    """Đường dẫn tương đối so với gốc repo, luôn dùng dấu / - để in ra cho người đọc."""
    try:
        return str(Path(path).resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def store_dir(store, lang="vi"):
    """Thư mục đầu tiên (theo ưu tiên) thực sự có dữ liệu của store này.

    Trả về None nếu không thư mục nào có - để phía gọi tự quyết định báo lỗi
    hay bỏ qua, thay vì ném exception giữa một batch dài.
    """
    for d in SOURCES:
        if (d / f"mart_{lang}_{store}_product.ndjson").exists():
            return d
    return None


def ndjson(store, lang="vi"):
    """Đường dẫn file NDJSON của store/ngôn ngữ, hoặc None nếu không có."""
    d = store_dir(store, lang)
    return None if d is None else d / f"mart_{lang}_{store}_product.ndjson"


def describe(store, lang="vi"):
    """Một dòng mô tả nguồn, để script in ra log cho người chạy biết đang đọc gì."""
    d = store_dir(store, lang)
    if d is None:
        return f"{store}/{lang}: KHÔNG tìm thấy trong " + ", ".join(rel(x) for x in SOURCES)
    r = rel(d)
    return f"{store}/{lang}: {r} (ảnh chụp {SNAPSHOT_DATE.get(r, 'không rõ')})"
