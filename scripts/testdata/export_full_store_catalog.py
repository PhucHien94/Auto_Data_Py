#!/usr/bin/env python3
"""
Export the FULL (unsampled) product catalog for one or more stores, joined
across EN/VI/KR by SKU, in the exact minimal shape the "Ranking Scorecard
Sandbox" artifact's PRODUCTS array expects.

Unlike generate_master_testset.py (which stratified-samples ~300 products for
golden-set testing), this script keeps every SKU - meant for single-store
Artifact pages where the whole catalog fits under the 16MB artifact size cap
(~13k SKU/store * ~300 bytes/SKU minified =~ 4-5MB, well under budget), which
embedding all 20 stores at once (~78MB) cannot.

Usage:
  python scripts/testdata/export_full_store_catalog.py --stores nsg,dng,gvp,wle,tbh \
    --product-dir data/ProductInfo --out-dir SmartSearch/full_store_catalog
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path

LANGS = ("vi", "en", "kr")

HTML_RE = re.compile(r"<[^>]*>")
ENTITY_RE = re.compile(r"&[a-z]+;")
WORD_RE = re.compile(r"[a-zA-Z0-9À-ỹ]+")

STOPWORDS_VI = {
    "va", "hoac", "la", "cua", "cho", "voi", "tai", "trong", "khi", "sau", "truoc",
    "de", "duoc", "khong", "co", "mot", "cac", "nhung", "nay", "do", "nen", "the",
    "san", "pham", "theo", "tu", "den", "neu", "hay", "vao", "ra", "len", "xuong",
    "nhu", "boi", "vi", "ma", "thi", "day", "kia", "moi", "rat", "qua", "con",
    "chi", "ban", "quy", "khach", "vui", "long", "xem", "tai", "chinh", "sach",
}


def norm_ascii(s):
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


def load_boilerplate(product_dir):
    path = Path(product_dir) / "boilerplate_vi.txt"
    if not path.exists():
        return []
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            lines.append(line)
    return lines


def description_keywords(rec, boilerplate, name_tokens_norm, max_tokens=20):
    raw = (rec.get("description") or "") + " " + (rec.get("short_description") or "")
    text = HTML_RE.sub(" ", raw)
    text = ENTITY_RE.sub(" ", text)
    for b in boilerplate:
        text = text.replace(b, " ")
    words = WORD_RE.findall(text)
    seen = set()
    out = []
    for w in words:
        if len(w) < 3:
            continue
        wn = norm_ascii(w)
        if wn in STOPWORDS_VI or wn in name_tokens_norm or wn in seen:
            continue
        seen.add(wn)
        out.append(w.lower())
        if len(out) >= max_tokens:
            break
    return " ".join(out)


def unwrap(obj):
    if isinstance(obj, dict) and "_source" in obj and isinstance(obj["_source"], dict):
        return obj["_source"]
    return obj


def stream_ndjson(path):
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except Exception:
                    continue


def load_lang(product_dir, lang, store):
    path = Path(product_dir) / f"mart_{lang}_{store}_product.ndjson"
    out = {}
    if not path.exists():
        return out
    for raw in stream_ndjson(path):
        src = unwrap(raw)
        sku = src.get("sku")
        if sku:
            out[sku] = src
    return out


def category_label(rec):
    path = rec.get("category_full_path") or []
    if len(path) > 1:
        return path[1]
    if path:
        return path[0]
    return "Khac"


def export_store(store, product_dir, out_dir, with_desc_keywords=False, desc_kw_max=20):
    per_lang = {lang: load_lang(product_dir, lang, store) for lang in LANGS}
    vi = per_lang["vi"]
    if not vi:
        print(f"[{store}] no VI records found, skipping")
        return None

    boilerplate = load_boilerplate(product_dir) if with_desc_keywords else []

    rows = []
    for sku, rec in vi.items():
        en = per_lang["en"].get(sku)
        kr = per_lang["kr"].get(sku)
        ca = rec.get("custom_attribute") or {}
        # "brand" (manufacturer, e.g. "P&G", "Unilever") is the field to search
        # by brand — populated on ~16% of SKUs. "sub_brand"/"sub_brand_new"
        # (product-line name, e.g. "Pantene") is populated far more often
        # (~64%) and is a reasonable fallback when brand itself is empty, even
        # though it sometimes just repeats a word already in the product name.
        brand = ca.get("brand") or ca.get("sub_brand") or ca.get("sub_brand_new") or ""
        row = {
            "sku": sku,
            "name": rec.get("name") or "",
            "cat": category_label(rec),
            "brand": brand,
            "price": rec.get("price_default") or 0,
            "discount": rec.get("price_discount_percent") or 0,
            "stock": rec.get("stock_qty") or 0,
            "sold30": (rec.get("best_sellings") or {}).get("30days") or 0,
            "viewed": rec.get("ext_viewed") or 0,
            "rating": rec.get("rating_summary"),
            "store": store,
            "name_en": (en or {}).get("name") or "",
            "name_kr": (kr or {}).get("name") or "",
        }
        if with_desc_keywords:
            name_tokens_norm = {norm_ascii(w) for w in WORD_RE.findall(row["name"])}
            row["desc_kw"] = description_keywords(rec, boilerplate, name_tokens_norm, desc_kw_max)
        rows.append(row)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{store}.json"
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    out_path.write_text(payload, encoding="utf-8")
    size_mb = len(payload.encode("utf-8")) / (1024 * 1024)
    print(f"[{store}] {len(rows)} SKU, {size_mb:.2f} MB -> {out_path}")
    return {"store": store, "count": len(rows), "size_mb": round(size_mb, 2)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--stores", required=True, help="comma-separated store codes")
    p.add_argument("--product-dir", default="data/ProductInfo")
    p.add_argument("--out-dir", default="SmartSearch/full_store_catalog")
    p.add_argument("--desc-keywords", action="store_true",
                    help="include a compact 'desc_kw' field (deduped description keywords, "
                         "boilerplate/stopwords/name-tokens stripped) for description-signal matching")
    p.add_argument("--desc-keywords-max", type=int, default=20)
    args = p.parse_args()

    stores = [s.strip() for s in args.stores.split(",") if s.strip()]
    manifest = []
    for store in stores:
        result = export_store(store, args.product_dir, args.out_dir,
                               with_desc_keywords=args.desc_keywords,
                               desc_kw_max=args.desc_keywords_max)
        if result:
            manifest.append(result)

    manifest_path = Path(args.out_dir) / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    total_mb = sum(m["size_mb"] for m in manifest)
    print(f"\nTotal: {sum(m['count'] for m in manifest)} SKU across {len(manifest)} store, {total_mb:.2f} MB combined")


if __name__ == "__main__":
    main()
