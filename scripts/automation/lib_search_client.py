#!/usr/bin/env python3
"""HTTP client + environment-config helpers shared by the golden-set/batch runners
(run_autoscript.py, run_batch_test.py). Kept dependency-free beyond PyYAML (stdlib
urllib only, matching runner_text_search.py) - except capture_cookie_via_headed_login,
which needs Playwright, imported lazily so it's only required when --headed-login
is actually used.
"""
import json
import os
import ssl
import time
from pathlib import Path
from urllib import parse, request


class ApiError(Exception):
    pass


def parse_headers(header_list):
    headers = {}
    for h in header_list or []:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()
    return headers


def load_env_config(env_name, config_path="config/environments.yaml"):
    if not env_name:
        return {}
    import yaml
    path = Path(config_path)
    if not path.exists():
        raise SystemExit(f"--env given but {config_path} not found")
    with path.open("r", encoding="utf-8") as fh:
        all_envs = yaml.safe_load(fh)
    if env_name not in all_envs:
        raise SystemExit(f"environment {env_name!r} not found in {config_path}")
    return all_envs[env_name]


def resolve_headers(cli_headers, auth_header_env, auth_header_name="Authorization"):
    headers = parse_headers(cli_headers)
    if auth_header_env and auth_header_env in os.environ and auth_header_name not in headers:
        headers[auth_header_name] = os.environ[auth_header_env]
    return headers


def resolve_template(value, store, lang):
    """Fill {store}/{lang} placeholders. Only touches strings - dicts/lists/other
    values (e.g. a JSON body's "filters": {}) are returned unchanged."""
    if isinstance(value, str):
        return value.replace("{store}", store).replace("{lang}", lang)
    return value


def resolve_extra_params(extra, store, lang):
    """Fill {store}/{lang} placeholders in a flat extra-params/body dict's string values."""
    return {k: resolve_template(v, store, lang) for k, v in (extra or {}).items()}


def build_request(method, param, query, extra_params):
    """Merge the query text into the endpoint's extra static fields (storeId,
    page, pageSize, ... for search; limit for autocomplete), then split into
    (params, json_body) depending on method - GET sends a query string,
    POST sends a JSON body, but the merge logic is identical either way."""
    merged = {**(extra_params or {}), param: query}
    if method == "GET":
        return merged, None
    return None, merged


def preflight_check(api_url, method, headers, params=None, json_body=None, required_keys=()):
    """One real call before burning a whole batch on a dead/expired session.

    Raises ApiError with a Vietnamese, actionable message on: network failure,
    a non-JSON body (typical of a WAF/login HTML challenge page swapped in for
    the real API response), or a JSON body missing every key in `required_keys`
    (e.g. the "products"/"suggestions" list - present on success, commonly
    absent on an auth-rejected-but-200 response).
    """
    try:
        payload, latency_ms = call_api(api_url, method, headers, params, json_body)
    except ApiError as e:
        raise ApiError(
            "Preflight thất bại khi gọi thử API - có thể chưa đăng nhập / cookie đã hết hạn. "
            "Hãy đăng nhập lại trên dev-console, copy Cookie header mới vào biến môi trường, "
            f"rồi chạy lại. Chi tiết lỗi gốc: {e}"
        ) from e
    if required_keys and isinstance(payload, dict) and not any(k in payload for k in required_keys):
        raise ApiError(
            f"Preflight gọi API thành công (HTTP OK) nhưng response không có field nào trong "
            f"{list(required_keys)} - nhiều khả năng đây là trang login/challenge trả về thay vì "
            f"response API thật (cookie hết hạn nhưng server vẫn trả 200). Response nhận được: "
            f"{json.dumps(payload, ensure_ascii=False)[:300]}"
        )
    return payload, latency_ms


def call_api(api_url, method, headers, params=None, json_body=None, timeout=30):
    """Returns (parsed_json, latency_ms). Raises ApiError on failure.

    GET requests send `params` as the query string; POST requests send
    `json_body` as the request body. The caller is responsible for merging
    the query text into whichever one applies (see build_search_request /
    build_autocomplete_request in run_autoscript.py) - the real MART search
    API takes extra static fields alongside the query (storeId, page,
    pageSize, ... for search; limit for autocomplete) that differ per
    endpoint, so a single `{param: query}` body is no longer enough.
    """
    start = time.time()
    ctx = ssl.create_default_context()
    try:
        if method == "GET":
            qstr = parse.urlencode(params or {})
            url = api_url + (("&" if "?" in api_url else "?") + qstr if qstr else "")
            req = request.Request(url, headers=headers, method="GET")
        else:
            body = json.dumps(json_body or {}).encode("utf-8")
            hdrs = dict(headers)
            hdrs.setdefault("Content-Type", "application/json")
            req = request.Request(api_url, data=body, headers=hdrs, method="POST")
        with request.urlopen(req, context=ctx, timeout=timeout) as resp:
            raw = resp.read()
        latency_ms = int((time.time() - start) * 1000)
        return json.loads(raw.decode("utf-8")), latency_ms
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        raise ApiError(str(e)) from e


def capture_cookie_via_headed_login(console_url,
                                     login_button_text="Sign in with Magento",
                                     logged_in_markers=("Search Playground", "Welcome to Lotte Mart Admin Console"),
                                     playground_click_texts=("Search Playground", "Playground"),
                                     mode_select_value="adaptive", clear_default_query=True,
                                     wait_seconds=180, poll_seconds=2, on_tick=None):
    """Opens a REAL, visible browser (Playwright, headed - not headless) so a human
    can log in by hand (username/password, then a 2FA authenticator code), then
    captures the resulting session cookies. This automates only the copy-paste step
    ("copy the Cookie header from DevTools" - see auth_header_env in
    config/environments.yaml); it never types credentials or a 2FA code itself.

    Real flow this was built against (dev-console.martonline.lotte.vn): a single
    `login_button_text` button redirects through a genuine OAuth2/OIDC chain whose
    redirect_uri lands on the API gateway domain directly - so, unlike an earlier
    attempt that tried to "probe" the gateway domain with a bare fetch()/goto()
    after logging into the console alone, no probing is needed at all: a real
    completed OAuth login naturally passes through and authenticates the gateway
    domain as part of the redirect chain.

    Cannot use an `input()` "press Enter when done" prompt: this runs from an
    automation harness whose Bash tool is not connected to the human's terminal
    stdin, so a blocking read would hang forever. Instead it polls for up to
    `wait_seconds` (2FA can take a while) looking for `logged_in_markers` text
    becoming visible on the page - far more reliable than watching page.url,
    which bounces through several intermediate OAuth domains and doesn't settle
    predictably. `on_tick(elapsed_seconds, logged_in)` is called each poll tick,
    for progress output.

    After login, best-effort (never discards an already-valid cookie just
    because these fail): clicks into a "Playground"-style page via
    `playground_click_texts` (tries force=True too - PrimeNG/Angular sidebar
    menus routinely report a sibling animation overlay "intercepting" the click
    even though the item is genuinely clickable), then sets a native HTML
    `<select>` to `mode_select_value` via `select_option(value=...)` - clicking
    an <option> by text does NOT work for a native select (the browser renders
    its option list outside normal DOM flow, so Playwright reports the option as
    "not visible"); `select_option` is the correct API for this element type.
    Finally, if `clear_default_query`, clears whatever demo query the page
    pre-fills on load - per the user, leaving that stale query in place is what
    made the backend look "stuck in a mock/simulated state" (same 1-2 generic
    results for everything); clearing it is what actually lets a fresh, real
    query reach the backend. Uses the first matching `<input>` that actually
    HAS a non-empty value (not just `.first`), since an earlier, always-empty
    sidebar "Search menu..." input would otherwise get "cleared" instead.

    Returns (cookie_str, warnings) - warnings is a list of human-readable
    Vietnamese strings for any best-effort step that didn't succeed; an empty
    list means every step completed cleanly.

    Requires the `playwright` package + a `playwright install chromium` browser -
    imported lazily so plain (non-headed) runs never need it installed.
    """
    from playwright.sync_api import sync_playwright

    warnings = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(viewport=None)
        page = context.new_page()
        page.goto(console_url, wait_until="networkidle", timeout=20000)
        page.bring_to_front()

        try:
            page.get_by_text(login_button_text).click()
            page.bring_to_front()
        except Exception:
            pass  # maybe already logged in, or a different landing page - the poll below still covers it

        elapsed = 0
        logged_in = False
        while elapsed <= wait_seconds:
            for marker in logged_in_markers:
                try:
                    if page.get_by_text(marker, exact=False).first.is_visible(timeout=500):
                        logged_in = True
                        break
                except Exception:
                    pass
            if on_tick:
                on_tick(elapsed, logged_in)
            if logged_in or elapsed >= wait_seconds:
                break
            page.wait_for_timeout(poll_seconds * 1000)
            elapsed += poll_seconds

        if not logged_in:
            warnings.append("hết thời gian chờ đăng nhập - không thấy marker text nào xác nhận đã login")
        else:
            page.wait_for_timeout(1000)
            playground_ok = False
            for text in playground_click_texts:
                for force in (False, True):
                    try:
                        page.get_by_text(text, exact=True).click(timeout=5000, force=force)
                        playground_ok = True
                        break
                    except Exception:
                        pass
                if playground_ok:
                    break
            if not playground_ok:
                warnings.append("đăng nhập OK nhưng không click được vào Playground - vẫn dùng cookie đã có")
            else:
                page.wait_for_timeout(1500)
                if mode_select_value:
                    mode_ok = False
                    try:
                        selects = page.locator("select")
                        for i in range(selects.count()):
                            sel = selects.nth(i)
                            if sel.locator(f"option[value='{mode_select_value}']").count() > 0:
                                sel.select_option(value=mode_select_value)
                                mode_ok = True
                                break
                    except Exception:
                        pass
                    if not mode_ok:
                        warnings.append(f"vào Playground OK nhưng không set được mode={mode_select_value!r}")

                if clear_default_query:
                    # Not just `.first`: the sidebar's own "Search menu..." input is
                    # usually earlier in the DOM than the actual product search box
                    # and would otherwise get cleared instead (it's already empty, so
                    # a naive `.first` silently "succeeds" at clearing the wrong box).
                    # Clear the first matching input that actually HAS a non-empty
                    # value - that is the one carrying the pre-filled demo query.
                    cleared = False
                    try:
                        inputs = page.locator("input[type='text'], input[type='search'], input:not([type])")
                        for i in range(inputs.count()):
                            el = inputs.nth(i)
                            try:
                                val = el.input_value(timeout=1000)
                            except Exception:
                                continue
                            if val.strip():
                                el.fill("")
                                cleared = True
                                break
                    except Exception:
                        pass
                    if not cleared:
                        warnings.append("không tìm/clear được ô search box có query demo mặc định")

        cookies = context.cookies()
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        browser.close()
        return cookie_str, warnings


def extract_id_list(payload, result_path, id_keys=("product_id", "productId", "id", "sku")):
    """Extract a flat list of product-id strings from a search response."""
    items = None
    if result_path and isinstance(payload, dict) and isinstance(payload.get(result_path), list):
        items = payload[result_path]
    else:
        for k in ("results", "items", "hits", "data"):
            if isinstance(payload, dict) and isinstance(payload.get(k), list):
                items = payload[k]
                break
    if items is None:
        return []
    out = []
    for item in items:
        if isinstance(item, (str, int)):
            out.append(str(item))
        elif isinstance(item, dict):
            for k in id_keys:
                if k in item:
                    out.append(str(item[k]))
                    break
    return out


def extract_keyword_list(payload, result_path, keyword_keys=("keyword", "query", "text", "suggestion", "title")):
    """Extract a flat list of suggestion keyword strings from an autocomplete response."""
    items = None
    if result_path and isinstance(payload, dict) and isinstance(payload.get(result_path), list):
        items = payload[result_path]
    else:
        for k in ("suggestions", "results", "items", "data"):
            if isinstance(payload, dict) and isinstance(payload.get(k), list):
                items = payload[k]
                break
    if items is None:
        return []
    out = []
    for item in items:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            for k in keyword_keys:
                if item.get(k):
                    out.append(str(item[k]))
                    break
    return out
