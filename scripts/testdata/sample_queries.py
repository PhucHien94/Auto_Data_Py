#!/usr/bin/env python3
"""
Sample queries from multilang query workbook to create a manageable test set.

Usage:
  python sample_queries.py --in text_testdata/multilang_queries.xlsx --out text_testdata/sample_queries.xlsx --size 1000
"""
import argparse
from pathlib import Path
import pandas as pd


def stratified_sample(df, by='variant_type', n=1000):
    groups = df.groupby(by)
    variants = list(groups.groups.keys())
    per = max(1, n // len(variants))
    samples = []
    for v in variants:
        g = groups.get_group(v)
        if len(g) <= per:
            samples.append(g)
        else:
            samples.append(g.sample(per, random_state=42))
    res = pd.concat(samples)
    if len(res) < n:
        # fill up with randoms from remaining
        remaining = df.drop(res.index)
        need = n - len(res)
        if len(remaining) > 0:
            res = pd.concat([res, remaining.sample(min(need, len(remaining)), random_state=42)])
    return res.sample(n=min(n, len(res)), random_state=42)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--in', dest='infile', required=True)
    p.add_argument('--out', dest='outfile', default='SmartSearch/text_testdata/sample_queries.xlsx')
    p.add_argument('--size', type=int, default=1000)
    args = p.parse_args()

    inp = Path(args.infile)
    out = Path(args.outfile)
    if not inp.exists():
        print('Input workbook not found:', inp)
        return
    df = pd.read_excel(inp, sheet_name='queries')
    # ensure variant_type exists
    if 'variant_type' not in df.columns:
        # try lowercase header
        df.columns = [c.lower() for c in df.columns]
    sample = stratified_sample(df, by='variant_type', n=args.size)
    sample.to_excel(out, sheet_name='queries', index=False)
    # also write NDJSON inputs for runner
    ndjson_out = out.parent / 'sample_inputs.ndjson'
    import json
    with ndjson_out.open('w', encoding='utf-8') as fh:
        for _, row in sample.iterrows():
            obj = {'test_id': row.get('test_id'), 'query': row.get('query'), 'product_id': row.get('sku')}
            fh.write(json.dumps(obj, ensure_ascii=False) + '\n')
    print(f'Wrote sample {len(sample)} to {out} and NDJSON to {ndjson_out}')


if __name__ == '__main__':
    main()
