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
    p.add_argument("--max-tries", type=int, default=6,
                    help="số lần thử lại tối đa cho MỖI call trước khi bỏ (default 6, có backoff giãn dần)")
    p.add_argument("--backoff-start-s", type=float, default=3.0,
                    help="thời gian chờ lần backoff đầu, giây (default 3.0, sau đó x1.5 mỗi lần, tối đa 15s)")
    p.add_argument("--skip-preflight", action="store_true")
    args = p.parse_args()

    path = Path(args.file)
    data = json.loads(path.read_text(encoding="utf-8"))
    # Mở rộng 2026-09-07: file Actual giờ có 3 loại call độc lập (search,
    # recommendations, autocomplete) nên mỗi loại có error field riêng và
    # phải retry riêng - trước đây script chỉ biết "api_error" (search), nên
    # lỗi recommendation/autocomplete không có đường nào sửa ngoài viết script
    # tạm mỗi lần.
    failed = [
        (i, s) for i, s in enumerate(data["scenarios"])
        if s.get("api_error") or s.get("recommendation_api_error") or s.get("autocomplete_api_error")
    ]
    if not failed:
        print("Không có scenario nào bị lỗi trong file này - không cần retry.")
        return
    n_s = sum(1 for _, s in failed if s.get("api_error"))
    n_r = sum(1 for _, s in failed if s.get("recommendation_api_error"))
    n_a = sum(1 for _, s in failed if s.get("autocomplete_api_error"))
    print(f"Tìm thấy {len(failed)} scenario bị lỗi trong {path.name} "
          f"(search={n_s}, recommendation={n_r}, autocomplete={n_a}), sẽ retry.")

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

    base_headers = resolve_headers(args.header, auth_header_env, auth_header_name)
    headers = {**base_headers, **cfg.get("search_headers", {})}

    # Endpoint/cấu hình cho 2 API bổ trợ (khớp export_actual_search_results.py)
    recommendations_api = resolve_template(cfg.get("recommendations_api"), store, lang)
    rec_method = cfg.get("recommendation_method", "POST")
    rec_result_path = cfg.get("recommendation_result_path", "products")
    rec_size = cfg.get("recommendation_size", 20)
    rec_headers = {**base_headers, **cfg.get("recommendation_headers", {})}
    autocomplete_api = resolve_template(cfg.get("autocomplete_api"), store, lang)
    ac_method = cfg.get("autocomplete_method", "GET")
    ac_param = cfg.get("autocomplete_param", "q")
    ac_result_path = cfg.get("autocomplete_result_path", "suggestions")
    ac_extra_params = resolve_extra_params(cfg.get("autocomplete_extra_params", {}), store, lang)
    ac_headers = {**base_headers, **cfg.get("autocomplete_headers", {})}

    def call_with_backoff(url, meth, hdrs, params=None, body=None):
        """Retry chính là để vượt qua 503 của WAF khi chạy batch dài, nên một
        lần gọi lại ngay lập tức thường vẫn 503 - phải giãn dần (3s, 4.5s,
        6.75s... tối đa 15s). Đây là lý do script cũ 'retry' vẫn để lại lỗi."""
        delay = args.backoff_start_s
        for attempt in range(args.max_tries):
            try:
                return call_api(url, meth, hdrs, params, body)
            except ApiError:
                if attempt == args.max_tries - 1:
                    raise
                time.sleep(delay)
                delay = min(delay * 1.5, 15)

    if not args.skip_preflight:
        print("Preflight...")
        params, body = build_request(method, param, "test", extra_params)
        try:
            preflight_check(search_api, method, headers, params, body, required_keys=(result_path,))
        except ApiError as e:
            raise SystemExit(str(e))
        print("Preflight OK.")

    rec_trigger_max = cfg.get("recommendation_trigger_max_results", 20)
    fixed = {"search": 0, "recommendation": 0, "autocomplete": 0}
    still = {"search": 0, "recommendation": 0, "autocomplete": 0}
    t0 = time.time()
    for j, (i, sc) in enumerate(failed):
        query = sc["query"]
        target = data["scenarios"][i]

        # --- 1) search ---
        if sc.get("api_error"):
            try:
                params, body = build_request(method, param, query, extra_params)
                payload, latency_ms = call_with_backoff(search_api, method, headers, params, body)
                products = extract_products(payload, result_path)
                search_results = [
                    {"rank": k + 1, **(item if isinstance(item, dict) else {"sku": str(item)})}
                    for k, item in enumerate(products)
                ]
                response_meta = {k: v for k, v in payload.items() if k != result_path} if isinstance(payload, dict) else {}
                target["search_results"] = search_results
                target["response_meta"] = response_meta
                target["api_latency_ms"] = latency_ms
                target["api_error"] = None
                # Search vừa có kết quả mới -> điều kiện gọi recommendations
                # (<=N sản phẩm) phải tính LẠI theo dữ liệu mới, không dùng
                # cờ cũ vốn được set khi search đang lỗi.
                if recommendations_api:
                    should = len(search_results) <= rec_trigger_max
                    target["recommendation_triggered"] = should
                    if should and not target.get("recommendation_results"):
                        target["recommendation_api_error"] = target.get("recommendation_api_error") or "cần gọi lại sau khi search được sửa"
                fixed["search"] += 1
            except ApiError as e:
                target["api_error"] = str(e)
                still["search"] += 1
            if args.sleep_ms:
                time.sleep(args.sleep_ms / 1000)

        # --- 2) recommendations ---
        if recommendations_api and target.get("recommendation_api_error") and target.get("recommendation_triggered"):
            skus = [r.get("sku") for r in (target.get("search_results") or []) if r.get("sku")]
            exclude = list(dict.fromkeys(str(s) for s in skus if s))
            rec_body = {"query": query, "storeId": store, "lang": lang,
                        "size": rec_size, "excludeSkus": exclude, "filters": {}}
            try:
                rec_payload, rec_latency = call_with_backoff(recommendations_api, rec_method, rec_headers, None, rec_body)
                rec_products = extract_products(rec_payload, rec_result_path)
                rec_results = [
                    {"rank": k + 1, **(item if isinstance(item, dict) else {"sku": str(item)})}
                    for k, item in enumerate(rec_products)
                ]
                target["recommendation_results"] = rec_results
                target["recommendation_count"] = len(rec_results)
                target["recommendation_api_latency_ms"] = rec_latency
                target["recommendation_api_error"] = None
                fixed["recommendation"] += 1
            except ApiError as e:
                target["recommendation_api_error"] = str(e)
                still["recommendation"] += 1
            if args.sleep_ms:
                time.sleep(args.sleep_ms / 1000)

        # --- 3) autocomplete ---
        if autocomplete_api and target.get("autocomplete_api_error"):
            ac_params, ac_body = build_request(ac_method, ac_param, query, ac_extra_params)
            try:
                ac_payload, ac_latency = call_with_backoff(autocomplete_api, ac_method, ac_headers, ac_params, ac_body)
                raw_sugg = extract_products(ac_payload, ac_result_path)
                target["autocomplete_suggestions"] = [
                    {"rank": k + 1, **(item if isinstance(item, dict) else {"text": str(item)})}
                    for k, item in enumerate(raw_sugg)
                ]
                target["autocomplete_suggestion_count"] = len(target["autocomplete_suggestions"])
                raw_prod = (ac_payload.get("products") or []) if isinstance(ac_payload, dict) else []
                target["autocomplete_products"] = [
                    {"rank": k + 1, **(item if isinstance(item, dict) else {"sku": str(item)})}
                    for k, item in enumerate(raw_prod)
                ]
                target["autocomplete_product_count"] = len(target["autocomplete_products"])
                target["autocomplete_api_latency_ms"] = ac_latency
                target["autocomplete_api_error"] = None
                fixed["autocomplete"] += 1
            except ApiError as e:
                target["autocomplete_api_error"] = str(e)
                still["autocomplete"] += 1
            if args.sleep_ms:
                time.sleep(args.sleep_ms / 1000)

        if (j + 1) % 20 == 0 or (j + 1) == len(failed):
            elapsed = time.time() - t0
            print(f"  ... {j + 1}/{len(failed)}, {elapsed:.0f}s, fixed={fixed}, still_failed={still}")

    data["retryPatchedDate"] = time.strftime("%Y-%m-%d")
    data["retryPatchedCount"] = len(failed)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    total_fixed = sum(fixed.values())
    total_still = sum(still.values())
    print(f"\nXong. Đã sửa {total_fixed} lỗi ({fixed}), còn lỗi {total_still} ({still}). Đã ghi lại {path}")


if __name__ == "__main__":
    main()
