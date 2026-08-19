// k6 script for MART Smart Search - search endpoint spot-check / light load test.
// Queries come from k6_queries.json (exported by scripts/performance/export_manual_qc_assets.py),
// so this file itself never needs hand-editing per store/dataset.
//
// Usage:
//   BASE_URL=https://staging-search.internal SEARCH_PATH=/api/v1/search \
//     k6 run scripts/performance/k6_search_test.js
//
//   # control load shape from the CLI, no script edits needed:
//   k6 run --vus 10 --duration 30s scripts/performance/k6_search_test.js

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
