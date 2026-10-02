# -*- coding: utf-8 -*-
"""Sinh bộ test data mới từ log truy vấn thật 6 tháng (T3-T8/2026), tách 3 ngôn ngữ.

Nguồn: mart_{vi,kr,en}_nsg_analysis-history_query_analysis_2026-03_2026-08.csv
Mỗi dòng là một truy vấn NGƯỜI DÙNG THẬT đã gõ, kèm số lượt, số kết quả trung
bình và tỷ lệ trả về 0 kết quả.

BA FILE RIÊNG, KHÔNG ĐỤNG BỘ CŨ (user 2026-09-17: "nếu số lượng quá lớn thì
toàn bộ tạo file data mới, k đụng file cũ"):

  vihist : chỉ những từ khoá tiếng Việt mà bộ test hiện tại CHƯA có.
  ko     : từ khoá tiếng Hàn thật, chạy với lang=ko.
  en     : từ khoá tiếng Anh thật, chạy với lang=en.

Trường "lang" nằm ngay trong metadata mỗi file, để export_actual_search_results.py
tự gọi API đúng ngôn ngữ mà không cần nhớ truyền --lang.

NGƯỠNG LƯỢT TÌM - vì sao không lấy hết: log VI có 418.204 truy vấn riêng biệt,
trong đó 398.118 cái chưa có trong bộ test. Gọi API thật cho từng cái ở tốc độ
~1,1 query/s là hơn 100 giờ, chưa kể còn phải crawl As-Is để chấm Pass/Fail.
Ngưỡng dưới đây giữ bộ test chạy được trong một buổi; hạ ngưỡng thì chỉ cần
sửa MIN_SEARCHES rồi chạy lại.

Chạy:
  python scripts/testdata/build_history_testdata.py
"""
import csv
import io
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]

SRC = Path("C:/Users/Admin/Downloads/nsg_analysis-history_query_analysis_2026-03_2026-08"
           "/nsg_analysis-history_query_analysis_2026-03_2026-08")
CUR_TESTDATA = ROOT / "SmartSearch/test_data/json/batches/NSG_ExpectedData_all_20260916c.json"
REMOVED = ROOT / "SmartSearch/test_data/compare/removed_scenarios_nsg.json"
OUT_DIR = ROOT / "SmartSearch/test_data/json/batches"
DATE = "20260917"

# (mã file, file nguồn, lang gửi lên API, tiền tố test_id, ngưỡng lượt tìm)
SETS = [
    ("vihist", "vi", "vi", "VIH", 500),
    ("ko",     "kr", "ko", "KO",   50),
    ("en",     "en", "en", "EN",   50),
]


def fold(s):
    """Bỏ dấu + thường hoá, để 'ba rọi' và 'ba roi' không bị coi là hai từ khoá."""
    s = re.sub(r"\s+", " ", str(s or "").strip().casefold()).replace("đ", "d")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def read_log(lang):
    p = SRC / f"mart_{lang}_nsg_analysis-history_query_analysis_2026-03_2026-08.csv"
    rows = []
    with io.open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            q = (r["query_text"] or "").strip()
            if not q:
                continue
            rows.append({
                "q": q,
                "n": int(r["total_searches"]),
                "avg": float(r["avg_results"]),
                "zero_pct": float(r["zero_results_pct"]),
                "max_hits": int(float(r["max_results"])),
                "avg_ms": float(r["avg_took_ms"]),
                "last": (r["last_searched_at"] or "")[:10],
            })
    return rows


def dedupe(rows):
    """Gộp các biến thể chỉ khác hoa/thường hoặc dấu (vd 'coffee' và 'Coffee').

    Giữ cách viết của biến thể NHIỀU LƯỢT NHẤT - đó là cách người dùng hay gõ
    nhất - và cộng dồn lượt tìm của cả nhóm.
    """
    best = {}
    for r in sorted(rows, key=lambda x: -x["n"]):
        k = fold(r["q"])
        if k in best:
            best[k]["n"] += r["n"]
            best[k]["variants"] += 1
        else:
            best[k] = dict(r, variants=1)
    return best


def main():
    cur = json.loads(CUR_TESTDATA.read_text(encoding="utf-8"))["scenarios"]
    have = {fold(s["query"]) for s in cur}
    rm = json.loads(REMOVED.read_text(encoding="utf-8"))
    rm_q = {fold(q) for q in (rm.get("entries") or rm.get("queries") or {})}
    print(f"Bộ test hiện tại: {len(cur):,} scenario · QA đã loại: {len(rm_q)}\n")

    for code, src_lang, api_lang, prefix, min_n in SETS:
        rows = read_log(src_lang)
        merged = dedupe(rows)
        raw_total = len(rows)

        picked = []
        for k, r in merged.items():
            if r["n"] < min_n:
                continue
            # Chỉ bộ tiếng Việt mới loại trùng với bộ test cũ. KO/EN là bộ
            # riêng cho ngôn ngữ khác, không liên quan tới bộ VI đang có.
            if code == "vihist" and (k in have or k in rm_q):
                continue
            picked.append(r)
        picked.sort(key=lambda r: -r["n"])

        scenarios = []
        for i, r in enumerate(picked, start=1):
            scenarios.append({
                "test_id": f"NSG-{prefix}-{i:05d}",
                "query": r["q"],
                "source_batch": f"query_history_2026-03_2026-08_{src_lang}",
                "original_test_id": None,
                "dimension": "real_search_history",
                "note": (f"Log truy vấn thật T3-T8/2026 ({src_lang}): {r['n']:,} lượt tìm, "
                         f"trung bình {r['avg']:.1f} kết quả, "
                         f"{r['zero_pct']:.1f}% lần trả về 0 kết quả, "
                         f"tối đa {r['max_hits']:,} sản phẩm. Lần gõ cuối {r['last']}."),
                "autocomplete_suggestions": [],
                "search_results": [],
                "search_results_total_before_cap": 0,
                "route": None,
                "confidence": None,
                "data_filled_from": [{"source_batch": f"query_history_{src_lang}",
                                      "fields": ["query"], "date": "2026-09-17"}],
                "real_search_score": r["n"],
                "real_search_rank": i,
                "real_search_variants": r["variants"],
                "real_history_all_zero": r["zero_pct"] >= 99.0,
                "real_history_hits_max": r["max_hits"],
                "real_history_zero_pct": r["zero_pct"],
                "real_history_avg_took_ms": round(r["avg_ms"], 1),
                "is_single_exact_match": None,
                "log_last_seen": r["last"],
            })

        out = OUT_DIR / f"NSG_ExpectedData_{code}_{DATE}.json"
        payload = {
            "generatedDate": "2026-09-17",
            "store": "nsg",
            "batchRange": code,
            # Ngôn ngữ gửi lên API khi chạy bộ này. export_actual_search_results.py
            # đọc trường này nên không cần nhớ truyền --lang.
            "lang": api_lang,
            "totalScenarios": len(scenarios),
            "scenarioCount": len(scenarios),
            "purpose": (f"Bộ test sinh từ log truy vấn thật T3-T8/2026, ngôn ngữ "
                        f"{src_lang}. File RIÊNG, không gộp vào bộ cũ."),
            "sourceFile": f"mart_{src_lang}_nsg_analysis-history_query_analysis_2026-03_2026-08.csv",
            "minSearches": min_n,
            "selectionRule": (
                f"Từ khoá có >= {min_n:,} lượt tìm trong 6 tháng. "
                + ("Loại những từ đã có trong NSG_ExpectedData_all_20260916c.json "
                   "hoặc đã bị QA remove." if code == "vihist" else
                   "Không đối chiếu với bộ tiếng Việt - đây là bộ riêng cho ngôn ngữ khác.")
                + " Biến thể chỉ khác hoa/thường hoặc dấu được gộp làm một, "
                  "giữ cách viết nhiều lượt nhất và cộng dồn lượt."),
            "sourceStats": {
                "rawQueries": raw_total,
                "afterCaseFoldMerge": len(merged),
                "aboveThreshold": sum(1 for r in merged.values() if r["n"] >= min_n),
                "picked": len(scenarios),
            },
            "scenarios": scenarios,
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

        skipped = (payload["sourceStats"]["aboveThreshold"] - len(scenarios))
        print(f"{code:<7} lang={api_lang:<3} | log {raw_total:>7,} -> gộp {len(merged):>7,} "
              f"-> >= {min_n} lượt: {payload['sourceStats']['aboveThreshold']:>6,} "
              f"-> chọn {len(scenarios):>6,}"
              + (f" (bỏ {skipped:,} đã có trong bộ cũ)" if skipped else ""))
        print(f"        -> {out.name}  ({out.stat().st_size/1024:.0f} KB)")
        if scenarios:
            print(f"        top: " + " · ".join(
                f"{s['query'][:18]}({s['real_search_score']:,})" for s in scenarios[:4]))
        print()


if __name__ == "__main__":
    main()
