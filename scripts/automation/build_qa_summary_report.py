# -*- coding: utf-8 -*-
"""Báo cáo tổng hợp QA một trang: Bug - Discussion - Hiệu năng.

Ba phần gập/mở độc lập, mặc định GẬP hết để người mở thấy ngay bức tranh tổng
rồi tự chọn chỗ cần đào sâu.

Phân nhóm bug/discussion dùng lại nguyên bộ luật của classify_findings.py -
không viết luật thứ hai, tránh hai báo cáo cùng nói về một tập ghi chú mà ra
hai con số khác nhau.

Chạy:
  python scripts/automation/build_qa_summary_report.py
"""
import html
import importlib.util
import io
import json
import statistics
import sys
from collections import Counter, OrderedDict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]

REPORT_DATE = "17/09/2026"
ACTUAL = ROOT / "SmartSearch/test_data/json/actual/NSG_ActualData_all_20260917_143705.json"
ASIS = ROOT / "SmartSearch/test_data/json/actual/AsIs_NSG_cache.json"
PF_STATE = ROOT / "SmartSearch/test_data/compare/pass_fail_state_nsg.json"
TRACKER = ROOT / "SmartSearch/test_data/compare/client_tracker_state_nsg.json"
OUT = ROOT / "SmartSearch/test_data/exports/qa_summary_20260917.html"

# Hai ngưỡng NẰM TRONG SPEC, trích nguyên văn để người đọc đối chiếu được.
P95_LIMIT = 650   # trang 15: "giám sát tự động thời gian phản hồi (P95 < 650ms)"
P99_LEXICAL_LIMIT = 300  # trang 10: BM25 đủ tốt thì "Trả kết quả ngay (P99 < 300ms)"


def load_classifier():
    spec = importlib.util.spec_from_file_location(
        "cf", ROOT / "scripts/automation/classify_findings.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def esc(s):
    return html.escape(str(s if s is not None else ""))


def norm_q(s):
    import re as _re, unicodedata as _ud
    return _re.sub(r"\s+", " ", _ud.normalize("NFC", str(s or "")).strip().casefold())


def load_tracker():
    """File theo dõi của khách - user cập nhật tay cuối mỗi ngày rồi nạp bằng
    import_client_tracker.py. Không có file thì phần này lặng lẽ bỏ qua."""
    if not TRACKER.exists():
        return None
    return json.loads(TRACKER.read_text(encoding="utf-8"))


def percentile(values, p):
    """Nội suy tuyến tính - cùng cách tính với hầu hết công cụ giám sát."""
    v = sorted(values)
    if not v:
        return 0
    k = (len(v) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


def stats_of(values):
    return {
        "n": len(values),
        "min": min(values), "max": max(values),
        "mean": statistics.mean(values), "median": statistics.median(values),
        "p95": percentile(values, 95), "p99": percentile(values, 99),
    }


# --------------------------------------------------------------------------
def collect_findings(cf):
    """Gom bug + discussion, gắn nhãn nhóm theo luật của classify_findings."""
    out = {}
    for kind, groups in (("bug", cf.BUG_GROUPS), ("discussion", cf.DISCUSSION_GROUPS)):
        entries = cf.load(kind, "nsg")
        rows, counts = [], Counter()
        for tid, v in sorted(entries.items(), key=lambda x: (x[1].get("query") or "").lower()):
            note = (v.get("note") or "").strip()
            hits = cf.match_groups(note, groups, tid)
            if not hits:
                hits = ["_unmatched"]
            for h in hits:
                counts[h] += 1
            rows.append({
                "test_id": tid, "query": v.get("query") or "",
                "dimension": v.get("dimension") or "", "note": note,
                "groups": hits, "has_shot": bool(v.get("screenshot")),
                "marked": (v.get("markedAt") or "")[:10],
                "source": "internal", "client_status": "", "client_note": "",
            })
        out[kind] = {"rows": rows, "counts": counts, "total": len(entries),
                     "groups": groups}
    return out


def collect_perf():
    act = json.loads(ACTUAL.read_text(encoding="utf-8"))["scenarios"]
    asis = json.loads(ASIS.read_text(encoding="utf-8"))["entries"]

    def meta(s, k):
        return (s.get("response_meta") or {}).get(k)

    rt = [s["api_latency_ms"] for s in act if s.get("api_latency_ms")]
    srv = [meta(s, "tookMs") for s in act if meta(s, "tookMs")]
    lex = [meta(s, "tookMs") for s in act
           if meta(s, "tookMs") and meta(s, "resolvedMode") == "lexical"]
    hyb = [meta(s, "tookMs") for s in act
           if meta(s, "tookMs") and meta(s, "resolvedMode") == "hybrid"]
    az = [v["search_latency_ms"] for v in asis.values() if v.get("search_latency_ms")]

    # keyword chậm nhất / nhanh nhất theo thời gian xử lý của chính server
    pairs = [(meta(s, "tookMs"), s["query"], meta(s, "resolvedMode"),
              s.get("api_latency_ms"), meta(s, "totalHits"))
             for s in act if meta(s, "tookMs")]
    pairs.sort()
    return {
        "roundtrip": stats_of(rt), "server": stats_of(srv),
        "lexical": stats_of(lex), "hybrid": stats_of(hyb), "asis": stats_of(az),
        "slowest": list(reversed(pairs[-12:])), "fastest": pairs[:12],
        "n_act": len(act), "n_asis": len(asis),
    }


def collect_reviewed():
    st = json.loads(PF_STATE.read_text(encoding="utf-8"))["entries"]
    manual = {k: v for k, v in st.items()
              if isinstance(v, dict) and v.get("manual_override")}
    return {
        "total_scenarios": len(st),
        "manual_total": len(manual),
        "manual_failed": sum(1 for v in manual.values() if v["manual_override"] == "failed"),
        "manual_passed": sum(1 for v in manual.values() if v["manual_override"] == "passed"),
        "failed_now": sum(1 for v in st.values()
                          if isinstance(v, dict) and v.get("status") == "failed"),
    }


# --------------------------------------------------------------------------
def group_table(kind, data, unmatched_label):
    groups = data["groups"]
    counts = data["counts"]
    chips = [f'<button class="chip" data-kind="{kind}" data-g="all" '
             f'aria-pressed="true">Tất cả <b>{data["total"]}</b></button>']
    rows_html = []
    for code, name, desc, _pat in groups:
        n = counts.get(code, 0)
        chips.append(f'<button class="chip" data-kind="{kind}" data-g="{code}" '
                     f'aria-pressed="false">{esc(name)} <b>{n}</b></button>')
        rows_html.append(
            f'<tr><td><b>{esc(name)}</b><div class="muted">{esc(desc)}</div></td>'
            f'<td class="num">{n}</td></tr>')
    nu = counts.get("_unmatched", 0)
    chips.append(f'<button class="chip" data-kind="{kind}" data-g="_unmatched" '
                 f'aria-pressed="false">{unmatched_label} <b>{nu}</b></button>')
    rows_html.append(
        f'<tr><td><b>{unmatched_label}</b><div class="muted">Ghi chú không khớp '
        f'luật phân nhóm nào - phải đọc tay để xếp loại.</div></td>'
        f'<td class="num">{nu}</td></tr>')
    return "\n".join(chips), "\n".join(rows_html)


def detail_rows(kind, data, show_tags=True):
    """Bảng chi tiết. `data-groups` vẫn giữ mã nhóm để chip lọc chạy được, còn
    hiển thị tag nhóm trong từng dòng là tuỳ mục - mục discussion đã có bảng
    đếm nhóm ngay phía trên nên không lặp lại."""
    out = []
    names = {g[0]: g[1] for g in data["groups"]}
    names["_unmatched"] = "Chưa phân nhóm"
    for r in data["rows"]:
        tags = " ".join(
            f'<span class="tag">{esc(names.get(g, g))}</span>'
            for g in r["groups"]) if show_tags else ""
        head = (f'{esc(r["test_id"])}<div class="muted">{esc(r["marked"])}</div>'
                if r["test_id"] else "")
        note = f'{esc(r["note"])[:700]}'
        if r.get("has_shot"):
            note += '<div class="muted">có ảnh chụp màn hình</div>'
        if r.get("client_note"):
            lead = ('<div class="muted" style="margin-top:6px">Ghi chú thêm:</div>'
                    if r["note"] else "")
            note += lead + esc(r["client_note"])[:700]
        out.append(
            f'<tr class="row" data-kind="{kind}" data-groups="{esc(" ".join(r["groups"]))}">'
            f'<td class="tid">{head}</td>'
            f'<td><b>{esc(r["query"])}</b>'
            f'<div class="muted">{esc(r["dimension"])}</div>{tags}</td>'
            f'<td class="note">{note}</td>'
            f'</tr>')
    return "\n".join(out)


OPEN_LIKE = {"OPEN", "NEED TO FIX", "IN_PROGRESS", "NEED_DISCUSS"}


def status_pill(st):
    cls = "bad" if st in ("OPEN", "NEED TO FIX") else (
        "warn" if st in ("IN_PROGRESS", "NEED_DISCUSS") else "ok")
    return f'<span class="pill {cls}">{esc(st)}</span>'


def tracker_bug_block(tr):
    """Bug theo KÊNH lấy từ file theo dõi của khách (autocomplete/banner/đa ngữ...)."""
    chans = tr["channels"]
    total_kw = sum(c["keywords"] for c in chans.values())
    total_open = sum(sum(n for st, n in c["statusCounts"].items() if st in OPEN_LIKE)
                     for c in chans.values())

    cards, chips, trows, drows = [], [], [], []
    chips.append(f'<button class="chip" data-kind="ch" data-g="all" '
                 f'aria-pressed="true">Tất cả <b>{total_kw}</b></button>')
    # Ba kênh user hỏi đích danh đứng trước để khỏi phải đi tìm.
    order = ["autocomplete", "banner", "multilanguage", "search", "mayyoulike", "other"]
    for code in [c for c in order if c in chans] + [c for c in chans if c not in order]:
        c = chans[code]
        op = sum(n for st, n in c["statusCounts"].items() if st in OPEN_LIKE)
        hl = " hl" if code in ("autocomplete", "banner", "multilanguage") else ""
        cards.append(f'<div class="card{hl}"><div class="n">{c["keywords"]}</div>'
                     f'<div class="l">{esc(c["label"])}<br><span class="muted">'
                     f'{op} còn phải xử lý</span></div></div>')
        chips.append(f'<button class="chip" data-kind="ch" data-g="{code}" '
                     f'aria-pressed="false">{esc(c["label"])} <b>{c["keywords"]}</b></button>')
        sc = " · ".join(f"{esc(k)} {v}" for k, v in sorted(c["statusCounts"].items()))
        trows.append(f'<tr><td><b>{esc(c["label"])}</b>'
                     f'<div class="muted">sheet {esc(c["sheet"])} · trạng thái tính tới '
                     f'{esc(c["statusDate"])}</div></td>'
                     f'<td class="num">{c["rawRows"]}</td><td class="num">{c["keywords"]}</td>'
                     f'<td class="num"><b>{op}</b></td><td class="muted">{sc}</td></tr>')
        for e in sorted(c["entries"], key=lambda x: x["query"].lower()):
            issues = "<br>".join(esc(i)[:300] for i in e["issues"]) or '<i>không ghi</i>'
            extra = (f'<div class="muted">{esc(" | ".join(e["notes"]))[:260]}</div>'
                     if e["notes"] else "")
            multi = (f'<div class="muted">gộp {e["rows"]} dòng cùng từ khoá</div>'
                     if e["rows"] > 1 else "")
            drows.append(
                f'<tr class="row" data-kind="ch" data-groups="{code}">'
                f'<td class="tid">{esc(c["label"])}{multi}</td>'
                f'<td><b>{esc(e["query"])}</b><div>{status_pill(e["status"])}</div></td>'
                f'<td class="note">{issues}{extra}</td></tr>')
    _j = chr(10).join
    return (_j(cards), _j(chips), _j(trows), _j(drows), total_kw, total_open)


def split_keys(q):
    """File khách đôi khi nhét nhiều từ khoá vào một ô: '"bông điên điển"/
    "bông so đũa"'. Tách theo / và , rồi bỏ ngoặc kép để đối chiếu từng cái."""
    import re as _re
    parts = [p.strip().strip('"' + "'") for p in _re.split(r"[/,]", str(q or ""))]
    return [p for p in parts if p]


def apply_client_note(row, note, hits, status):
    """Dồn ghi chú của khách vào một dòng đã có. Hai bên chép lại của nhau thì
    giữ bản dài hơn, không in hai lần cùng một câu."""
    row["source"] = "both"
    row["client_status"] = status
    a, b = norm_q(row["note"]), norm_q(note)
    if not b or (a and b in a):
        pass
    elif a and a in b:
        row["note"] = note
    else:
        row["client_note"] = (row["client_note"] + "\n" + note).strip() if row.get(
            "client_note") else note
    for h in hits:
        if h not in row["groups"]:
            row["groups"].append(h)
    if len(row["groups"]) > 1 and "_unmatched" in row["groups"]:
        row["groups"].remove("_unmatched")


def merge_client_discussion(tr, data, cf):
    """Gộp discussion trong file khách vào CHÍNH bảng discussion nội bộ.

    Cùng bộ luật phân nhóm, cùng bảng, cùng bộ lọc - chỉ khác cái nhãn nguồn.
    Trùng từ khoá thì nhập làm MỘT dòng, giữ cả hai ghi chú, nhóm là hợp của
    hai bên: hai nguồn đang nói về cùng một quyết định cần chốt.
    """
    ents = (tr.get("discussion") or {}).get("entries", []) if tr else []
    by_q = {norm_q(r["query"]): r for r in data["rows"]}
    both = client_only = 0
    for e in sorted(ents, key=lambda x: x["query"].lower()):
        note = "\n".join([t for t in e["issues"] + e["notes"] if t]).strip()
        hits = cf.match_groups(note, data["groups"])
        # Ô gộp nhiều từ khoá mà từ khoá nào cũng đã có dòng riêng: không tạo
        # dòng trùng, dồn thẳng ghi chú vào từng dòng đó.
        parts = split_keys(e["query"])
        targets = [by_q[norm_q(p)] for p in parts if norm_q(p) in by_q]
        if len(parts) > 1 and len(targets) == len(parts):
            for row in targets:
                apply_client_note(row, note, hits, e["status"])
            both += len(targets)
            continue
        row = by_q.get(norm_q(e["query"]))
        if row:
            both += 1
            apply_client_note(row, note, hits, e["status"])
        else:
            client_only += 1
            data["rows"].append({
                "test_id": "", "query": e["query"], "dimension": "",
                "note": "", "groups": hits or ["_unmatched"], "has_shot": False,
                "marked": "", "source": "client", "client_status": e["status"],
                "client_note": note})
    # Đếm lại từ đầu trên bảng đã gộp - không cộng dồn hai bộ đếm rời, vì dòng
    # trùng chỉ được tính MỘT lần dù có ở cả hai nguồn.
    data["rows"].sort(key=lambda r: (r["query"] or "").lower())
    counts = Counter()
    for r in data["rows"]:
        for g in r["groups"]:
            counts[g] += 1
        counts["src_" + r["source"]] += 1
    data["counts"] = counts
    data["total"] = len(data["rows"])
    return {"client": len(ents), "both": both, "client_only": client_only,
            "internal_only": data["total"] - both - client_only,
            "counts": counts}


def verdict(value, limit):
    ok = value < limit
    cls = "ok" if ok else "bad"
    word = "ĐẠT" if ok else "KHÔNG ĐẠT"
    gap = abs(value - limit)
    detail = f"dưới ngưỡng {gap:.0f}ms" if ok else f"vượt ngưỡng {gap:.0f}ms"
    return f'<span class="verdict {cls}">{word}</span> <span class="muted">({detail})</span>'


def perf_row(label, s, note=""):
    return (f'<tr><td><b>{esc(label)}</b>'
            f'{f"<div class=\"muted\">{esc(note)}</div>" if note else ""}</td>'
            f'<td class="num">{s["n"]:,}</td><td class="num">{s["min"]:,.0f}</td>'
            f'<td class="num">{s["median"]:,.0f}</td><td class="num">{s["mean"]:,.0f}</td>'
            f'<td class="num"><b>{s["p95"]:,.0f}</b></td><td class="num">{s["p99"]:,.0f}</td>'
            f'<td class="num">{s["max"]:,.0f}</td></tr>')


def main():
    cf = load_classifier()
    find = collect_findings(cf)
    tr = load_tracker()
    perf = collect_perf()
    rev = collect_reviewed()

    internal_before = find["discussion"]["total"]
    cd = merge_client_discussion(tr, find["discussion"], cf)
    if tr:
        ch_cards, ch_chips, ch_trows, ch_drows, ch_kw, ch_open = tracker_bug_block(tr)
        tr_date = tr["channels"]["search"]["statusDate"]
    else:
        ch_cards = ch_chips = ch_trows = ch_drows = ""
        ch_kw = ch_open = 0
        tr_date = "-"

    bug_chips, bug_groups_rows = group_table("bug", find["bug"], "Chưa phân nhóm")
    dis_chips, dis_groups_rows = group_table("discussion", find["discussion"], "Chưa phân nhóm")

    slow = "\n".join(
        f'<tr><td><b>{esc(q)}</b></td><td class="num">{t:,}</td>'
        f'<td class="num">{rt:,}</td><td>{esc(m)}</td><td class="num">{(h or 0):,}</td></tr>'
        for t, q, m, rt, h in perf["slowest"])
    fast = "\n".join(
        f'<tr><td><b>{esc(q)}</b></td><td class="num">{t:,}</td>'
        f'<td class="num">{rt:,}</td><td>{esc(m)}</td><td class="num">{(h or 0):,}</td></tr>'
        for t, q, m, rt, h in perf["fastest"])

    tr_date_disc = (tr.get("discussion") or {}).get("statusDate", "-") if tr else "-"

    srv, rtp, lex, hyb, asis = (perf["server"], perf["roundtrip"], perf["lexical"],
                                perf["hybrid"], perf["asis"])
    faster = asis["mean"] / rtp["mean"]

    doc = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Báo Cáo QA Smart Search NSG</title><style>
:root{{--bg:#fbfaf9;--fg:#1c1917;--mut:#78716c;--line:#e7e5e4;--card:#fff;
--acc:#1d4ed8;--ok:#15803d;--bad:#b91c1c;--warn:#a16207}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}}
.wrap{{max-width:1240px;margin:0 auto;padding:30px 20px 70px}}
h1{{font-size:27px;margin:0 0 4px;letter-spacing:-.02em}}
.sub{{color:var(--mut);margin:0 0 22px}}
details{{background:var(--card);border:1px solid var(--line);border-radius:12px;
margin-bottom:14px;overflow:hidden}}
details[open]{{box-shadow:0 1px 3px rgba(0,0,0,.05)}}
summary{{cursor:pointer;padding:16px 20px;font-size:17px;font-weight:650;
list-style:none;display:flex;align-items:center;gap:12px;user-select:none}}
summary::-webkit-details-marker{{display:none}}
summary::before{{content:"▸";color:var(--acc);font-size:15px;transition:transform .15s}}
details[open] summary::before{{transform:rotate(90deg)}}
summary .cnt{{margin-left:auto;font-weight:500;font-size:13px;color:var(--mut)}}
.body{{padding:0 20px 22px;border-top:1px solid var(--line)}}
.cards{{display:flex;gap:11px;flex-wrap:wrap;margin:18px 0}}
.card{{border:1px solid var(--line);border-radius:10px;padding:13px 17px;min-width:135px}}
.card.hl{{border-color:var(--acc);background:#eff6ff}}
.card .n{{font-size:25px;font-weight:650;letter-spacing:-.02em}}
.card .l{{color:var(--mut);font-size:12px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{padding:9px 11px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}
th{{background:#f5f5f4;font-size:12px;color:#57534e;font-weight:600}}
td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums}}
.muted{{color:var(--mut);font-size:11.5px}}
.scroll{{overflow-x:auto;border:1px solid var(--line);border-radius:9px;margin-bottom:16px}}
.chips{{display:flex;gap:7px;flex-wrap:wrap;margin:14px 0}}
.chip{{font:inherit;font-size:12.5px;padding:5px 11px;border-radius:99px;cursor:pointer;
border:1px solid var(--line);background:#f5f5f4;color:#57534e}}
.chip[aria-pressed="true"]{{background:var(--acc);border-color:var(--acc);color:#fff}}
.chip b{{font-variant-numeric:tabular-nums}}
.tag{{display:inline-block;font-size:10.5px;padding:1px 7px;border-radius:99px;
background:#eff6ff;color:#1e40af;border:1px solid #bfdbfe;margin:3px 3px 0 0}}
.tid{{font-size:11.5px;color:var(--mut);white-space:nowrap}}
.note{{white-space:pre-wrap;font-size:12px;color:#44403c;max-width:560px}}
.verdict{{font-weight:700}} .verdict.ok{{color:var(--ok)}} .verdict.bad{{color:var(--bad)}}
.callout{{border-left:4px solid var(--warn);background:#fffbeb;padding:12px 15px;
border-radius:0 8px 8px 0;margin:16px 0;font-size:13px}}
.callout b{{color:#92400e}}
.pill{{display:inline-block;font-size:10.5px;font-weight:700;padding:1px 8px;
border-radius:99px;margin-top:3px}}
.pill.bad{{background:#fef2f2;color:var(--bad);border:1px solid #fecaca}}
.pill.warn{{background:#fffbeb;color:var(--warn);border:1px solid #fde68a}}
.pill.ok{{background:#f0fdf4;color:var(--ok);border:1px solid #bbf7d0}}
h4{{font-size:14px;margin:26px 0 6px;padding-top:18px;border-top:1px solid var(--line)}}
.hidden{{display:none}}
</style></head><body><div class="wrap">

<h1>Báo Cáo QA Smart Search — NSG</h1>
<p class="sub">Ngày báo cáo {REPORT_DATE} · Expected 16/09 · Actual dev 17/09 · As-Is production
· {rev["total_scenarios"]:,} kịch bản · bấm từng mục để mở</p>

<details>
<summary>1 · Báo cáo Bug<span class="cnt">{find["bug"]["total"]} bug đã ghi ·
{rev["manual_failed"]} case Failed đã duyệt tay</span></summary>
<div class="body">

<div class="cards">
<div class="card hl"><div class="n">{find["bug"]["total"]}</div><div class="l">bug đã ghi</div></div>
<div class="card"><div class="n">{rev["manual_failed"]}</div><div class="l">case Failed QA duyệt tay</div></div>
<div class="card"><div class="n">{rev["manual_passed"]}</div><div class="l">case QA chấm lại thành Passed</div></div>
<div class="card"><div class="n">{rev["manual_total"]}</div><div class="l">tổng đã duyệt tay</div></div>
<div class="card"><div class="n">{rev["failed_now"]}</div><div class="l">đang Failed (cả máy chấm)</div></div>
</div>

<p class="muted">Một bug có thể thuộc NHIỀU nhóm cùng lúc - ghi chú nêu hai vấn đề thì
nằm ở cả hai. Vì vậy tổng các nhóm lớn hơn {find["bug"]["total"]}, và đó là cố ý:
gán một nhãn duy nhất sẽ làm mất việc phải sửa.</p>

<div class="scroll"><table>
<tr><th>Nhóm lỗi</th><th class="num">Số bug</th></tr>
{bug_groups_rows}
</table></div>

<div class="chips">{bug_chips}</div>
<div class="scroll"><table>
<tr><th style="width:110px">Test ID</th><th style="width:250px">Từ khoá</th><th>Ghi chú của QA</th></tr>
{detail_rows("bug", find["bug"])}
</table></div>

<h4>Bug theo kênh — từ file theo dõi của khách</h4>
<p class="muted">Nguồn: <code>Part1_SmartSearch_QueryList.xlsx</code>, user cập nhật tay cuối
mỗi ngày rồi nạp bằng <code>import_client_tracker.py</code>. Trạng thái lấy ở cột ngày mới
nhất của từng sheet.</p>

<div class="cards">{ch_cards}</div>

<div class="scroll"><table>
<tr><th>Kênh</th><th class="num">Dòng thô</th><th class="num">Từ khoá</th>
<th class="num">Còn phải xử lý</th><th>Phân bố trạng thái</th></tr>
{ch_trows}
</table></div>

<div class="callout">
<b>Về việc bỏ từ khoá trùng.</b> Trùng <b>trong cùng một kênh</b> thì gộp làm một, nhưng
<b>giữ lại mọi mô tả lỗi khác nhau</b> — ví dụ <i>bánh hotteok</i> có một dòng "check lại
list" đã DONE và một dòng "thiếu SKU 8935297103726 dù còn hàng" vẫn OPEN; đó là hai lỗi
khác nhau, xoá một dòng là mất việc phải sửa. Trùng <b>giữa các kênh</b> thì KHÔNG gộp:
<i>lays</i> hay <i>bnh kinh do</i> có mặt ở cả Search, AutoComplete và Banner vì lỗi ở ba
chỗ khác nhau. Tổng cộng gộp được 4 dòng trùng thật.
</div>

<div class="chips">{ch_chips}</div>
<div class="scroll"><table>
<tr><th style="width:150px">Kênh</th><th style="width:230px">Từ khoá / trạng thái</th>
<th>Mô tả lỗi</th></tr>
{ch_drows}
</table></div>
</div>
</details>

<details>
<summary>2 · Báo cáo Discussion<span class="cnt">{find["discussion"]["total"]} keyword chờ chốt</span></summary>
<div class="body">

<div class="cards">
<div class="card hl"><div class="n">{find["discussion"]["total"]}</div><div class="l">keyword cần thảo luận<br><span class="muted">đã gộp 2 nguồn</span></div></div>
<div class="card"><div class="n">{len(find["discussion"]["groups"])}</div><div class="l">nhóm vấn đề</div></div>
</div>

<p class="muted">Đây là những ca <b>chưa chốt được đúng/sai</b> - không phải bug.
Phần lớn là câu hỏi nghiệp vụ cần BA/PO quyết, không phải việc của dev.</p>

<div class="scroll"><table>
<tr><th>Nhóm vấn đề</th><th class="num">Số keyword</th></tr>
{dis_groups_rows}
</table></div>

<div class="chips">{dis_chips}</div>
<div class="scroll"><table>
<tr><th style="width:110px">Test ID</th><th style="width:250px">Từ khoá</th><th>Nội dung cần chốt</th></tr>
{detail_rows("discussion", find["discussion"], show_tags=False)}
</table></div>
</div>
</details>

<details>
<summary>3 · Hiệu năng: hệ mới (dev) so với hệ cũ (production)<span class="cnt">
P95 máy chủ {srv["p95"]:,.0f}ms / ngưỡng {P95_LIMIT}ms</span></summary>
<div class="body">

<div class="cards">
<div class="card hl"><div class="n">{srv["p95"]:,.0f}<span style="font-size:14px">ms</span></div>
<div class="l">P95 thời gian máy chủ xử lý</div></div>
<div class="card"><div class="n">{rtp["p95"]:,.0f}<span style="font-size:14px">ms</span></div>
<div class="l">P95 tính cả đường truyền</div></div>
<div class="card"><div class="n">{asis["p95"]:,.0f}<span style="font-size:14px">ms</span></div>
<div class="l">P95 hệ cũ (production)</div></div>
<div class="card"><div class="n">{faster:.1f}×</div><div class="l">hệ mới nhanh hơn hệ cũ (trung bình)</div></div>
</div>

<h3 style="font-size:15px;margin:20px 0 8px">Đối chiếu với ngưỡng trong spec</h3>
<div class="scroll"><table>
<tr><th>Yêu cầu trong spec</th><th class="num">Đo được</th><th>Kết luận</th></tr>
<tr><td><b>P95 &lt; {P95_LIMIT}ms</b><div class="muted">Trang 15: "Duy trì giám sát tự động
thời gian phản hồi (P95 &lt; 650ms)". Đo bằng <code>response_meta.tookMs</code> —
thời gian chính máy chủ tự báo.</div></td>
<td class="num">{srv["p95"]:,.0f}ms</td><td>{verdict(srv["p95"], P95_LIMIT)}</td></tr>
<tr><td>Cùng ngưỡng nhưng tính <b>cả đường truyền mạng</b><div class="muted">Thời gian
người dùng thật sự chờ, đo từ máy chạy test.</div></td>
<td class="num">{rtp["p95"]:,.0f}ms</td><td>{verdict(rtp["p95"], P95_LIMIT)}</td></tr>
<tr><td><b>P99 &lt; {P99_LEXICAL_LIMIT}ms</b> cho nhánh nhanh<div class="muted">Trang 10:
BM25 đủ tốt thì "Trả kết quả ngay (P99 &lt; 300ms)". Chỉ tính
{lex["n"]:,} keyword đi nhánh <code>lexical</code>.</div></td>
<td class="num">{lex["p99"]:,.0f}ms</td><td>{verdict(lex["p99"], P99_LEXICAL_LIMIT)}</td></tr>
</table></div>

<div class="callout">
<b>Kết luận P95 phụ thuộc vào đo cái gì.</b> Tính theo thời gian máy chủ tự báo thì
<b>đạt</b>, nhưng chỉ dư {P95_LIMIT - srv["p95"]:.0f}ms — sát ngưỡng, tải cao hơn là vượt.
Tính cả đường truyền thì <b>không đạt</b> ({rtp["p95"]:,.0f}ms). Spec không nói rõ đo ở đâu,
nên cần chốt lại với dev trước khi coi đây là đạt hay trượt.
</div>

<h3 style="font-size:15px;margin:22px 0 8px">Số liệu đầy đủ (mili-giây)</h3>
<div class="scroll"><table>
<tr><th>Phép đo</th><th class="num">Số mẫu</th><th class="num">Nhanh nhất</th>
<th class="num">Trung vị</th><th class="num">Trung bình</th><th class="num">P95</th>
<th class="num">P99</th><th class="num">Chậm nhất</th></tr>
{perf_row("Hệ mới — máy chủ xử lý", srv, "response_meta.tookMs")}
{perf_row("Hệ mới — cả đường truyền", rtp, "đo từ máy chạy test")}
{perf_row("Hệ mới — nhánh lexical", lex, "BM25 thuần, không gọi vector")}
{perf_row("Hệ mới — nhánh hybrid", hyb, "có gọi thêm vector k-NN")}
{perf_row("Hệ cũ (production)", asis, "www.lottemart.vn, cả đường truyền")}
</table></div>

<div class="callout">
<b>Hai con số cuối không so trực tiếp được với nhau.</b> Hệ mới đo hôm nay, hệ cũ đo
ngày 08/09; và hệ cũ chỉ có số cả-đường-truyền, không có thời gian máy chủ tự báo.
Dòng hợp lệ để so là <b>"cả đường truyền" của hệ mới ({rtp["mean"]:,.0f}ms trung bình)
với hệ cũ ({asis["mean"]:,.0f}ms)</b> — cùng cách đo, cùng một máy.
Hệ cũ có ca chậm nhất tới {asis["max"]:,.0f}ms, hệ mới cao nhất {rtp["max"]:,.0f}ms.
</div>

<h3 style="font-size:15px;margin:22px 0 8px">12 từ khoá máy chủ xử lý chậm nhất</h3>
<div class="scroll"><table>
<tr><th>Từ khoá</th><th class="num">Máy chủ (ms)</th><th class="num">Cả đường truyền</th>
<th>Nhánh</th><th class="num">Tổng kết quả</th></tr>
{slow}
</table></div>

<h3 style="font-size:15px;margin:22px 0 8px">12 từ khoá nhanh nhất</h3>
<div class="scroll"><table>
<tr><th>Từ khoá</th><th class="num">Máy chủ (ms)</th><th class="num">Cả đường truyền</th>
<th>Nhánh</th><th class="num">Tổng kết quả</th></tr>
{fast}
</table></div>
</div>
</details>

</div>
<script>
// Lọc đa chọn trong từng mục. Bấm "Tất cả" xoá hết lựa chọn; bấm lại một nhãn
// đang bật thì tắt nhãn đó. Không chọn gì = hiện tất cả.
document.querySelectorAll('.chip').forEach(function (c) {{
  c.addEventListener('click', function () {{
    var kind = c.dataset.kind, g = c.dataset.g;
    var chips = document.querySelectorAll('.chip[data-kind="' + kind + '"]');
    if (g === 'all') {{
      chips.forEach(function (x) {{ x.setAttribute('aria-pressed', x.dataset.g === 'all'); }});
    }} else {{
      c.setAttribute('aria-pressed', c.getAttribute('aria-pressed') !== 'true');
      var anyOn = Array.prototype.some.call(chips, function (x) {{
        return x.dataset.g !== 'all' && x.getAttribute('aria-pressed') === 'true';
      }});
      document.querySelector('.chip[data-kind="' + kind + '"][data-g="all"]')
        .setAttribute('aria-pressed', !anyOn);
    }}
    var on = [];
    chips.forEach(function (x) {{
      if (x.dataset.g !== 'all' && x.getAttribute('aria-pressed') === 'true') on.push(x.dataset.g);
    }});
    document.querySelectorAll('.row[data-kind="' + kind + '"]').forEach(function (r) {{
      var gs = r.dataset.groups.split(' ');
      var show = !on.length || on.some(function (o) {{ return gs.indexOf(o) !== -1; }});
      r.classList.toggle('hidden', !show);
    }});
  }});
}});
</script>
</body></html>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")

    print(f"Bug        : {find['bug']['total']} | Discussion: {find['discussion']['total']}")
    print(f"Failed duyệt tay: {rev['manual_failed']} | Passed duyệt tay: {rev['manual_passed']}")
    print(f"P95 máy chủ {srv['p95']:.0f}ms (ngưỡng {P95_LIMIT}) -> "
          f"{'ĐẠT' if srv['p95'] < P95_LIMIT else 'KHÔNG ĐẠT'}")
    print(f"P95 cả đường truyền {rtp['p95']:.0f}ms -> "
          f"{'ĐẠT' if rtp['p95'] < P95_LIMIT else 'KHÔNG ĐẠT'}")
    print(f"P99 lexical {lex['p99']:.0f}ms (ngưỡng {P99_LEXICAL_LIMIT}) -> "
          f"{'ĐẠT' if lex['p99'] < P99_LEXICAL_LIMIT else 'KHÔNG ĐẠT'}")
    print(f"\n-> {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
