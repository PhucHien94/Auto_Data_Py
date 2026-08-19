#!/usr/bin/env python3
"""
Generate a golden test set (autocomplete + search-result expectations) for one
store, joining the EN/VI/KR product NDJSON files by SKU.

This is the "standard dataset" generator described in the Smart Search test
strategy (Part 1): one dataset per store, capped at --max-products, split into
two output streams because Autocomplete and Search Result are scored
differently (SS-SCR-002-SC1-TC3: autocomplete suggests search keywords, not
product titles).

Usage:
  python scripts/generate_master_testset.py --store nsg --out-dir output/golden_testsets/nsg
  python scripts/generate_master_testset.py --all-stores --out-dir output/golden_testsets

Known assumptions (see manifest.json written alongside the output):
  - Autocomplete "expected_suggestions" popularity is a PROXY built from
    best_sellings/ext_viewed on the matching products, not real search-query
    volume. Treat as a starting point for QA/BA sign-off, not ground truth.
  - "regional" and "related" dimensions only produce variants for terms
    present in data/glossary/*.csv. Those files ship with example/placeholder
    rows only - populate them with QA/BA-verified entries before relying on
    those dimensions in a real test cycle.
"""
import argparse
import csv
import json
import random
import unicodedata
from collections import defaultdict
from pathlib import Path

LANGS = ("en", "vi", "kr")
TITLE_KEYS = ("title", "name", "product_name", "name_en", "name_vi", "name_kr")
SKU_KEYS = ("sku", "sku_code", "id", "product_id")


def unwrap(obj):
    if isinstance(obj, dict) and "_source" in obj and isinstance(obj["_source"], dict):
        return obj["_source"]
    return obj


def stream_ndjson(path):
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def find_title(obj):
    for k in TITLE_KEYS:
        if obj.get(k):
            return str(obj[k])
    return None


def find_sku(obj):
    for k in SKU_KEYS:
        if obj.get(k):
            return str(obj[k])
    return None


def category_l1(obj):
    path = obj.get("category_full_path")
    if isinstance(path, list) and path:
        return str(path[0])
    return "UNKNOWN"


def popularity(obj):
    bs = obj.get("best_sellings") or {}
    d7 = bs.get("7days") or 0
    d30 = bs.get("30days") or 0
    viewed = obj.get("ext_viewed") or 0
    try:
        return float(d7) * 3 + float(d30) + float(viewed) * 0.1
    except (TypeError, ValueError):
        return 0.0


def load_store_lang(product_dir, lang, store):
    path = Path(product_dir) / f"mart_{lang}_{store}_product.ndjson"
    if not path.exists():
        return {}
    out = {}
    for raw in stream_ndjson(path):
        src = unwrap(raw)
        sku = find_sku(src)
        title = find_title(src)
        if not sku or not title:
            continue
        out[sku] = src
    return out


def load_glossary(glossary_dir, filename, relation_type):
    path = Path(glossary_dir) / filename
    rows = []
    if not path.exists():
        return rows
    with open(path, "r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("relation_type") == relation_type and row.get("term") and row.get("variant"):
                rows.append(row)
    return rows


def strip_diacritics(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def price_quartile(price, quartile_bounds):
    if price is None:
        return "unknown"
    for i, bound in enumerate(quartile_bounds):
        if price <= bound:
            return f"q{i + 1}"
    return f"q{len(quartile_bounds) + 1}"


def stratified_sample(joined, cap, seed=42):
    """joined: list of dicts with 'sku','category_l1','price','stock_zero'."""
    rng = random.Random(seed)
    prices = sorted(p["price"] for p in joined if p["price"] is not None)
    bounds = []
    if prices:
        n = len(prices)
        for q in (0.25, 0.5, 0.75):
            bounds.append(prices[min(n - 1, int(n * q))])

    buckets = defaultdict(list)
    for p in joined:
        key = (p["category_l1"], price_quartile(p["price"], bounds), p["stock_zero"])
        buckets[key].append(p)
    for v in buckets.values():
        rng.shuffle(v)

    sample = []
    bucket_keys = list(buckets.keys())
    rng.shuffle(bucket_keys)
    idx = {k: 0 for k in bucket_keys}
    while len(sample) < cap and any(idx[k] < len(buckets[k]) for k in bucket_keys):
        for k in bucket_keys:
            if idx[k] < len(buckets[k]):
                sample.append(buckets[k][idx[k]])
                idx[k] += 1
                if len(sample) >= cap:
                    break
    return sample


def make_typo(title):
    if len(title) < 4:
        return None
    s = list(title)
    i = min(len(s) - 2, max(1, len(s) // 4))
    s[i], s[i + 1] = s[i + 1], s[i]
    return "".join(s)


def make_partial(title):
    words = title.split()
    if len(words) <= 1:
        return None
    take = min(4, max(2, len(words) // 2))
    return " ".join(words[:take])


def variant_rows(lang, title, synonyms, regionals):
    """Yield (dimension, query) pairs for one product title in one language."""
    title = " ".join(title.split())
    seen = set()

    def emit(dim, q):
        if not q:
            return None
        key = q.lower()
        if key not in seen:
            seen.add(key)
            return (dim, q)
        return None

    candidates = [
        emit("exact", title),
        emit("lowercase", title.lower()),
        emit("partial", make_partial(title)),
        emit("typo", make_typo(title)),
    ]
    if lang == "vi":
        candidates.append(emit("no_diacritics", strip_diacritics(title)))

    lower_title = title.lower()
    for row in synonyms:
        if row["term"].lower() in lower_title:
            variant_query = lower_title.replace(row["term"].lower(), row["variant"].lower())
            candidates.append(emit("synonym", variant_query))
    for row in regionals:
        if row["term"].lower() in lower_title:
            variant_query = lower_title.replace(row["term"].lower(), row["variant"].lower())
            candidates.append(emit("regional", variant_query))

    return [c for c in candidates if c]


def build_related_rows(joined_by_sku, related_glossary, lang_key):
    """relation_type=related rows: variant phrase -> acceptable_set of SKUs whose
    title (in lang_key) contains `term`."""
    out = []
    for row in related_glossary:
        term_l = row["term"].lower()
        matches = [
            sku for sku, rec in joined_by_sku.items()
            if rec.get(lang_key) and term_l in find_title(rec[lang_key]).lower()
        ]
        if matches:
            out.append({"query": row["variant"], "acceptable_set": matches, "note": row.get("verified_by", "")})
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--store")
    p.add_argument("--all-stores", action="store_true")
    p.add_argument("--product-dir", default="data/ProductInfo")
    p.add_argument("--glossary-dir", default="data/glossary")
    p.add_argument("--max-products", type=int, default=300)
    p.add_argument("--topn", type=int, default=10, help="suggestion list size for autocomplete_expected")
    p.add_argument("--out-dir", default="output/golden_testsets")
    args = p.parse_args()

    if not args.store and not args.all_stores:
        p.error("provide --store <code> or --all-stores")

    product_dir = Path(args.product_dir)
    if args.all_stores:
        stores = sorted({
            f.name.split("_", 2)[2].rsplit("_product.ndjson", 1)[0]
            for f in product_dir.glob("mart_en_*_product.ndjson")
        })
    else:
        stores = [args.store]

    synonyms = load_glossary(args.glossary_dir, "synonyms.csv", "synonym")
    regionals = load_glossary(args.glossary_dir, "regional_terms.csv", "regional")
    relateds = load_glossary(args.glossary_dir, "related_terms.csv", "related")

    for store in stores:
        store_out_dir = Path(args.out_dir) / store if args.all_stores else Path(args.out_dir)
        run_for_store(store, product_dir, args.max_products,
                       args.topn, store_out_dir, synonyms, regionals, relateds)


def run_for_store(store, product_dir, max_products, topn, out_dir,
                   synonyms, regionals, relateds):
    per_lang = {lang: load_store_lang(product_dir, lang, store) for lang in LANGS}
    counts = {lang: len(v) for lang, v in per_lang.items()}
    if not any(counts.values()):
        print(f"[{store}] no product files found, skipping")
        return

    anchor_lang = max(counts, key=counts.get)
    joined_by_sku = {}
    for sku, rec in per_lang[anchor_lang].items():
        entry = {anchor_lang: rec}
        for lang in LANGS:
            if lang != anchor_lang and sku in per_lang[lang]:
                entry[lang] = per_lang[lang][sku]
        joined_by_sku[sku] = entry

    pool = []
    for sku, entry in joined_by_sku.items():
        rec = entry[anchor_lang]
        pool.append({
            "sku": sku,
            "category_l1": category_l1(rec),
            "price": rec.get("price_default"),
            "stock_zero": (rec.get("stock_qty") or 0) == 0,
        })

    sampled = stratified_sample(pool, max_products)
    sampled_skus = {p["sku"] for p in sampled}

    out_dir.mkdir(parents=True, exist_ok=True)
    search_path = out_dir / "search_result_expected.ndjson"
    auto_path = out_dir / "autocomplete_expected.ndjson"

    dim_counts = defaultdict(int)
    test_id = 0
    autocomplete_id = 0

    keyword_pop = []  # (dimension, lang, keyword, sku, popularity) for autocomplete ranking

    with search_path.open("w", encoding="utf-8") as fsearch:
        for sku in sampled_skus:
            entry = joined_by_sku[sku]
            pop = popularity(entry[anchor_lang])
            for lang in LANGS:
                if lang not in entry:
                    continue
                title = find_title(entry[lang])
                if not title:
                    continue
                for dim, query in variant_rows(lang, title, synonyms, regionals):
                    test_id += 1
                    dim_counts[dim] += 1
                    row = {
                        "test_id": f"GS-{store.upper()}-{test_id:06d}",
                        "sku": sku,
                        "lang": lang,
                        "dimension": dim,
                        "query": query,
                        "expected_top1": sku,
                        "acceptable_set": [sku],
                        "note": "",
                    }
                    fsearch.write(json.dumps(row, ensure_ascii=False) + "\n")
                    keyword_pop.append((dim, lang, query, sku, pop))

        # related-term dimension: query -> multiple acceptable SKUs, not tied to 1 product
        for lang in LANGS:
            related_rows = build_related_rows(
                {sku: joined_by_sku[sku] for sku in sampled_skus}, relateds, lang
            )
            for r in related_rows:
                test_id += 1
                dim_counts["related"] += 1
                row = {
                    "test_id": f"GS-{store.upper()}-{test_id:06d}",
                    "sku": None,
                    "lang": lang,
                    "dimension": "related",
                    "query": r["query"],
                    "expected_top1": r["acceptable_set"][0],
                    "acceptable_set": r["acceptable_set"],
                    "note": r["note"],
                }
                fsearch.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Autocomplete: for each (lang, prefix) rank candidate keywords by popularity proxy.
    by_prefix = defaultdict(list)
    for dim, lang, query, sku, pop in keyword_pop:
        if dim not in ("exact", "partial", "no_diacritics"):
            continue
        prefix = query[:3].lower()
        by_prefix[(lang, prefix)].append((query, pop))

    with auto_path.open("w", encoding="utf-8") as fauto:
        for (lang, prefix), rows in sorted(by_prefix.items()):
            ranked = sorted(rows, key=lambda r: r[1], reverse=True)
            seen_kw = set()
            suggestions = []
            for kw, pop in ranked:
                if kw.lower() in seen_kw:
                    continue
                seen_kw.add(kw.lower())
                suggestions.append({"keyword": kw, "rank": len(suggestions) + 1})
                if len(suggestions) >= topn:
                    break
            if not suggestions:
                continue
            autocomplete_id += 1
            out_row = {
                "test_id": f"AC-{store.upper()}-{autocomplete_id:06d}",
                "lang": lang,
                "query_prefix": prefix,
                "expected_suggestions": suggestions,
                "source_note": (
                    "popularity proxy = best_sellings.7days*3 + best_sellings.30days + "
                    "ext_viewed*0.1 on matching products - NOT real search-query volume, "
                    "needs BA/Data sign-off before use as strict ground truth"
                ),
            }
            fauto.write(json.dumps(out_row, ensure_ascii=False) + "\n")

    manifest = {
        "store": store,
        "anchor_lang": anchor_lang,
        "lang_record_counts": counts,
        "products_sampled": len(sampled_skus),
        "max_products": max_products,
        "search_result_rows": test_id,
        "search_result_by_dimension": dict(dim_counts),
        "autocomplete_prefix_groups": autocomplete_id,
        "glossary_loaded": {
            "synonyms": len(synonyms),
            "regional_terms": len(regionals),
            "related_terms": len(relateds),
        },
        "assumptions": [
            "Autocomplete expected_suggestions ranking uses a popularity PROXY "
            "(best_sellings + ext_viewed), not real search logs.",
            "regional/related dimensions only cover terms present in "
            "data/glossary/*.csv, which ship with placeholder rows only.",
        ],
    }
    with (out_dir / "manifest.json").open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    print(f"[{store}] {len(sampled_skus)} products sampled, {test_id} search rows, "
          f"{autocomplete_id} autocomplete prefix groups -> {out_dir}")


if __name__ == "__main__":
    main()
