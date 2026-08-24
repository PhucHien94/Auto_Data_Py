#!/usr/bin/env python3
r"""
Generate image-search test input/output from an NDJSON product file.

Usage:
  python generate_image_testdata.py \
    --ndjson "C:\Users\Admin\Downloads\files (1)\v1\mart_en_nsg_product.ndjson" \
    --out-dir ./image_testdata \
    --max-products 500 --sample-per-product 1

Outputs (written to --out-dir):
  - inputs.ndjson  : each line is a test input {test_id, image, product_id, title}
  - expected.ndjson: expected outputs {test_id, expected_top1, expected_topN}
  - inputs.csv     : CSV view of inputs

The script streams the NDJSON so it can handle large files.
"""
import argparse
import json
import os
from pathlib import Path
from itertools import islice


def find_image_fields(obj):
    # common image field candidates
    candidates = ['image', 'image_url', 'images', 'image_urls', 'media', 'photos']
    found = []
    for k in candidates:
        if k in obj and obj[k]:
            v = obj[k]
            if isinstance(v, list):
                found.extend(v)
            else:
                found.append(v)
    # also search nested keys
    for k, v in obj.items():
        if isinstance(v, dict):
            for kk in ['image', 'url', 'src']:
                if kk in v and v[kk]:
                    found.append(v[kk])
    # dedupe and normalize to strings
    out = []
    for it in found:
        if not isinstance(it, str):
            try:
                s = json.dumps(it, ensure_ascii=False)
            except Exception:
                continue
        else:
            s = it
        if s and s not in out:
            out.append(s)
    return out


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


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--ndjson', required=True)
    p.add_argument('--out-dir', default='SmartSearch/image_testdata')
    p.add_argument('--max-products', type=int, default=1000)
    p.add_argument('--sample-per-product', type=int, default=1)
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

    with inputs_path.open('w', encoding='utf-8') as fin, expected_path.open('w', encoding='utf-8') as fexp:
        for prod in islice(stream_ndjson(ndpath), args.max_products):
            prod_count += 1
            # try common id fields
            pid = prod.get('product_id') or prod.get('id') or prod.get('sku') or prod.get('productId')
            title = prod.get('title') or prod.get('name') or prod.get('product_name') or ''
            images = find_image_fields(prod)
            if not images:
                continue
            # sample up to sample-per-product
            for img in images[:args.sample_per_product]:
                test_count += 1
                test_id = f'TC-{test_count:06d}'
                inp = {'test_id': test_id, 'image': img, 'product_id': pid, 'title': title}
                fin.write(json.dumps(inp, ensure_ascii=False) + '\n')
                exp = {'test_id': test_id, 'expected_top1': pid, 'expected_topN': [pid], 'notes': ''}
                fexp.write(json.dumps(exp, ensure_ascii=False) + '\n')
            if prod_count % 100 == 0:
                print(f'Processed {prod_count} products, tests so far: {test_count}')

    # write CSV summary
    with csv_path.open('w', encoding='utf-8') as fc:
        fc.write('test_id,image,product_id,title\n')
        with inputs_path.open('r', encoding='utf-8') as fin:
            for line in fin:
                obj = json.loads(line)
                # escape quotes
                title = (obj.get('title') or '').replace('"', '""')
                fc.write(f"{obj.get('test_id')},{obj.get('image')},{obj.get('product_id')},\"{title}\"\n")

    print(f'Wrote {test_count} test inputs to {inputs_path} and expected to {expected_path}. CSV at {csv_path}')


if __name__ == '__main__':
    main()
