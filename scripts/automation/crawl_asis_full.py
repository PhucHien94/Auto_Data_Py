#!/usr/bin/env python3
"""Crawl LẠI toàn bộ query trên hệ thống CŨ (As-Is, lottemart.vn production)
để lấy ĐỦ 3 thứ mà cache As-Is hiện tại đang thiếu:

  1. search_results  - cache cũ đã có, nhưng crawl lại để cùng thời điểm đo
  2. latency_ms      - cache cũ KHÔNG hề lưu (0/2383 entry) -> đây là lý do
                       chính phải chạy lại, không có nó thì không so được
                       performance cũ vs mới (P90/P95/P99)
  3. autocomplete    - chưa từng crawl; cần cho phần so sánh AutoComplete

Chạy vào PRODUCTION thật (www.lottemart.vn) nên: tuần tự, có throttle, có
backoff khi lỗi. Endpoint không cần auth (đã verify).

Usage:
  python scripts/automation/crawl_asis_full.py \
    --queries SmartSearch/test_data/json/batches/NSG_ExpectedData_all_20260907.json \
    --out SmartSearch/client_report/data/asis_full_<date>.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from lib_search_client import (call_api, build_request, ApiError, load_env_config,  # noqa: E402
                                resolve_template, resolve_extra_params, get_nested)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--queries", required=True, help="file Expected/batch chứa scenarios[] để lấy danh sách query")
    p.add_argument("--out", required=True)
    p.add_argument("--env", default="legacy")
    p.add_argument("--store", default="nsg")
    p.add_argument("--lang", default="vi")
    p.add_argument("--sleep-ms", type=int, default=400, help="nghỉ giữa các scenario (mặc định 400ms - đây là production)")
    p.add_argument("--max-tries", type=int, default=4)
    p.add_argument("--limit", type=int, help="chỉ chạy N query đầu (để thử)")
    p.add_argument("--progress-every", type=int, default=50)
    args = p.parse_args()

    cfg = load_env_config(args.env)
    search_api = resolve_template(cfg["search_api"], args.store, args.lang)
    ac_api = resolve_template(cfg.get("autocomplete_api"), args.store, args.lang)
    s_method = cfg.get("search_method", "POST")
    s_param = cfg.get("search_param", "q")
    s_extra = resolve_extra_params(cfg.get("search_extra_params", {}), args.store, args.lang)
    s_path = cfg.get("search_result_path", "data.items")
    s_headers = cfg.get("search_headers", {})
    ac_method = cfg.get("autocomplete_method", "GET")
    ac_param = cfg.get("autocomplete_param", "q")
    ac_extra = resolve_extra_params(cfg.get("autocomplete_extra_params", {}), args.store, args.lang)
    ac_path = cfg.get("autocomplete_result_path", "data")
    ac_headers = cfg.get("autocomplete_headers", {})

    data = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    scenarios = data["scenarios"] if isinstance(data, dict) else data
    if args.limit:
        scenarios = scenarios[: args.limit]
    print(f"As-Is search      : {search_api}")
    print(f"As-Is autocomplete: {ac_api}")
    print(f"Số query: {len(scenarios)} | throttle {args.sleep_ms}ms\n")

    def call_backoff(url, method, headers, params=None, body=None):
        delay = 2.0
        for i in range(args.max_tries):
            try:
                return call_api(url, method, headers, params, body)
            except ApiError:
                if i == args.max_tries - 1:
                    raise
                time.sleep(delay)
                delay = min(delay * 1.8, 15)

    out = []
    n_err_s = n_err_a = n_zero = 0
    t0 = time.time()
    for i, sc in enumerate(scenarios):
        q = sc["query"]
        row = {"test_id": sc.get("test_id"), "query": q, "dimension": sc.get("dimension"),
               "source_batch": sc.get("source_batch")}
        # --- search ---
        try:
            params, body = build_request(s_method, s_param, q, s_extra)
            payload, lat = call_backoff(search_api, s_method, s_headers, params, body)
            items = get_nested(payload, s_path) if "." in s_path else payload.get(s_path)
            items = items if isinstance(items, list) else []
            # Giữ cả `price`: cache As-Is của compare_results.py hiển thị giá ở
            # panel As-Is, bỏ đi thì panel hiện "0 đ" trông như dữ liệu hỏng.
            row["search_results"] = [
                {"rank": j + 1, "sku": str(it.get("sku") or it.get("id") or ""),
                 "name": it.get("name", ""), "price": it.get("price")}
                for j, it in enumerate(items)
            ]
            row["search_count"] = len(items)
            row["search_total_before_cap"] = (payload.get("data") or {}).get("total_items") if isinstance(payload, dict) else None
            row["search_latency_ms"] = lat
            row["search_error"] = None
            if not items:
                n_zero += 1
        except ApiError as e:
            row.update({"search_results": [], "search_count": 0, "search_total_before_cap": None,
                        "search_latency_ms": None, "search_error": str(e)})
            n_err_s += 1
        # --- autocomplete ---
        if ac_api:
            try:
                p2, b2 = build_request(ac_method, ac_param, q, ac_extra)
                pay2, lat2 = call_backoff(ac_api, ac_method, ac_headers, p2, b2)
                sugg = get_nested(pay2, ac_path) if "." in ac_path else pay2.get(ac_path)
                sugg = sugg if isinstance(sugg, list) else []
                # response As-Is chỉ là mảng STRING tên sản phẩm
                row["autocomplete_suggestions"] = [
                    {"rank": j + 1, "text": (s if isinstance(s, str) else str(s.get("text", "")))}
                    for j, s in enumerate(sugg)
                ]
                row["autocomplete_count"] = len(sugg)
                row["autocomplete_latency_ms"] = lat2
                row["autocomplete_error"] = None
            except ApiError as e:
                row.update({"autocomplete_suggestions": [], "autocomplete_count": 0,
                            "autocomplete_latency_ms": None, "autocomplete_error": str(e)})
                n_err_a += 1
        out.append(row)
        if args.sleep_ms:
            time.sleep(args.sleep_ms / 1000)
        if (i + 1) % args.progress_every == 0 or (i + 1) == len(scenarios):
            el = time.time() - t0
            rate = (i + 1) / el if el else 0
            eta = (len(scenarios) - i - 1) / rate / 60 if rate else 0
            print(f"  ... {i+1}/{len(scenarios)}, {el:.0f}s, {rate:.2f} q/s, còn ~{eta:.0f} phút "
                  f"(lỗi search={n_err_s}, lỗi ac={n_err_a}, zero-result={n_zero})")

    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    lat_s = sorted(r["search_latency_ms"] for r in out if r.get("search_latency_ms") is not None)
    lat_a = sorted(r["autocomplete_latency_ms"] for r in out if r.get("autocomplete_latency_ms") is not None)

    def pct(arr, p):
        if not arr:
            return None
        k = max(0, min(len(arr) - 1, int(round((p / 100) * len(arr))) - 1))
        return arr[k]

    payload = {
        "generatedDate": time.strftime("%Y-%m-%d"),
        "crawledAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "system": "As-Is (lottemart.vn production)",
        "searchApi": search_api,
        "autocompleteApi": ac_api,
        "searchPageLimit": s_extra.get("limit"),
        "autocompleteLimit": ac_extra.get("limit"),
        "totalQueries": len(out),
        "errors": {"search": n_err_s, "autocomplete": n_err_a},
        "zeroResultQueries": n_zero,
        "latencySummary": {
            "search": {"count": len(lat_s), "avg": round(sum(lat_s) / len(lat_s), 1) if lat_s else None,
                       "p50": pct(lat_s, 50), "p90": pct(lat_s, 90), "p95": pct(lat_s, 95), "p99": pct(lat_s, 99),
                       "min": lat_s[0] if lat_s else None, "max": lat_s[-1] if lat_s else None},
            "autocomplete": {"count": len(lat_a), "avg": round(sum(lat_a) / len(lat_a), 1) if lat_a else None,
                             "p50": pct(lat_a, 50), "p90": pct(lat_a, 90), "p95": pct(lat_a, 95), "p99": pct(lat_a, 99),
                             "min": lat_a[0] if lat_a else None, "max": lat_a[-1] if lat_a else None},
        },
        "scenarios": out,
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    el = time.time() - t0
    print(f"\nXong ({el/60:.0f} phút). -> {dest}")
    print(f"  lỗi search={n_err_s}, lỗi autocomplete={n_err_a}, query 0 kết quả={n_zero}")
    print(f"  search  latency: avg={payload['latencySummary']['search']['avg']}ms "
          f"P90={payload['latencySummary']['search']['p90']} P95={payload['latencySummary']['search']['p95']} "
          f"P99={payload['latencySummary']['search']['p99']}")
    print(f"  autocomplete   : avg={payload['latencySummary']['autocomplete']['avg']}ms "
          f"P90={payload['latencySummary']['autocomplete']['p90']} P95={payload['latencySummary']['autocomplete']['p95']}")


if __name__ == "__main__":
    main()
