#!/usr/bin/env python3
"""
Generate text-search test inputs (queries) and expected outputs from an NDJSON product file.

Usage:
  python generate_text_testdata.py --ndjson "path/to/mart_en_nsg_product.ndjson" --out-dir text_testdata --max-products 100 --variants 3

Outputs in --out-dir:
  - inputs.ndjson    (test_id, query, product_id, title, variant_type)
  - expected.ndjson  (test_id, expected_top1, expected_topN)
  - inputs.csv       CSV summary

Variant types generated per product:
  - exact: exact product title
  - partial: first N words of title
  - lowercase: lowercase title
  - typo: simulated typo (adjacent char swap)
  - extended: title plus extra words (e.g., color/size)
"""
import argparse
import json
from pathlib import Path
from itertools import islice
import random
import pandas as pd


def stream_ndjson(path):
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def make_variants(title, max_variants=3):
    variants = []
    if not title:
        return variants
    title = ' '.join(title.split())
    # exact
    variants.append(('exact', title))
    # lowercase
    variants.append(('lowercase', title.lower()))
    # partial: first 2-4 words
    words = title.split()
    if len(words) > 1:
        take = min(4, max(2, len(words)//2))
        variants.append(('partial', ' '.join(words[:take])))
    # typo: swap two adjacent characters
    if len(title) >= 4:
        s = list(title)
        i = min(len(s)-2, max(1, len(s)//4))
        s[i], s[i+1] = s[i+1], s[i]
        variants.append(('typo', ''.join(s)))
    # extended: add generic words
    variants.append(('extended', title + ' product'))

    # dedupe while preserving order
    seen = set()
    out = []
    for t, q in variants:
        key = q.lower()
        if key not in seen:
            out.append((t, q))
            seen.add(key)
        if len(out) >= max_variants:
            break
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ndjson', required=True)
    p.add_argument('--out-dir', default='output/text_testdata')
    p.add_argument('--max-products', type=int, default=500)
    p.add_argument('--variants', type=int, default=3)
    p.add_argument('--topn', type=int, default=5)
    args = p.parse_args()

    ndpath = Path(args.ndjson)
    outdir = Path(args.out_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    inputs_path = outdir / 'inputs.ndjson'
    expected_path = outdir / 'expected.ndjson'
    csv_path = outdir / 'inputs.csv'

    prod_count = 0
    test_count = 0

    def unwrap(prod):
        if isinstance(prod, dict) and '_source' in prod and isinstance(prod['_source'], dict):
            return prod['_source']
        return prod

    with inputs_path.open('w', encoding='utf-8') as fin, expected_path.open('w', encoding='utf-8') as fexp:
        for prod in islice(stream_ndjson(ndpath), args.max_products):
            prod_count += 1
            p = unwrap(prod)
            pid = p.get('product_id') or p.get('id') or p.get('sku') or p.get('productId') or p.get('sku') or p.get('id')
            title = p.get('title') or p.get('name') or p.get('product_name') or ''
            if not title:
                continue
            variants = make_variants(title, max_variants=args.variants)
            for vtype, query in variants:
                test_count += 1
                tid = f'TX-{test_count:06d}'
                inp = {'test_id': tid, 'query': query, 'product_id': pid, 'title': title, 'variant': vtype}
                fin.write(json.dumps(inp, ensure_ascii=False) + '\n')
                exp = {'test_id': tid, 'expected_top1': pid, 'expected_topN': [pid], 'notes': ''}
                fexp.write(json.dumps(exp, ensure_ascii=False) + '\n')
            if prod_count % 100 == 0:
                print(f'Processed {prod_count} products, tests so far: {test_count}')

    with csv_path.open('w', encoding='utf-8') as fc:
        fc.write('test_id,query,product_id,title,variant\n')
        with inputs_path.open('r', encoding='utf-8') as fin:
            for line in fin:
                obj = json.loads(line)
                title = (obj.get('title') or '').replace('"', '""')
                q = (obj.get('query') or '').replace('"', '""')
                fc.write(f'"{obj.get("test_id")}","{q}",{obj.get("product_id")},"{title}",{obj.get("variant")}\n')

    # Also save to Excel workbook with two sheets
    try:
        df_inputs = pd.read_csv(csv_path)
        # build expected DataFrame
        exp_rows = []
        with expected_path.open('r', encoding='utf-8') as fexp:
            for line in fexp:
                exp_rows.append(json.loads(line))
        df_expected = pd.DataFrame(exp_rows)
        excel_path = outdir / 'text_testdata.xlsx'
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            df_inputs.to_excel(writer, sheet_name='inputs', index=False)
            df_expected.to_excel(writer, sheet_name='expected', index=False)
        print(f'Wrote {test_count} text-search test inputs to {inputs_path} (CSV at {csv_path}) and Excel at {excel_path}')
    except Exception as e:
        print(f'Wrote {test_count} text-search test inputs to {inputs_path} (CSV at {csv_path}). Failed to write Excel: {e}')


if __name__ == '__main__':
    main()
