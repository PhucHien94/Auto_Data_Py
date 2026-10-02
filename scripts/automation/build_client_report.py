#!/usr/bin/env python3
"""Dựng REPORT CHO CLIENT (HTML, in ra PDF được) tổng kết kết quả test Smart
Search phase này: so sánh hệ thống MỚI (Actual) với hệ thống CŨ (As-Is) trên
3 mặt Search Result / AutoComplete / Performance.

Nguồn dữ liệu (đều là dữ liệu đã đo thật, không mô phỏng lại gì ở đây):
  --expected  NSG_ExpectedData_all_*.json      (kỳ vọng, engine mô phỏng)
  --actual    NSG_ActualData_all_*.json        (hệ thống MỚI: kết quả + latency)
  --asis      client_report/data/asis_full_*.json (hệ thống CŨ: kết quả + latency)
  --state     pass_fail_state_<store>.json     (Pass/Fail + override thủ công)

Usage:
  python scripts/automation/build_client_report.py \
    --expected SmartSearch/test_data/json/batches/NSG_ExpectedData_all_20260907.json \
    --actual   SmartSearch/test_data/json/actual/NSG_ActualData_all_20260907_160705.json \
    --asis     SmartSearch/client_report/data/asis_full_20260908.json \
    --out      SmartSearch/client_report/SmartSearch_TestReport_NSG_20260908.html
"""
import argparse
import html
import json
import re
import statistics
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Phân loại query thành 6 SECTION theo yêu cầu client.
# Thứ tự tín hiệu (xem docstring classify() để biết vì sao):
#   1. `dimension` bộ test tự khai báo - luôn thắng
#   2. ký tự không phải Latin (CJK/Hangul/Kana/Cyrillic) - đọc thẳng từ query
#   3. từ khoá mô tả nhu cầu trong chính query (INTENT_MARKERS)
#   KHÔNG dùng `tier` của engine mô phỏng - xem docstring classify()
# ---------------------------------------------------------------------------
SECTIONS = [
    ("foreign", "Query ngoại ngữ", "Query gõ bằng tiếng nước ngoài (Hàn/Trung/Nhật/Nga/Anh)"),
    ("typo", "Query lỗi chính tả", "Query sai chính tả hoặc gõ không dấu"),
    ("regional", "Query từ địa phương",
     "Cách gọi theo vùng miền của cùng một sản phẩm (trái thơm / quả dứa / trái khóm, cá quả / cá lóc)"),
    ("semantic", "Query ngữ nghĩa / từ đồng nghĩa",
     "Cụm mô tả theo ngữ nghĩa (“áo khoác giữ ấm mùa đông”) và tên gọi đồng nghĩa của sản phẩm"),
    ("context", "Query ngữ cảnh chung", "Query mô tả nhu cầu chung chung, không nêu tên sản phẩm cụ thể"),
    ("fulltext", "Query full-text search", "Query gõ thẳng tên/thương hiệu sản phẩm - phần lớn traffic thật"),
]
SECTION_ORDER = [s[0] for s in SECTIONS]

NON_LATIN_RE = re.compile(r"[ᄀ-ᇿ぀-ヿ㐀-䶿一-鿿가-힯Ѐ-ӿ]")
ASCII_ONLY_RE = re.compile(r"^[a-zA-Z0-9 \-&'./]+$")

FOREIGN_DIMS = {"foreign_language"}
TYPO_DIMS = {"misspelling"}
REGIONAL_DIMS = {"regional_dialect"}
SEMANTIC_DIMS = {"semantic_phrase", "synonym_variant"}
CONTEXT_DIMS = {"generic_vague_intent"}

# Dấu hiệu query MÔ TẢ NHU CẦU chứ không nêu tên sản phẩm ("đồ ăn cho người
# giảm cân", "giỏ quà tết"). Dùng cho các query mà `dimension` không khai báo
# nhóm - bộ demo là túi đựng chung 20 case trải khắp mọi nhóm nên dimension
# của nó vô nghĩa cho việc phân loại.
# Đây là tín hiệu đọc từ CHÍNH CHỮ TRONG QUERY, khác hẳn tier của engine mô
# phỏng (tier chỉ nói engine đã khớp bằng cách nào).
# Khớp NGUYÊN TỪ: từng gặp lỗi "quà" khớp vào giữa chữ "quần" ở bộ tự đánh giá.
INTENT_MARKERS = [
    "cho người", "cho bé", "cho trẻ", "cho mẹ", "dành cho", "phù hợp",
    "giảm cân", "tăng cân", "ăn kiêng", "eat clean", "healthy", "lành mạnh",
    "bồi bổ", "hỗ trợ", "tăng cường", "chế độ", "thực đơn",
    "quà", "tặng", "biếu", "lễ", "tết", "sinh nhật", "cưới",
    "du lịch", "dã ngoại", "cắm trại", "picnic", "văn phòng", "năm học",
    "trang trí", "mùa hè", "mùa đông",
]


def _strip_accents(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d")


INTENT_RE = re.compile("|".join(
    r"(?<![a-z0-9])" + re.escape(_strip_accents(m).lower()) + r"(?![a-z0-9])" for m in INTENT_MARKERS))


def classify_outcome(row):
    """Xếp 1 kịch bản vào Đạt / Chưa đạt / Chưa rà soát (user 2026-09-09).

    QUAN TRỌNG - vì sao KHÔNG lấy độ trùng SKU làm "chưa đạt":
    độ trùng thấp chỉ nói MÁY ĐO THẤY LỆCH, chưa ai xác nhận đó là lỗi. Với
    từ khoá rộng, khác thứ tự hoặc khác tập con là bình thường và hệ mới vẫn
    có thể đang trả kết quả tốt hơn. Gọi 695 kịch bản là "chưa đạt" chỉ vì
    máy đo lệch là vu cho hệ thống.

    Định nghĩa đúng:
      - Đạt          : đã kết luận đạt. Đánh giá tay của QA THẮNG, kể cả khi
                       trước đó có ghi bug (QA xem lại và chấp nhận -> bug note
                       giữ làm ghi chú cải thiện, không phải lỗi chặn).
      - Chưa đạt     : QA ĐÃ ghi nhận vấn đề - có bug note hoặc discussion note.
      - Chưa rà soát : máy đo thấy lệch nhưng CHƯA ai ghi nhận gì. Chưa kết
                       luận được, không tính vào cả hai bên.
    """
    if row.get("status") == "passed":
        return "pass"
    if row.get("has_bug_note") or row.get("has_discussion_note"):
        return "fail"
    return "pending"


def classify(scenario):
    """Xếp query vào 1 trong 6 nhóm cho báo cáo client.

    Thứ tự tín hiệu (user 2026-09-08, phát hiện "bếp từ" bị xếp vào vùng
    miền/ngữ nghĩa):

    1. `dimension` của bộ test LUÔN thắng. Đây là nhóm mà người thiết kế bộ
       test tự khai báo khi sinh dữ liệu - đáng tin nhất. Trước đây điều kiện
       `semantic` đứng trước `context` nên 22 query `generic_vague_intent` bị
       đẩy sai sang nhóm ngữ nghĩa.

    2. Ký tự không phải Latin - tín hiệu khách quan, đọc thẳng từ query.

    3. TUYỆT ĐỐI KHÔNG dùng `tier` của engine. Tier nói ENGINE ĐÃ KHỚP BẰNG
       CÁCH NÀO, không nói QUERY LÀ LOẠI GÌ - đã sai 2 lần:
         - tier `intent`/`synonym`: "bếp từ", "đường cát" gõ thẳng tên sản
           phẩm nhưng engine khớp qua bước dự phòng intent (catalog không có
           đúng mặt hàng đó) -> bị xếp nhầm sang nhóm ngữ nghĩa;
         - tier `typo`/`no_diacritics`: "trái khế", "ếch đồng", "đồ khô" viết
           ĐÚNG CHÍNH TẢ CÓ DẤU, nhưng engine khớp qua nhánh bỏ dấu/mờ ->
           bị xếp nhầm sang nhóm lỗi chính tả.
       Thêm nữa tier do search_engine.js MÔ PHỎNG sinh ra, không phải dữ liệu
       đo được - không nên để nó quyết định cách phân nhóm trong báo cáo gửi
       client. Query mà dimension không khai báo nhóm thì để nguyên ở
       full-text, đó là mặc định trung thực nhất.
    """
    dim = scenario.get("dimension") or ""
    query = scenario.get("query") or ""

    if dim in FOREIGN_DIMS or NON_LATIN_RE.search(query):
        return "foreign"
    if dim in TYPO_DIMS:
        return "typo"
    if dim in REGIONAL_DIMS:
        return "regional"
    if dim in SEMANTIC_DIMS:
        return "semantic"
    if dim in CONTEXT_DIMS:
        return "context"
    # dimension chung chung -> chỉ còn tín hiệu đọc từ CHÍNH CHỮ trong query
    if INTENT_RE.search(_strip_accents(query).lower()):
        return "context"
    return "fulltext"


def pctl(sorted_vals, p):
    if not sorted_vals:
        return None
    k = max(0, min(len(sorted_vals) - 1, int(round((p / 100) * len(sorted_vals))) - 1))
    return sorted_vals[k]


def latency_stats(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return {"count": 0, "avg": None, "p50": None, "p90": None, "p95": None, "p99": None,
                "min": None, "max": None}
    return {
        "count": len(vals),
        "avg": round(statistics.fmean(vals), 1),
        "p50": pctl(vals, 50), "p90": pctl(vals, 90), "p95": pctl(vals, 95), "p99": pctl(vals, 99),
        "min": vals[0], "max": vals[-1],
    }


def fmt(v, suffix=""):
    return "—" if v is None else f"{v:,.0f}{suffix}" if isinstance(v, (int, float)) else f"{v}{suffix}"


def pct_of(part, whole):
    return round(part / whole * 100, 1) if whole else 0.0


def esc(s):
    return html.escape(str(s if s is not None else ""))


def rows_from_report(args):
    """Lấy scenarios TRỰC TIẾP từ compare_report.html - nguồn duy nhất, không
    ghép tay.

    Vì sao ưu tiên đường này (user 2026-09-08 "từ scenario và report đó"):
      - report đã LOẠI các keyword trong removed_scenarios_*.json, ghép từ file
        Expected sẽ kéo lại 25 keyword đã bỏ;
      - Pass/Fail trong report đã chấm theo AS-IS↔ACTUAL (hệ đang chạy thật),
        không phải theo Expected do search_engine.js mô phỏng sinh ra;
      - report có sẵn trạng thái "discussion" = hệ cũ 0 KQ nhưng hệ mới CÓ KQ,
        nhóm không được tự chấm đạt/không đạt;
      - override tay của QA đã nằm trong đó.
    Latency hệ cũ vẫn phải lấy từ file crawl As-Is (report không lưu).
    """
    src = Path(args.from_report).read_text(encoding="utf-8")
    scen = None
    for line in src.splitlines():
        if line.startswith("const scenarios = ["):
            scen = json.loads(line[len("const scenarios = "):].rstrip().rstrip(";"))
            break
    if scen is None:
        raise SystemExit(f"Không tìm thấy mảng scenarios trong {args.from_report}")

    asis = json.loads(Path(args.asis).read_text(encoding="utf-8"))
    asis_by_q = {s["query"].strip().lower(): s for s in asis["scenarios"]}

    rows = []
    for x in scen:
        q = (x.get("query") or "").strip().lower()
        z = asis_by_q.get(q) or {}
        st = x.get("pass_fail_status")
        act_n = len(x.get("actual_items") or [])
        asis_n = len(x.get("asis_items") or [])
        # asis_cached=True nghĩa là query NÀY đã thực sự được gọi trên hệ cũ.
        # Bắt buộc phải tách khỏi "chưa có dữ liệu", nếu gộp thì mọi query
        # thiếu dữ liệu đều bị đếm thành "hệ mới cứu được" -> thổi phồng đúng
        # con số quan trọng nhất của báo cáo.
        asis_ok = bool(x.get("asis_cached"))
        act_ok = x.get("actual_error") in (None, "")
        rows.append({
            "test_id": x.get("test_id"), "query": x.get("query"),
            "section": classify({"dimension": x.get("dimension"), "query": x.get("query"),
                                 "search_results": x.get("expected_items") or []}),
            "dimension": x.get("dimension"),
            "status": st,
            "override": x.get("pass_fail_manual_override"),
            # Dùng phân loại theo AS-IS, không phải match_category của Expected.
            "match_category": x.get("asis_match_category"),
            "actual_count": act_n, "asis_count": asis_n,
            "actual_total_hits": x.get("actual_total_hits"),
            "asis_total": x.get("asis_total_before_cap"),
            "resolved_mode": x.get("resolved_mode"),
            "actual_lat": x.get("actual_latency_ms"),
            "asis_lat": z.get("search_latency_ms"),
            "actual_ac_n": len(x.get("autocomplete_actual_items") or []),
            "asis_ac_n": len(x.get("autocomplete_asis_items") or []),
            "actual_ac_lat": x.get("autocomplete_latency_ms"),
            "asis_ac_lat": z.get("autocomplete_latency_ms"),
            "asis_ok": asis_ok, "act_ok": act_ok,
            # 2 cờ này quyết định Đạt/Chưa đạt - xem classify_outcome()
            "has_bug_note": bool(x.get("bug_note")),
            "has_discussion_note": bool(x.get("discussion_note")),
            # "Hệ mới cứu được" TRÙNG KHÍT với trạng thái discussion của report
            # (As-Is 0 KQ + Actual có KQ) - tính lại từ số lượng cho khớp.
            "recovered": asis_ok and act_ok and asis_n == 0 and act_n > 0,
            "regressed_zero": asis_ok and act_ok and asis_n > 0 and act_n == 0,
        })
    m = re.search(r"catalogVersion[\"']?\s*[:=]\s*[\"']([^\"']+)", src)
    meta = {"scenarios": scen, "store": args.store,
            "catalogVersion": m.group(1) if m else "v1.1",
            "catalogSkuCount": "18.122"}
    return rows, meta, meta


def rows_from_files(args):
    """Đường cũ: ghép expected + actual + pass_fail_state. Giữ lại để còn chạy
    được với bộ dữ liệu chưa có compare report."""
    asis = json.loads(Path(args.asis).read_text(encoding='utf-8'))
    exp = json.loads(Path(args.expected).read_text(encoding='utf-8'))
    act = json.loads(Path(args.actual).read_text(encoding='utf-8'))
    state = json.loads(Path(args.state).read_text(encoding="utf-8")) if Path(args.state).exists() else {"entries": {}}

    exp_by_id = {s["test_id"]: s for s in exp["scenarios"]}
    act_by_q = {s["query"].strip().lower(): s for s in act["scenarios"]}
    asis_by_q = {s["query"].strip().lower(): s for s in asis["scenarios"]}
    pf_entries = state.get("entries", {})

    rows = []
    for e in exp["scenarios"]:
        q = e["query"].strip().lower()
        a = act_by_q.get(q) or {}
        z = asis_by_q.get(q) or {}
        pf = pf_entries.get(e["test_id"]) or {}
        act_n = len(a.get("search_results") or [])
        asis_n = len(z.get("search_results") or [])
        # Phân biệt "As-Is TRẢ VỀ 0 kết quả" với "chưa có dữ liệu As-Is cho
        # query này". Nếu gộp làm một thì mọi query thiếu dữ liệu đều bị đếm
        # thành "hệ thống mới cứu được" - thổi phồng con số quan trọng nhất
        # của báo cáo. Chỉ tính khi query THỰC SỰ đã được gọi và không lỗi.
        asis_ok = bool(z) and z.get("search_error") is None
        act_ok = bool(a) and a.get("api_error") is None
        rows.append({
            "test_id": e["test_id"], "query": e["query"], "section": classify(e),
            "dimension": e.get("dimension"),
            "status": pf.get("status"), "override": pf.get("manual_override"),
            "match_category": pf.get("match_category"),
            "actual_count": act_n, "asis_count": asis_n,
            "actual_total_hits": (a.get("response_meta") or {}).get("totalHits"),
            "asis_total": z.get("search_total_before_cap"),
            "resolved_mode": (a.get("response_meta") or {}).get("resolvedMode"),
            "actual_lat": a.get("api_latency_ms"), "asis_lat": z.get("search_latency_ms"),
            "actual_ac_n": len(a.get("autocomplete_suggestions") or []),
            "asis_ac_n": len(z.get("autocomplete_suggestions") or []),
            "actual_ac_lat": a.get("autocomplete_api_latency_ms"), "asis_ac_lat": z.get("autocomplete_latency_ms"),
            "asis_ok": asis_ok, "act_ok": act_ok,
            # Chỉ tính khi CẢ HAI hệ thống đều đã được gọi thành công cho query
            # này - xem comment ở asis_ok.
            "recovered": asis_ok and act_ok and asis_n == 0 and act_n > 0,
            "regressed_zero": asis_ok and act_ok and asis_n > 0 and act_n == 0,
        })
    return rows, exp, act


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from-report",
                   help="Đọc scenarios TRỰC TIẾP từ compare_report.html thay vì ghép lại "
                        "expected+actual+state. Nên dùng: report đã áp dụng danh sách "
                        "keyword bị loại, đã chấm Pass/Fail theo As-Is↔Actual và đã có "
                        "trạng thái 'discussion' (As-Is 0 KQ) - ghép tay lại rất dễ lệch.")
    p.add_argument("--expected")
    p.add_argument("--actual")
    p.add_argument("--asis", required=True, help="file crawl As-Is - cần cho số liệu latency hệ cũ")
    p.add_argument("--state", default="SmartSearch/test_data/compare/pass_fail_state_nsg.json")
    p.add_argument("--out", required=True)
    p.add_argument("--store", default="NSG (Nam Sài Gòn)")
    p.add_argument("--scope-note",
                   help="Câu mô tả PHẠM VI dữ liệu, hiện thành banner nổi bật đầu báo cáo. "
                        "BẮT BUỘC dùng khi báo cáo chỉ chạy trên một phần bộ test - không có nó, "
                        "người đọc sẽ hiểu tỷ lệ đạt là của toàn bộ kịch bản.")
    p.add_argument("--max-list", type=int, default=40,
                    help="số scenario hiển thị tối đa mỗi bảng phụ lục (mặc định 40)")
    args = p.parse_args()

    # asis dùng cho phần metadata + latency hệ cũ ở cả 2 đường
    asis = json.loads(Path(args.asis).read_text(encoding="utf-8"))
    if args.from_report:
        rows, exp, act = rows_from_report(args)
    else:
        if not (args.expected and args.actual):
            raise SystemExit("Thiếu --expected/--actual (hoặc dùng --from-report)")
        rows, exp, act = rows_from_files(args)

    total = len(rows)
    for r in rows:
        r["outcome"] = classify_outcome(r)
    passed = sum(1 for r in rows if r["outcome"] == "pass")
    failed = sum(1 for r in rows if r["outcome"] == "fail")
    # Nhóm hệ cũ 0 KQ / hệ mới CÓ KQ: KHÔNG tự chấm đạt hay không đạt (quyết
    # định của QA 2026-09-08). Phải để riêng, và mẫu số của "tỷ lệ đạt" chỉ
    # gồm các kịch bản thực sự kết luận được - nếu nhồi cả nhóm này vào mẫu số
    # thì tỷ lệ đạt bị dìm xuống một cách vô căn cứ.
    pending = sum(1 for r in rows if r["outcome"] == "pending")
    n_judged = passed + failed
    recovered = [r for r in rows if r["recovered"]]
    regressed = [r for r in rows if r["regressed_zero"]]
    # Mẫu số cho các chỉ số SO SÁNH 2 hệ thống: chỉ những query đã gọi thành
    # công ở CẢ HAI bên mới so được. Nếu lấy mẫu số là toàn bộ scenario thì
    # query thiếu dữ liệu một bên sẽ bóp méo tỷ lệ.
    comparable = [r for r in rows if r["asis_ok"] and r["act_ok"]]
    n_cmp = len(comparable)
    asis_zero = [r for r in comparable if r["asis_count"] == 0]

    # --- performance -------------------------------------------------------
    perf = {
        "asis_search": latency_stats([r["asis_lat"] for r in rows]),
        "actual_search": latency_stats([r["actual_lat"] for r in rows]),
        "asis_ac": latency_stats([r["asis_ac_lat"] for r in rows]),
        "actual_ac": latency_stats([r["actual_ac_lat"] for r in rows]),
    }

    # --- theo section ------------------------------------------------------
    by_section = {}
    for key, label, desc in SECTIONS:
        rs = [r for r in rows if r["section"] == key]
        by_section[key] = {
            "label": label, "desc": desc, "rows": rs, "total": len(rs),
            "passed": sum(1 for r in rs if r["outcome"] == "pass"),
            "failed": sum(1 for r in rs if r["outcome"] == "fail"),
            "pending": sum(1 for r in rs if r["outcome"] == "pending"),
            "n_judged": sum(1 for r in rs if r["outcome"] in ("pass", "fail")),
            "recovered": [r for r in rs if r["recovered"]],
            "regressed": [r for r in rs if r["regressed_zero"]],
            "asis_search": latency_stats([r["asis_lat"] for r in rs]),
            "actual_search": latency_stats([r["actual_lat"] for r in rs]),
            "asis_ac": latency_stats([r["asis_ac_lat"] for r in rs]),
            "actual_ac": latency_stats([r["actual_ac_lat"] for r in rs]),
            "asis_ac_zero": sum(1 for r in rs if r["asis_ac_n"] == 0),
            "actual_ac_zero": sum(1 for r in rs if r["actual_ac_n"] == 0),
        }

    html_out = render(args, exp, act, asis, rows, total, passed, failed, recovered, regressed,
                      pending, n_judged,
                      perf, by_section, n_cmp, asis_zero)
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html_out, encoding="utf-8")
    size_mb = dest.stat().st_size / 1048576
    print(f"-> {dest} ({size_mb:.2f} MB)")
    print(f"   {total} scenario | Passed {passed} ({pct_of(passed,total)}%) | Failed {failed} ({pct_of(failed,total)}%)")
    print(f"   So sánh được (có dữ liệu cả 2 hệ thống): {n_cmp}/{total}")
    print(f"   As-Is trả 0 kết quả: {len(asis_zero)} ({pct_of(len(asis_zero),n_cmp)}% trên tập so sánh được)")
    print(f"   Trong đó hệ thống mới CÓ kết quả: {len(recovered)} ({pct_of(len(recovered),n_cmp)}%)")
    print(f"   Ngược lại (mới về 0): {len(regressed)}")
    print(f"   Search  latency: As-Is P95={perf['asis_search']['p95']}ms -> Actual P95={perf['actual_search']['p95']}ms")
    print(f"   Autocomp latency: As-Is P95={perf['asis_ac']['p95']}ms -> Actual P95={perf['actual_ac']['p95']}ms")


# ---------------------------------------------------------------------------
def bar_row(label, asis_v, actual_v, max_v, note=""):
    """1 dòng bar chart so sánh As-Is vs Actual. Vẽ bằng div/CSS thuần - report
    này phải mở được offline và in ra PDF, nên không nhúng thư viện chart."""
    if not max_v:
        max_v = 1
    a_w = (asis_v or 0) / max_v * 100
    n_w = (actual_v or 0) / max_v * 100
    if asis_v and actual_v:
        delta = (asis_v - actual_v) / asis_v * 100
        badge = (f'<span class="delta good">nhanh hơn {delta:.0f}%</span>' if delta > 0
                 else f'<span class="delta bad">chậm hơn {abs(delta):.0f}%</span>')
    else:
        badge = '<span class="delta na">—</span>'
    return f"""
      <div class="bar-row">
        <div class="bar-label">{esc(label)}{f'<span class="bar-note">{esc(note)}</span>' if note else ''}</div>
        <div class="bar-track">
          <div class="bar bar-asis" style="width:{a_w:.1f}%"><span>{fmt(asis_v)}ms</span></div>
          <div class="bar bar-actual" style="width:{n_w:.1f}%"><span>{fmt(actual_v)}ms</span></div>
        </div>
        <div class="bar-delta">{badge}</div>
      </div>"""


def perf_table(title, asis, actual, total=None):
    """Bảng percentile + SỐ SCENARIO ĐO ĐƯỢC của từng hệ (user 2026-09-09).

    Nêu rõ mẫu số là bắt buộc: hai hệ có thể không đo được cùng số lượng
    scenario (lỗi mạng, timeout, endpoint không trả latency...). Nếu chỉ đưa
    P95 mà không nói đo trên bao nhiêu scenario thì người đọc không biết con
    số đó đại diện cho bao nhiêu phần bộ test - dễ so sánh hai cột đứng cạnh
    nhau như thể cùng mẫu số.
    """
    def cell(a, n):
        if a is None or n is None:
            return f"<td>{fmt(a)}</td><td>{fmt(n)}</td><td class='delta na'>—</td>"
        d = (a - n) / a * 100 if a else 0
        cls = "good" if d > 0 else ("bad" if d < 0 else "na")
        sign = "−" if d > 0 else "+"
        return f"<td>{fmt(a)}</td><td>{fmt(n)}</td><td class='delta {cls}'>{sign}{abs(d):.0f}%</td>"

    na_, nn = asis.get("count") or 0, actual.get("count") or 0
    def cov(n):
        if not total:
            return f"{n:,}"
        return f"{n:,} <span class='cov'>({pct_of(n, total)}% của {total:,})</span>"
    warn = ""
    if total and (na_ < total or nn < total):
        warn = (f"<p class='muted small warn-cov'>Hai hệ thống không đo được cùng số lượng: "
                f"hệ cũ <b>{na_:,}</b>, hệ mới <b>{nn:,}</b> trên tổng <b>{total:,}</b> kịch bản. "
                f"Các kịch bản thiếu số đo (lỗi gọi, không trả thời gian phản hồi) không được "
                f"tính vào percentile của bên đó.</p>")
    return f"""
    <table class="perf">
      <thead><tr><th>{esc(title)}</th><th>Hệ thống cũ (As-Is)</th><th>Hệ thống mới (Actual)</th><th>Chênh lệch</th></tr></thead>
      <tbody>
        <tr class="cnt-row"><th>Số kịch bản đo được</th><td>{cov(na_)}</td><td>{cov(nn)}</td><td class="delta na">—</td></tr>
        <tr><th>Trung bình</th>{cell(asis['avg'], actual['avg'])}</tr>
        <tr><th>P50 (trung vị)</th>{cell(asis['p50'], actual['p50'])}</tr>
        <tr><th>P90</th>{cell(asis['p90'], actual['p90'])}</tr>
        <tr><th>P95</th>{cell(asis['p95'], actual['p95'])}</tr>
        <tr><th>P99</th>{cell(asis['p99'], actual['p99'])}</tr>
        <tr><th>Nhanh nhất</th>{cell(asis['min'], actual['min'])}</tr>
        <tr><th>Chậm nhất</th>{cell(asis['max'], actual['max'])}</tr>
      </tbody>
    </table>{warn}"""


def scenario_table(rows, max_list, show_counts=True):
    if not rows:
        return '<p class="muted">Không có scenario nào trong nhóm này.</p>'
    head = "<tr><th>#</th><th>Test ID</th><th>Từ khoá</th>"
    if show_counts:
        head += "<th>As-Is</th><th>Hệ thống mới</th>"
    head += "<th>Kết quả</th><th>Nhánh xử lý</th></tr>"
    body = []
    for i, r in enumerate(rows[:max_list], 1):
        st = r["status"] or "—"
        cls = "pass" if st == "passed" else ("fail" if st == "failed" else "na")
        ov = ' <span class="ov" title="QA đánh giá tay">✎</span>' if r.get("override") else ""
        cnt = (f"<td class='num'>{r['asis_count']}</td><td class='num'>{r['actual_count']}</td>"
               if show_counts else "")
        mode = r.get("resolved_mode") or "—"
        body.append(f"<tr><td class='num'>{i}</td><td class='mono'>{esc(r['test_id'])}</td>"
                    f"<td>{esc(r['query'])}</td>{cnt}"
                    f"<td><span class='st {cls}'>{esc(st)}</span>{ov}</td>"
                    f"<td class='mono'>{esc(mode)}</td></tr>")
    more = (f'<p class="muted">… và {len(rows) - max_list} scenario khác '
            f'(xem đầy đủ trong file dữ liệu kèm theo).</p>' if len(rows) > max_list else "")
    return f'<table class="scen"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table>{more}'


def render(args, exp, act, asis, rows, total, passed, failed, recovered, regressed, pending, n_judged, perf, by_section,
           n_cmp, asis_zero):
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    scope_banner = (f'<div class="scope"><b>Phạm vi báo cáo</b><p>{esc(args.scope_note)}</p></div>'
                    if getattr(args, "scope_note", None) else "")
    asis_lat = perf["asis_search"]
    act_lat = perf["actual_search"]
    speed_gain = ((asis_lat["p95"] - act_lat["p95"]) / asis_lat["p95"] * 100) if (asis_lat["p95"] and act_lat["p95"]) else 0

    # bar chart: latency P95 theo từng nhóm query
    max_lat = max([by_section[k]["asis_search"]["p95"] or 0 for k in by_section] +
                  [by_section[k]["actual_search"]["p95"] or 0 for k in by_section] + [1])
    bars = "".join(
        bar_row(by_section[k]["label"], by_section[k]["asis_search"]["p95"],
                by_section[k]["actual_search"]["p95"], max_lat,
                note=f'{by_section[k]["total"]} query')
        for k in SECTION_ORDER if by_section[k]["total"]
    )
    max_ac = max([by_section[k]["asis_ac"]["p95"] or 0 for k in by_section] +
                 [by_section[k]["actual_ac"]["p95"] or 0 for k in by_section] + [1])
    bars_ac = "".join(
        bar_row(by_section[k]["label"], by_section[k]["asis_ac"]["p95"],
                by_section[k]["actual_ac"]["p95"], max_ac,
                note=f'{by_section[k]["total"]} query')
        for k in SECTION_ORDER if by_section[k]["total"]
    )

    # bảng tổng hợp theo section
    sec_rows = "".join(
        f"<tr><td><b>{esc(by_section[k]['label'])}</b><div class='muted small'>{esc(by_section[k]['desc'])}</div></td>"
        f"<td class='num'>{by_section[k]['total']}</td>"
        f"<td class='num'>{by_section[k]['passed']}</td>"
        f"<td class='num'>{by_section[k]['failed']}</td>"
        f"<td class='num'>{pct_of(by_section[k]['passed'], by_section[k]['n_judged'])}%</td>"
        f"<td class='num hl'>{len(by_section[k]['recovered'])}</td>"
        f"<td class='num'>{pct_of(len(by_section[k]['recovered']), by_section[k]['total'])}%</td></tr>"
        for k in SECTION_ORDER if by_section[k]["total"]
    )

    # chi tiết từng section
    details = []
    for k in SECTION_ORDER:
        s = by_section[k]
        if not s["total"]:
            continue
        details.append(f"""
      <section class="sec">
        <h3>{esc(s['label'])} <span class="muted small">({s['total']} scenario)</span></h3>
        <p class="muted">{esc(s['desc'])}</p>
        <div class="kpi-row">
          <div class="kpi"><div class="kv">{s['total']}</div><div class="kl">Scenario</div></div>
          <div class="kpi ok"><div class="kv">{s['passed']}</div><div class="kl">Đạt ({pct_of(s['passed'], s['total'])}%)</div></div>
          <div class="kpi no"><div class="kv">{s['failed']}</div><div class="kl">Chưa đạt ({pct_of(s['failed'], s['total'])}%)</div></div>
          <div class="kpi hl"><div class="kv">{len(s['recovered'])}</div><div class="kl">Cũ 0 KQ → mới CÓ KQ</div></div>
        </div>
        <h4>Search Result — hệ thống cũ không trả kết quả, hệ thống mới có trả</h4>
        {scenario_table(s['recovered'], args.max_list)}
        <h4>AutoComplete — số query không có gợi ý</h4>
        <p>Hệ thống cũ: <b>{s['asis_ac_zero']}</b>/{s['total']} ({pct_of(s['asis_ac_zero'], s['total'])}%) ·
           Hệ thống mới: <b>{s['actual_ac_zero']}</b>/{s['total']} ({pct_of(s['actual_ac_zero'], s['total'])}%)</p>
        <h4>Performance nhóm này (P95)</h4>
        <p>Search: cũ <b>{fmt(s['asis_search']['p95'])}ms</b> → mới <b>{fmt(s['actual_search']['p95'])}ms</b> ·
           AutoComplete: cũ <b>{fmt(s['asis_ac']['p95'])}ms</b> → mới <b>{fmt(s['actual_ac']['p95'])}ms</b></p>
        <details><summary>Xem danh sách scenario chưa đạt ({s['failed']})</summary>
        {scenario_table([r for r in s['rows'] if r['status'] == 'failed'], args.max_list)}
        </details>
      </section>""")

    regressed_block = ""
    if regressed:
        regressed_block = f"""
      <div class="warn">
        <b>Cần lưu ý — {len(regressed)} trường hợp ngược lại:</b> hệ thống cũ CÓ trả kết quả nhưng hệ thống mới trả 0 kết quả.
        {scenario_table(regressed, args.max_list)}
      </div>"""
    else:
        regressed_block = """
      <div class="note ok-note"><b>Không có trường hợp thụt lùi:</b> không query nào mà hệ thống cũ có kết quả còn hệ thống mới trả về 0 kết quả.</div>"""

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Báo cáo kết quả kiểm thử Smart Search — {esc(args.store)}</title>
<style>
  :root {{
    --ink:#1a1f2b; --muted:#6b7280; --line:#e3e6ec; --bg:#ffffff; --soft:#f7f8fa;
    --old:#94a3b8; --new:#2563eb; --ok:#15803d; --okbg:#ecfdf5; --no:#b91c1c; --nobg:#fef2f2;
    --hl:#7c3aed; --hlbg:#f5f3ff; --warn:#b45309; --warnbg:#fffbeb;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font:14px/1.6 "Segoe UI",-apple-system,Roboto,Arial,sans-serif; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:32px 28px 64px; }}
  h1 {{ font-size:26px; margin:0 0 6px; letter-spacing:-.02em; }}
  h2 {{ font-size:19px; margin:38px 0 12px; padding-bottom:8px; border-bottom:2px solid var(--line); }}
  h3 {{ font-size:16px; margin:26px 0 6px; }}
  h4 {{ font-size:13px; margin:18px 0 6px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }}
  p {{ margin:8px 0; }}
  .muted {{ color:var(--muted); }} .small {{ font-size:12px; }}
  .mono {{ font-family:ui-monospace,Consolas,monospace; font-size:12px; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  header.cover {{ border-bottom:3px solid var(--ink); padding-bottom:18px; margin-bottom:8px; }}
  .meta {{ display:flex; flex-wrap:wrap; gap:6px 26px; color:var(--muted); font-size:13px; margin-top:10px; }}
  .kpi-row {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:16px 0; }}
  .kpi {{ border:1px solid var(--line); border-radius:10px; padding:14px 16px; background:var(--soft); }}
  .kpi .kv {{ font-size:26px; font-weight:700; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }}
  .kpi .kl {{ font-size:12px; color:var(--muted); margin-top:2px; }}
  .kpi.ok {{ background:var(--okbg); border-color:#bbf7d0; }} .kpi.ok .kv {{ color:var(--ok); }}
  .kpi.no {{ background:var(--nobg); border-color:#fecaca; }} .kpi.no .kv {{ color:var(--no); }}
  .kpi.wait {{ background:#fffbeb; border-color:#fde68a; }}
 .kpi.wait .kv {{ color:#b45309; }}
 .eq {{ font-size:15px; margin:14px 0 6px; padding:10px 14px; background:var(--soft);
        border:1px solid var(--line); border-radius:8px; }}
 .eq-ok {{ color:#15803d; font-weight:600; }}
 .eq-no {{ color:#b91c1c; font-weight:600; }}
 .eq-wait {{ color:#b45309; font-weight:600; }}
 .c-ok {{ color:#15803d; }} .c-no {{ color:#b91c1c; }} .c-wait {{ color:#b45309; }}
 table.tight td, table.tight th {{ font-size:13px; }}
 tr.sum td {{ background:var(--soft); border-top:2px solid var(--line); }}
 .kpi.hl {{ background:var(--hlbg); border-color:#ddd6fe; }} .kpi.hl .kv {{ color:var(--hl); }}
  table {{ border-collapse:collapse; width:100%; margin:10px 0 4px; font-size:13px; }}
  th,td {{ border:1px solid var(--line); padding:7px 10px; text-align:left; vertical-align:top; }}
  thead th {{ background:var(--soft); font-size:12px; text-transform:uppercase; letter-spacing:.03em; color:var(--muted); }}
  tbody th {{ background:var(--soft); font-weight:600; }}
  table.perf td {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .delta.good {{ color:var(--ok); font-weight:700; }}
  .delta.bad {{ color:var(--no); font-weight:700; }}
  .delta.na {{ color:var(--muted); }}
  .st {{ display:inline-block; padding:1px 8px; border-radius:20px; font-size:12px; font-weight:600; }}
  .st.pass {{ background:var(--okbg); color:var(--ok); }}
  .st.fail {{ background:var(--nobg); color:var(--no); }}
  .st.na {{ background:var(--soft); color:var(--muted); }}
  .ov {{ color:var(--hl); font-weight:700; }}
  .hl {{ color:var(--hl); font-weight:700; }}
  .bar-row {{ display:grid; grid-template-columns:210px 1fr 130px; gap:12px; align-items:center; margin:9px 0; }}
  .bar-label {{ font-size:13px; font-weight:600; }}
  .bar-note {{ display:block; font-weight:400; font-size:11px; color:var(--muted); }}
  .bar-track {{ display:flex; flex-direction:column; gap:3px; }}
  .bar {{ height:19px; border-radius:3px; position:relative; min-width:52px; transition:width .2s; }}
  .bar span {{ position:absolute; right:7px; top:1px; font-size:11px; color:#fff; font-variant-numeric:tabular-nums; }}
  .bar-asis {{ background:var(--old); }}
  .bar-actual {{ background:var(--new); }}
  .bar-delta {{ text-align:right; font-size:12px; }}
  .legend {{ display:flex; gap:18px; font-size:12px; color:var(--muted); margin:6px 0 14px; }}
  .legend i {{ display:inline-block; width:12px; height:12px; border-radius:2px; margin-right:5px; vertical-align:-1px; }}
  .note, .warn {{ border-radius:10px; padding:12px 16px; margin:14px 0; font-size:13px; }}
  .note {{ background:var(--soft); border:1px solid var(--line); }}
  .ok-note {{ background:var(--okbg); border-color:#bbf7d0; }}
  .warn {{ background:var(--warnbg); border:1px solid #fde68a; color:#78350f; }}
  details {{ margin:10px 0; }} summary {{ cursor:pointer; font-size:13px; color:var(--new); font-weight:600; }}
  .toolbar {{ position:sticky; top:0; background:rgba(255,255,255,.96); padding:10px 0; border-bottom:1px solid var(--line);
    display:flex; gap:10px; align-items:center; z-index:5; }}
  .btn {{ background:var(--new); color:#fff; border:0; border-radius:7px; padding:8px 16px; font-size:13px;
    font-weight:600; cursor:pointer; }}
  .btn:hover {{ filter:brightness(1.08); }}
  footer {{ margin-top:44px; padding-top:16px; border-top:1px solid var(--line); color:var(--muted); font-size:12px; }}
  /* Mục 1./2./3... gập mở được (user 2026-09-08). Nội dung mỗi mục được JS bọc
     vào .sect-body ngay sau <h2> nên không phải sửa cấu trúc HTML từng mục. */
  h2.sect-h {{ cursor:pointer; user-select:none; display:flex; align-items:center; gap:8px; }}
  h2.sect-h::before {{
    content:'▾'; font-size:13px; color:var(--muted); transition:transform .15s;
    display:inline-block; width:14px; text-align:center;
  }}
  h2.sect-h.collapsed::before {{ transform:rotate(-90deg); }}
  h2.sect-h:hover {{ color:var(--hl); }}
  h2.sect-h.collapsed {{ margin-bottom:6px; }}
  .btn.ghost {{ background:#fff; color:var(--ink); border:1px solid var(--line); }}
  .scope {{ background:#eff6ff; border:1px solid #93c5fd; border-left:5px solid #2563eb;
    border-radius:9px; padding:12px 16px; margin:18px 0 4px; }}
  .scope b {{ color:#1d4ed8; font-size:14px; }}
  .scope p {{ margin:5px 0 0; font-size:13px; color:#1e3a5f; }}
  tr.cnt-row td, tr.cnt-row th {{ background:var(--soft); font-weight:600; }}
  .cov {{ font-weight:400; color:var(--muted); font-size:12px; }}
  .warn-cov {{ background:#fffbeb; border:1px solid #fde68a; border-radius:7px; padding:8px 12px; margin-top:8px; }}
  @media print {{
    /* In ra PDF thì luôn mở hết, kể cả mục đang gập trên màn hình. */
    .sect-body {{ display:block !important; }}
    h2.sect-h::before {{ display:none; }}
    .toolbar {{ display:none; }}
    .wrap {{ max-width:none; padding:0 8px; }}
    body {{ font-size:11px; }}
    h2 {{ page-break-after:avoid; }} .sec {{ page-break-inside:avoid; }}
    table {{ page-break-inside:auto; font-size:10px; }} tr {{ page-break-inside:avoid; }}
    details {{ display:none; }}
    @page {{ margin:14mm; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <div class="toolbar">
    <button class="btn" onclick="window.print()">🖨️ Xuất PDF / In</button>
    <button class="btn ghost" id="expandAll" type="button">⊞ Mở tất cả</button>
    <button class="btn ghost" id="collapseAll" type="button">⊟ Thu tất cả</button>
    <span class="muted small">Hộp thoại in hiện ra, chọn “Save as PDF”. Các mục “Xem danh sách…” sẽ được ẩn khi in để báo cáo gọn.</span>
  </div>

  <header class="cover">
    <h1>Báo cáo kết quả kiểm thử Smart Search</h1>
    <p class="muted">So sánh hệ thống tìm kiếm MỚI với hệ thống ĐANG VẬN HÀNH — cửa hàng {esc(args.store)}</p>
    <div class="meta">
      <span><b>Ngày lập:</b> {now}</span>
      <span><b>Phạm vi:</b> {total:,} kịch bản tìm kiếm</span>
      <span><b>Hệ thống cũ:</b> {esc(asis.get('system',''))}</span>
      <span><b>Dữ liệu sản phẩm:</b> {esc(exp.get('catalogVersion','—'))} ({esc(str(exp.get('catalogSkuCount','—')))} SKU)</span>
    </div>
  </header>

  {scope_banner}

  <h2>1. Tổng quan kết quả</h2>
  <div class="kpi-row">
    <div class="kpi"><div class="kv">{total:,}</div><div class="kl">Tổng kịch bản kiểm thử</div></div>
    <div class="kpi ok"><div class="kv">{passed:,}</div><div class="kl">Đạt</div></div>
    <div class="kpi no"><div class="kv">{failed:,}</div><div class="kl">Chưa đạt</div></div>
    <div class="kpi wait"><div class="kv">{pending:,}</div><div class="kl">Chưa rà soát</div></div>
  </div>
  <table class="tight">
    <thead><tr><th>Phân loại</th><th>Số kịch bản</th><th>% trên tổng</th><th>Ý nghĩa</th></tr></thead>
    <tbody>
      <tr><td><b class="c-ok">Đạt</b></td><td class="num">{passed:,}</td><td class="num">{pct_of(passed,total)}%</td>
        <td>Đã kết luận đạt: danh sách sản phẩm hệ thống mới trả về trùng khớp cao với hệ thống cũ đang
            vận hành, hoặc QA đã rà soát tay và xác nhận hợp lệ.</td></tr>
      <tr><td><b class="c-no">Chưa đạt</b></td><td class="num">{failed:,}</td><td class="num">{pct_of(failed,total)}%</td>
        <td><b>QA đã ghi nhận vấn đề cụ thể</b> cho kịch bản này — có phiếu lỗi (bug) hoặc mục cần thảo
            luận nghiệp vụ kèm nội dung. Đây là danh sách việc cần xử lý, chi tiết ở phần phân nhóm.</td></tr>
      <tr><td><b class="c-wait">Chưa rà soát</b></td><td class="num">{pending:,}</td><td class="num">{pct_of(pending,total)}%</td>
        <td>Phép đo tự động thấy kết quả lệch so với hệ thống cũ, nhưng <b>chưa ai xác nhận đây là lỗi</b>.
            Với từ khoá rộng, khác thứ tự hoặc khác tập sản phẩm là bình thường và hệ thống mới vẫn có thể
            đang trả kết quả hợp lý hơn. Vì vậy <b>không tính vào Đạt lẫn Chưa đạt</b> cho tới khi QA rà soát.</td></tr>
      <tr class="sum"><td><b>Tổng</b></td><td class="num"><b>{total:,}</b></td><td class="num"><b>100%</b></td><td></td></tr>
    </tbody>
  </table>
  {regressed_block}

  <h2>2. Kết quả theo từng nhóm truy vấn</h2>
  <table>
    <thead><tr><th>Nhóm truy vấn</th><th>Scenario</th><th>Đạt</th><th>Chưa đạt</th><th>Tỷ lệ đạt</th>
      <th>Cũ 0 KQ → mới có</th><th>Tỷ lệ</th></tr></thead>
    <tbody>{sec_rows}</tbody>
  </table>

  <h2>3. Performance — Search</h2>
  {perf_table("Thời gian phản hồi (ms)", perf["asis_search"], perf["actual_search"], total)}
  <p class="muted small">Gọi tuần tự vào từng hệ thống trên cùng bộ <b>{total:,}</b> truy vấn. Số nhỏ hơn là tốt hơn.
     P95 = 95% truy vấn phản hồi nhanh hơn mức này. Dòng đầu bảng cho biết mỗi hệ thống thực sự
     thu được số đo trên bao nhiêu kịch bản — percentile chỉ tính trên số đó.</p>

  <h3>Mức cải thiện theo từng nhóm truy vấn (P95)</h3>
  <div class="legend"><span><i style="background:var(--old)"></i>Hệ thống cũ</span>
    <span><i style="background:var(--new)"></i>Hệ thống mới</span></div>
  {bars}

  <h2>4. Performance — AutoComplete</h2>
  {perf_table("Thời gian phản hồi (ms)", perf["asis_ac"], perf["actual_ac"], total)}
  <h3>Mức cải thiện theo từng nhóm truy vấn (P95)</h3>
  <div class="legend"><span><i style="background:var(--old)"></i>Hệ thống cũ</span>
    <span><i style="background:var(--new)"></i>Hệ thống mới</span></div>
  {bars_ac}

  <h2>5. Chi tiết theo từng nhóm truy vấn</h2>
  {''.join(details)}

  <footer>
    <p><b>Nguồn dữ liệu:</b> hệ thống mới đo ngày {esc(act.get('generatedDate',''))} ·
       hệ thống cũ đo ngày {esc(asis.get('generatedDate',''))} ·
       bộ kỳ vọng dựng trên dữ liệu sản phẩm {esc(exp.get('catalogVersion','—'))} (crawl {esc(exp.get('catalogCrawledDate','—'))}).</p>
    <p><b>Ghi chú phương pháp:</b> Mỗi truy vấn được gọi thật vào cả hai hệ thống, không dùng dữ liệu mô phỏng.
       Thời gian phản hồi đo ở phía client nên bao gồm cả độ trễ mạng. Hệ thống cũ trả tối đa
       {esc(str(asis.get('searchPageLimit','—')))} sản phẩm/truy vấn, hệ thống mới trả tối đa 50 — nên số lượng kết quả
       giữa hai bên không so trực tiếp được, báo cáo chỉ so “có kết quả / không có kết quả” và độ khớp với bộ kỳ vọng.</p>
    <p>Báo cáo tạo tự động lúc {now}.</p>
  </footer>
</div>
<script>
// Bọc nội dung giữa 2 thẻ <h2> vào 1 khối .sect-body rồi cho gập/mở. Làm bằng
// JS thay vì sửa template từng mục để không phải chạm vào 8 mục HTML rời rạc.
(function () {{
  var hs = Array.prototype.slice.call(document.querySelectorAll('.wrap h2'));
  hs.forEach(function (h) {{
    var wrap = document.createElement('div');
    wrap.className = 'sect-body';
    var n = h.nextElementSibling;
    while (n && n.tagName !== 'H2') {{
      var next = n.nextElementSibling;
      wrap.appendChild(n);
      n = next;
    }}
    h.parentNode.insertBefore(wrap, h.nextSibling);
    h.classList.add('sect-h');
    h.setAttribute('title', 'Bấm để gập/mở mục này');
    h.addEventListener('click', function () {{
      var col = h.classList.toggle('collapsed');
      wrap.hidden = col;
    }});
  }});
  function setAll(collapsed) {{
    document.querySelectorAll('.wrap h2.sect-h').forEach(function (h) {{
      h.classList.toggle('collapsed', collapsed);
      var b = h.nextElementSibling;
      if (b && b.classList.contains('sect-body')) b.hidden = collapsed;
    }});
  }}
  var ea = document.getElementById('expandAll'), ca = document.getElementById('collapseAll');
  if (ea) ea.addEventListener('click', function () {{ setAll(false); }});
  if (ca) ca.addEventListener('click', function () {{ setAll(true); }});
  // Trước khi in: mở hết để PDF không mất nội dung của mục đang gập.
  window.addEventListener('beforeprint', function () {{ setAll(false); }});
}})();
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
