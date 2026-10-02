# -*- coding: utf-8 -*-
"""Chuyển kết quả crawl_asis_full.py thành file cache mà compare_results.py đọc.

crawl_asis_full ghi ra dạng {"scenarios": [...]} còn compare đọc dạng
{"entries": {query_đã_chuẩn_hoá: {...}}}. Trước đây bước này làm tay; viết lại
thành script vì bộ ko/en cần cache RIÊNG cho từng ngôn ngữ - cùng chuỗi query
gọi lang khác nhau ra tập sản phẩm khác nhau, dùng chung một file là ghi đè
lẫn nhau và tạo ra dữ liệu As-Is sai không cách nào phát hiện.

Chạy:
  python scripts/automation/build_asis_cache.py \\
      --in SmartSearch/client_report/data/asis_ko_20260917.json --lang ko
"""
import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]


def load_compare():
    spec = importlib.util.spec_from_file_location(
        "cr", ROOT / "scripts/automation/compare_results.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="src", required=True, help="file asis_*.json của crawl_asis_full")
    ap.add_argument("--lang", required=True, help="ngôn ngữ của bộ này (ko/en/vi)")
    ap.add_argument("--out", default=None, help="mặc định: AsIs_NSG_cache_<lang>.json")
    args = ap.parse_args()

    cr = load_compare()
    src = json.loads(Path(args.src).read_text(encoding="utf-8"))
    scenarios = src.get("scenarios") or []

    out_path = Path(args.out) if args.out else cr.asis_cache_path_for(args.lang)
    entries, n_err, n_zero = {}, 0, 0
    for s in scenarios:
        q = s.get("query")
        if not q:
            continue
        if s.get("search_error"):
            # Dòng lỗi KHÔNG được vào cache: cache là "đã hỏi rồi, khỏi hỏi
            # lại", ghi một lần lỗi vào là vĩnh viễn coi query đó có 0 kết quả.
            n_err += 1
            continue
        res = s.get("search_results") or []
        if not res:
            n_zero += 1
        entries[cr.normalize_query(q)] = {
            "query": q,
            "fetchedAt": src.get("crawledAt") or datetime.now().isoformat(),
            "search_results": res,
            "search_results_total_before_cap": s.get("search_total_before_cap"),
            "search_latency_ms": s.get("search_latency_ms"),
            "autocomplete_suggestions": s.get("autocomplete_suggestions"),
            "autocomplete_latency_ms": s.get("autocomplete_latency_ms"),
        }

    payload = {
        "store": src.get("store") or "nsg",
        "lang": args.lang,
        "createdAt": datetime.now().isoformat(timespec="seconds"),
        "source": src.get("system") or "legacy (lottemart.vn)",
        "rebuiltFrom": str(Path(args.src).as_posix()),
        "searchApi": src.get("searchApi"),
        "entries": entries,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"lang={args.lang} | {len(scenarios):,} scenario -> {len(entries):,} entry")
    print(f"  bỏ vì lỗi gọi API : {n_err}")
    print(f"  trả về 0 kết quả  : {n_zero:,} ({n_zero/max(len(entries),1)*100:.1f}%)")
    print(f"  API dùng          : {src.get('searchApi')}")
    print(f"  -> {out_path}  ({out_path.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
