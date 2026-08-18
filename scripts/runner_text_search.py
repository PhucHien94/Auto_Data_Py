#!/usr/bin/env python3
"""
Flexible runner to execute text-search testcases and write results into the Excel workbook.

Usage examples:
  python runner_text_search.py --inputs text_testdata/inputs.ndjson --excel text_testdata/text_testdata.xlsx \
    --api-url "https://api.example.com/search" --method GET --param q --topn 5 --header "Authorization:Bearer TOKEN"

The script supports GET (query param) or POST (JSON body) and accepts multiple `--header` entries.
It attempts to extract product ids from response results by checking common id fields.
"""
import argparse
import json
import time
from pathlib import Path
from urllib import parse, request
import ssl
from openpyxl import load_workbook


def extract_ids_from_result(obj):
    # Look for common id fields
    for key in ('product_id', 'productId', 'id', 'sku'):
        if key in obj:
            return str(obj[key])
    # fallback: if value has 'sku' inside nested
    for v in obj.values() if isinstance(obj, dict) else []:
        if isinstance(v, (str, int)):
            pass
    return None


def parse_headers(header_list):
    headers = {}
    if not header_list:
        return headers
    for h in header_list:
        if ':' in h:
            k, v = h.split(':', 1)
            headers[k.strip()] = v.strip()
    return headers


def call_api_get(url, headers):
    req = request.Request(url, headers=headers, method='GET')
    ctx = ssl.create_default_context()
    with request.urlopen(req, context=ctx, timeout=30) as resp:
        data = resp.read()
        return data


def call_api_post(url, headers, body_bytes):
    req = request.Request(url, data=body_bytes, headers=headers, method='POST')
    ctx = ssl.create_default_context()
    with request.urlopen(req, context=ctx, timeout=30) as resp:
        data = resp.read()
        return data


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--inputs', required=False, help='Path to inputs NDJSON')
    p.add_argument('--excel-input', required=False, help='Path to Excel file with queries sheet')
    p.add_argument('--sheet', default='queries', help='Sheet name when using --excel-input')
    p.add_argument('--excel', required=True)
    p.add_argument('--api-url', required=True)
    p.add_argument('--method', choices=['GET', 'POST'], default='GET')
    p.add_argument('--param', default='q', help='Query param name or JSON key')
    p.add_argument('--topn', type=int, default=5)
    p.add_argument('--header', action='append', help='Custom header in form Key:Value')
    p.add_argument('--result-path', default='results', help='Top-level key in JSON containing result list')
    args = p.parse_args()

    excel_path = Path(args.excel)
    headers = parse_headers(args.header)

    # load inputs either from NDJSON or from Excel queries sheet
    tests = []
    if args.excel_input:
        try:
            import pandas as pd
            df = pd.read_excel(args.excel_input, sheet_name=args.sheet)
            for _, row in df.iterrows():
                tests.append({'test_id': row.get('test_id') or row.get('Test ID') or None,
                              'query': row.get('query') or row.get('Query') or row.get('query'),
                              'product_id': row.get('sku') or row.get('product_id') or row.get('productId')})
        except Exception as e:
            print('Failed to read excel input:', e)
            return
    else:
        if not args.inputs:
            print('Either --inputs or --excel-input must be provided')
            return
        inputs_path = Path(args.inputs)
        if not inputs_path.exists():
            print('Inputs file not found:', inputs_path)
            return
        with inputs_path.open('r', encoding='utf-8') as fh:
            for line in fh:
                if not line.strip():
                    continue
                tests.append(json.loads(line))

    # prepare results rows
    results = []
    for t in tests:
        tid = t.get('test_id')
        query = t.get('query')
        expected = t.get('product_id')

        # build request
        start = time.time()
        try:
            if args.method == 'GET':
                qstr = parse.urlencode({args.param: query})
                url = args.api_url + ('?' if '?' not in args.api_url else '&') + qstr
                raw = call_api_get(url, headers)
            else:
                body = json.dumps({args.param: query}).encode('utf-8')
                hdrs = dict(headers)
                hdrs['Content-Type'] = 'application/json'
                raw = call_api_post(args.api_url, hdrs, body)
            latency = int((time.time() - start) * 1000)
            text = raw.decode('utf-8')
            j = json.loads(text)
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            results.append({
                'test_id': tid, 'query': query, 'expected_top1': expected,
                'actual_top1': None, 'actual_topN': [], 'position_of_expected': None,
                'latency_ms': latency, 'pass_fail': 'ERROR', 'notes': str(e), 'raw_response': ''
            })
            continue

        # extract result list
        res_list = []
        if args.result_path and args.result_path in j and isinstance(j[args.result_path], list):
            res_list = j[args.result_path]
        else:
            # try common keys: 'results', 'items', 'hits'
            for k in ('results', 'items', 'hits', 'data'):
                if k in j and isinstance(j[k], list):
                    res_list = j[k]
                    break

        top_ids = []
        for item in res_list[:args.topn]:
            if isinstance(item, (str, int)):
                top_ids.append(str(item))
            elif isinstance(item, dict):
                pid = extract_ids_from_result(item)
                if pid:
                    top_ids.append(pid)
                else:
                    # fallback: try 'product_id' in nested
                    top_ids.append(json.dumps(item, ensure_ascii=False))
        pos = None
        try:
            if expected is not None:
                expected_s = str(expected)
                if expected_s in top_ids:
                    pos = top_ids.index(expected_s) + 1
        except Exception:
            pos = None

        pass_fail = 'PASS' if pos == 1 else ('PARTIAL' if pos and pos <= args.topn else 'FAIL')

        results.append({
            'test_id': tid, 'query': query, 'expected_top1': expected,
            'actual_top1': top_ids[0] if top_ids else None, 'actual_topN': ','.join(top_ids),
            'position_of_expected': pos, 'latency_ms': latency, 'pass_fail': pass_fail,
            'notes': '', 'raw_response': json.dumps(j, ensure_ascii=False)
        })

    # write results to Excel
    wb = load_workbook(excel_path)
    if 'results' in wb.sheetnames:
        ws = wb['results']
        # clear after header
        for row in list(ws.rows)[1:]:
            for cell in row:
                cell.value = None
    else:
        ws = wb.create_sheet('results')
        headers = [
            'test_id', 'query', 'expected_top1', 'actual_top1', 'actual_topN',
            'position_of_expected', 'latency_ms', 'pass_fail', 'notes', 'raw_response'
        ]
        for i, h in enumerate(headers, start=1):
            ws.cell(row=1, column=i, value=h)

    # append rows
    for i, r in enumerate(results, start=2):
        ws.cell(row=i, column=1, value=r['test_id'])
        ws.cell(row=i, column=2, value=r['query'])
        ws.cell(row=i, column=3, value=r['expected_top1'])
        ws.cell(row=i, column=4, value=r['actual_top1'])
        ws.cell(row=i, column=5, value=r['actual_topN'])
        ws.cell(row=i, column=6, value=r['position_of_expected'])
        ws.cell(row=i, column=7, value=r['latency_ms'])
        ws.cell(row=i, column=8, value=r['pass_fail'])
        ws.cell(row=i, column=9, value=r['notes'])
        ws.cell(row=i, column=10, value=r['raw_response'])

    wb.save(excel_path.with_name(excel_path.stem + '_with_results' + excel_path.suffix))
    print('Wrote results to', excel_path.with_name(excel_path.stem + '_with_results' + excel_path.suffix))


if __name__ == '__main__':
    main()
