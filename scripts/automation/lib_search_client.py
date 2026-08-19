#!/usr/bin/env python3
"""HTTP client helpers shared by the golden-set runners.

Kept deliberately small and dependency-free (stdlib urllib only, matching
runner_text_search.py) since the real API contract is not fixed yet - only
--result-path / common-key fallbacks are assumed.
"""
import json
import ssl
import time
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


def call_api(api_url, method, param, query, headers, timeout=30):
    """Returns (parsed_json, latency_ms). Raises ApiError on failure."""
    start = time.time()
    ctx = ssl.create_default_context()
    try:
        if method == "GET":
            qstr = parse.urlencode({param: query})
            url = api_url + ("&" if "?" in api_url else "?") + qstr
            req = request.Request(url, headers=headers, method="GET")
        else:
            body = json.dumps({param: query}).encode("utf-8")
            hdrs = dict(headers)
            hdrs["Content-Type"] = "application/json"
            req = request.Request(api_url, data=body, headers=hdrs, method="POST")
        with request.urlopen(req, context=ctx, timeout=timeout) as resp:
            raw = resp.read()
        latency_ms = int((time.time() - start) * 1000)
        return json.loads(raw.decode("utf-8")), latency_ms
    except Exception as e:
        latency_ms = int((time.time() - start) * 1000)
        raise ApiError(str(e)) from e
    finally:
        pass


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


def extract_keyword_list(payload, result_path):
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
            for k in ("keyword", "query", "text", "suggestion", "title"):
                if item.get(k):
                    out.append(str(item[k]))
                    break
    return out
