#!/usr/bin/env python3
"""
Call the LIVE search API for every scenario in one or more
NSG_ExpectedData_<range>_<date>.json batches (under SmartSearch/test_data/json/batches/)
and export the actual results into a JSON file shaped like the *expected* files
(generatedDate / store / batchRange / totalScenarios / scenarios[...]), so the two
can be diffed directly (e.g. by the "Search Result Comparator" Artifact) without a
format conversion step.

Unlike run_batch_test.py (which scores expected-vs-actual into an Excel/HTML
dashboard), this script does NOT score anything - it only captures what the live
API actually returned, one scenario at a time, in expected-json shape. Reuses the
same auth/session machinery (lib_search_client) as run_batch_test.py: no fixed
bearer token exists for the dev gateway (WAF session cookie only), so you must log
in first, either via --headed-login (a real, visible browser you log into by hand)
or by exporting a freshly copied Cookie header into the env var named by
config/environments.yaml's auth_header_env (DEV_SEARCH_COOKIE for --env dev).

Usage:
  # smoke test - 20 scenarios from batch 0-1000, browser login
  python scripts/automation/export_actual_search_results.py --env dev --batch 0-1000 \
    --headed-login --limit 20

  # full batch, cookie already in DEV_SEARCH_COOKIE
  python scripts/automation/export_actual_search_results.py --env dev --batch 0-1000

  # every batch found under SmartSearch/test_data/json/batches/
  python scripts/automation/export_actual_search_results.py --env dev --batch all --headed-login
"""
import argparse
import glob
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from lib_search_client import (call_api, ApiError, load_env_config, resolve_headers,  # noqa: E402
                                resolve_template, resolve_extra_params, build_request,
                                preflight_check, capture_cookie_via_headed_login)
from run_batch_test import discover_batches, select_batches, load_batch, StuckResultGuard, DegradedSessionError  # noqa: E402

DEFAULT_OUT_DIR = "SmartSearch/test_data/json/actual"


def extract_products(payload, result_path):
    """Full product list (not just id/sku) so nothing the live API returned is
    thrown away - unlike lib_search_client.extract_id_list (used for scoring),
    which only pulls a flat id list."""
    items = None
    if result_path and isinstance(payload, dict) and isinstance(payload.get(result_path), list):
        items = payload[result_path]
    else:
        for k in ("results", "items", "hits", "data", "products"):
            if isinstance(payload, dict) and isinstance(payload.get(k), list):
                items = payload[k]
                break
    return items if items is not None else []


def run_export(scenarios, search_api, method, param, extra_params, result_path, headers,
                page_size, limit, sleep_ms, stuck_streak_limit, progress_every=50):
    extra_params = {**extra_params, "pageSize": page_size}
    stuck_guard = StuckResultGuard(streak_limit=stuck_streak_limit)
    out_scenarios = []
    t0 = time.time()
    n = min(limit, len(scenarios)) if limit else len(scenarios)
    for i, sc in enumerate(scenarios[:n]):
        query = sc["query"]
        try:
            params, body = build_request(method, param, query, extra_params)
            payload, latency_ms = call_api(search_api, method, headers, params, body)
            products = extract_products(payload, result_path)
            search_results = [
                {"rank": j + 1, **(item if isinstance(item, dict) else {"sku": str(item)})}
                for j, item in enumerate(products)
            ]
            response_meta = {k: v for k, v in payload.items() if k != result_path} if isinstance(payload, dict) else {}
            error = None
            skus_for_guard = [r.get("sku") or r.get("productId") or r.get("id") for r in search_results]
        except ApiError as e:
            search_results, response_meta, latency_ms, error = [], {}, None, str(e)
            skus_for_guard = []

        stuck_guard.check(query, skus_for_guard)

        out_scenarios.append({
            "test_id": sc.get("test_id"),
            "query": query,
            "dimension": sc.get("dimension"),
            "note": sc.get("note"),
            "route": sc.get("route"),
            "search_results": search_results,
            "response_meta": response_meta,
            "api_latency_ms": latency_ms,
            "api_error": error,
        })
        if sleep_ms:
            time.sleep(sleep_ms / 1000)
        if (i + 1) % progress_every == 0 or (i + 1) == n:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed else 0
            print(f"  ... {i + 1}/{n}, {elapsed:.0f}s, {rate:.2f} query/s")
    return out_scenarios


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--batch", required=True, help='"all", or range strings e.g. "0-1000" or "0-1000,2000-3000"')
    p.add_argument("--batches-dir", default="SmartSearch/test_data/json/batches")
    p.add_argument("--env")
    p.add_argument("--search-api")
    p.add_argument("--lang")
    p.add_argument("--store", help='defaults to the batch file\'s own "store" field')
    p.add_argument("--header", action="append", help="Key:Value, repeatable")
    p.add_argument("--auth-header-name")
    p.add_argument("--headed-login", action="store_true",
                    help="open a real, visible browser (Playwright) so you log in by hand, then capture "
                         "the session cookie automatically. Requires `pip install playwright` + "
                         "`playwright install chromium`. Never automates the login itself.")
    p.add_argument("--console-url", default="https://dev-console.martonline.lotte.vn/")
    p.add_argument("--login-wait-seconds", type=int, default=180)
    p.add_argument("--page-size", type=int, default=50, help="pageSize sent to the search API (default 50)")
    p.add_argument("--limit", type=int, help="cap scenarios per batch, for a smoke run")
    p.add_argument("--sleep-ms", type=int, default=0, help="pause between calls, to stay gentle on the WAF")
    p.add_argument("--stuck-streak-limit", type=int, default=8)
    p.add_argument("--skip-preflight", action="store_true")
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    args = p.parse_args()

    cfg = load_env_config(args.env)
    available = discover_batches(args.batches_dir)
    batches = select_batches(args.batch, available)
    print(f"Batch được chọn: {[b for b, _ in batches]}")

    first_data = load_batch(batches[0][1])
    store = args.store or first_data.get("store") or cfg.get("store") or "nsg"
    lang = args.lang or cfg.get("lang", "vi")

    search_api = resolve_template(args.search_api or cfg.get("search_api"), store, lang)
    if not search_api:
        raise SystemExit("thiếu search_api - dùng --env dev hoặc truyền --search-api")

    method = cfg.get("search_method") or cfg.get("method", "GET")
    param = cfg.get("search_param", "q")
    extra_params = resolve_extra_params(cfg.get("search_extra_params", {}), store, lang)
    result_path = cfg.get("search_result_path", "results")
    auth_header_name = args.auth_header_name or cfg.get("auth_header_name", "Authorization")
    auth_header_env = cfg.get("auth_header_env")

    if args.headed_login:
        if not auth_header_env:
            raise SystemExit("--headed-login cần --env có khai báo auth_header_env (VD --env dev)")
        print(f"Mở trình duyệt thật tại {args.console_url} - hãy đăng nhập tay (username/password rồi mã 2FA).")
        print(f"Sẽ tự động chờ tối đa {args.login_wait_seconds}s, phát hiện đăng nhập xong qua nội dung trang.")

        def _on_tick(elapsed, is_logged_in):
            print(f"  ... {elapsed}s / {args.login_wait_seconds}s, logged_in={is_logged_in}")

        captured, login_warnings = capture_cookie_via_headed_login(
            args.console_url, wait_seconds=args.login_wait_seconds, on_tick=_on_tick)
        for w in login_warnings:
            print(f"[headed-login warning] {w}")
        if not captured:
            raise SystemExit("Không capture được cookie nào - trình duyệt có thể đã bị đóng sớm hoặc "
                              "console_url không đúng. Thử lại với --login-wait-seconds lớn hơn.")
        os.environ[auth_header_env] = captured
        print(f"Đã capture session cookie ({len(captured)} ký tự) từ browser thật, dùng cho tiến trình này - không lưu ra file nào.")

    headers = resolve_headers(args.header, auth_header_env, auth_header_name)
    headers = {**headers, **cfg.get("search_headers", {})}

    if not args.skip_preflight:
        print("Preflight: kiểm tra đăng nhập/kết nối bằng 1 request thật trước khi chạy cả batch...")
        params, body = build_request(method, param, "test", {**extra_params, "pageSize": args.page_size})
        try:
            preflight_check(search_api, method, headers, params, body, required_keys=(result_path,))
        except ApiError as e:
            raise SystemExit(str(e))
        print("Preflight OK - bắt đầu chạy batch.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d")

    t0 = time.time()
    for batch_range, batch_path in batches:
        data = load_batch(batch_path)
        scenarios = data.get("scenarios", [])
        print(f"Batch {batch_range} ({Path(batch_path).name}): {len(scenarios)} scenario, gọi API thật {search_api}")
        try:
            out_scenarios = run_export(
                scenarios, search_api, method, param, extra_params, result_path, headers,
                args.page_size, args.limit, args.sleep_ms, args.stuck_streak_limit)
        except DegradedSessionError as e:
            raise SystemExit(f"\nDừng export: {e}")

        out_data = {
            "generatedDate": datetime.now().strftime("%Y-%m-%d"),
            "store": store,
            "batchRange": batch_range,
            "totalScenarios": len(out_scenarios),
            "sourceExpectedFile": Path(batch_path).name,
            "apiEndpoint": search_api,
            "scenarios": out_scenarios,
        }
        out_name = f"{store.upper()}_ActualData_{batch_range}_{ts}.json"
        out_path = out_dir / out_name
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(out_data, fh, ensure_ascii=False, indent=2)
        n_errors = sum(1 for s in out_scenarios if s["api_error"])
        print(f"  -> {out_path} ({len(out_scenarios)} scenario, lỗi={n_errors})")

    elapsed = time.time() - t0
    print(f"\nXong ({elapsed:.0f}s). Kết quả actual tại: {out_dir}")


if __name__ == "__main__":
    main()
