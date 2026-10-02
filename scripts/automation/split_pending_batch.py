#!/usr/bin/env python3
"""Tách các scenario FAILED mà QA CHƯA duyệt tay ra 1 batch riêng để tập trung
xử lý, KHÔNG làm hỏng bộ testcase gốc.

Vì sao "tạm" tách chứ không cắt hẳn (user 2026-09-09 "tạm thời move data qua
1 batch riêng"): danh sách này thay đổi mỗi lần QA duyệt thêm - duyệt xong 1
case là nó phải rời nhóm. Nếu cắt hẳn khỏi file gốc thì mỗi lần duyệt lại phải
ghép ngược, rất dễ lệch. Nên:

  - file gốc NSG_ExpectedData_all_*.json  -> KHÔNG đụng tới
  - batch tách ra nằm ở thư mục RIÊNG (--out-dir), không nằm trong batches/
    để lần chạy `--batch all` sau này không vô tình chạy trùng 2 lần
  - chạy lại script này bất cứ lúc nào để làm mới danh sách

Điều kiện "failed chưa duyệt" đọc từ compare report:
    pass_fail_status == "failed"  AND  pass_fail_reviewed != true

Usage:
  python scripts/automation/split_pending_batch.py \
    --report SmartSearch/test_data/compare/run_all_20260909_112622/compare_report.html \
    --expected SmartSearch/test_data/json/batches/NSG_ExpectedData_all_20260907.json \
    --actual SmartSearch/test_data/json/actual/NSG_ActualData_all_20260909_103403.json \
    --out-dir SmartSearch/test_data/json/pending_review
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def nq(s):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(s or "")).strip().casefold())


def load_scenarios_from_report(path):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.startswith("const scenarios = ["):
            return json.loads(line[len("const scenarios = "):].rstrip().rstrip(";"))
    raise SystemExit(f"Không tìm thấy mảng scenarios trong {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", required=True)
    ap.add_argument("--expected", required=True)
    ap.add_argument("--actual", required=True)
    ap.add_argument("--out-dir", default="SmartSearch/test_data/json/pending_review")
    ap.add_argument("--label", default="pending_review",
                    help="tên batch tách ra (mặc định pending_review)")
    args = ap.parse_args()

    scen = load_scenarios_from_report(args.report)
    # Dùng effective status đã tính sẵn phía Python: override tay đã được áp
    # vào pass_fail_status, nên case QA đánh Passed sẽ không lọt vào đây.
    pending = [s for s in scen
               if s.get("pass_fail_status") == "failed" and not s.get("pass_fail_reviewed")]
    ids = {s["test_id"] for s in pending}
    qs = {nq(s["query"]) for s in pending}

    print(f"Report: {len(scen)} scenario")
    print(f"  failed                     : {sum(1 for s in scen if s.get('pass_fail_status') == 'failed')}")
    print(f"  failed + ĐÃ duyệt tay      : {sum(1 for s in scen if s.get('pass_fail_status') == 'failed' and s.get('pass_fail_reviewed'))}")
    print(f"  failed + CHƯA duyệt -> tách: {len(pending)}\n")
    print("  theo nhóm truy vấn:")
    for k, v in Counter(s.get("dimension") for s in pending).most_common():
        print(f"     {k or '(không rõ)'}: {v}")
    print("\n  đã ghi bug / chưa:", dict(Counter("đã ghi bug" if s.get("bug_note") else "chưa ghi bug"
                                                 for s in pending)))

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    meta_common = {
        "generatedDate": datetime.now().strftime("%Y-%m-%d"),
        "batch": args.label,
        "purpose": ("Scenario KHÔNG ĐẠT mà QA chưa rà soát tay - tách riêng để tập trung xử lý. "
                    "Đây là bản CHỤP tại thời điểm tạo: mỗi lần QA duyệt thêm thì chạy lại "
                    "scripts/automation/split_pending_batch.py để làm mới."),
        "sourceReport": str(args.report),
        "criteria": 'pass_fail_status == "failed" AND pass_fail_reviewed != true',
        "scenarioCount": len(pending),
    }

    written = []
    for src_path, kind in ((args.expected, "ExpectedData"), (args.actual, "ActualData")):
        d = json.loads(Path(src_path).read_text(encoding="utf-8"))
        kept = [s for s in d["scenarios"] if s.get("test_id") in ids or nq(s.get("query")) in qs]
        nd = {k: v for k, v in d.items() if k != "scenarios"}
        nd.update(meta_common)
        nd["scenarioCount"] = len(kept)
        nd["sourceFile"] = Path(src_path).name
        nd["scenarios"] = kept
        p = out / f"NSG_{kind}_{args.label}_{stamp}.json"
        p.write_text(json.dumps(nd, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append((p, len(kept)))

    # danh sách phẳng để dán vào Excel/Jira
    lst = out / f"queries_{args.label}_{stamp}.json"
    lst.write_text(json.dumps({
        **meta_common,
        "queries": [{"test_id": s["test_id"], "query": s["query"],
                     "dimension": s.get("dimension"),
                     "asis_match": s.get("asis_match_category"),
                     "has_bug_note": bool(s.get("bug_note")),
                     "actual_count": len(s.get("actual_items") or []),
                     "asis_count": len(s.get("asis_items") or [])}
                    for s in sorted(pending, key=lambda x: x.get("query") or "")],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    for p, n in written:
        print(f"-> {p}  ({n} scenario)")
    print(f"-> {lst}  (danh sách phẳng)")
    print("\nFile testcase gốc KHÔNG bị sửa. Batch này nằm ngoài batches/ nên "
          "`--batch all` sẽ không chạy trùng.")


if __name__ == "__main__":
    main()
