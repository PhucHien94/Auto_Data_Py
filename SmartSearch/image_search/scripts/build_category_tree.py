# -*- coding: utf-8 -*-
"""Dung cay nganh hang THAT tu ProductInfo (category_full_path, toi 5 cap).

    python scripts/build_category_tree.py

Vi sao khong dung truong `cat` cua full_store_catalog: no chi la chuoi 2 cap
("HÀNG PHI THỰC PHẨM / Chăm Sóc Cá Nhân") — 48 nhanh. Thuc te moi san pham
thuoc NHIEU nganh long nhau toi 5 cap:

    HÀNG PHI THỰC PHẨM
    HÀNG PHI THỰC PHẨM / Chăm Sóc Cá Nhân
    HÀNG PHI THỰC PHẨM / Chăm Sóc Cá Nhân / Chăm Sóc Cơ Thể
    HÀNG PHI THỰC PHẨM / Chăm Sóc Cá Nhân / Chăm Sóc Cơ Thể / Làm Sạch Cơ Thể
    ... / Tẩy Tế Bào Chết

Do phu tren 48 nhanh la do tren ban do thu nho. Script nay ghi ra
cache/category_tree.json: moi nganh (moi cap) -> so san pham + SKU thuoc nganh do.
"""
import json, os, sys, collections

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        _s.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(ROOT))
SRC = os.path.join(REPO, 'data', 'ProductInfo_v1.1', 'v1.1', 'mart_vi_nsg_product.ndjson')
OUT_DIR = os.path.join(ROOT, 'cache')
OUT = os.path.join(OUT_DIR, 'category_tree.json')


def main():
    if not os.path.exists(SRC):
        sys.exit('Khong thay %s' % SRC)
    os.makedirs(OUT_DIR, exist_ok=True)

    per_cat = collections.defaultdict(set)      # nganh -> {sku}
    sku2paths = {}                              # sku -> [nganh day du]
    sku2name = {}
    n, kept = 0, 0
    with open(SRC, encoding='utf-8') as fh:
        for line in fh:
            n += 1
            try:
                src = json.loads(line)['_source']
            except Exception:
                continue
            sku = str(src.get('sku') or src.get('barcode') or '').strip()
            paths = src.get('category_full_path') or []
            if not sku or not paths:
                continue
            kept += 1
            sku2paths[sku] = paths
            sku2name[sku] = src.get('name') or ''
            for p in paths:
                per_cat[p].add(sku)
            if n % 5000 == 0:
                print('  ...%d dòng, %d sản phẩm có ngành' % (n, kept))

    tree = {c: len(s) for c, s in per_cat.items()}
    by_level = collections.Counter(c.count('/') + 1 for c in tree)
    data = {
        'source': os.path.relpath(SRC, REPO),
        'products': kept,
        'categories': tree,
        'sku_paths': sku2paths,
    }
    with open(OUT, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False)

    print('\n%d dòng đọc · %d sản phẩm có ngành · %d ngành (mọi cấp)' % (n, kept, len(tree)))
    for lv in sorted(by_level):
        print('   cấp %d: %4d ngành' % (lv, by_level[lv]))
    print('Đã ghi: %s' % OUT)


if __name__ == '__main__':
    main()
