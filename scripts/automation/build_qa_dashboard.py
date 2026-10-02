#!/usr/bin/env python3
"""Dựng DASHBOARD QA cho Smart Search (text search), bộ tiếng Việt, CHỈ tính
các kịch bản đã duyệt tay: tổng = Passed + Failed + Discussion của nhóm này
(xem review_status). Kèm performance (latency hệ mới vs As-Is production) và
phân loại bug + discussion. HTML tự chứa, gập/mở từng phần, có nút Xuất PDF
(window.print - chạy khi mở file trực tiếp bằng trình duyệt).

Nguồn dữ liệu - đều là số liệu đã đo, script không chấm lại gì:
  --vi     compare_report.html của run bộ VI (mặc định run_all_* mới nhất)
  --asis   file crawl As-Is production (mặc định asis_full_20260908.json - bản
           crawl 08/09; kịch bản không có trong bản crawl này bị loại)
  bug_notes_<store>.json, discussion_notes_<store>.json, client_tracker_state_<store>.json

Usage:
  python scripts/automation/build_qa_dashboard.py
  python scripts/automation/build_qa_dashboard.py --vi <run_dir> --asis <asis.json> --out <file.html>
"""
import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_client_report import SECTIONS, classify, latency_stats  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
SS = ROOT / "SmartSearch"
COMPARE = SS / "test_data" / "compare"
ASIS_DIR = SS / "client_report" / "data"

HIST_EDGES = [0, 250, 500, 750, 1000, 1500, None]  # ms, None = vô cực

# ---------------------------------------------------------------------------
# Phân loại BUG theo nội dung ghi chú QA. Thứ tự = độ ưu tiên (loại đầu tiên
# khớp là loại chính). Chỉ đọc phần chữ QA viết, bỏ các dòng dán danh sách SKU.
# ---------------------------------------------------------------------------
BUG_CATS = [
    ("gift_stock", "SP tặng / hết hàng lọt vào kết quả",
     "Sản phẩm quà tặng (1đ), hàng hết vẫn hiển thị hoặc che mất hàng còn bán",
     r"tặng|hết hàng|hêt hàng|\b1đ\b"),
    ("reco_section", "Bị đẩy sang Recommendation",
     "Sản phẩm đúng nằm ở section Recommendation thay vì Search result, hoặc recommend chưa hợp lý",
     r"recommend"),
    ("wrong_set", "Sai bộ kết quả / không liên quan",
     "Top kết quả chứa sản phẩm khác loại (đồ chơi khi tìm đồ ăn, coca khi tìm colgate...)",
     r"sai|k đúng|không đúng|chưa đúng|không liên quan|k liên quan|k nên hiển thị|không nên hiển thị|"
     r"k phải|không phải|đồ chơi|thức ăn cho (chó|mèo)|nguồn gốc|xuất xứ|không hiển thị (các|thực phẩm)|"
     r"k hiển thị thực phẩm|k được hiển thị|k thể hiển thị|cần hiển thị (?!thêm)|^hiển thị các|"
     r"đang hiển thị trong bộ"),
    ("missing", "Thiếu sản phẩm (recall)",
     "Sản phẩm còn hàng, đúng từ khoá nhưng không xuất hiện hoặc số lượng kết quả hụt so với As-Is",
     r"thiếu|không tìm thấy|k tìm thấy|chưa hiển thị|k thấy|không thấy|k hiển thị|số lượng|chỉ còn|"
     r"hiển thị thêm|bổ sung|đề xuất thêm|check lại data|ra \d+ sp"),
    ("ranking", "Xếp hạng / thứ tự",
     "Có sản phẩm đúng nhưng bị xếp sau sản phẩm kém liên quan",
     r"ưu ti[eê]n|đẩy xuống|xếp sau|hiển thị sau|phía sau|lên đầu|lên trước|lên trên|\btop\b|thứ tự|"
     r"no\.\s?\d+"),
    ("other", "Khác / cần xem lại", "Ghi chú chưa đủ rõ để xếp loại tự động", r"$^"),
]

DISC_CATS = [
    ("zero_reco", "Zero result + Recommendation?",
     "Catalog không có hàng đúng - nên trả 0 kèm Recommendation hay trả hàng gần đúng",
     r"zero result|hiển thị 0|k có result|không có result|k có sản phẩm"),
    ("result_vs_reco", "Search result hay Recommendation?",
     "Sản phẩm liên quan gián tiếp nên nằm ở Search result hay chuyển sang section Recommendation",
     r"recommend"),
    ("scope", "Phạm vi sản phẩm liên quan",
     "Có nên hiển thị các sản phẩm cùng họ / thay thế (dưa lưới khi tìm dưa hấu vàng...)",
     r"có nên|nên hiển thị|hiển thị thêm|xen kẽ|có hiển thị|bao gồm|có bao gồm|nên nằm|đang hiển thị"),
    ("ordering", "Thứ tự hiển thị",
     "Cần thống nhất sản phẩm nào lên trước khi từ khoá mơ hồ (ga / gà / gas, mắc ca / cá)",
     r"thứ tự|trước|hiển thị sau|ưu ti[eê]n|đẩy lên|lên top"),
    ("undefined", "Chưa xác định Expected",
     "Chưa đủ thông tin để định nghĩa kết quả mong đợi - cần trao đổi với khách", r"$^"),
]

PASTED_ROW_RE = re.compile(r"\s\d{1,3}\s*$")


def qa_text(note):
    """Phần chữ QA tự viết - cắt bỏ danh sách sản phẩm/SKU dán vào (dạng
    `rank<TAB>sku<TAB>tên`) để tên sản phẩm không làm lệch phân loại. Dòng dán
    có khi nằm chung dòng với câu QA viết nên cắt tại TAB đầu tiên, không bỏ
    cả dòng."""
    parts = []
    for ln in str(note or "").replace('"', " ").splitlines():
        head = PASTED_ROW_RE.sub("", ln.split("\t", 1)[0]).strip()
        if head and not head.isdigit():
            parts.append(head)
    return " ".join(parts).lower()


def pick_cat(note, cats):
    t = qa_text(note)
    hits = [k for k, _, _, rx in cats if re.search(rx, t)]
    return (hits[0] if hits else cats[-1][0]), hits


def load_scenarios(run_dir):
    src = (Path(run_dir) / "compare_report.html").read_text(encoding="utf-8")
    for line in src.splitlines():
        if line.startswith("const scenarios = ["):
            return json.loads(line[len("const scenarios = "):].rstrip().rstrip(";"))
    raise SystemExit(f"Không tìm thấy mảng scenarios trong {run_dir}")


def latest_run(prefix):
    runs = sorted(p for p in COMPARE.glob(prefix + "*") if (p / "compare_report.html").exists())
    return runs[-1] if runs else None


def norm_q(q):
    return re.sub(r"\s+", " ", str(q or "").strip().lower())


def hist(vals):
    out = []
    for i in range(len(HIST_EDGES) - 1):
        lo, hi = HIST_EDGES[i], HIST_EDGES[i + 1]
        out.append(sum(1 for v in vals if v >= lo and (hi is None or v < hi)))
    return out


def share_under(vals, ms):
    return round(sum(1 for v in vals if v < ms) / len(vals) * 100, 1) if vals else None


def perf_block(scen, asis_by_q):
    new = [int(s["actual_latency_ms"]) for s in scen if s.get("actual_latency_ms") is not None]
    old = []
    for s in scen:
        z = asis_by_q.get(norm_q(s.get("query")))
        if z and z.get("search_latency_ms") is not None and not z.get("search_error"):
            old.append(int(z["search_latency_ms"]))
    ac_new = [int(s["autocomplete_latency_ms"]) for s in scen if s.get("autocomplete_latency_ms") is not None]
    ac_old = [int(z["autocomplete_latency_ms"]) for z in (asis_by_q.get(norm_q(s.get("query"))) for s in scen)
              if z and z.get("autocomplete_latency_ms") is not None]
    by_mode = {}
    for mode in sorted({s.get("resolved_mode") or "?" for s in scen}):
        vals = [int(s["actual_latency_ms"]) for s in scen
                if (s.get("resolved_mode") or "?") == mode and s.get("actual_latency_ms") is not None]
        by_mode[mode] = latency_stats(vals)
    return {
        "new": latency_stats(new), "old": latency_stats(old),
        "hist_new": hist(new), "hist_old": hist(old),
        "under500_new": share_under(new, 500), "under500_old": share_under(old, 500),
        "under1000_new": share_under(new, 1000), "under1000_old": share_under(old, 1000),
        "ac_new": latency_stats(ac_new), "ac_old": latency_stats(ac_old),
        "by_mode": by_mode,
        "errors": sum(1 for s in scen if s.get("actual_error")),
    }


def review_status(s):
    """Trạng thái của 1 kịch bản ĐÃ DUYỆT TAY, hoặc None nếu chưa ai duyệt
    (user 2026-09-24: dashboard chỉ đếm case đã duyệt tay).

    "Đã duyệt tay" = QA đã để lại dấu vết trên kịch bản: chấm Pass/Fail bằng
    tay (pass_fail_reviewed), ghi bug, hoặc ghi discussion. Thứ tự ưu tiên khi
    một kịch bản có nhiều dấu vết:
      1. có discussion note -> discussion (expected chưa chốt thì chưa kết
         luận được, kể cả khi đã chấm tay)
      2. QA chấm tay Pass/Fail -> theo chấm tay (Pass kèm bug note = QA chấp
         nhận, bug giữ làm đề xuất cải thiện)
      3. chỉ có bug note -> failed (QA đã xem và ghi nhận lỗi, bất kể máy chấm gì)
    """
    if s.get("discussion_note"):
        return "discussion"
    if s.get("pass_fail_reviewed"):
        return s.get("pass_fail_status")
    if s.get("bug_note"):
        return "failed"
    return None


def review_basis(s):
    if s.get("discussion_note"):
        return "discussion_note"
    if s.get("pass_fail_reviewed"):
        return "manual_verdict"
    return "bug_note"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--vi", help="thư mục run compare bộ VI (mặc định: run_all_* mới nhất)")
    p.add_argument("--asis", default=str(ASIS_DIR / "asis_full_20260908.json"),
                   help="file crawl As-Is production (mặc định: bản crawl 08/09)")
    p.add_argument("--store", default="nsg")
    p.add_argument("--store-label", default="NSG (Nam Sài Gòn)")
    p.add_argument("--out")
    args = p.parse_args()

    vi_dir = Path(args.vi) if args.vi else latest_run("run_all_")
    if not vi_dir:
        raise SystemExit("Không tìm thấy run compare bộ VI")
    asis_path = Path(args.asis)
    asis_doc = json.loads(asis_path.read_text(encoding="utf-8"))
    asis_vi = {norm_q(s.get("query")): s for s in asis_doc.get("scenarios", [])}

    all_scen = load_scenarios(vi_dir)
    for s in all_scen:
        s["_status"] = review_status(s)
        s["_section"] = classify({"dimension": s.get("dimension"), "query": s.get("query")})
    vi = [s for s in all_scen if s["_status"]]
    # Chỉ giữ kịch bản có trong bản crawl As-Is được chọn - keyword bổ sung sau
    # ngày crawl không có mốc so sánh cùng đợt.
    not_in_asis = [s for s in vi if norm_q(s["query"]) not in asis_vi]
    vi = [s for s in vi if norm_q(s["query"]) in asis_vi]

    st = Counter(s["_status"] for s in vi)
    summary = {
        "all_scenarios": len(all_scen), "total": len(vi),
        "passed": st["passed"], "failed": st["failed"], "discuss": st["discussion"],
        "basis": dict(Counter(review_basis(s) for s in vi)),
        "excluded_not_in_asis": len(not_in_asis),
        "verdict_with_disc": sum(1 for s in vi if s.get("pass_fail_reviewed") and s.get("discussion_note")),
        "bug_only_autopass": sum(1 for s in vi if review_basis(s) == "bug_note"
                                 and s.get("pass_fail_status") == "passed"),
    }
    perf = perf_block(vi, asis_vi)

    sections = []
    for key, label, desc in SECTIONS:
        rs = [s for s in vi if s["_section"] == key]
        if not rs:
            continue
        c = Counter(s["_status"] for s in rs)
        new = latency_stats([int(s["actual_latency_ms"]) for s in rs if s.get("actual_latency_ms") is not None])
        old = latency_stats([int(z["search_latency_ms"]) for z in (asis_vi.get(norm_q(s["query"])) for s in rs)
                             if z and z.get("search_latency_ms") is not None])
        sections.append({
            "key": key, "label": label, "desc": desc, "total": len(rs),
            "passed": c["passed"], "failed": c["failed"], "discuss": c["discussion"],
            "bugs": sum(1 for s in rs if s.get("bug_note")),
            "p95_new": new["p95"], "p95_old": old["p95"], "p50_new": new["p50"], "p50_old": old["p50"],
        })

    slowest = sorted((s for s in vi if s.get("actual_latency_ms") is not None),
                     key=lambda s: -int(s["actual_latency_ms"]))[:20]
    slowest = [{
        "id": s["test_id"], "q": s["query"], "sec": s["_section"], "ms": int(s["actual_latency_ms"]),
        "old": (asis_vi.get(norm_q(s["query"])) or {}).get("search_latency_ms"),
        "mode": s.get("resolved_mode"), "hits": s.get("actual_total_hits"),
    } for s in slowest]

    # ---- bug + discussion ----
    by_id = {s["test_id"]: s for s in vi}
    tracker_path = COMPARE / f"client_tracker_state_{args.store}.json"
    tracker = json.loads(tracker_path.read_text(encoding="utf-8")) if tracker_path.exists() else {}
    search_ch = (tracker.get("channels") or {}).get("search") or {}
    track_by_q = {norm_q(e.get("query")): e for e in search_ch.get("entries", [])}

    def notes(kind):
        f = COMPARE / f"{kind}_notes_{args.store}.json"
        return json.loads(f.read_text(encoding="utf-8")).get("entries", {}) if f.exists() else {}

    def note_row(tid, n, cats):
        s = by_id[tid]
        cat, hits = pick_cat(n.get("note"), cats)
        tr = track_by_q.get(norm_q(n.get("query")))
        return {
            "id": tid, "q": n.get("query"), "sec": s["_section"],
            "status": s["_status"], "basis": review_basis(s), "cat": cat, "tags": hits,
            "asis": s.get("asis_match_category"), "auto": s.get("pass_fail_status"),
            "track": tr.get("status") if tr else None,
            "track_hist": tr.get("history") if tr else None,
            "note": (n.get("note") or "").strip(), "at": (n.get("markedAt") or "")[:10],
            "shot": bool(n.get("screenshot")),
        }

    # note của kịch bản đã loại khỏi bộ test / ngoài bản crawl As-Is thì bỏ
    bugs = [note_row(t, n, BUG_CATS) for t, n in notes("bug").items() if t in by_id]
    discs = [note_row(t, n, DISC_CATS) for t, n in notes("discussion").items() if t in by_id]

    run_ts = datetime.fromtimestamp((vi_dir / "compare_report.html").stat().st_mtime)
    crawled = asis_doc.get("crawledAt") or ""
    data = {
        "meta": {
            "store": args.store_label, "generated": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "run_at": run_ts.strftime("%d/%m/%Y %H:%M"), "run": vi_dir.name,
            "asis_file": asis_path.name, "asis_system": asis_doc.get("system"),
            "asis_api": asis_doc.get("searchApi"),
            "asis_crawled": datetime.fromisoformat(crawled).strftime("%d/%m/%Y") if crawled else "—",
            "hist_edges": HIST_EDGES, "tracker_date": search_ch.get("statusDate"),
        },
        "summary": summary, "sections": sections, "perf": perf, "slowest": slowest,
        "sec_labels": {k: l for k, l, _ in SECTIONS},
        "bug_cats": [{"key": k, "label": l, "desc": d} for k, l, d, _ in BUG_CATS],
        "disc_cats": [{"key": k, "label": l, "desc": d} for k, l, d, _ in DISC_CATS],
        "bugs": bugs, "discs": discs,
    }

    out = Path(args.out) if args.out else SS / "client_report" / \
        f"SmartSearch_QADashboard_{args.store.upper()}_{datetime.now():%Y%m%d}.html"
    tpl = (Path(__file__).resolve().parent / "qa_dashboard_template.html").read_text(encoding="utf-8")

    def write(path, d):
        payload = json.dumps(d, ensure_ascii=False).replace("</", "<\\/")
        path.write_text(tpl.replace("__DATA__", payload), encoding="utf-8")

    write(out, data)

    # Bản TÓM TẮT (user 2026-09-24): cùng dashboard nhưng ẩn danh sách bug cụ
    # thể, danh sách câu hỏi discussion, phần định nghĩa & nguồn dữ liệu. Dữ
    # liệu nhúng cũng bị cắt về đúng các trường dùng để đếm (không còn từ khoá,
    # mã test, ghi chú) - ẩn trên giao diện mà vẫn để trong source thì ai mở
    # view-source cũng đọc được.
    # bản tóm tắt cũng không hiện tracker của khách (user 2026-09-24)
    keep = ("cat", "sec", "status")
    summary_data = dict(data, summary_only=True,
                        bugs=[{k: r[k] for k in keep} for r in bugs],
                        discs=[{k: r[k] for k in keep} for r in discs])
    summary_data["meta"] = {k: v for k, v in data["meta"].items() if k not in ("run", "asis_file", "asis_api")}
    out_summary = out.with_name(out.stem + "_Summary" + out.suffix)
    write(out_summary, summary_data)

    print(f"OK -> {out}")
    print(f"OK -> {out_summary} (bản tóm tắt)")
    print(f"   Đã duyệt tay {summary['total']} / {summary['all_scenarios']}: P {summary['passed']} / "
          f"F {summary['failed']} / discuss {summary['discuss']} | căn cứ {summary['basis']} | "
          f"loại vì ngoài {asis_path.name}: {summary['excluded_not_in_asis']}")
    print(f"   Bug {len(bugs)}: {dict(Counter(b['cat'] for b in bugs))}")
    print(f"   Discussion {len(discs)}: {dict(Counter(d['cat'] for d in discs))}")
    print(f"   Search P95 ({perf['new']['count']} query): As-Is {perf['old']['p95']}ms -> mới {perf['new']['p95']}ms")


if __name__ == "__main__":
    main()
