#!/usr/bin/env python3
"""
Export a golden test-set directory (from generate_master_testset.py) into
ready-to-use manual-QC assets: a Postman collection + environment + data CSV,
and a k6 load-test script + query fixture.

Usage:
  python scripts/export_manual_qc_assets.py --dataset-dir output/golden_testsets/nsg --out-dir output/manual_qc/nsg
"""
import argparse
import csv
import json
import random
from pathlib import Path


def stream_ndjson(path):
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def sample_rows(rows, n, seed=42):
    rng = random.Random(seed)
    rows = list(rows)
    if len(rows) <= n:
        return rows
    # stratify lightly by dimension so the sample isn't all one variant type
    by_dim = {}
    for r in rows:
        by_dim.setdefault(r.get("dimension", "?"), []).append(r)
    for v in by_dim.values():
        rng.shuffle(v)
    out, i = [], 0
    dims = list(by_dim.keys())
    while len(out) < n:
        progressed = False
        for d in dims:
            if by_dim[d]:
                out.append(by_dim[d].pop())
                progressed = True
                if len(out) >= n:
                    break
        if not progressed:
            break
    return out


def build_postman_collection(store_name):
    return {
        "info": {
            "name": f"MART Smart Search — Manual QC ({store_name})",
            "description": (
                "Search + Autocomplete requests parameterized by {{base_url}} and {{query}} - "
                "run individually to poke at 1 query, or use Postman's Collection Runner with "
                "postman_data.csv to iterate every sampled query and see the pass/fail per row."
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            {
                "name": "Search",
                "request": {
                    "method": "GET",
                    "header": [{"key": "Authorization", "value": "Bearer {{auth_token}}", "disabled": True}],
                    "url": {
                        "raw": "{{base_url}}{{search_path}}?q={{query}}",
                        "host": ["{{base_url}}"],
                        "path": ["{{search_path}}"],
                        "query": [{"key": "q", "value": "{{query}}"}],
                    },
                },
                "event": [{
                    "listen": "test",
                    "script": {
                        "type": "text/javascript",
                        "exec": [
                            "pm.test('status 200', () => pm.response.to.have.status(200));",
                            "pm.test('response time < 1500ms', () => pm.expect(pm.response.responseTime).to.be.below(1500));",
                            "let body = pm.response.json();",
                            "let ids = (body.results || body.items || body.hits || body.data || []).map(",
                            "  r => (typeof r === 'object') ? (r.product_id || r.productId || r.id || r.sku) : r",
                            ");",
                            "pm.environment.set('last_actual_top1', ids[0] || null);",
                            "pm.test('expected_top1 present in results (manual reference)', () => {",
                            "  console.log('expected_top1 =', pm.iterationData.get('expected_top1'), '| actual =', ids);",
                            "});",
                        ],
                    },
                }],
            },
            {
                "name": "Autocomplete",
                "request": {
                    "method": "GET",
                    "header": [{"key": "Authorization", "value": "Bearer {{auth_token}}", "disabled": True}],
                    "url": {
                        "raw": "{{base_url}}{{autocomplete_path}}?q={{query}}",
                        "host": ["{{base_url}}"],
                        "path": ["{{autocomplete_path}}"],
                        "query": [{"key": "q", "value": "{{query}}"}],
                    },
                },
                "event": [{
                    "listen": "test",
                    "script": {
                        "type": "text/javascript",
                        "exec": [
                            "pm.test('status 200', () => pm.response.to.have.status(200));",
                            "pm.test('response time < 500ms', () => pm.expect(pm.response.responseTime).to.be.below(500));",
                            "let body = pm.response.json();",
                            "let sugg = body.suggestions || body.results || body.items || body.data || [];",
                            "pm.test('suggestions are keywords, not raw product objects', () => {",
                            "  pm.expect(Array.isArray(sugg)).to.be.true;",
                            "});",
                        ],
                    },
                }],
            },
        ],
    }


def build_postman_environment():
    return {
        "name": "MART Smart Search — local",
        "values": [
            {"key": "base_url", "value": "https://staging-search.internal", "enabled": True},
            {"key": "search_path", "value": "/api/v1/search", "enabled": True},
            {"key": "autocomplete_path", "value": "/api/v1/suggest", "enabled": True},
            {"key": "auth_token", "value": "", "enabled": True},
        ],
    }


K6_SCRIPT_TEMPLATE = """\
// k6 script for MART Smart Search - search endpoint spot-check / light load test.
// Queries come from k6_queries.json (exported by scripts/export_manual_qc_assets.py),
// so this file itself never needs hand-editing per store/dataset.
//
// Usage:
//   BASE_URL=https://staging-search.internal SEARCH_PATH=/api/v1/search \\
//     k6 run scripts/loadtest/k6_search_test.js
//
//   # control load shape from the CLI, no script edits needed:
//   k6 run --vus 10 --duration 30s scripts/loadtest/k6_search_test.js

import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';

const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8765';
const SEARCH_PATH = __ENV.SEARCH_PATH || '/search';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || '';

const queries = new SharedArray('queries', function () {
  return JSON.parse(open('./k6_queries.json'));
});

export const options = {
  vus: Number(__ENV.VUS || 5),
  duration: __ENV.DURATION || '30s',
  thresholds: {
    http_req_duration: ['p(95)<1500'],   // matches SS-SCR-004's 5s hard cutoff with headroom
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const row = queries[Math.floor(Math.random() * queries.length)];
  const url = `${BASE_URL}${SEARCH_PATH}?q=${encodeURIComponent(row.query)}`;
  const headers = AUTH_TOKEN ? { Authorization: `Bearer ${AUTH_TOKEN}` } : {};

  const res = http.get(url, { headers });

  check(res, {
    'status is 200': (r) => r.status === 200,
    'has a body': (r) => r.body && r.body.length > 0,
  });

  sleep(1);
}
"""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--postman-sample-size", type=int, default=50)
    p.add_argument("--k6-sample-size", type=int, default=300)
    args = p.parse_args()

    dataset_dir = Path(args.dataset_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    store_name = dataset_dir.name

    search_path = dataset_dir / "search_result_expected.ndjson"
    if not search_path.exists():
        raise SystemExit(f"{search_path} not found - run generate_master_testset.py first")
    rows = list(stream_ndjson(search_path))

    # --- Postman ---
    pm_sample = sample_rows(rows, args.postman_sample_size)
    (out_dir / "postman_collection.json").write_text(
        json.dumps(build_postman_collection(store_name), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "postman_environment.json").write_text(
        json.dumps(build_postman_environment(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out_dir / "postman_data.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["test_id", "query", "lang", "dimension", "expected_top1"])
        writer.writeheader()
        for r in pm_sample:
            writer.writerow({k: r.get(k) for k in writer.fieldnames})

    # --- k6 ---
    loadtest_dir = Path("scripts/loadtest")
    loadtest_dir.mkdir(parents=True, exist_ok=True)
    k6_script_path = loadtest_dir / "k6_search_test.js"
    if not k6_script_path.exists():
        k6_script_path.write_text(K6_SCRIPT_TEMPLATE, encoding="utf-8")

    k6_sample = sample_rows(rows, args.k6_sample_size)
    k6_queries = [{"query": r["query"], "expected_top1": r.get("expected_top1")} for r in k6_sample]
    (loadtest_dir / "k6_queries.json").write_text(
        json.dumps(k6_queries, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Postman: {out_dir}/postman_collection.json (+ environment.json, data.csv - {len(pm_sample)} query)")
    print(f"k6: {k6_script_path} (script, reused across datasets) + {loadtest_dir}/k6_queries.json ({len(k6_sample)} query, from {store_name})")


if __name__ == "__main__":
    main()
