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
                                preflight_check, capture_cookie_via_headed_login, get_nested)
from run_batch_test import discover_batches, select_batches, load_batch, StuckResultGuard, DegradedSessionError  # noqa: E402

DEFAULT_OUT_DIR = "SmartSearch/test_data/json/actual"


def extract_products(payload, result_path):
    """Full product list (not just id/sku) so nothing the live API returned is
    thrown away - unlike lib_search_client.extract_id_list (used for scoring),
    which only pulls a flat id list. result_path may be a dotted path
    ("data.items") for a nested response body (e.g. the legacy lottemart.vn
    search API)."""
    items = None
    if result_path:
        found = get_nested(payload, result_path) if "." in result_path else (
            payload.get(result_path) if isinstance(payload, dict) else None)
        if isinstance(found, list):
            items = found
    if items is None:
        for k in ("results", "items", "hits", "data", "products"):
            if isinstance(payload, dict) and isinstance(payload.get(k), list):
                items = payload[k]
                break
    return items if items is not None else []


def run_export(scenarios, search_api, method, param, extra_params, result_path, headers,
                page_size, limit, sleep_ms, stuck_streak_limit, progress_every=50,
                recommendations_api=None, rec_method="POST", rec_result_path="products",
                rec_headers=None, rec_size=20, rec_trigger_max_results=20, store=None, lang="vi",
                autocomplete_api=None, ac_method="GET", ac_param="q", ac_extra_params=None,
                ac_result_path="suggestions", ac_headers=None):
    extra_params = {**extra_params, "pageSize": page_size}
    stuck_guard = StuckResultGuard(streak_limit=stuck_streak_limit)
    out_scenarios = []
    n_recommendation_calls = 0
    n_autocomplete_calls = 0
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

        # Recommendations backfill (added 2026-09-07): when the real search
        # already returned <=N products, the product also calls a separate
        # recommendations API to pad the results - mirrors that here so the
        # captured Actual data matches what a real user would see. Only
        # triggered when the search call itself succeeded (error is None);
        # excludeSkus is the search results' own SKUs so recommendations
        # don't just repeat what's already shown.
        recommendation_results = []
        recommendation_triggered = False
        recommendation_error = None
        recommendation_latency_ms = None
        if recommendations_api and error is None and len(search_results) <= rec_trigger_max_results:
            recommendation_triggered = True
            n_recommendation_calls += 1
            exclude_skus = list(dict.fromkeys(str(s) for s in skus_for_guard if s))
            rec_body = {
                "query": query, "storeId": store, "lang": lang,
                "size": rec_size, "excludeSkus": exclude_skus, "filters": {},
            }
            try:
                rec_payload, recommendation_latency_ms = call_api(
                    recommendations_api, rec_method, rec_headers or {}, None, rec_body)
                rec_products = extract_products(rec_payload, rec_result_path)
                recommendation_results = [
                    {"rank": j + 1, **(item if isinstance(item, dict) else {"sku": str(item)})}
                    for j, item in enumerate(rec_products)
                ]
            except ApiError as e:
                recommendation_error = str(e)

        # Autocomplete (added 2026-09-07 per user's curl): a SEPARATE endpoint
        # from search - GET ?q=<query>&limit=N - called for EVERY scenario
        # (không điều kiện, khác recommendations). Response carries two
        # independent lists: "suggestions" (keyword gợi ý: text/type/hitCount)
        # and "products" (preview sản phẩm ngay trong dropdown) - cả hai đều
        # được lưu lại vì UI thật hiển thị cả hai.
        autocomplete_suggestions = []
        autocomplete_products = []
        autocomplete_error = None
        autocomplete_latency_ms = None
        if autocomplete_api:
            n_autocomplete_calls += 1
            ac_params, ac_body = build_request(ac_method, ac_param, query, ac_extra_params or {})
            try:
                ac_payload, autocomplete_latency_ms = call_api(
                    autocomplete_api, ac_method, ac_headers or {}, ac_params, ac_body)
                raw_suggestions = extract_products(ac_payload, ac_result_path)
                autocomplete_suggestions = [
                    {"rank": j + 1, **(item if isinstance(item, dict) else {"text": str(item)})}
                    for j, item in enumerate(raw_suggestions)
                ]
                raw_ac_products = (ac_payload.get("products") or []) if isinstance(ac_payload, dict) else []
                autocomplete_products = [
                    {"rank": j + 1, **(item if isinstance(item, dict) else {"sku": str(item)})}
                    for j, item in enumerate(raw_ac_products)
                ]
            except ApiError as e:
                autocomplete_error = str(e)

        out_scenarios.append({
            "test_id": sc.get("test_id"),
            # Thời điểm GỌI API cho CHÍNH scenario này (2026-09-17). Trước đây
            # file chỉ có generatedDate ở cấp file, mà một lần chạy kéo dài ~40
            # phút và file cuối còn là bản ghép nhiều lần chạy khác nhau - nên
            # không truy được keyword nào gọi lúc nào. Kết quả hệ thống thật
            # biến động tới 20,6% trong cùng một ngày, nên mốc này cần thiết
            # khi đối chiếu về sau.
            "fetched_at": datetime.now().isoformat(timespec="seconds"),
            "query": query,
            "dimension": sc.get("dimension"),
            "note": sc.get("note"),
            "route": sc.get("route"),
            "search_results": search_results,
            "response_meta": response_meta,
            "api_latency_ms": latency_ms,
            "api_error": error,
            "recommendation_triggered": recommendation_triggered,
            "recommendation_results": recommendation_results,
            "recommendation_count": len(recommendation_results),
            "recommendation_api_latency_ms": recommendation_latency_ms,
            "recommendation_api_error": recommendation_error,
            "autocomplete_suggestions": autocomplete_suggestions,
            "autocomplete_suggestion_count": len(autocomplete_suggestions),
            "autocomplete_products": autocomplete_products,
            "autocomplete_product_count": len(autocomplete_products),
            "autocomplete_api_latency_ms": autocomplete_latency_ms,
            "autocomplete_api_error": autocomplete_error,
        })
        if sleep_ms:
            time.sleep(sleep_ms / 1000)
        if (i + 1) % progress_every == 0 or (i + 1) == n:
            elapsed = time.time() - t0
            rate = (i + 1) / elapsed if elapsed else 0
            print(f"  ... {i + 1}/{n}, {elapsed:.0f}s, {rate:.2f} query/s "
                  f"(recommendation: {n_recommendation_calls}, autocomplete: {n_autocomplete_calls})")
    return out_scenarios


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--batch", required=True, help='"all", or range strings e.g. "0-1000" or "0-1000,2000-3000"')
    p.add_argument("--batches-dir", default="SmartSearch/test_data/json/batches")
    p.add_argument("--store-prefix", default="NSG",
                    help='which <PREFIX>_ExpectedData_<range>_<date>.json batches to discover (default NSG; '
                         'use WLE for WLE_ExpectedData_*.json) - NSG and WLE can share the same range string '
                         '(e.g. both have "0-1000"), so this must be set correctly to avoid picking the wrong store.')
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
    p.add_argument("--no-auth", action="store_true",
                    help="call the API directly with NO auth header at all - ignores DEV_SEARCH_COOKIE/"
                         "auth_header_env even if set, no --headed-login needed. Per user confirmation "
                         "(2026-08-28), the dev-gateway endpoint answers without any auth header. "
                         "Mutually exclusive with --headed-login.")
    p.add_argument("--page-size", type=int, default=50, help="pageSize sent to the search API (default 50)")
    p.add_argument("--limit", type=int, help="cap scenarios per batch, for a smoke run")
    p.add_argument("--sleep-ms", type=int, default=0, help="pause between calls, to stay gentle on the WAF")
    p.add_argument("--stuck-streak-limit", type=int, default=8)
    p.add_argument("--skip-preflight", action="store_true")
    p.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    p.add_argument("--skip-recommendations", action="store_true",
                    help="không gọi thêm API recommendations kể cả khi actual search result <= threshold")
    p.add_argument("--recommendations-api", help="override recommendations_api trong config/environments.yaml")
    p.add_argument("--recommendation-size", type=int,
                    help="override recommendation_size (tham số size trong body, default lấy từ config, 20)")
    p.add_argument("--recommendation-trigger-max-results", type=int,
                    help="chỉ gọi recommendations khi actual search_results <= N (default lấy từ config, 20)")
    p.add_argument("--skip-autocomplete", action="store_true",
                    help="không gọi API autocomplete (mặc định gọi cho mọi scenario)")
    p.add_argument("--autocomplete-api", help="override autocomplete_api trong config/environments.yaml")
    p.add_argument("--autocomplete-limit", type=int,
                    help="override limit của autocomplete (default lấy từ config autocomplete_extra_params, 8)")
    args = p.parse_args()

    cfg = load_env_config(args.env)
    available = discover_batches(args.batches_dir, store_prefix=args.store_prefix)
    batches = select_batches(args.batch, available)
    print(f"Batch được chọn: {[b for b, _ in batches]}")

    first_data = load_batch(batches[0][1])
    store = args.store or first_data.get("store") or cfg.get("store") or "nsg"
    # Ngôn ngữ gửi lên API: --lang thắng tất cả; nếu không truyền thì lấy trường
    # "lang" ghi ngay trong file batch (bộ ko/en sinh bởi build_history_testdata.py
    # có sẵn trường này), cuối cùng mới đến mặc định của --env.
    # Lý do để trong file: người chạy không phải nhớ "bộ ko thì kèm --lang ko" -
    # quên một lần là cả bộ tiếng Hàn bị gọi bằng lang=vi mà log vẫn xanh.
    lang = args.lang or first_data.get("lang") or cfg.get("lang", "vi")

    search_api = resolve_template(args.search_api or cfg.get("search_api"), store, lang)
    if not search_api:
        raise SystemExit("thiếu search_api - dùng --env dev hoặc truyền --search-api")

    method = cfg.get("search_method") or cfg.get("method", "GET")
    param = cfg.get("search_param", "q")
    extra_params = resolve_extra_params(cfg.get("search_extra_params", {}), store, lang)
    result_path = cfg.get("search_result_path", "results")
    auth_header_name = args.auth_header_name or cfg.get("auth_header_name", "Authorization")
    auth_header_env = cfg.get("auth_header_env")

    if args.no_auth and args.headed_login:
        raise SystemExit("--no-auth và --headed-login xung đột nhau - chọn 1 trong 2 chế độ auth.")

    if args.no_auth:
        print("Chế độ --no-auth: gọi thẳng API, không kèm cookie/token đăng nhập nào.")
        auth_header_env = None
    elif args.headed_login:
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

    base_headers = resolve_headers(args.header, auth_header_env, auth_header_name)
    headers = {**base_headers, **cfg.get("search_headers", {})}

    recommendations_api = None
    rec_method = cfg.get("recommendation_method", "POST")
    rec_result_path = cfg.get("recommendation_result_path", "products")
    rec_size = args.recommendation_size or cfg.get("recommendation_size", 20)
    rec_trigger_max_results = args.recommendation_trigger_max_results
    if rec_trigger_max_results is None:
        rec_trigger_max_results = cfg.get("recommendation_trigger_max_results", 20)
    rec_headers = {**base_headers, **cfg.get("recommendation_headers", {})}
    if not args.skip_recommendations:
        recommendations_api = resolve_template(
            args.recommendations_api or cfg.get("recommendations_api"), store, lang)
        if recommendations_api:
            print(f"Recommendations API: {recommendations_api} (kích hoạt khi actual search result <= {rec_trigger_max_results} sản phẩm)")
        else:
            print("[cảnh báo] Không có recommendations_api trong config - bỏ qua bước gọi recommendations.")

    autocomplete_api = None
    ac_method = cfg.get("autocomplete_method", "GET")
    ac_param = cfg.get("autocomplete_param", "q")
    ac_result_path = cfg.get("autocomplete_result_path", "suggestions")
    ac_extra_params = resolve_extra_params(cfg.get("autocomplete_extra_params", {}), store, lang)
    if args.autocomplete_limit:
        ac_extra_params = {**ac_extra_params, "limit": args.autocomplete_limit}
    ac_headers = {**base_headers, **cfg.get("autocomplete_headers", {})}
    if not args.skip_autocomplete:
        autocomplete_api = resolve_template(
            args.autocomplete_api or cfg.get("autocomplete_api"), store, lang)
        if autocomplete_api:
            print(f"Autocomplete API: {autocomplete_api} (gọi cho mọi scenario, limit={ac_extra_params.get('limit', 8)})")
        else:
            print("[cảnh báo] Không có autocomplete_api trong config - bỏ qua bước gọi autocomplete.")

    if not args.skip_preflight:
        print("Preflight: kiểm tra đăng nhập/kết nối bằng 1 request thật trước khi chạy cả batch...")
        preflight_query = cfg.get("preflight_query", "test")
        params, body = build_request(method, param, preflight_query, {**extra_params, "pageSize": args.page_size})
        try:
            preflight_check(search_api, method, headers, params, body, required_keys=(result_path,))
        except ApiError as e:
            raise SystemExit(str(e))
        print("Preflight OK - bắt đầu chạy batch.")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    t0 = time.time()
    for batch_range, batch_path in batches:
        data = load_batch(batch_path)
        scenarios = data.get("scenarios", [])
        # Chạy nhiều batch khác ngôn ngữ trong một lệnh thì mỗi batch phải dựng
        # lại URL theo lang của chính nó.
        batch_lang = args.lang or data.get("lang") or lang
        if batch_lang != lang:
            search_api = resolve_template(args.search_api or cfg.get("search_api"), store, batch_lang)
            extra_params = resolve_extra_params(cfg.get("search_extra_params", {}), store, batch_lang)
            if recommendations_api:
                recommendations_api = resolve_template(
                    args.recommendations_api or cfg.get("recommendations_api"), store, batch_lang)
            if autocomplete_api:
                autocomplete_api = resolve_template(
                    args.autocomplete_api or cfg.get("autocomplete_api"), store, batch_lang)
            lang = batch_lang
        print(f"Batch {batch_range} ({Path(batch_path).name}): {len(scenarios)} scenario, "
              f"lang={lang}, gọi API thật {search_api}")
        try:
            out_scenarios = run_export(
                scenarios, search_api, method, param, extra_params, result_path, headers,
                args.page_size, args.limit, args.sleep_ms, args.stuck_streak_limit,
                recommendations_api=recommendations_api, rec_method=rec_method, rec_result_path=rec_result_path,
                rec_headers=rec_headers, rec_size=rec_size, rec_trigger_max_results=rec_trigger_max_results,
                store=store, lang=lang,
                autocomplete_api=autocomplete_api, ac_method=ac_method, ac_param=ac_param,
                ac_extra_params=ac_extra_params, ac_result_path=ac_result_path, ac_headers=ac_headers)
        except DegradedSessionError as e:
            raise SystemExit(f"\nDừng export: {e}")

        n_rec_triggered = sum(1 for s in out_scenarios if s["recommendation_triggered"])
        n_ac_ok = sum(1 for s in out_scenarios if s["autocomplete_suggestions"])
        n_ac_err = sum(1 for s in out_scenarios if s["autocomplete_api_error"])
        out_data = {
            "generatedDate": datetime.now().strftime("%Y-%m-%d"),
            "store": store,
            "batchRange": batch_range,
            "lang": lang,
            "totalScenarios": len(out_scenarios),
            "sourceExpectedFile": Path(batch_path).name,
            "apiEndpoint": search_api,
            "recommendationsApiEndpoint": recommendations_api,
            "recommendationTriggerMaxResults": rec_trigger_max_results,
            "autocompleteApiEndpoint": autocomplete_api,
            "autocompleteLimit": ac_extra_params.get("limit") if autocomplete_api else None,
            "scenarios": out_scenarios,
        }
        out_name = f"{store.upper()}_ActualData_{batch_range}_{ts}.json"
        out_path = out_dir / out_name
        with out_path.open("w", encoding="utf-8") as fh:
            json.dump(out_data, fh, ensure_ascii=False, indent=2)
        n_errors = sum(1 for s in out_scenarios if s["api_error"])
        print(f"  -> {out_path} ({len(out_scenarios)} scenario, lỗi search={n_errors}, "
              f"recommendation kích hoạt={n_rec_triggered}, autocomplete có gợi ý={n_ac_ok}, lỗi autocomplete={n_ac_err})")

    elapsed = time.time() - t0
    print(f"\nXong ({elapsed:.0f}s). Kết quả actual tại: {out_dir}")


if __name__ == "__main__":
    main()
