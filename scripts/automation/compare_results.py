#!/usr/bin/env python3
"""
Compare Expected vs Actual Search Results and generate comparison artifacts:
1. matched_100_percent.json (Saved as baseline standard)
2. mismatched_keywords.json (Detailed breakdown of differences)
3. summary_stats.json (Summary metrics, Top-1, Top-5, Top-20 KPIs)
4. compare_report.html (Interactive standalone HTML comparison dashboard with Tooltips)

Output folder: auto-derived from the expected/actual filenames + today's date
(e.g. "SmartSearch/test_data/compare/run_realsearch_top1000_20260828") unless
--out-dir overrides it. Every run always lands in a NEW folder - old
comparison folders are never deleted or silently overwritten; re-running the
same comparison on the same day bumps to a time-suffixed folder name instead
of colliding.

As-Is panel (2026-08-28, user's explicit design; shown-for-every-scenario +
reordered-first 2026-08-31): the FIRST column of the 3, showing what the
CURRENT/legacy production system (lottemart.vn, real money per call) returns
- NOT scored against Expected. Always sourced from ONE persistent cache file,
SmartSearch/test_data/json/actual/AsIs_NSG_cache.json (created on first use,
only ever appended to) - never pass a file for it. DISPLAYED for every
scenario as long as its query is already in the cache (a cache read is free);
a real call to the legacy system is only ever made to fill a cache MISS for a
scenario whose Expected-vs-Actual Top-30 match is <= 50% (ASIS_MATCH_
THRESHOLD_PCT) - saved to the cache immediately, never re-called for that
query again by any future run. --no-asis-fetch limits this to cache-hits-only
(zero real calls); --no-asis disables the panel entirely.

Usage:
  python scripts/automation/compare_results.py \\
    --expected SmartSearch/test_data/json/for_dev/MART_SmartSearch_AutocompleteSearch_TestData_v1.0_realsearch_top1000_20260827.json \\
    --actual "C:/Users/Admin/Downloads/test1_outputs 1.json"
"""
import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))
from lib_search_client import (call_api, ApiError, load_env_config, resolve_headers,  # noqa: E402
                                resolve_template, resolve_extra_params, build_request, get_nested)

# Single persistent cache of As-Is (current/legacy production system, e.g.
# lottemart.vn) search results, keyed by normalized query text - created
# once, only ever APPENDED to, never overwritten wholesale. This is a real
# production system, so it is only ever called for a query NOT already in
# this file (see fetch_and_cache_asis() below) - never re-call for a query
# that's already cached, no matter how many scenarios/compare runs share it.
ASIS_CACHE_PATH = Path("SmartSearch/test_data/json/actual/AsIs_NSG_cache.json")
# Only scenarios at/under this Top-20-overlap match% trigger an As-Is lookup/
# fetch at all - per user's explicit ask (2026-08-28), don't touch the As-Is
# system (production, costs money) for scenarios that already match well.
ASIS_MATCH_THRESHOLD_PCT = 50


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_CATALOG_CACHE = {}  # store -> {sku: {name, price, category}} - loaded at most once per store per run


def load_catalog(store):
    """Same shape/source as scripts/testdata/export_smartsearch_testdata.py's
    load_catalog() - duplicated (not imported) on purpose, to keep this
    script standalone rather than reaching across scripts/testdata/."""
    if store in _CATALOG_CACHE:
        return _CATALOG_CACHE[store]
    out = {}
    path = Path("data/ProductInfo") / f"mart_vi_{store}_product.ndjson"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)["_source"]
                sku = d.get("sku")
                if not sku:
                    continue
                cat_path = d.get("category_full_path") or [""]
                out[sku] = {
                    "name": (d.get("name") or "").strip(),
                    "price": d.get("price_default") or 0,
                    "category": cat_path[1] if len(cat_path) > 1 else (cat_path[0] if cat_path else ""),
                }
    _CATALOG_CACHE[store] = out
    return out


def fill_missing_names(scenarios, store):
    """Some inputs (e.g. the raw smoke_test/*.json or a batch straight from
    _source/, as opposed to a for_dev/ export) carry only {sku, score, tier}
    per search_results item - no name/price, because they were never run
    through export_smartsearch_testdata.py's denormalize() step. Rather than
    silently showing a blank product name in the comparison (confusing -
    looks like a real data bug, see 2026-08-28 user report), backfill name/
    price/category from the real catalog here, once, for whichever items are
    missing it - works for ANY of --expected/--actual regardless of which
    exact file variant was passed. A SKU with no catalog match (stale/typo)
    is left with an empty name rather than silently invented."""
    catalog = load_catalog(store)
    if not catalog:
        return
    for sc in scenarios:
        for item in sc.get("search_results") or []:
            if item.get("name"):
                continue
            hit = catalog.get(str(item.get("sku", "")))
            if hit:
                item["name"] = hit["name"]
                item.setdefault("price", hit["price"])
                item.setdefault("category", hit["category"])


def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_query(q):
    return " ".join(str(q or "").strip().lower().split())


# Known filename prefixes/suffixes to strip when deriving a human-readable
# label from an expected/actual file path, e.g.
# "MART_SmartSearch_AutocompleteSearch_TestData_v1.0_realsearch_top1000_20260827.json"
# or "NSG_ActualData_realsearch_top1000_20260827.json" both -> "realsearch_top1000".
_LABEL_PREFIXES = [
    "MART_SmartSearch_AutocompleteSearch_TestData_WLE_v1.0_",
    "MART_SmartSearch_AutocompleteSearch_TestData_v1.0_",
    "NSG_ExpectedData_", "WLE_ExpectedData_",
    "NSG_ActualData_", "WLE_ActualData_",
]


def derive_label(*paths):
    for p in paths:
        name = Path(p).stem
        name = re.sub(r"_\d{8}(_\d{6})?$", "", name)  # trailing _YYYYMMDD or _YYYYMMDD_HHMMSS
        for prefix in _LABEL_PREFIXES:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        name = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")
        if name:
            return name
    return "compare"


def next_free_dir(preferred):
    """Never overwrite an existing non-empty comparison folder - if `preferred`
    already exists and has files in it, append the current time (and, in the
    rare case that STILL collides within the same second, an incrementing
    counter) so every run always lands in a genuinely NEW folder. Old folders
    are never touched/deleted."""
    preferred = Path(preferred)
    if not preferred.exists() or not any(preferred.iterdir()):
        return preferred
    base = preferred.parent / f"{preferred.name}_{datetime.now().strftime('%H%M%S')}"
    candidate = base
    n = 2
    while candidate.exists() and any(candidate.iterdir()):
        candidate = Path(f"{base}_{n}")
        n += 1
    return candidate


def _normalize_price(raw):
    """Price shows up as a flat number in engine/dev-gateway data but as a
    nested {"VND": {"default": N, ...}} object in the legacy lottemart.vn
    response - normalize both to a plain number (or None) so the HTML/JS
    price formatting code never has to special-case the source."""
    if isinstance(raw, dict):
        vnd = raw.get("VND")
        if isinstance(vnd, dict):
            return vnd.get("default")
        return None
    return raw


def load_asis_cache(path=ASIS_CACHE_PATH):
    if not path.exists():
        return {"createdAt": datetime.now().isoformat(), "store": "nsg",
                "source": "legacy (lottemart.vn)", "entries": {}}
    with open(path, "r", encoding="utf-8") as f:
        cache = json.load(f)
    cache.setdefault("entries", {})
    return cache


def save_asis_cache(cache, path=ASIS_CACHE_PATH):
    path.parent.mkdir(parents=True, exist_ok=True)
    cache["updatedAt"] = datetime.now().isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def fetch_legacy_result(query):
    """One real call to the legacy/As-Is production search (config/
    environments.yaml's "legacy" env - no auth, verified public 2026-08-28).
    Returns (search_results, total_before_cap) in the same {rank,sku,name,
    price} shape everything else in this file expects. Raises ApiError on
    failure - the caller decides what to do (this function never silently
    swallows a failed real call)."""
    cfg = load_env_config("legacy")
    store = cfg.get("store") or "nsg"
    lang = cfg.get("lang", "vi")
    search_api = resolve_template(cfg.get("search_api"), store, lang)
    method = cfg.get("search_method", "POST")
    param = cfg.get("search_param", "where.query")
    extra = resolve_extra_params(cfg.get("search_extra_params", {}), store, lang)
    # "legacy" carries no auth_header_env - the endpoint needs no auth at all
    # (verified 200 OK with zero cookie/token, 2026-08-28) - resolve_headers
    # with auth_header_env=None just returns the static search_headers.
    headers = resolve_headers(None, None, cfg.get("auth_header_name", "Authorization"))
    headers = {**headers, **cfg.get("search_headers", {})}
    params, body = build_request(method, param, query, extra)
    payload, latency_ms = call_api(search_api, method, headers, params, body)
    result_path = cfg.get("search_result_path", "data.items")
    items = get_nested(payload, result_path) if "." in result_path else (payload.get(result_path) if isinstance(payload, dict) else None)
    items = items or []
    search_results = [
        {"rank": i + 1, "sku": str(it.get("sku", "")), "name": it.get("name", ""), "price": it.get("price")}
        for i, it in enumerate(items)
    ]
    total = None
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        total = payload["data"].get("total_items")
    return search_results, total


def get_or_fetch_asis(query, cache, allow_fetch=True, log=print, cache_path=ASIS_CACHE_PATH):
    """The ONLY place that may call the real legacy/As-Is system. Cache-first,
    always: a query already present in `cache["entries"]` is NEVER re-fetched
    (production system, real cost per call - see ASIS_CACHE_PATH's docstring).
    Returns a scenario-shaped dict ({"search_results": [...], ...}) for
    build_asis_items(), or None if not cached and fetching is disabled/failed."""
    key = normalize_query(query)
    entry = cache["entries"].get(key)
    if entry is not None:
        return {"search_results": entry.get("search_results", []),
                "search_results_total_before_cap": entry.get("search_results_total_before_cap")}
    if not allow_fetch:
        return None
    try:
        search_results, total = fetch_legacy_result(query)
    except ApiError as e:
        log(f"  [as-is] Gọi hệ thống cũ thất bại cho query {query!r}: {e}")
        return None
    cache["entries"][key] = {
        "query": query,
        "fetchedAt": datetime.now().isoformat(),
        "search_results": search_results,
        "search_results_total_before_cap": total,
    }
    save_asis_cache(cache, cache_path)  # persist immediately - never lose a real, paid-for call
    log(f"  [as-is] Đã gọi hệ thống cũ cho query {query!r} ({len(search_results)} kết quả) - đã lưu vào cache, sẽ không gọi lại.")
    return {"search_results": search_results, "search_results_total_before_cap": total}


def build_asis_items(asis_sc, top_n):
    """Plain reference list (no expected-comparison status) for the As-Is
    (current/legacy production system) panel - just what that system
    actually returns today, for a human to eyeball alongside Expected/
    Actual. Not scored - this system isn't the one under test."""
    if not asis_sc:
        return []
    results = (asis_sc.get("search_results") or [])[:top_n]
    out = []
    for idx, item in enumerate(results, start=1):
        out.append({
            "rank": idx,
            "sku": str(item.get("sku", "")),
            "name": item.get("name", ""),
            "price": _normalize_price(item.get("price")),
        })
    return out


def compare_scenario(exp_sc, act_sc, top_n=20, asis_sc=None):
    query = exp_sc.get("query") or act_sc.get("query")
    test_id = exp_sc.get("test_id") or act_sc.get("test_id")
    dimension = exp_sc.get("dimension") or act_sc.get("dimension") or "unknown"
    route = exp_sc.get("route") or act_sc.get("route")
    # Real API response time for the Actual (system-under-test) call, saved by
    # export_actual_search_results.py as "api_latency_ms" or by
    # run_batch_test.py's raw ndjson (converted) as "latency_ms" - read either
    # name so the report works regardless of which tool produced --actual.
    actual_latency_ms = act_sc.get("api_latency_ms")
    if actual_latency_ms is None:
        actual_latency_ms = act_sc.get("latency_ms")

    exp_results = exp_sc.get("search_results") or []
    act_results = act_sc.get("search_results") or []

    exp_top = exp_results[:top_n]
    act_top = act_results[:top_n]

    exp_all_skus = [str(x["sku"]) for x in exp_results if "sku" in x]
    act_all_skus = [str(x["sku"]) for x in act_results if "sku" in x]

    exp_top_skus = [str(x["sku"]) for x in exp_top if "sku" in x]
    act_top_skus = [str(x["sku"]) for x in act_top if "sku" in x]

    exp_all_sku_set = set(exp_all_skus)
    act_all_sku_set = set(act_all_skus)

    exp_top_sku_set = set(exp_top_skus)
    act_top_sku_set = set(act_top_skus)

    # Rank mappings
    exp_rank_map = {sku: idx + 1 for idx, sku in enumerate(exp_all_skus)}
    act_rank_map = {sku: idx + 1 for idx, sku in enumerate(act_all_skus)}

    # Matches
    matched_exact_order = (exp_top_skus == act_top_skus) and len(exp_top_skus) > 0
    matched_set = (exp_top_sku_set == act_top_sku_set) and len(exp_top_sku_set) > 0

    top1_match = False
    if exp_top_skus and act_top_skus:
        top1_match = (exp_top_skus[0] == act_top_skus[0])

    # Top-5 Overlap
    top5_exp = exp_top_skus[:5]
    top5_act = act_top_skus[:5]
    top5_overlap = len(set(top5_exp) & set(top5_act))
    top5_overlap_pct = round(top5_overlap / max(1, len(top5_exp)) * 100, 1) if top5_exp else 0

    # Top-10 Overlap
    top10_exp = exp_top_skus[:10]
    top10_act = act_top_skus[:10]
    top10_overlap = len(set(top10_exp) & set(top10_act))
    top10_overlap_pct = round(top10_overlap / max(1, len(top10_exp)) * 100, 1) if top10_exp else 0

    # Top-20 Overlap
    top20_exp = exp_top_skus[:20]
    top20_act = act_top_skus[:20]
    top20_overlap = len(set(top20_exp) & set(top20_act))
    top20_overlap_pct = round(top20_overlap / max(1, len(top20_exp)) * 100, 1) if top20_exp else 0

    # Top-30 Overlap - same fixed-window pattern as top5/10/20 above (always
    # measures this exact window regardless of top_n), added specifically as
    # the As-Is trigger metric (user, 2026-08-28: "sửa thành Top-30") - kept
    # separate from the existing Top-20 KPI/badge, which stays unchanged.
    top30_exp = exp_top_skus[:30]
    top30_act = act_top_skus[:30]
    top30_overlap = len(set(top30_exp) & set(top30_act))
    top30_overlap_pct = round(top30_overlap / max(1, len(top30_exp)) * 100, 1) if top30_exp else 0

    # Overlap in top_n
    common_top_skus = exp_top_sku_set & act_top_sku_set
    overlap_count = len(common_top_skus)
    overlap_pct = round(overlap_count / max(1, len(exp_top_skus)) * 100, 1) if exp_top_skus else 0

    # Missing from actual top N
    missing_from_top_n = [sku for sku in exp_top_skus if sku not in act_top_sku_set]
    missing_from_all_actual = [sku for sku in exp_top_skus if sku not in act_all_sku_set]

    # Extras in actual top N (not present anywhere in expected results)
    extra_in_top_n = [sku for sku in act_top_skus if sku not in exp_all_sku_set]

    # Detailed items comparison
    exp_details = []
    for idx, item in enumerate(exp_top, start=1):
        sku = str(item.get("sku", ""))
        act_rank = act_rank_map.get(sku)
        if act_rank == idx:
            status = "exact_rank"
        elif act_rank is not None and act_rank <= top_n:
            status = "rank_shifted"
        elif act_rank is not None:
            status = "outside_top"
        else:
            status = "missing"
        
        exp_details.append({
            "rank": idx,
            "sku": sku,
            "name": item.get("name", ""),
            "price": item.get("price"),
            "category": item.get("category", ""),
            "tier": item.get("tier", ""),
            "score": item.get("score"),
            "status": status,
            "actual_rank": act_rank
        })

    act_details = []
    for idx, item in enumerate(act_top, start=1):
        sku = str(item.get("sku", ""))
        exp_rank = exp_rank_map.get(sku)
        if exp_rank == idx:
            status = "exact_rank"
        elif exp_rank is not None and exp_rank <= top_n:
            status = "rank_shifted"
        elif exp_rank is not None:
            status = "outside_top"
        else:
            status = "extra"

        act_details.append({
            "rank": idx,
            "sku": sku,
            "name": item.get("name", ""),
            "price": item.get("price"),
            "category": item.get("category", ""),
            "tier": item.get("tier", ""),
            "score": item.get("score"),
            "status": status,
            "expected_rank": exp_rank
        })

    # Categorize status
    if matched_exact_order:
        match_category = "100_PERCENT_EXACT"
    elif matched_set:
        match_category = "100_PERCENT_SET"
    elif len(act_top) == 0 and len(exp_top) > 0:
        match_category = "ZERO_RESULT"
    elif top20_overlap_pct >= 70:
        match_category = "HIGH_MATCH"
    elif top20_overlap_pct >= 30:
        match_category = "PARTIAL_MATCH"
    elif top20_overlap_pct > 0:
        match_category = "LOW_MATCH"
    else:
        match_category = "NO_MATCH"

    return {
        "test_id": test_id,
        "query": query,
        "dimension": dimension,
        "route": route,
        "match_category": match_category,
        "is_100_percent_exact_order": matched_exact_order,
        "is_100_percent_set_match": matched_set,
        "top1_match": top1_match,
        "top5_overlap_count": top5_overlap,
        "top5_overlap_pct": top5_overlap_pct,
        "top10_overlap_count": top10_overlap,
        "top10_overlap_pct": top10_overlap_pct,
        "top20_overlap_count": top20_overlap,
        "top20_overlap_pct": top20_overlap_pct,
        "top30_overlap_count": top30_overlap,
        "top30_overlap_pct": top30_overlap_pct,
        "expected_count": len(exp_top),
        "actual_count": len(act_top),
        "expected_total_before_cap": exp_sc.get("search_results_total_before_cap", len(exp_results)),
        "actual_total_before_cap": act_sc.get("search_results_total_before_cap", len(act_results)),
        "overlap_count": overlap_count,
        "overlap_pct": overlap_pct,
        "missing_count": len(missing_from_top_n),
        "extra_count": len(extra_in_top_n),
        "expected_items": exp_details,
        "actual_items": act_details,
        "missing_skus": missing_from_top_n,
        "extra_skus": extra_in_top_n,
        # As-Is (current/legacy production system) - reference only, not
        # scored against Expected (that system isn't the one under test).
        "asis_items": build_asis_items(asis_sc, top_n),
        "asis_total_before_cap": asis_sc.get("search_results_total_before_cap", len(asis_sc.get("search_results") or [])) if asis_sc else None,
        # Distinct from "asis_items is empty" - a cache hit that genuinely
        # returned 0 real results ("As-Is trả về 0 kết quả") must read
        # differently in the UI than "never looked up" ("chưa có dữ liệu As-Is").
        "asis_cached": asis_sc is not None,
        "actual_latency_ms": actual_latency_ms,
    }


def generate_html_report(stats, scenarios, exp_meta, act_meta, out_file, report_id=None):
    scenarios_json = json.dumps(scenarios, ensure_ascii=False)
    stats_json = json.dumps(stats, ensure_ascii=False)
    report_id_json = json.dumps(report_id or Path(out_file).parent.name)
    has_asis_json = json.dumps(bool(stats.get("asis_cache_file")))

    html_content = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Smart Search Result Comparison Dashboard</title>
<style>
  :root {{
    --bg: #f6f7fb;
    --card-bg: #ffffff;
    --card-border: #dde1ea;
    --text-primary: #14181f;
    --text-secondary: #565f70;
    --text-muted: #7b8494;
    --accent: #0284c7;
    --accent-hover: #0369a1;
    --green: #16a34a;
    --green-bg: rgba(22, 163, 74, 0.12);
    --yellow: #b45309;
    --yellow-bg: rgba(217, 119, 6, 0.12);
    --red: #dc2626;
    --red-bg: rgba(220, 38, 38, 0.10);
    --blue: #2563eb;
    --blue-bg: rgba(37, 99, 235, 0.10);
    --purple: #7e22ce;
    --purple-bg: rgba(126, 34, 206, 0.10);
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background-color: var(--bg);
    color: var(--text-primary);
    line-height: 1.5;
    padding: 24px;
  }}

  .container {{ max-width: 1440px; margin: 0 auto; }}

  /* Header */
  .header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--card-border);
    margin-bottom: 24px;
    flex-wrap: wrap;
    gap: 16px;
  }}
  .header h1 {{ font-size: 24px; font-weight: 700; color: var(--text-primary); display: flex; align-items: center; gap: 10px; }}
  .header p {{ color: var(--text-secondary); font-size: 14px; margin-top: 4px; }}
  .meta-tag {{
    display: inline-flex;
    align-items: center;
    background: #eef1f6;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 12px;
    color: #3f4a5c;
    margin-right: 6px;
  }}

  /* Tooltip Container */
  [data-tooltip] {{
    position: relative;
    cursor: help;
  }}
  [data-tooltip]::after {{
    content: attr(data-tooltip);
    position: absolute;
    bottom: 110%;
    left: 50%;
    transform: translateX(-50%);
    background: #090d16;
    color: #f1f5f9;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 400;
    line-height: 1.4;
    white-space: normal;
    width: max-content;
    max-width: 280px;
    z-index: 1000;
    box-shadow: 0 10px 25px rgba(0,0,0,0.5);
    border: 1px solid #475569;
    opacity: 0;
    visibility: hidden;
    transition: opacity 0.2s, visibility 0.2s;
    pointer-events: none;
    text-transform: none;
    text-align: left;
  }}
  [data-tooltip]:hover::after {{
    opacity: 1;
    visibility: visible;
  }}

  /* KPI Grid */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 14px;
    margin-bottom: 28px;
  }}
  .kpi-card {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 16px;
    position: relative;
    overflow: visible;
  }}
  .kpi-card::before {{
    content: "";
    position: absolute;
    top: 0; left: 0; right: 0; height: 3px;
    background: var(--accent);
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
  }}
  .kpi-card.green::before {{ background: var(--green); }}
  .kpi-card.yellow::before {{ background: var(--yellow); }}
  .kpi-card.purple::before {{ background: var(--purple); }}
  .kpi-card.blue::before {{ background: var(--blue); }}
  .kpi-card.red::before {{ background: var(--red); }}

  .kpi-title {{ font-size: 12px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; display: flex; justify-content: space-between; align-items: center; }}
  .kpi-value {{ font-size: 26px; font-weight: 700; color: var(--text-primary); margin: 4px 0 2px 0; }}
  .kpi-sub {{ font-size: 12px; color: var(--text-muted); }}
  .info-icon {{ font-size: 13px; color: var(--text-muted); margin-left: 4px; }}

  /* Controls & Search */
  .toolbar {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }}
  .search-box {{
    flex: 1;
    min-width: 280px;
    position: relative;
  }}
  .search-input {{
    width: 100%;
    padding: 10px 16px 10px 38px;
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    color: var(--text-primary);
    font-size: 14px;
    outline: none;
  }}
  .search-input:focus {{ border-color: var(--accent); }}
  .search-icon {{
    position: absolute;
    left: 12px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-muted);
  }}

  .filter-tabs {{
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }}
  .tab-btn {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    color: var(--text-secondary);
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
  }}
  .tab-btn:hover {{ background: #eef1f6; color: var(--text-primary); }}
  .tab-btn.active {{
    background: var(--accent);
    color: #0f172a;
    font-weight: 700;
    border-color: var(--accent);
  }}

  /* Scenario List */
  .scenario-list {{ display: flex; flex-direction: column; gap: 16px; }}
  .scenario-card {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    /* NOT overflow:hidden - clips tooltips (data-tooltip::after) that pop up
       from badges near the card's top/right edge, e.g. the "Fix Expected"
       button (2026-08-28 bug report: tooltip visibly cut off on hover).
       Corner-clipping is handled per-element below instead (only
       .scenario-header has a visible background box that could otherwise
       poke past the card's rounded corners - .scenario-body/.bug-panel are
       transparent/self-contained and don't need it). */
    transition: border-color 0.2s;
  }}
  .scenario-card:hover {{ border-color: #b7c0d1; }}

  .scenario-header {{
    padding: 14px 20px;
    background: rgba(15,23,42,0.02);
    border-bottom: 1px solid var(--card-border);
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    cursor: pointer;
    user-select: none;
    flex-wrap: wrap;
    gap: 12px;
  }}
  .scenario-title-area {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
  .scenario-id {{ font-weight: 700; font-size: 13px; color: var(--accent); font-family: monospace; }}
  .scenario-query {{ font-size: 16px; font-weight: 600; color: var(--text-primary); }}
  .scenario-badges {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}

  .badge {{
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
  }}
  .badge-exact {{ background: var(--green-bg); color: var(--green); border: 1px solid var(--green); }}
  .badge-set {{ background: var(--purple-bg); color: var(--purple); border: 1px solid var(--purple); }}
  .badge-high {{ background: var(--blue-bg); color: var(--blue); border: 1px solid var(--blue); }}
  .badge-partial {{ background: var(--yellow-bg); color: var(--yellow); border: 1px solid var(--yellow); }}
  .badge-low {{ background: var(--red-bg); color: var(--red); border: 1px solid var(--red); }}
  .badge-zero {{ background: var(--red-bg); color: var(--red); border: 1px solid var(--red); }}

  .scenario-body {{
    padding: 20px;
    display: none;
  }}
  .scenario-body.open {{ display: block; }}

  .compare-columns {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }}
  .compare-columns.has-asis {{ grid-template-columns: 1fr 1fr 1fr; }}
  /* Expected panel is hide-by-default (checkbox opt-in, "showExpandedToggle")
     - these 2 variants cover HAS_ASIS with Expected hidden (2 cols: As-Is +
     Actual) and no As-Is at all with Expected hidden (1 col: Actual only). */
  .compare-columns.has-asis-no-expected {{ grid-template-columns: 1fr 1fr; }}
  .compare-columns.no-expected {{ grid-template-columns: 1fr; }}
  @media (max-width: 1200px) {{
    .compare-columns.has-asis {{ grid-template-columns: 1fr 1fr; }}
  }}
  @media (max-width: 900px) {{
    .compare-columns,
    .compare-columns.has-asis,
    .compare-columns.has-asis-no-expected,
    .compare-columns.no-expected {{ grid-template-columns: 1fr; }}
  }}
  .col-box.asis-box {{ border-color: #c4933f; }}
  .col-box.asis-box .col-title {{ color: #92660a; }}

  .col-box {{
    background: #f6f7fb;
    border: 1px solid var(--card-border);
    border-radius: 8px;
    padding: 12px;
  }}
  .col-title {{
    font-size: 13px;
    font-weight: 700;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}

  /* Product Tables */
  .prod-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }}
  .prod-table th {{
    text-align: left;
    padding: 6px 8px;
    color: var(--text-muted);
    border-bottom: 1px solid var(--card-border);
    font-weight: 600;
  }}
  .prod-table td {{
    padding: 8px;
    border-bottom: 1px solid #eef1f6;
    vertical-align: middle;
  }}
  .prod-table tr:hover {{ background: rgba(15,23,42,0.03); }}

  .rank-num {{
    font-weight: 700;
    color: var(--text-muted);
    width: 24px;
    display: inline-block;
  }}
  .item-name {{ color: var(--text-primary); font-weight: 500; display: block; max-width: 260px; word-break: break-word; }}
  .item-meta {{ font-size: 11px; color: var(--text-muted); }}

  .tag-status {{
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 600;
    display: inline-block;
  }}
  .tag-exact {{ background: var(--green-bg); color: var(--green); }}
  .tag-shift {{ background: var(--yellow-bg); color: var(--yellow); }}
  .tag-outside {{ background: rgba(100, 116, 139, 0.12); color: #46536b; }}
  .tag-missing {{ background: var(--red-bg); color: var(--red); }}
  .tag-extra {{ background: var(--blue-bg); color: var(--blue); }}

  .pagination-info {{
    margin-top: 20px;
    text-align: center;
    color: var(--text-secondary);
    font-size: 13px;
  }}
  .pagination-controls {{
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin-top: 12px;
  }}
  .pagination-controls button,
  .pagination-controls select,
  .sort-control select {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 6px;
    color: var(--text-primary);
    padding: 7px 10px;
    font-size: 12px;
  }}
  .pagination-controls button {{ cursor: pointer; }}
  .pagination-controls button:hover:not(:disabled) {{ border-color: var(--accent); }}
  .pagination-controls button:disabled {{ cursor: not-allowed; opacity: 0.45; }}
  .sort-control {{ display: flex; align-items: center; gap: 8px; }}
  .sort-control label {{ color: var(--text-secondary); font-size: 12px; }}

  /* Bug marking - per-keyword */
  .bug-btn {{
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    color: var(--text-secondary);
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
  }}
  .bug-btn:hover {{ border-color: var(--red); color: var(--red); }}
  .bug-btn.marked {{
    background: var(--red-bg);
    border-color: var(--red);
    color: var(--red);
  }}

  .bug-panel {{
    display: none;
    margin-top: 14px;
    background: var(--red-bg);
    border: 1px solid var(--red);
    border-radius: 8px;
    padding: 14px;
  }}
  .bug-panel.open {{ display: block; }}
  .bug-panel-title {{ font-size: 13px; font-weight: 700; color: var(--red); margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }}
  .bug-field-label {{ font-size: 12px; color: var(--text-secondary); margin-bottom: 6px; display: block; font-weight: 600; }}
  .bug-textarea {{
    width: 100%;
    min-height: 70px;
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 6px;
    color: var(--text-primary);
    font-size: 13px;
    padding: 10px;
    resize: vertical;
    font-family: inherit;
    margin-bottom: 12px;
  }}
  .bug-textarea:focus {{ outline: none; border-color: var(--red); }}
  .paste-zone {{
    border: 2px dashed var(--card-border);
    border-radius: 8px;
    padding: 16px;
    text-align: center;
    color: var(--text-muted);
    font-size: 12px;
    cursor: text;
    margin-bottom: 12px;
    transition: border-color 0.15s, background 0.15s;
    outline: none;
  }}
  .paste-zone:focus, .paste-zone.dragover {{ border-color: var(--accent); background: rgba(56,189,248,0.06); }}
  .paste-zone.has-image {{ padding: 8px; border-style: solid; }}
  .bug-thumb {{ max-width: 100%; max-height: 260px; border-radius: 6px; display: block; margin: 0 auto; }}
  .bug-actions {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
  .bug-save-btn, .bug-remove-btn, .bug-cancel-btn {{
    padding: 8px 16px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    border: 1px solid var(--card-border);
    background: var(--card-bg);
    color: var(--text-primary);
  }}
  .bug-save-btn {{ background: var(--red); border-color: var(--red); color: #fff; }}
  .bug-save-btn:hover {{ background: #dc2626; }}
  .bug-remove-btn {{ color: var(--red); }}
  .bug-remove-btn:hover {{ border-color: var(--red); }}
  .bug-saved-note {{ font-size: 11px; color: var(--text-muted); margin-left: auto; }}
  .bug-file-input {{ display: none; }}
  .bug-pick-file {{ color: var(--accent); text-decoration: underline; cursor: pointer; }}

  .export-bug-btn {{
    background: var(--red-bg);
    border: 1px solid var(--red);
    color: var(--red);
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    white-space: nowrap;
  }}
  .export-bug-btn:hover {{ background: var(--red); color: #fff; }}
  .export-bug-btn:disabled {{ opacity: 0.4; cursor: not-allowed; background: var(--card-bg); color: var(--text-muted); border-color: var(--card-border); }}
  .export-bug-group {{ display: flex; gap: 8px; flex-wrap: wrap; }}
</style>
</head>
<body>
<div class="container">
  <!-- Header -->
  <div class="header">
    <div>
      <h1>🔍 Smart Search Result Comparison</h1>
      <p>Báo cáo đối soát chi tiết Expected vs Actual Search Results (Di chuột vào các mục để xem giải thích)</p>
    </div>
    <div style="text-align: right;">
      <span class="meta-tag" data-tooltip="Thời gian thực thi đối soát">📅 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</span>
      <span class="meta-tag" data-tooltip="Mã chi nhánh siêu thị được test">🏢 Store: {html.escape(exp_meta.get("store", "NSG"))}</span>
      <span class="meta-tag" data-tooltip="Tổng số kịch bản test trong đợt đối soát">📊 Total: {stats["total_scenarios"]} Scenarios</span>
      {f'<span class="meta-tag" style="background:rgba(180,131,10,0.14);color:#92660a;" data-tooltip="As-Is (hệ thống hiện tại đang chạy thật trên lottemart.vn) chỉ tra/gọi cho scenario có %khớp Top-30 <= {stats.get("asis_match_threshold_pct")}% - {stats.get("asis_scenarios_used") or 0} scenario dùng As-Is ({stats.get("asis_newly_fetched") or 0} query mới phải gọi thật, còn lại lấy từ cache có sẵn - không gọi lại hệ thống production).">🕰️ As-Is: {stats.get("asis_scenarios_used") or 0} scenario ({stats.get("asis_newly_fetched") or 0} mới gọi)</span>' if stats.get("asis_cache_file") else ''}
    </div>
  </div>

  <!-- KPI Cards -->
  <div class="kpi-grid">
    <div class="kpi-card purple" data-tooltip="[Mục 1] Số scenario mà tập hợp SKU Actual khớp 100% với tập Expected (chứa đủ tất cả SKU, không quan tâm thứ tự).">
      <div class="kpi-title">⭐ 100% SET MATCH <span class="info-icon">ⓘ</span></div>
      <div class="kpi-value">{stats["set_match_count"]}</div>
      <div class="kpi-sub">{stats["set_match_pct"]}% tổng scenarios</div>
    </div>
    <div class="kpi-card green" data-tooltip="[Mục 2] Số scenario khớp hoàn hảo 100% cả tập SKU VÀ đúng tuyệt đối từng vị trí thứ hạng (Rank 1, Rank 2...).">
      <div class="kpi-title">🎯 100% EXACT ORDER <span class="info-icon">ⓘ</span></div>
      <div class="kpi-value">{stats["exact_order_count"]}</div>
      <div class="kpi-sub">{stats["exact_order_pct"]}% khớp tuyệt đối thứ tự</div>
    </div>
    <div class="kpi-card" data-tooltip="[Mục 3] Tỷ lệ sản phẩm ở vị trí số 1 (Top-1) của Actual trùng khớp hoàn toàn với Expected Top-1.">
      <div class="kpi-title">🥇 TOP-1 MATCH (P@1) <span class="info-icon">ⓘ</span></div>
      <div class="kpi-value">{stats["top1_match_count"]}</div>
      <div class="kpi-sub">{stats["top1_match_pct"]}% top-1 trùng khớp</div>
    </div>
    <div class="kpi-card yellow" data-tooltip="[Mục 4] Tỷ lệ phần trăm trùng khớp trung bình giữa 5 sản phẩm đầu tiên của Actual so với Expected.">
      <div class="kpi-title">📈 ĐỘ PHỦ TOP-5 <span class="info-icon">ⓘ</span></div>
      <div class="kpi-value">{stats["avg_top5_overlap_pct"]}%</div>
      <div class="kpi-sub">Avg Top-5 Overlap</div>
    </div>
    <div class="kpi-card blue" data-tooltip="[Mục 5] Tỷ lệ phần trăm trùng khớp trung bình giữa 20 sản phẩm đầu tiên của Actual so với Expected.">
      <div class="kpi-title">🌐 ĐỘ PHỦ TOP-20 <span class="info-icon">ⓘ</span></div>
      <div class="kpi-value">{stats["avg_top20_overlap_pct"]}%</div>
      <div class="kpi-sub">Avg Top-20 Overlap</div>
    </div>
    <div class="kpi-card red" data-tooltip="[Mục 6] Tổng số scenario có sự sai lệch (về vị trí, thiếu SKU hoặc có SKU lạ xuất hiện) cần xem xét.">
      <div class="kpi-title">⚠️ MISMATCHED / DIFF <span class="info-icon">ⓘ</span></div>
      <div class="kpi-value">{stats["mismatch_count"]}</div>
      <div class="kpi-sub">{stats["mismatch_pct"]}% có độ lệch</div>
    </div>
    <div class="kpi-card red" data-tooltip="[Mục 7] Số scenario mà API Actual trả về 0 kết quả (rỗng) trong khi Expected có kết quả.">
      <div class="kpi-title">🚫 ZERO RESULT <span class="info-icon">ⓘ</span></div>
      <div class="kpi-value">{stats["zero_result_count"]}</div>
      <div class="kpi-sub">Không có kết quả trả về</div>
    </div>
  </div>

  <!-- Comparison mode + sort (moved up from the bottom pagination bar so it's
       visible without scrolling - user request 2026-08-31) -->
  <div class="toolbar" style="margin-bottom: 12px;">
    <div class="sort-control" data-tooltip="Chọn 2 nguồn dữ liệu dùng để tính %matching, badge và sắp xếp cho từng scenario bên dưới. Panel As-Is/Actual LUÔN hiển thị; panel Expected ẩn/hiện riêng theo checkbox bên cạnh - lựa chọn ở đây chỉ đổi cách tính điểm matching, không tự ẩn/hiện panel nào.">
      <label for="modeSelect">So sánh:</label>
      <select id="modeSelect" aria-label="Chọn 2 nguồn dữ liệu để so sánh">
        <option value="expected_actual" selected>📋 Expected ↔ 🚀 Actual</option>
        <option value="asis_actual">🕰️ As-Is ↔ 🚀 Actual</option>
      </select>
    </div>
    <div class="sort-control" data-tooltip="Sắp xếp theo tỷ lệ SKU trùng khớp trong Top-20, tính theo chế độ so sánh đang chọn ở trên. 0% là lệch hoàn toàn; tỷ lệ càng cao thì matching càng tốt.">
      <label for="sortSelect">Matching:</label>
      <select id="sortSelect" aria-label="Sắp xếp theo độ matching">
        <option value="default">Mặc định</option>
        <option value="low">Thấp nhất trước</option>
        <option value="high">Cao nhất trước</option>
      </select>
    </div>
    <div class="sort-control" data-tooltip="Panel Expected mặc định ẨN để gọn màn hình (đặc biệt hữu ích với file không có Expected, ví dụ file demo) - tick vào đây nếu cần xem lại Expected.">
      <label for="showExpectedToggle" style="display:flex;align-items:center;gap:6px;cursor:pointer;">
        <input type="checkbox" id="showExpectedToggle">
        Hiển thị panel Expected
      </label>
    </div>
  </div>

  <!-- Toolbar -->
  <div class="toolbar">
    <div class="search-box">
      <span class="search-icon">🔍</span>
      <input type="text" id="searchInput" class="search-input" placeholder="[Mục 15] Tìm theo từ khóa, test_id, SKU hoặc tên sản phẩm..." data-tooltip="[Mục 15] Gõ từ khóa tìm kiếm, mã Test ID, mã SKU hoặc tên sản phẩm để lọc tức thì.">
    </div>
    <div class="filter-tabs">
      <button class="tab-btn active" data-filter="all" data-tooltip="[Mục 8] Xem toàn bộ tất cả các scenarios">Tất cả (<span id="cnt-all">{stats["total_scenarios"]}</span>)</button>
      <button class="tab-btn" data-filter="100_PERCENT_EXACT" data-tooltip="[Mục 9] Lọc các query đạt chuẩn 100% khớp đúng từng vị trí thứ hạng. Chỉ tính được ở chế độ Expected↔Actual - As-Is↔Actual không phân biệt exact-order, luôn gộp vào 100% Set.">⭐ 100% Exact (<span id="cnt-exact">{stats["exact_order_count"]}</span>)</button>
      <button class="tab-btn" data-filter="100_PERCENT_SET" data-tooltip="[Mục 10] Lọc các query khớp 100% tập SKU (chứa đủ các sản phẩm)">🟣 100% Set (<span id="cnt-set">{stats["set_match_count"]}</span>)</button>
      <button class="tab-btn" data-filter="HIGH_MATCH" data-tooltip="[Mục 11] Lọc các query có độ trùng khớp cao từ 70% trở lên">🔵 Khớp cao (&ge;70%)</button>
      <button class="tab-btn" data-filter="PARTIAL_MATCH" data-tooltip="[Mục 12] Lọc các query có độ trùng khớp từ 30% đến 69%">🟡 Khớp 1 phần (30-69%)</button>
      <button class="tab-btn" data-filter="LOW_MATCH" data-tooltip="[Mục 13] Lọc các query có độ lệch lớn (độ trùng dưới 30%)">🔴 Khớp thấp / Lệch</button>
      <button class="tab-btn" data-filter="ZERO_RESULT" data-tooltip="[Mục 14] Lọc các query bị lỗi trả về 0 kết quả">🚫 Zero Result (<span id="cnt-zero">{stats["zero_result_count"]}</span>)</button>
    </div>
    <div class="export-bug-group">
      <button id="exportBugHtmlBtn" type="button" class="export-bug-btn" disabled data-tooltip="Xuất ra 1 file HTML liệt kê toàn bộ keyword đã đánh dấu Bug, có ảnh đính kèm nhúng sẵn (xem trực tiếp trong trình duyệt) và nội dung Expected cần sửa.">📤 Xuất HTML (<span id="bugCountHtml">0</span>)</button>
      <button id="exportBugJsonBtn" type="button" class="export-bug-btn" disabled data-tooltip="Xuất ra 1 file JSON liệt kê toàn bộ keyword đã đánh dấu Bug - KHÔNG kèm ảnh (file gọn hơn, phù hợp để đưa vào script/BA đọc), chỉ có test_id/query/dimension/route/ghi chú/thời gian.">🗂️ Xuất JSON (<span id="bugCountJson">0</span>)</button>
    </div>
  </div>

  <!-- Scenario List Container -->
  <div id="scenarioList" class="scenario-list"></div>
  <div id="paginationInfo" class="pagination-info"></div>
  <div class="pagination-controls" data-tooltip="Dùng các nút để xem đủ scenarios sau khi lọc. Chọn 'Tất cả' nếu muốn hiển thị toàn bộ kết quả trên một trang.">
    <button id="prevPage" type="button" aria-label="Trang trước">← Trang trước</button>
    <button id="nextPage" type="button" aria-label="Trang sau">Trang sau →</button>
    <label for="pageSizeSelect">Số dòng/trang</label>
    <select id="pageSizeSelect" aria-label="Số dòng mỗi trang">
      <option value="25">25</option>
      <option value="50" selected>50</option>
      <option value="100">100</option>
      <option value="all">Tất cả</option>
    </select>
  </div>
</div>

<script>
const scenarios = {scenarios_json};
const HAS_ASIS = {has_asis_json};
let currentFilter = 'all';
let searchQuery = '';
let currentPage = 1;
let selectedPageSize = 50;
let sortOrder = 'default';
// Which 2 panels drive %matching/badge/sort/filter for every scenario card.
// Both panels of EITHER mode - and the 3rd, non-driving one - stay visible;
// this only changes which pair's overlap is scored (user request 2026-08-31).
let comparisonMode = 'expected_actual'; // or 'asis_actual'
// Expected panel is hidden by default (checkbox opt-in) - user request
// 2026-08-31: "thêm option ẩn expected panel đi, nếu chọn hiển thị thì mới
// hiển thị lên." As-Is and Actual always show regardless of this toggle.
let showExpected = false;

function panelsClass() {{
  if (HAS_ASIS && showExpected) return 'has-asis';
  if (HAS_ASIS && !showExpected) return 'has-asis-no-expected';
  if (!HAS_ASIS && !showExpected) return 'no-expected';
  return ''; // !HAS_ASIS && showExpected - the original 2-col default (Expected + Actual)
}}

// Client-side overlap scoring for a (base, other) item-list pair - mirrors
// the Python-side compare_scenario() math (Top-5/Top-20 fixed windows, same
// match_category thresholds) so switching comparisonMode doesn't need a
// second server-computed stat set embedded per scenario. Order-fidelity
// (100_PERCENT_EXACT) isn't replicated here - As-Is is reference-only, not
// scored for rank precision - a full base/other set match always reports as
// 100_PERCENT_SET regardless of order.
function computeOverlapMetrics(baseItems, otherItems) {{
  const base = (baseItems || []).map(i => String(i.sku));
  const otherSet = new Set((otherItems || []).map(i => String(i.sku)));
  const top5Base = base.slice(0, 5);
  const top5Count = top5Base.filter(sku => otherSet.has(sku)).length;
  const top5Pct = top5Base.length ? Math.round((top5Count / top5Base.length) * 1000) / 10 : 0;
  const top20Base = base.slice(0, 20);
  const top20Count = top20Base.filter(sku => otherSet.has(sku)).length;
  const top20Pct = top20Base.length ? Math.round((top20Count / top20Base.length) * 1000) / 10 : 0;
  const baseSet = new Set(base);
  const fullSetMatch = base.length > 0 && base.every(sku => otherSet.has(sku)) &&
    (otherItems || []).every(i => baseSet.has(String(i.sku)));
  const top1Match = base.length > 0 && (otherItems || []).length > 0 &&
    base[0] === String(otherItems[0].sku);
  let matchCategory;
  if (base.length === 0) matchCategory = 'ZERO_RESULT';
  else if (fullSetMatch) matchCategory = '100_PERCENT_SET';
  else if (top20Pct >= 70) matchCategory = 'HIGH_MATCH';
  else if (top20Pct >= 30) matchCategory = 'PARTIAL_MATCH';
  else if (top20Pct > 0) matchCategory = 'LOW_MATCH';
  else matchCategory = 'NO_MATCH';
  return {{
    top5_overlap_count: top5Count, top5_overlap_pct: top5Pct,
    top20_overlap_count: top20Count, top20_overlap_pct: top20Pct,
    overlap_count: top20Count, overlap_pct: top20Pct,
    match_category: matchCategory, top1_match: top1Match,
    expected_count: base.length,
  }};
}}

// Per-scenario metrics for whichever comparisonMode is active. In the
// default mode this is a free pass-through of the stats compare_results.py
// already computed server-side; in As-Is mode it's computed fresh from the
// already-embedded asis_items/actual_items (no extra data needed, no server
// call). A scenario with no As-Is data cached gets its own category so it
// doesn't silently look like "no match" in filters/sort.
function getModeMetrics(s) {{
  if (comparisonMode === 'asis_actual') {{
    // Not cached at all (never queried) - distinct from "queried, genuinely
    // 0 results" (s.asis_cached === true, empty items), which falls through
    // to computeOverlapMetrics() below and correctly reports ZERO_RESULT.
    if (!s.asis_cached) {{
      return {{
        top5_overlap_count: 0, top5_overlap_pct: 0, top20_overlap_count: 0, top20_overlap_pct: 0,
        overlap_count: 0, overlap_pct: 0, match_category: 'NO_ASIS_DATA', top1_match: false,
        expected_count: 0,
      }};
    }}
    return computeOverlapMetrics(s.asis_items, s.actual_items);
  }}
  return {{
    top5_overlap_count: s.top5_overlap_count, top5_overlap_pct: s.top5_overlap_pct,
    top20_overlap_count: s.top20_overlap_count, top20_overlap_pct: s.top20_overlap_pct,
    overlap_count: s.overlap_count, overlap_pct: s.overlap_pct,
    match_category: s.match_category, top1_match: s.top1_match, expected_count: s.expected_count,
  }};
}}

function updateFilterTabCounts() {{
  // Assumes s.__m has already been (re)computed for every scenario by the
  // caller (renderScenarios(), right before this) for the active mode.
  let all = scenarios.length, exact = 0, set = 0, zero = 0;
  scenarios.forEach(s => {{
    const m = s.__m || getModeMetrics(s);
    if (m.match_category === '100_PERCENT_EXACT') exact++;
    if (m.match_category === '100_PERCENT_SET') set++;
    if (m.match_category === 'ZERO_RESULT') zero++;
  }});
  const setText = (id, v) => {{ const el = document.getElementById(id); if (el) el.textContent = v; }};
  setText('cnt-all', all);
  setText('cnt-exact', exact);
  setText('cnt-set', set);
  setText('cnt-zero', zero);
}}

// --- Bug tracking (per-keyword "cần fix Expected" marker) ---------------
// localStorage is shared across ALL file:// pages in most browsers, so every
// key is namespaced by REPORT_ID (derived from this report's own output
// folder) to avoid one report's bugs leaking into another report opened
// later in the same browser.
const REPORT_ID = {report_id_json};
const BUG_STORAGE_KEY = 'smartsearch_bugs::' + REPORT_ID;

let bugStore = {{}};       // persisted (localStorage): test_id -> {{query, dimension, route, note, screenshot, markedAt}}
let bugDraft = {{}};       // in-memory, unsaved edits while a panel is open: test_id -> {{note, screenshot}}
let openBugPanels = {{}};  // test_id -> bool

function loadBugStore() {{
  try {{
    const raw = localStorage.getItem(BUG_STORAGE_KEY);
    bugStore = raw ? JSON.parse(raw) : {{}};
  }} catch (e) {{
    console.warn('Không đọc được bug đã lưu trước đó:', e);
    bugStore = {{}};
  }}
}}

function persistBugStore() {{
  try {{
    localStorage.setItem(BUG_STORAGE_KEY, JSON.stringify(bugStore));
  }} catch (e) {{
    alert('Không lưu được vào bộ nhớ trình duyệt (có thể do đầy dung lượng). '
      + 'Bug vẫn được giữ tạm trong phiên xem này - hãy Xuất Bug ngay để không bị mất. Lỗi: ' + e.message);
  }}
}}

function updateExportButtonCount() {{
  const count = Object.keys(bugStore).length;
  for (const suffix of ['Html', 'Json']) {{
    const btn = document.getElementById('exportBug' + suffix + 'Btn');
    const countEl = document.getElementById('bugCount' + suffix);
    if (countEl) countEl.textContent = count;
    if (btn) btn.disabled = count === 0;
  }}
}}

function downloadBlob(content, mimeType, filename) {{
  const blob = new Blob([content], {{ type: mimeType }});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}}

function bugExportFilename(ext) {{
  // A browser tab (even a local file:// page) has NO way to force-save to an
  // arbitrary absolute filesystem path - that's a hard security boundary in
  // every browser, not something any web page can bypass. The one thing a
  // plain download CAN do is a subfolder relative to the browser's own
  // configured Downloads directory (Chrome/Edge honor a "sub/dir/name.ext"
  // path in the `download` attribute) - so exports land in
  // "<your Downloads folder>/bug_report/...". To get them landing directly
  // in SmartSearch/test_data/bug_report/ in the repo, either point your
  // browser's default download location at that folder once (Settings ->
  // Downloads), or hand the downloaded file to Claude to move it over.
  return 'bug_report/bug_report_' + REPORT_ID.replace(/[^a-zA-Z0-9_-]+/g, '_')
    + '_' + new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-') + '.' + ext;
}}

function syncDraftNoteFromDOM(testId) {{
  const ta = document.getElementById('bugtext-' + testId);
  if (!bugDraft[testId]) bugDraft[testId] = {{ note: '', screenshot: null }};
  if (ta) bugDraft[testId].note = ta.value;
}}

function toggleBugPanel(testId) {{
  const opening = !openBugPanels[testId];
  openBugPanels[testId] = opening;
  if (opening && !bugDraft[testId]) {{
    const existing = bugStore[testId];
    bugDraft[testId] = {{
      note: existing ? existing.note : '',
      screenshot: existing ? existing.screenshot : null,
    }};
  }}
  renderScenarios();
  const panel = document.getElementById('bugpanel-' + testId);
  if (panel && panel.classList.contains('open')) {{
    panel.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
  }}
}}

function resizeImageDataUrl(dataUrl, maxWidth, callback) {{
  const img = new Image();
  img.onload = () => {{
    let w = img.width, h = img.height;
    if (w > maxWidth) {{ h = Math.round(h * (maxWidth / w)); w = maxWidth; }}
    try {{
      const canvas = document.createElement('canvas');
      canvas.width = w; canvas.height = h;
      canvas.getContext('2d').drawImage(img, 0, 0, w, h);
      callback(canvas.toDataURL('image/jpeg', 0.82));
    }} catch (e) {{
      callback(dataUrl);
    }}
  }};
  img.onerror = () => callback(dataUrl);
  img.src = dataUrl;
}}

function readImageFile(file, callback) {{
  if (!file || !file.type || file.type.indexOf('image/') !== 0) return;
  const reader = new FileReader();
  reader.onload = (e) => resizeImageDataUrl(e.target.result, 1000, callback);
  reader.readAsDataURL(file);
}}

function setDraftScreenshot(testId, dataUrl) {{
  syncDraftNoteFromDOM(testId);
  bugDraft[testId].screenshot = dataUrl;
  renderScenarios();
}}

function handleBugPaste(event, testId) {{
  event.preventDefault();
  const items = (event.clipboardData || window.clipboardData || {{}}).items || [];
  for (const item of items) {{
    if (item.type && item.type.indexOf('image/') === 0) {{
      readImageFile(item.getAsFile(), (dataUrl) => setDraftScreenshot(testId, dataUrl));
      break;
    }}
  }}
}}

function handleBugDrop(event, testId) {{
  event.preventDefault();
  event.currentTarget.classList.remove('dragover');
  const files = (event.dataTransfer && event.dataTransfer.files) || [];
  if (files.length > 0) readImageFile(files[0], (dataUrl) => setDraftScreenshot(testId, dataUrl));
}}

function handleBugFile(event, testId) {{
  const file = event.target.files && event.target.files[0];
  if (file) readImageFile(file, (dataUrl) => setDraftScreenshot(testId, dataUrl));
}}

function saveBug(testId) {{
  syncDraftNoteFromDOM(testId);
  const draft = bugDraft[testId] || {{}};
  const sc = scenarios.find(x => x.test_id === testId) || {{}};
  bugStore[testId] = {{
    test_id: testId,
    query: sc.query || '',
    dimension: sc.dimension || '',
    route: sc.route || '',
    match_category: sc.match_category || '',
    note: draft.note || '',
    screenshot: draft.screenshot || null,
    markedAt: new Date().toISOString(),
  }};
  persistBugStore();
  updateExportButtonCount();
  openBugPanels[testId] = false;
  renderScenarios();
}}

function removeBug(testId) {{
  if (!confirm('Bỏ đánh dấu Bug cho keyword này?')) return;
  delete bugStore[testId];
  delete bugDraft[testId];
  persistBugStore();
  updateExportButtonCount();
  renderScenarios();
}}

function escapeHtmlText(str) {{
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}}

function exportAllBugsJson() {{
  const entries = Object.values(bugStore).sort((a, b) => (a.markedAt || '').localeCompare(b.markedAt || ''));
  if (entries.length === 0) {{
    alert('Chưa có bug nào được ghi nhận.');
    return;
  }}
  // No screenshot field on purpose - keeps the file small/text-only for
  // scripts or BA to read; the HTML export is the one that keeps images.
  const payload = {{
    exportedAt: new Date().toISOString(),
    reportId: REPORT_ID,
    totalBugs: entries.length,
    bugs: entries.map(b => ({{
      test_id: b.test_id,
      query: b.query,
      dimension: b.dimension,
      route: b.route,
      match_category: b.match_category,
      note: b.note,
      has_screenshot: !!b.screenshot,
      markedAt: b.markedAt,
    }})),
  }};
  downloadBlob(JSON.stringify(payload, null, 2), 'application/json', bugExportFilename('json'));
}}

function exportAllBugsHtml() {{
  const entries = Object.values(bugStore).sort((a, b) => (a.markedAt || '').localeCompare(b.markedAt || ''));
  if (entries.length === 0) {{
    alert('Chưa có bug nào được ghi nhận.');
    return;
  }}
  const rows = entries.map((b, i) => `
    <div style="border:1px solid #dde1ea;border-radius:10px;padding:16px;margin-bottom:16px;background:#ffffff;">
      <div style="font-weight:700;color:#14181f;font-size:15px;margin-bottom:6px;">#${{i + 1}} - ${{escapeHtmlText(b.test_id)}} - "${{escapeHtmlText(b.query)}}"</div>
      <div style="font-size:12px;color:#565f70;margin-bottom:10px;">Dimension: ${{escapeHtmlText(b.dimension)}} | Route: ${{escapeHtmlText(b.route)}} | Ghi nhận lúc: ${{new Date(b.markedAt).toLocaleString()}}</div>
      ${{b.screenshot ? `<img src="${{b.screenshot}}" style="max-width:600px;max-height:400px;border-radius:8px;display:block;margin-bottom:10px;border:1px solid #dde1ea;">` : '<div style="color:#7b8494;font-size:12px;margin-bottom:10px;">(Không có ảnh đính kèm)</div>'}}
      <div style="background:#f6f7fb;border:1px solid #dde1ea;border-radius:6px;padding:10px;font-size:13px;color:#14181f;white-space:pre-wrap;"><b>Expected đúng phải là:</b><br>${{escapeHtmlText(b.note) || '(chưa ghi chú)'}}</div>
    </div>
  `).join('');

  const doc = `<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8"><title>Danh sách Bug - Smart Search Compare</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background:#f6f7fb; color:#14181f; padding:24px; }}
  .wrap {{ max-width: 900px; margin: 0 auto; }}
  h1 {{ font-size: 20px; margin-bottom: 4px; }}
  .sub {{ color:#565f70; font-size:13px; margin-bottom:20px; }}
</style></head>
<body><div class="wrap">
  <h1>🐞 Danh sách Bug đã ghi nhận - Smart Search Compare</h1>
  <div class="sub">Xuất lúc ${{new Date().toLocaleString()}} - Tổng số: ${{entries.length}} bug - Nguồn: ${{REPORT_ID}}</div>
  ${{rows}}
</div></body></html>`;

  downloadBlob(doc, 'text/html', bugExportFilename('html'));
}}

loadBugStore();

function getBadgeHtml(cat, pct) {{
  if (cat === '100_PERCENT_EXACT') return `<span class="badge badge-exact" data-tooltip="Khớp hoàn hảo 100% đúng từng vị trí">⭐ 100% Exact</span>`;
  if (cat === '100_PERCENT_SET') return `<span class="badge badge-set" data-tooltip="Khớp đủ tất cả SKU (có thể đảo vị trí)">🟣 100% Set Match</span>`;
  if (cat === 'HIGH_MATCH') return `<span class="badge badge-high" data-tooltip="Độ trùng khớp cao trong Top-20">Khớp ${{pct}}%</span>`;
  if (cat === 'PARTIAL_MATCH') return `<span class="badge badge-partial" data-tooltip="Độ trùng khớp trung bình trong Top-20">Khớp ${{pct}}%</span>`;
  if (cat === 'LOW_MATCH') return `<span class="badge badge-low" data-tooltip="Độ lệch lớn, trùng khớp ít">Lệch nhiều (${{pct}}%)</span>`;
  if (cat === 'ZERO_RESULT') return `<span class="badge badge-zero" data-tooltip="API trả về danh sách rỗng (0 sản phẩm)">Zero Result</span>`;
  if (cat === 'NO_ASIS_DATA') return `<span class="badge badge-zero" data-tooltip="Chưa có dữ liệu As-Is trong cache cho query này - chạy compare_results.py để gọi/lưu cache rồi mở lại report.">Chưa có As-Is</span>`;
  return `<span class="badge badge-low" data-tooltip="Không trùng khớp sản phẩm nào">No Match (0%)</span>`;
}}

function getStatusTagHtml(status, rank, column) {{
  if (status === 'exact_rank') return `<span class="tag-status tag-exact" data-tooltip="[Mục 20] Sản phẩm đứng đúng chính xác vị trí thứ hạng ở cả Expected và Actual">✓ Đúng Rank</span>`;
  if (status === 'rank_shifted') return `<span class="tag-status tag-shift" data-tooltip="[Mục 23] Sản phẩm có xuất hiện nhưng bị trồi/sụt đến vị trí Rank ${{rank}}">↕ Rank ${{rank}}</span>`;
  if (status === 'outside_top') {{
    const tooltip = column === 'actual'
      ? `[Mục 22] SKU này nằm ngoài Top 20 của Expected (Expected rank ${{rank}}), nhưng Actual đã đưa vào Top 20.`
      : `[Mục 22] SKU này có trong Expected Top 20 nhưng Actual đẩy xuống ngoài Top 20 (Actual rank ${{rank}}).`;
    return `<span class="tag-status tag-outside" data-tooltip="${{tooltip}}">Out Top (${{rank}})</span>`;
  }}
  if (status === 'missing') return `<span class="tag-status tag-missing" data-tooltip="[Mục 21] Sản phẩm mong đợi trong Top 20 nhưng Actual KHÔNG tìm thấy trong Top 20">✗ Missing</span>`;
  if (status === 'extra') return `<span class="tag-status tag-extra" data-tooltip="Sản phẩm lạ do Actual trả về, không nằm trong danh sách mong đợi">+ Extra</span>`;
  return '';
}}

function renderScenarios() {{
  const listEl = document.getElementById('scenarioList');
  const pagEl = document.getElementById('paginationInfo');

  // Recompute per-scenario metrics for the active comparisonMode and stash
  // them on the scenario object (s.__m) - cheap (plain array ops over
  // already-embedded items, no server round-trip) and keeps every other `s.*`
  // reference below (query/test_id/expected_items/actual_items/asis_items/...)
  // untouched regardless of mode.
  scenarios.forEach(s => {{ s.__m = getModeMetrics(s); }});
  updateFilterTabCounts();

  const filtered = scenarios.filter(s => {{
    const matchFilter = (currentFilter === 'all') || (s.__m.match_category === currentFilter);
    if (!matchFilter) return false;

    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return s.query.toLowerCase().includes(q) ||
           s.test_id.toLowerCase().includes(q) ||
           s.expected_items.some(i => i.name.toLowerCase().includes(q) || i.sku.includes(q)) ||
           s.actual_items.some(i => i.name.toLowerCase().includes(q) || i.sku.includes(q));
  }});

  if (sortOrder !== 'default') {{
    filtered.sort((a, b) => {{
      const difference = Number(a.__m.top20_overlap_pct || 0) - Number(b.__m.top20_overlap_pct || 0);
      return sortOrder === 'low' ? difference : -difference;
    }});
  }}

  const total = filtered.length;
  const pageSize = selectedPageSize === 'all' ? total || 1 : selectedPageSize;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  currentPage = Math.min(currentPage, totalPages);
  const start = (currentPage - 1) * pageSize;
  const paged = filtered.slice(start, start + pageSize);

  if (total === 0) {{
    listEl.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-muted); background: var(--card-bg); border-radius: 12px;">Không tìm thấy scenario phù hợp bộ lọc.</div>`;
    pagEl.innerHTML = 'Không có dữ liệu trong trang này.';
    updatePaginationControls(1, 1);
    return;
  }}

  listEl.innerHTML = paged.map(s => `
    <div class="scenario-card" id="card-${{s.test_id}}">
      <div class="scenario-header" onclick="toggleCard('${{s.test_id}}')">
        <div class="scenario-title-area">
          <span class="scenario-id">${{s.test_id}}</span>
          <span class="scenario-query">"${{s.query}}"</span>
          ${{getBadgeHtml(s.__m.match_category, s.__m.top20_overlap_pct)}}
          ${{s.__m.top1_match ? '<span class="badge badge-exact" data-tooltip="Sản phẩm Top-1 khớp chính xác giữa 2 nguồn đang so sánh">Top-1 Match</span>' : ''}}
        </div>
        <div class="scenario-badges">
          <span class="meta-tag" data-tooltip="Chiều kiểm thử / Dimension của từ khóa">Dim: ${{s.dimension}}</span>
          <span class="meta-tag" data-tooltip="Luồng xử lý route (keyword hoặc keyword_ai)">Route: ${{s.route || 'auto'}}</span>
          ${{s.actual_latency_ms != null ? `<span class="meta-tag" data-tooltip="Thời gian API search (Actual) thực sự phản hồi khi lấy dữ liệu này - đo lúc chạy data test, lưu sẵn trong file actual.">⏱️ ${{s.actual_latency_ms}}ms</span>` : ''}}
          <span class="meta-tag" data-tooltip="[Mục 16] Số SKU trùng khớp trong 5 kết quả đầu tiên, theo chế độ so sánh đang chọn (${{s.__m.top5_overlap_count}}/5 sản phẩm)">Top-5: ${{s.__m.top5_overlap_count}}/5 (${{s.__m.top5_overlap_pct}}%)</span>
          <span class="meta-tag" style="background: rgba(2, 132, 199, 0.12); color: #0369a1; font-weight: 600;" data-tooltip="[Mục 17] Số SKU trùng khớp trong 20 kết quả đầu tiên, theo chế độ so sánh đang chọn (${{s.__m.top20_overlap_count}}/${{s.__m.expected_count}} sản phẩm)">Top-20: ${{s.__m.top20_overlap_count}}/${{s.__m.expected_count}} (${{s.__m.top20_overlap_pct}}%)</span>
          <button type="button" class="bug-btn ${{bugStore[s.test_id] ? 'marked' : ''}}" id="bugbtn-${{s.test_id}}"
                  data-tooltip="Đánh dấu keyword này cần fix lại Expected (kèm ảnh chụp UI thực tế và ghi chú Expected đúng phải là gì)"
                  onclick="event.stopPropagation(); toggleBugPanel('${{s.test_id}}')">🐞 ${{bugStore[s.test_id] ? 'Đã ghi Bug' : 'Fix Expected'}}</button>
          <span style="color: var(--text-muted); font-size: 12px;">▼</span>
        </div>
      </div>
      <div class="bug-panel ${{openBugPanels[s.test_id] ? 'open' : ''}}" id="bugpanel-${{s.test_id}}">
        <div class="bug-panel-title">🐞 Đánh dấu Bug - cần sửa lại Expected cho keyword "${{s.query}}"</div>
        <span class="bug-field-label">Ảnh chụp UI thực tế (dán bằng Ctrl+V sau khi click vào khung dưới đây, hoặc chọn file):</span>
        <div class="paste-zone ${{(bugDraft[s.test_id] && bugDraft[s.test_id].screenshot) ? 'has-image' : ''}}" id="pastezone-${{s.test_id}}"
             tabindex="0" contenteditable="true"
             onpaste="handleBugPaste(event, '${{s.test_id}}')"
             ondragover="event.preventDefault(); this.classList.add('dragover');"
             ondragleave="this.classList.remove('dragover');"
             ondrop="handleBugDrop(event, '${{s.test_id}}')">${{(bugDraft[s.test_id] && bugDraft[s.test_id].screenshot)
              ? `<img class="bug-thumb" src="${{bugDraft[s.test_id].screenshot}}">`
              : 'Click vào đây rồi dán ảnh (Ctrl+V), hoặc kéo-thả ảnh vào'}}</div>
        <div style="margin: 6px 0 12px;">
          <span class="bug-pick-file" onclick="document.getElementById('bugfile-${{s.test_id}}').click()">📎 hoặc chọn file ảnh...</span>
        </div>
        <input type="file" accept="image/*" class="bug-file-input" id="bugfile-${{s.test_id}}" onchange="handleBugFile(event, '${{s.test_id}}')">
        <span class="bug-field-label">Expected đúng phải là (ghi rõ để BA/Dev fix lại dữ liệu expected):</span>
        <textarea class="bug-textarea" id="bugtext-${{s.test_id}}" placeholder="Ví dụ: SKU 123456 phải xếp Top-1 vì khớp tên chính xác, expected hiện tại đang để SKU khác lên đầu là sai...">${{(bugDraft[s.test_id] && bugDraft[s.test_id].note) || ''}}</textarea>
        <div class="bug-actions">
          <button type="button" class="bug-save-btn" onclick="saveBug('${{s.test_id}}')">💾 Lưu Bug</button>
          <button type="button" class="bug-cancel-btn" onclick="toggleBugPanel('${{s.test_id}}')">Đóng</button>
          ${{bugStore[s.test_id] ? `<button type="button" class="bug-remove-btn" onclick="removeBug('${{s.test_id}}')">🗑 Bỏ đánh dấu</button>` : ''}}
          ${{bugStore[s.test_id] ? `<span class="bug-saved-note">Đã lưu lúc ${{new Date(bugStore[s.test_id].markedAt).toLocaleString()}}</span>` : ''}}
        </div>
      </div>
      <div class="scenario-body" id="body-${{s.test_id}}">
        <div class="compare-columns ${{panelsClass()}}">
          ${{HAS_ASIS ? `
          <!-- As-Is Column (current/legacy production system - reference only, not scored) -->
          <div class="col-box asis-box">
            <div class="col-title">
              <span>🕰️ As-Is (Hệ thống hiện tại) (${{s.asis_items.length}})</span>
              <span data-tooltip="Kết quả từ hệ thống search ĐANG chạy thật trên lottemart.vn hôm nay (không phải hệ thống mới đang test) - chỉ để tham khảo, không tính điểm/so khớp với Expected.">TOTAL BEFORE CAP: ${{s.asis_total_before_cap ?? '-'}} ⓘ</span>
            </div>
            <table class="prod-table">
              <thead>
                <tr>
                  <th style="width: 30px;">#</th>
                  <th>SKU / Sản phẩm</th>
                </tr>
              </thead>
              <tbody>
                ${{s.asis_items.length ? s.asis_items.map(it => `
                  <tr>
                    <td><span class="rank-num">${{it.rank}}</span></td>
                    <td>
                      <span class="item-name">${{it.name}}</span>
                      <span class="item-meta">SKU: ${{it.sku}} | ${{Number(it.price || 0).toLocaleString()}} đ</span>
                    </td>
                  </tr>
                `).join('') : (s.asis_cached
                    ? `<tr><td colspan="2" style="color:var(--text-muted);padding:12px 8px;">Đã gọi hệ thống As-Is cho query này - hệ thống hiện tại (lottemart.vn) trả về 0 kết quả thật (không phải do chưa lấy dữ liệu).</td></tr>`
                    : `<tr><td colspan="2" style="color:var(--text-muted);padding:12px 8px;">(Chưa có dữ liệu As-Is cho query này trong cache)</td></tr>`)}}
              </tbody>
            </table>
          </div>
          ` : ''}}

          ${{showExpected ? `
          <!-- Expected Column -->
          <div class="col-box">
            <div class="col-title">
              <span>📋 Expected Top Results (${{s.expected_items.length}})</span>
              <span data-tooltip="[Mục 18] Tổng số sản phẩm thỏa mãn tìm kiếm trong catalog gốc trước khi lấy Top 20 (hoặc Cap 80)">TOTAL BEFORE CAP: ${{s.expected_total_before_cap}} ⓘ</span>
            </div>
            <table class="prod-table">
              <thead>
                <tr>
                  <th style="width: 30px;">#</th>
                  <th>SKU / Sản phẩm</th>
                  <th>Tier / Score</th>
                  <th>Trạng thái Actual</th>
                </tr>
              </thead>
              <tbody>
                ${{s.expected_items.map(it => `
                  <tr>
                    <td><span class="rank-num">${{it.rank}}</span></td>
                    <td>
                      <span class="item-name">${{it.name}}</span>
                      <span class="item-meta">SKU: ${{it.sku}} | ${{Number(it.price || 0).toLocaleString()}} đ</span>
                    </td>
                    <td><span class="meta-tag" style="margin:0;" data-tooltip="Tier chấm điểm và độ liên quan của sản phẩm">${{it.tier || '-'}} (${{it.score || '-'}})</span></td>
                    <td>${{getStatusTagHtml(it.status, it.actual_rank, 'expected')}}</td>
                  </tr>
                `).join('')}}
              </tbody>
            </table>
          </div>
          ` : ''}}

          <!-- Actual Column -->
          <div class="col-box">
            <div class="col-title">
              <span>🚀 Actual Top Results (${{s.actual_items.length}})</span>
              <span data-tooltip="[Mục 19] Tổng số sản phẩm do hệ thống Actual tìm thấy trước khi phân trang hiển thị Top 20">TOTAL BEFORE CAP: ${{s.actual_total_before_cap}} ⓘ</span>
            </div>
            <table class="prod-table">
              <thead>
                <tr>
                  <th style="width: 30px;">#</th>
                  <th>SKU / Sản phẩm</th>
                  <th>Tier / Score</th>
                  <th>So với Expected</th>
                </tr>
              </thead>
              <tbody>
                ${{s.actual_items.map(it => `
                  <tr>
                    <td><span class="rank-num">${{it.rank}}</span></td>
                    <td>
                      <span class="item-name">${{it.name}}</span>
                      <span class="item-meta">SKU: ${{it.sku}} | ${{Number(it.price || 0).toLocaleString()}} đ</span>
                    </td>
                    <td><span class="meta-tag" style="margin:0;" data-tooltip="Chế độ search mode và điểm số của backend">${{it.tier || '-'}} (${{it.score || '-'}})</span></td>
                    <td>${{getStatusTagHtml(it.status, it.expected_rank, 'actual')}}</td>
                  </tr>
                `).join('')}}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `).join('');

  pagEl.innerHTML = `Hiển thị ${{start + 1}} - ${{Math.min(start + pageSize, total)}} trên tổng số ${{total}} scenarios (trang ${{currentPage}}/${{totalPages}})`;
  updatePaginationControls(currentPage, totalPages);
}}

function updatePaginationControls(page, totalPages) {{
  document.getElementById('prevPage').disabled = page <= 1;
  document.getElementById('nextPage').disabled = page >= totalPages;
}}

function toggleCard(id) {{
  const body = document.getElementById('body-' + id);
  if (body) body.classList.toggle('open');
}}

// Event Listeners
document.querySelectorAll('.tab-btn').forEach(btn => {{
  btn.addEventListener('click', (e) => {{
    // currentTarget (not target) - the count is now wrapped in a <span> inside
    // some tab labels, so a click landing on the digits would otherwise miss
    // data-filter/active entirely.
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    e.currentTarget.classList.add('active');
    currentFilter = e.currentTarget.getAttribute('data-filter');
    currentPage = 1;
    renderScenarios();
  }});
}});

document.getElementById('modeSelect').addEventListener('change', (e) => {{
  comparisonMode = e.target.value;
  currentPage = 1;
  renderScenarios();
}});

document.getElementById('showExpectedToggle').addEventListener('change', (e) => {{
  showExpected = e.target.checked;
  renderScenarios();
}});

document.getElementById('searchInput').addEventListener('input', (e) => {{
  searchQuery = e.target.value;
  currentPage = 1;
  renderScenarios();
}});

document.getElementById('prevPage').addEventListener('click', () => {{
  if (currentPage > 1) {{
    currentPage -= 1;
    renderScenarios();
    window.scrollTo({{ top: document.getElementById('scenarioList').offsetTop - 16, behavior: 'smooth' }});
  }}
}});

document.getElementById('nextPage').addEventListener('click', () => {{
  currentPage += 1;
  renderScenarios();
  window.scrollTo({{ top: document.getElementById('scenarioList').offsetTop - 16, behavior: 'smooth' }});
}});

document.getElementById('pageSizeSelect').addEventListener('change', (e) => {{
  selectedPageSize = e.target.value === 'all' ? 'all' : Number(e.target.value);
  currentPage = 1;
  renderScenarios();
}});

document.getElementById('sortSelect').addEventListener('change', (e) => {{
  sortOrder = e.target.value;
  currentPage = 1;
  renderScenarios();
}});

document.getElementById('exportBugHtmlBtn').addEventListener('click', exportAllBugsHtml);
document.getElementById('exportBugJsonBtn').addEventListener('click', exportAllBugsJson);
updateExportButtonCount();

// Initial render
renderScenarios();
</script>
</body>
</html>
"""
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html_content)


def main():
    parser = argparse.ArgumentParser(description="Compare Search Results (Expected vs Actual)")
    parser.add_argument("--expected", required=True, help="Path to Expected JSON file")
    parser.add_argument("--actual", required=True, help="Path to Actual JSON file")
    parser.add_argument("--no-asis", action="store_true",
                         help="skip the As-Is panel entirely (no cache lookup, no legacy calls) - "
                              "the normal offline expected-vs-actual compare only.")
    parser.add_argument("--no-asis-fetch", action="store_true",
                         help="use the As-Is cache for already-cached queries but never call the "
                              "real legacy system for a cache miss (still free/offline) - use this "
                              "if you want to compare without risking any real production calls.")
    parser.add_argument("--out-dir", default=None, help="Output directory for comparison results")
    parser.add_argument("--topn", type=int, default=30, help="Top-N results shown/compared when a keyword is "
                                                               "expanded (default 30) - independent of the "
                                                               "fixed Top-5/Top-10/Top-20 KPI metrics below, "
                                                               "which always measure those exact windows "
                                                               "regardless of this value")
    args = parser.parse_args()

    exp_path = Path(args.expected)
    act_path = Path(args.actual)

    if not exp_path.exists():
        sys.exit(f"File expected không tồn tại: {exp_path}")
    if not act_path.exists():
        sys.exit(f"File actual không tồn tại: {act_path}")

    exp_data = load_json(exp_path)
    act_data = load_json(act_path)

    exp_scenarios = exp_data.get("scenarios", [])
    act_scenarios = act_data.get("scenarios", [])

    # Backfill product name/price/category from the real catalog wherever a
    # search_results item doesn't already carry one (raw/non-denormalized
    # inputs only have {sku, score, tier}) - see fill_missing_names()'s
    # docstring. Cheap no-op for inputs that already have names.
    fill_missing_names(exp_scenarios, exp_data.get("store", "nsg"))
    fill_missing_names(act_scenarios, act_data.get("store", "nsg"))

    # Index expected by test_id and query
    exp_by_id = {s.get("test_id"): s for s in exp_scenarios if "test_id" in s}
    exp_by_query = {normalize_query(s.get("query")): s for s in exp_scenarios if "query" in s}

    # As-Is: ONE persistent cache file (SmartSearch/test_data/json/actual/
    # AsIs_NSG_cache.json), never an uploaded/passed-in file - see
    # get_or_fetch_asis()'s docstring. Only consulted for a scenario whose
    # Expected-vs-Actual match is at/under ASIS_MATCH_THRESHOLD_PCT (50%);
    # a real legacy-system call happens ONLY on a genuine cache miss for
    # such a scenario, and only if --no-asis-fetch wasn't passed.
    asis_cache = load_asis_cache() if not args.no_asis else None
    asis_lookups = 0
    asis_fetched_new = 0

    # Match actual scenarios against expected
    compared_list = []
    matched_by_id_count = 0
    matched_by_query_count = 0
    unmatched_count = 0

    for act_sc in act_scenarios:
        test_id = act_sc.get("test_id")
        query_norm = normalize_query(act_sc.get("query"))

        exp_sc = None
        if test_id and test_id in exp_by_id:
            exp_sc = exp_by_id[test_id]
            matched_by_id_count += 1
        elif query_norm in exp_by_query:
            exp_sc = exp_by_query[query_norm]
            matched_by_query_count += 1
        else:
            unmatched_count += 1
            exp_sc = {"test_id": test_id, "query": act_sc.get("query"), "search_results": []}

        res = compare_scenario(exp_sc, act_sc, top_n=args.topn)

        if asis_cache is not None:
            # Display: look up (and show) As-Is for EVERY scenario, regardless of
            # match% - a cache read costs nothing. Fetch-if-missing stays gated
            # to <=50% match (ASIS_MATCH_THRESHOLD_PCT) so a dataset that hasn't
            # been pre-fetched this way doesn't silently trigger a real call (and
            # real cost) for every single scenario, not just the poor matches.
            query_text = exp_sc.get("query") or act_sc.get("query") or ""
            was_cached = normalize_query(query_text) in asis_cache["entries"]
            allow_fetch = (not args.no_asis_fetch) and res["top30_overlap_pct"] <= ASIS_MATCH_THRESHOLD_PCT
            asis_sc = get_or_fetch_asis(query_text, asis_cache, allow_fetch=allow_fetch)
            if asis_sc is not None:
                asis_lookups += 1
                if not was_cached:
                    asis_fetched_new += 1
                res["asis_items"] = build_asis_items(asis_sc, args.topn)
                res["asis_total_before_cap"] = asis_sc.get("search_results_total_before_cap")
                res["asis_cached"] = True

        compared_list.append(res)

    # Separate 100% matches and mismatches
    matched_100_percent = [s for s in compared_list if s["is_100_percent_set_match"] or s["is_100_percent_exact_order"]]
    mismatched_keywords = [s for s in compared_list if not (s["is_100_percent_set_match"] or s["is_100_percent_exact_order"])]

    # Compute aggregate stats
    total = len(compared_list)
    exact_order_count = sum(1 for s in compared_list if s["is_100_percent_exact_order"])
    set_match_count = sum(1 for s in compared_list if s["is_100_percent_set_match"])
    top1_match_count = sum(1 for s in compared_list if s["top1_match"])
    zero_result_count = sum(1 for s in compared_list if s["match_category"] == "ZERO_RESULT")

    top5_overlaps = [s["top5_overlap_pct"] for s in compared_list]
    avg_top5_overlap = round(sum(top5_overlaps) / max(1, len(top5_overlaps)), 1)

    top10_overlaps = [s["top10_overlap_pct"] for s in compared_list]
    avg_top10_overlap = round(sum(top10_overlaps) / max(1, len(top10_overlaps)), 1)

    top20_overlaps = [s["top20_overlap_pct"] for s in compared_list]
    avg_top20_overlap = round(sum(top20_overlaps) / max(1, len(top20_overlaps)), 1)

    overlaps = [s["overlap_pct"] for s in compared_list]
    avg_overlap = round(sum(overlaps) / max(1, len(overlaps)), 1)

    stats = {
        "timestamp": datetime.now().isoformat(),
        "expected_file": str(exp_path),
        "actual_file": str(act_path),
        "asis_cache_file": str(ASIS_CACHE_PATH) if asis_cache is not None else None,
        "asis_match_threshold_pct": ASIS_MATCH_THRESHOLD_PCT if asis_cache is not None else None,
        "asis_scenarios_used": asis_lookups if asis_cache is not None else None,
        "asis_newly_fetched": asis_fetched_new if asis_cache is not None else None,
        "total_scenarios": total,
        "matched_by_test_id": matched_by_id_count,
        "matched_by_query": matched_by_query_count,
        "unmatched_scenarios": unmatched_count,
        "exact_order_count": exact_order_count,
        "exact_order_pct": round(exact_order_count / max(1, total) * 100, 1),
        "set_match_count": set_match_count,
        "set_match_pct": round(set_match_count / max(1, total) * 100, 1),
        "top1_match_count": top1_match_count,
        "top1_match_pct": round(top1_match_count / max(1, total) * 100, 1),
        "mismatch_count": len(mismatched_keywords),
        "mismatch_pct": round(len(mismatched_keywords) / max(1, total) * 100, 1),
        "zero_result_count": zero_result_count,
        "avg_overlap_pct": avg_overlap,
        "avg_top5_overlap_pct": avg_top5_overlap,
        "avg_top10_overlap_pct": avg_top10_overlap,
        "avg_top20_overlap_pct": avg_top20_overlap,
        "breakdown_by_category": {
            "100_PERCENT_EXACT": exact_order_count,
            "100_PERCENT_SET": set_match_count,
            "HIGH_MATCH": sum(1 for s in compared_list if s["match_category"] == "HIGH_MATCH"),
            "PARTIAL_MATCH": sum(1 for s in compared_list if s["match_category"] == "PARTIAL_MATCH"),
            "LOW_MATCH": sum(1 for s in compared_list if s["match_category"] == "LOW_MATCH"),
            "ZERO_RESULT": zero_result_count,
            "NO_MATCH": sum(1 for s in compared_list if s["match_category"] == "NO_MATCH"),
        }
    }

    # Determine out_dir: ALWAYS date+time-marked (not just date - two runs on
    # the same day must get visibly different folder names on their own,
    # not just when they happen to collide), derived from the expected/
    # actual filenames when possible (e.g.
    # "run_realsearch_top1000_20260828_143022"), falling back to a bare
    # label if none can be extracted. Every run must land in a brand-new
    # folder - old comparison folders are NEVER deleted or silently
    # overwritten, so next_free_dir() is kept as a last-resort safety net
    # for the rare case of two runs within the same second.
    if args.out_dir:
        preferred_out_dir = Path(args.out_dir)
    else:
        label = derive_label(exp_path, act_path)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        preferred_out_dir = Path(f"SmartSearch/test_data/compare/run_{label}_{ts_str}")
    out_dir = next_free_dir(preferred_out_dir)
    if out_dir != preferred_out_dir:
        print(f"[note] {preferred_out_dir} đã tồn tại và có dữ liệu - không ghi đè, "
              f"tạo thư mục mới: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save files
    save_json(out_dir / "matched_100_percent.json", {
        "description": "Các keyword matching 100% search result làm chuẩn",
        "timestamp": stats["timestamp"],
        "count": len(matched_100_percent),
        "scenarios": matched_100_percent
    })

    save_json(out_dir / "mismatched_keywords.json", {
        "description": "Danh sách các keyword bị lệch/lỗi so với expected",
        "timestamp": stats["timestamp"],
        "count": len(mismatched_keywords),
        "scenarios": mismatched_keywords
    })

    save_json(out_dir / "summary_stats.json", stats)

    # Generate HTML Dashboard with Tooltips
    generate_html_report(stats, compared_list, exp_data, act_data, out_dir / "compare_report.html",
                          report_id=str(out_dir).replace("\\", "/"))

    print(f"\n=======================================================")
    print(f"🎉 SO SÁNH HOÀN TẤT & ĐÃ TẠO HTML CÓ TOOLTIP!")
    print(f"📂 Thư mục output: {out_dir}")
    if asis_cache is not None:
        print(f"🕰️  As-Is: hiển thị cho {asis_lookups}/{total} scenario (mọi mức % khớp, miễn có trong cache) - "
              f"{asis_fetched_new} query mới phải gọi hệ thống cũ thật (chỉ tự động gọi khi ≤{ASIS_MATCH_THRESHOLD_PCT}% khớp), "
              f"{asis_lookups - asis_fetched_new} lấy từ cache có sẵn. Cache: {ASIS_CACHE_PATH}")
    print(f"=======================================================\n")


if __name__ == "__main__":
    main()
