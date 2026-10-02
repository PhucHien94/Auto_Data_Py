# -*- coding: utf-8 -*-
"""Dashboard so sánh text search DEV (Actual) vs PROD (As-Is) cho danh sách keyword
trong Part1_SmartSearch_QueryList.xlsx (batch part1vi / part1ko do
scripts/testdata/import_part1_querylist.py sinh ra).

Nguồn:
  - mảng `scenarios` trong compare_report.html của run_PART1_VI_* / run_PART1_KO_* mới nhất
  - batch Expected (giữ ghi chú Excel: Actual - Expected, Fix status Sep 18, sheet/No.)
  - keyword bị removed_scenarios_nsg.json loại khỏi compare vẫn được đưa vào, tính
    trực tiếp từ file Actual + cache As-Is (gắn nhãn "QA đã loại khỏi bộ chính").

Độ khớp dùng đúng compute_asis_match_category() của compare_results.py:
  % SKU trong top-20 PROD có xuất hiện trong top-30 DEV (ngưỡng 70/30).

Usage:
  python scripts/automation/build_part1_dashboard.py
  python scripts/automation/build_part1_dashboard.py --vi <run dir> --ko <run dir>
"""
import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_qa_dashboard import load_scenarios, latest_run  # noqa: E402
from compare_results import compute_asis_match_category, normalize_query  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ACTUAL_DIR = ROOT / "SmartSearch" / "test_data" / "json" / "actual"
OUT_DIR = ROOT / "SmartSearch" / "client_report"
ASIS_CACHE = {"vi": "AsIs_NSG_cache.json", "ko": "AsIs_NSG_cache_ko.json"}
TOPN = 10
SCORING_TOPN = 30  # = scoring_top_n của compare_results.py (chấm trên top-30 Dev)


def overlap_pct(asis, actual):
    top = [str(i.get("sku")) for i in (asis or [])[:20]]
    act = {str(i.get("sku")) for i in (actual or [])}
    return round(sum(1 for s in top if s in act) / len(top) * 100) if top else None


def slim(items, n=TOPN):
    return [{"sku": str(i.get("sku")), "name": i.get("name")} for i in (items or [])[:n]]


def rows_for(run_dir, lang):
    summ = json.loads((run_dir / "summary_stats.json").read_text(encoding="utf-8"))
    exp = json.loads((ROOT / summ["expected_file"]).read_text(encoding="utf-8"))
    act = json.loads((ROOT / summ["actual_file"]).read_text(encoding="utf-8"))
    comp = {s["test_id"]: s for s in load_scenarios(run_dir)}
    act_by = {s["test_id"]: s for s in act["scenarios"]}
    cache = json.loads((ACTUAL_DIR / ASIS_CACHE[lang]).read_text(encoding="utf-8"))["entries"]
    rows = []
    for e in exp["scenarios"]:
        c = comp.get(e["test_id"])
        if c:
            dev, prod = c.get("actual_items") or [], c.get("asis_items")
            dev_total, prod_total = c.get("actual_total_hits") or c.get("actual_total_before_cap"), c.get("asis_total_before_cap")
            ac_dev = [i.get("text") for i in (c.get("autocomplete_actual_items") or [])]
            ac_prod = [i.get("text") for i in (c.get("autocomplete_asis_items") or [])]
            removed = False
        else:  # bị removed_scenarios loại khỏi compare
            a = act_by.get(e["test_id"], {})
            ce = cache.get(normalize_query(e["query"])) or {}
            dev, prod = a.get("search_results") or [], ce.get("search_results")
            dev_total = (a.get("response_meta") or {}).get("totalHits") or len(dev)
            prod_total = ce.get("search_results_total_before_cap")
            ac_dev = [x.get("text") if isinstance(x, dict) else x for x in (a.get("autocomplete_suggestions") or [])]
            ac_prod = list(ce.get("autocomplete_suggestions") or [])
            removed = True
        cat = compute_asis_match_category(prod, dev[:SCORING_TOPN])
        rows.append({
            "id": e["test_id"], "lang": lang, "query": e["query"], "removed": removed,
            "sources": [{k: s.get(k) for k in ("sheet", "no", "raw_query", "actual_expected",
                                                "fix_status_sep18", "last_fix_date", "last_fix_status")}
                        for s in e.get("sources", [])],
            "cat": cat or "NO_ASIS", "ov": overlap_pct(prod, dev[:SCORING_TOPN]),
            "dev_n": dev_total, "prod_n": prod_total,
            "dev": slim(dev), "prod": slim(prod),
            "ac_dev": ac_dev[:8], "ac_prod": ac_prod[:8],
        })
    return rows, summ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vi")
    ap.add_argument("--ko")
    ap.add_argument("--out")
    args = ap.parse_args()
    vi_dir = Path(args.vi) if args.vi else latest_run("run_PART1_VI_")
    ko_dir = Path(args.ko) if args.ko else latest_run("run_PART1_KO_")
    rows, summ = rows_for(vi_dir, "vi")
    if ko_dir:
        rows += rows_for(ko_dir, "ko")[0]
    stamp = datetime.fromisoformat(summ["timestamp"])
    exp = json.loads((ROOT / summ["expected_file"]).read_text(encoding="utf-8"))
    meta = {
        "generated": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "run_at": stamp.strftime("%d/%m/%Y %H:%M"),
        "source": exp.get("source", ""),
        "runs": [str(p.relative_to(ROOT)) for p in (vi_dir, ko_dir) if p],
    }
    tpl = (Path(__file__).parent / "part1_dashboard_template.html").read_text(encoding="utf-8")
    out = Path(args.out) if args.out else OUT_DIR / f"SmartSearch_Part1_DevVsProd_NSG_{stamp:%Y%m%d}.html"
    data = json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False).replace("</", "<\\/")
    out.write_text(tpl.replace("/*__DATA__*/null", data).replace("__TITLE_SRC__", html.escape(meta["source"])),
                   encoding="utf-8")
    cats = {}
    for r in rows:
        cats[r["cat"]] = cats.get(r["cat"], 0) + 1
    print(f"OK -> {out}")
    print(f"   {len(rows)} keyword | {cats}")


if __name__ == "__main__":
    main()
