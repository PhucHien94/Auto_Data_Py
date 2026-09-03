#!/usr/bin/env python3
"""
Re-call the live search API for only the scenarios that failed (api_error is
set) in a JSON file produced by export_actual_search_results.py, and patch
those entries in place - so a transient server-side blip (e.g. an HTTP 500
streak) doesn't require re-running an entire 1000-row batch.

Usage:
  python scripts/automation/retry_failed_actual.py \
    --file SmartSearch/test_data/json/actual/NSG_ActualData_1000-2000_20260827.json \
    --env dev --headed-login
"""
import argparse
import json
import sys
import time
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from lib_search_client import (call_api, ApiError, load_env_config, resolve_headers,  # noqa: E402
                                resolve_template, resolve_extra_params, build_request,
                                preflight_check, capture_cookie_via_headed_login)
from export_actual_search_results import extract_products  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", required=True, help="the *_ActualData_*.json file to patch in place")
    p.add_argument("--env")
    p.add_argument("--search-api")
    p.add_argument("--lang")
    p.add_argument("--header", action="append")
    p.add_argument("--auth-header-name")
    p.add_argument("--headed-login", action="store_true")
    p.add_argument("--console-url", default="https://dev-console.martonline.lotte.vn/")
    p.add_argument("--login-wait-seconds", type=int, default=180)
    p.add_argument("--page-size", type=int, default=50)
    p.add_argument("--sleep-ms", type=int, default=100, help="pause between retry calls (default 100ms - a bit gentler)")
    p.add_argument("--skip-preflight", action="store_true")
    args = p.parse_args()

    path = Path(args.file)
    data = json.loads(path.read_text(encoding="utf-8"))
    failed = [(i, s) for i, s in enumerate(data["scenarios"]) if s.get("api_error")]
    if not failed:
        print("Không có scenario nào bị lỗi trong file này - không cần retry.")
        return
    print(f"Tìm thấy {len(failed)} scenario bị lỗi trong {path.name}, sẽ retry.")

    cfg = load_env_config(args.env)
    store = data.get("store") or cfg.get("store") or "nsg"
    lang = args.lang or cfg.get("lang", "vi")

    search_api = resolve_template(args.search_api or cfg.get("search_api"), store, lang)
    if not search_api:
        raise SystemExit("thiếu search_api - dùng --env dev hoặc truyền --search-api")
    method = cfg.get("search_method") or cfg.get("method", "GET")
    param = cfg.get("search_param", "q")
    extra_params = resolve_extra_params(cfg.get("search_extra_params", {}), store, lang)
    extra_params = {**extra_params, "pageSize": args.page_size}
    result_path = cfg.get("search_result_path", "results")
    auth_header_name = args.auth_header_name or cfg.get("auth_header_name", "Authorization")
    auth_header_env = cfg.get("auth_header_env")

    if args.headed_login:
        if not auth_header_env:
            raise SystemExit("--headed-login cần --env có khai báo auth_header_env (VD --env dev)")
        print(f"Mở trình duyệt thật tại {args.console_url} - hãy đăng nhập tay (username/password rồi mã 2FA).")

        def _on_tick(elapsed, is_logged_in):
            print(f"  ... {elapsed}s / {args.login_wait_seconds}s, logged_in={is_logged_in}")

        import os
        captured, warnings = capture_cookie_via_headed_login(
            args.console_url, wait_seconds=args.login_wait_seconds, on_tick=_on_tick)
        for w in warnings:
            print(f"[warning] {w}")
        if not captured:
            raise SystemExit("Không capture được cookie.")
        os.environ[auth_header_env] = captured
        print(f"Đã capture session cookie ({len(captured)} ký tự).")

    headers = resolve_headers(args.header, auth_header_env, auth_header_name)
    headers = {**headers, **cfg.get("search_headers", {})}

    if not args.skip_preflight:
        print("Preflight...")
        params, body = build_request(method, param, "test", extra_params)
        try:
            preflight_check(search_api, method, headers, params, body, required_keys=(result_path,))
        except ApiError as e:
            raise SystemExit(str(e))
        print("Preflight OK.")

    n_fixed = 0
    n_still_failed = 0
    t0 = time.time()
    for j, (i, sc) in enumerate(failed):
        query = sc["query"]
        try:
            params, body = build_request(method, param, query, extra_params)
            payload, latency_ms = call_api(search_api, method, headers, params, body)
            products = extract_products(payload, result_path)
            search_results = [
                {"rank": k + 1, **(item if isinstance(item, dict) else {"sku": str(item)})}
                for k, item in enumerate(products)
            ]
            response_meta = {k: v for k, v in payload.items() if k != result_path} if isinstance(payload, dict) else {}
            data["scenarios"][i]["search_results"] = search_results
            data["scenarios"][i]["response_meta"] = response_meta
            data["scenarios"][i]["api_latency_ms"] = latency_ms
            data["scenarios"][i]["api_error"] = None
            n_fixed += 1
        except ApiError as e:
            data["scenarios"][i]["api_error"] = str(e)
            n_still_failed += 1
        if args.sleep_ms:
            time.sleep(args.sleep_ms / 1000)
        if (j + 1) % 50 == 0 or (j + 1) == len(failed):
            elapsed = time.time() - t0
            print(f"  ... {j + 1}/{len(failed)}, {elapsed:.0f}s, fixed={n_fixed}, still_failed={n_still_failed}")

    data["retryPatchedDate"] = time.strftime("%Y-%m-%d")
    data["retryPatchedCount"] = len(failed)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nXong. Đã sửa {n_fixed}/{len(failed)}, còn lỗi {n_still_failed}. Đã ghi lại {path}")


if __name__ == "__main__":
    main()
