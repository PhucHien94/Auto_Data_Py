# -*- coding: utf-8 -*-
"""So độ lệch kết quả giữa TIẾNG VIỆT / TIẾNG ANH / TIẾNG HÀN khi lang khớp query.

Ba nhánh:
  VI : query tiếng Việt  + lang=vi   (mốc; lấy từ bộ Actual 16/09)
  EN : bản dịch tiếng Anh + lang=en
  KO : bản dịch tiếng Hàn + lang=ko

Khác với bộ chạy 14/09 (giữ lang=vi cố định cho mọi query): ở đó chỉ đo khả năng
engine HIỂU CHỮ nước ngoài. Ở đây lang đi theo query, tức mô phỏng đúng đường mà
người dùng Hàn/Anh thật đi khi đổi ngôn ngữ trên app - nên đo được cả tác động
của tham số lang lẫn của chuỗi query.

Để tách riêng phần chênh do RIÊNG tham số lang: chạy thêm nhánh đối chứng CÙNG
NGÀY - y hệt chuỗi query EN/KO nhưng gửi lang=vi. Chuỗi query giống nhau, chỉ
khác mỗi lang, nên phần chênh còn lại quy được cho lang. Đối chứng bắt buộc phải
cùng ngày: biến động kết quả trong một ngày đã đo được tới 20,6%.

CẢNH BÁO diễn giải - in thẳng trong report: bản dịch do QA làm tay, nên "khác
kết quả" có thể do engine, mà cũng có thể do từ dịch chưa khớp cách gọi trong
catalog. Report nêu "khác biệt cần review", không tự gán nhãn bug.
"""
import argparse
import html
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
LANG_NAME = {"en": "Tiếng Anh", "ko": "Tiếng Hàn"}
ORDER = ["en", "ko"]

BADGE = {
    "IDENTICAL": ("giống hệt", "#15803d", "#f0fdf4"),
    "SAME_SET": ("cùng tập, khác thứ tự", "#0369a1", "#f0f9ff"),
    "HIGH": ("trùng cao", "#15803d", "#f0fdf4"),
    "PARTIAL": ("trùng một phần", "#a16207", "#fefce8"),
    "LOW": ("trùng rất ít", "#c2410c", "#fff7ed"),
    "NONE": ("không trùng SKU nào", "#b91c1c", "#fef2f2"),
    "ZERO": ("0 kết quả", "#b91c1c", "#fef2f2"),
    "VI_ZERO": ("bản Việt 0 KQ", "#7c3aed", "#faf5ff"),
    "BOTH_ZERO": ("cả hai 0 KQ", "#57534e", "#fafaf9"),
    "ERROR": ("lỗi gọi API", "#57534e", "#fafaf9"),
}
SEVERITY = ["ZERO", "NONE", "LOW", "PARTIAL", "HIGH", "SAME_SET", "IDENTICAL",
            "BOTH_ZERO", "VI_ZERO", "ERROR"]
SEV = {c: i for i, c in enumerate(SEVERITY)}
DIVERGENT = {"ZERO", "NONE", "LOW", "PARTIAL"}


def classify(vi, other):
    """Mốc là top-20 SKU của bản tiếng Việt - cùng thước đo với compare_results.py."""
    if other is None:
        return "ERROR", 0.0
    if not vi:
        return ("BOTH_ZERO", 100.0) if not other else ("VI_ZERO", 0.0)
    if not other:
        return "ZERO", 0.0
    top20 = vi[:20]
    oset = set(other)
    pct = round(sum(1 for s in top20 if s in oset) / len(top20) * 1000) / 10
    if vi == other:
        return "IDENTICAL", pct
    if set(vi) == oset:
        return "SAME_SET", pct
    if pct >= 70:
        return "HIGH", pct
    if pct >= 30:
        return "PARTIAL", pct
    return ("LOW", pct) if pct > 0 else ("NONE", pct)


def esc(s):
    return html.escape(str(s if s is not None else ""))


def read_ndjson_best(path):
    """Dòng sau đè dòng trước cho cùng (test_id, lang); dòng lỗi không đè dòng tốt."""
    best = {}
    if not path.exists():
        return best
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            k = (r["test_id"], r["lang"])
            prev = best.get(k)
            if prev is not None and prev.get("error") is None and r.get("error"):
                continue
            best[k] = r
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--actual", default="SmartSearch/test_data/json/actual/NSG_ActualData_all_20260916_full.json",
                    help="bộ Actual tiếng Việt (lang=vi) dùng làm mốc")
    ap.add_argument("--raw", default="SmartSearch/test_data/multilang/langmatch_raw.ndjson")
    ap.add_argument("--raw-langvi",
                    default="SmartSearch/test_data/multilang/langvi_control_20260917.ndjson",
                    help="nhánh đối chứng: CÙNG chuỗi query EN/KO nhưng giữ lang=vi, crawl "
                         "CÙNG NGÀY với nhánh chính. Phải cùng ngày thì mới tách sạch được "
                         "tác động của lang - bộ 14/09 cách 3 ngày, mà riêng biến động trong "
                         "một ngày đã đo được tới 20,6%%, nên không dùng làm đối chứng.")
    ap.add_argument("--translations", default="SmartSearch/test_data/multilang/translations.json")
    ap.add_argument("--passfail", default="SmartSearch/test_data/compare/pass_fail_state_nsg.json",
                    help="trạng thái QA đã soát của chính bản tiếng Việt. Dùng để tách bằng "
                         "chứng chắc / chưa kết luận được: nếu bản Việt đã Fail sẵn thì bản "
                         "dịch lệch theo cũng không nói lên điều gì về xử lý đa ngữ.")
    ap.add_argument("--out-html", default="SmartSearch/test_data/multilang/langmatch_report.html")
    ap.add_argument("--out-json", default="SmartSearch/test_data/multilang/langmatch_findings.json")
    ap.add_argument("--max-rows", type=int, default=400)
    args = ap.parse_args()

    # --- mốc tiếng Việt ---
    vi = {}
    for s in json.loads((ROOT / args.actual).read_text(encoding="utf-8"))["scenarios"]:
        vi[s["test_id"]] = {
            "query": s["query"],
            "skus": [str(p["sku"]) for p in (s.get("search_results") or [])],
            "names": [p.get("name") for p in (s.get("search_results") or [])][:20],
            "total": (s.get("response_meta") or {}).get("totalHits"),
            "mode": (s.get("response_meta") or {}).get("resolvedMode"),
            "dimension": s.get("dimension"),
        }

    pf = {}
    _pf = ROOT / args.passfail
    if _pf.exists():
        pf = {k: (v.get("status") if isinstance(v, dict) else v)
              for k, v in json.loads(_pf.read_text(encoding="utf-8"))["entries"].items()}

    tr = {i["test_id"]: i for i in
          json.loads((ROOT / args.translations).read_text(encoding="utf-8"))["items"]}
    rows = read_ndjson_best(ROOT / args.raw)
    rows_vi = read_ndjson_best(ROOT / args.raw_langvi)  # đối chứng: cùng query, lang=vi

    n_err = sum(1 for r in rows.values() if r.get("error"))

    findings = []
    per = {lg: Counter() for lg in ORDER}
    overlap = {lg: [] for lg in ORDER}
    modes = {"vi": Counter(), "en": Counter(), "ko": Counter()}
    lang_only = {lg: [] for lg in ORDER}   # chênh do RIÊNG tham số lang

    for tid, v in vi.items():
        if tid not in tr:
            continue
        langs = {}
        for lg in ORDER:
            r = rows.get((tid, lg))
            if not r:
                continue
            code, pct = classify(v["skus"], r.get("skus"))
            per[lg][code] += 1
            overlap[lg].append(pct)
            modes[lg][r.get("resolved_mode") or "-"] += 1
            # cùng chuỗi query, chỉ khác lang -> chênh thuần do lang
            rv = rows_vi.get((tid, lg))
            same_lang_diff = None
            if rv and not rv.get("error") and not r.get("error"):
                a, b = rv.get("skus") or [], r.get("skus") or []
                if a or b:
                    same_lang_diff = (len(set(a) & set(b)) / len(set(a) | set(b)) * 100
                                      if (set(a) | set(b)) else 100.0)
                    lang_only[lg].append(same_lang_diff)
            langs[lg] = {
                "query": r.get("query"), "code": code, "overlap_pct": pct,
                "n": len(r.get("skus") or []), "mode": r.get("resolved_mode"),
                "top3": (r.get("names") or [])[:3], "error": r.get("error"),
                "jaccard_vs_langvi": same_lang_diff,
            }
        if not langs:
            continue
        modes["vi"][v["mode"] or "-"] += 1
        worst = min(SEV[x["code"]] for x in langs.values())
        findings.append({
            "test_id": tid, "vi_query": v["query"], "dimension": v["dimension"],
            "vi_n": len(v["skus"]), "vi_total": v["total"], "vi_mode": v["mode"],
            "vi_top3": v["names"][:3], "langs": langs, "worst_rank": worst,
            "vi_qa_status": pf.get(tid),
        })

    findings.sort(key=lambda x: x["worst_rank"])
    divergent = [f for f in findings
                 if any(d["code"] in DIVERGENT for d in f["langs"].values())]

    # Vế A: đổi CHỮ nhưng giữ lang=vi. So với vế B (đổi cả chữ lẫn lang) thì
    # biết được phần nào do chuỗi query, phần nào do tham số lang.
    ctrl_vs_vi = {lg: [] for lg in ORDER}
    for tid, v in vi.items():
        if tid not in tr or not v["skus"]:
            continue
        for lg in ORDER:
            rv = rows_vi.get((tid, lg))
            if not rv or rv.get("error"):
                continue
            oset = set(rv.get("skus") or [])
            t20 = v["skus"][:20]
            ctrl_vs_vi[lg].append(sum(1 for s_ in t20 if s_ in oset) / len(t20) * 100)

    # Bản Việt đã Pass -> bản dịch lệch là bằng chứng dùng được.
    # Bản Việt đang Fail -> chính mốc đã sai, lệch thêm không kết luận được gì.
    solid = [f for f in divergent if f.get("vi_qa_status") == "passed"]
    inconclusive = [f for f in divergent if f.get("vi_qa_status") != "passed"]

    # EN vs KO trực tiếp
    en_ko = []
    for f in findings:
        a = f["langs"].get("en")
        b = f["langs"].get("ko")
        if not a or not b:
            continue
        ra = rows.get((f["test_id"], "en")) or {}
        rb = rows.get((f["test_id"], "ko")) or {}
        sa, sb = set(ra.get("skus") or []), set(rb.get("skus") or [])
        if sa or sb:
            en_ko.append(len(sa & sb) / len(sa | sb) * 100)

    stats = {}
    for lg in ORDER:
        v = overlap[lg]
        if not v:
            continue
        n = len(v)
        stats[lg] = {
            "n": n, "mean": statistics.mean(v), "median": statistics.median(v),
            "ge70": sum(1 for x in v if x >= 70) / n * 100,
            "ge50": sum(1 for x in v if x >= 50) / n * 100,
            "zero": sum(1 for x in v if x == 0) / n * 100,
            "zero_n": sum(1 for x in v if x == 0),
            "divergent": sum(per[lg][c] for c in DIVERGENT),
        }

    (ROOT / args.out_json).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / args.out_json).write_text(json.dumps({
        "generated": "2026-09-17", "store": "nsg",
        "method": "VI(lang=vi) vs EN(lang=en) vs KO(lang=ko); mốc = top-20 SKU bản tiếng Việt",
        "counts": {"testable": len(findings), "divergent": len(divergent),
                   "divergent_solid": len(solid), "divergent_inconclusive": len(inconclusive),
                   "api_errors": n_err},
        "overlap_stats": stats,
        "per_lang_buckets": {lg: dict(c) for lg, c in per.items()},
        "resolved_mode": {k: dict(v) for k, v in modes.items()},
        "en_vs_ko_jaccard_mean": statistics.mean(en_ko) if en_ko else None,
        "findings": findings,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------------- HTML ----------------
    def badge(code, pct=None):
        label, fg, bg = BADGE[code]
        extra = f" {pct}%" if pct is not None and code not in ("IDENTICAL", "BOTH_ZERO", "ERROR") else ""
        return (f'<span class="bdg" style="color:{fg};background:{bg};border-color:{fg}33">'
                f'{esc(label)}{extra}</span>')

    ov_rows = "".join(
        f"<tr><td><b>{LANG_NAME[lg]}</b></td>"
        f"<td class=num><b>{o['mean']:.1f}%</b></td><td class=num>{o['median']:.1f}%</td>"
        f"<td class=num>{o['ge70']:.1f}%</td><td class=num>{o['ge50']:.1f}%</td>"
        f"<td class=num><b>{o['zero']:.1f}%</b> <span class=pc>({o['zero_n']})</span></td>"
        f"<td class=num>{o['divergent']}</td></tr>"
        for lg, o in sorted(stats.items(), key=lambda kv: -kv[1]["mean"]))

    mode_rows = ""
    for k, lbl in (("vi", "Tiếng Việt (lang=vi)"), ("en", "Tiếng Anh (lang=en)"), ("ko", "Tiếng Hàn (lang=ko)")):
        c = modes[k]
        tot = sum(c.values()) or 1
        mode_rows += (f"<tr><td><b>{lbl}</b></td>"
                      f"<td class=num>{c.get('lexical', 0)} <span class=pc>({c.get('lexical',0)/tot*100:.1f}%)</span></td>"
                      f"<td class=num>{c.get('hybrid', 0)} <span class=pc>({c.get('hybrid',0)/tot*100:.1f}%)</span></td></tr>")

    lang_only_rows = ""
    for lg in ORDER:
        v = lang_only[lg]
        if not v:
            continue
        lang_only_rows += (f"<tr><td><b>{LANG_NAME[lg]}</b></td><td class=num>{len(v)}</td>"
                           f"<td class=num><b>{statistics.mean(v):.1f}%</b></td>"
                           f"<td class=num>{sum(1 for x in v if x < 50)} "
                           f"<span class=pc>({sum(1 for x in v if x < 50)/len(v)*100:.1f}%)</span></td></tr>")

    body = []
    for f in (solid + inconclusive)[: args.max_rows]:
        tds = []
        for lg in ORDER:
            d = f["langs"].get(lg)
            if not d:
                tds.append('<td class="na">—</td>')
                continue
            top = "<br>".join(esc(x)[:50] for x in d["top3"]) or "<i>không có kết quả</i>"
            tds.append(f'<td><div class="q">{esc(d["query"])}</div>{badge(d["code"], d["overlap_pct"])}'
                       f'<div class="meta">{d["n"]} sp · {esc(d["mode"] or "-")}</div>'
                       f'<div class="top">{top}</div></td>')
        vitop = "<br>".join(esc(x)[:50] for x in f["vi_top3"]) or "<i>không có kết quả</i>"
        qa = f.get("vi_qa_status")
        qa_html = ('<span class="bdg" style="color:#15803d;background:#f0fdf4;border-color:#15803d33">'
                   'bản Việt Pass</span>' if qa == "passed" else
                   f'<span class="bdg" style="color:#78716c;background:#fafaf9;border-color:#78716c33">'
                   f'bản Việt {esc(qa or "chưa soát")}</span>')
        body.append(f'<tr><td class="vi"><div class="q vq">{esc(f["vi_query"])}</div>'
                    f'<div class="meta">{esc(f["test_id"])} · {esc(f["dimension"])}</div>'
                    f'<div style="margin:3px 0">{qa_html}</div>'
                    f'<div class="meta">{f["vi_n"]} sp · {esc(f["vi_mode"] or "-")}</div>'
                    f'<div class="top">{vitop}</div></td>{"".join(tds)}</tr>')

    truncated = ("" if len(divergent) <= args.max_rows else
                 f'<p class="note">Bảng hiển thị {args.max_rows} dòng lệch nặng nhất '
                 f'trong {len(divergent)}. Toàn bộ nằm ở file JSON kèm theo.</p>')

    enko = f"{statistics.mean(en_ko):.1f}%" if en_ko else "—"
    ctrl_en = statistics.mean(ctrl_vs_vi["en"]) if ctrl_vs_vi["en"] else 0.0
    ctrl_ko = statistics.mean(ctrl_vs_vi["ko"]) if ctrl_vs_vi["ko"] else 0.0
    full_en = stats.get("en", {}).get("mean", 0.0)
    full_ko = stats.get("ko", {}).get("mean", 0.0)
    d_en, d_ko = full_en - ctrl_en, full_ko - ctrl_ko

    doc = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lệch Kết Quả Việt · Anh · Hàn</title><style>
:root{{--bg:#fbfaf8;--fg:#1c1917;--mut:#78716c;--line:#e7e5e4;--card:#fff;--acc:#1d4ed8}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}}
.wrap{{max-width:1320px;margin:0 auto;padding:28px 20px 60px}}
h1{{font-size:26px;margin:0 0 4px;letter-spacing:-.02em}}
h2{{font-size:18px;margin:34px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--acc);display:inline-block}}
.sub{{color:var(--mut);margin:0 0 20px}}
.warn{{background:#fffbeb;border:1px solid #fcd34d;border-left:4px solid #d97706;padding:14px 16px;border-radius:8px;margin:18px 0}}
.warn b{{color:#92400e}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px;min-width:150px}}
.card.hl{{border-color:var(--acc);background:#eff6ff}}
.card .n{{font-size:26px;font-weight:650;letter-spacing:-.02em}}
.card .l{{color:var(--mut);font-size:12px}}
table{{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}}
th,td{{padding:9px 11px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top;font-size:13px}}
th{{background:#f5f5f4;font-weight:600;font-size:12px;color:#57534e}}
td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums}}
.pc{{color:var(--mut);font-size:11px}}
.scroll{{overflow-x:auto;border-radius:10px}}
.q{{font-weight:600;margin-bottom:3px;word-break:break-word}}
.vq{{color:var(--acc)}}
.meta{{color:var(--mut);font-size:11px}}
.top{{color:#57534e;font-size:11px;margin-top:5px;line-height:1.45}}
.na{{color:var(--mut)}}
.bdg{{display:inline-block;padding:1px 7px;border-radius:99px;border:1px solid;font-size:11px;font-weight:600;white-space:nowrap}}
.note{{color:var(--mut);font-size:12px;font-style:italic}}
td.vi{{background:#fdfcfb}}
</style></head><body><div class="wrap">
<h1>Lệch Kết Quả Việt · Anh · Hàn</h1>
<p class="sub">Cửa hàng NSG · 17/09/2026 · mỗi ngôn ngữ gửi <code>lang</code> khớp với chính ngôn ngữ của từ khoá</p>

<div class="warn">
<b>Đọc số liệu này thế nào.</b> Bản dịch Anh/Hàn do QA làm tay. Khi một dòng cho kết quả khác,
nguyên nhân có thể là engine chưa xử lý được ngôn ngữ đó, <b>mà cũng có thể là từ dịch chưa
trùng cách gọi trong catalog</b>. Đây là danh sách <b>khác biệt cần review</b>, không phải
danh sách bug. Cột bản dịch luôn để cạnh kết quả để đối chiếu lại từng dòng.
</div>

<div class="cards">
<div class="card"><div class="n">{len(findings)}</div><div class="l">keyword đối chiếu được</div></div>
<div class="card"><div class="n">{len(divergent)}</div><div class="l">có ít nhất 1 ngôn ngữ lệch</div></div>
<div class="card hl"><div class="n">{len(solid)}</div><div class="l">trong đó bản Việt đã Pass</div></div>
<div class="card"><div class="n">{enko}</div><div class="l">Anh ↔ Hàn trùng nhau</div></div>
<div class="card"><div class="n">{n_err}</div><div class="l">lỗi gọi API</div></div>
</div>

<h2>Độ trùng SKU thật so với bản tiếng Việt</h2>
<p>Con số thô, đọc thẳng: <b>trung bình bao nhiêu phần trăm SKU trong top-20 bản tiếng Việt
cũng xuất hiện ở bản dịch</b>. Xem bảng này trước bảng phân nhóm.</p>
<div class="scroll"><table>
<tr><th>Ngôn ngữ</th><th class=num>Trùng trung bình</th><th class=num>Trung vị</th>
<th class=num>≥70%</th><th class=num>≥50%</th><th class=num>Không trùng SKU nào</th>
<th class=num>Số keyword lệch</th></tr>
{ov_rows}
</table></div>
<p class="note">"Lệch" gộp cả nhóm trùng một phần (30–70%), nên con số đó nghiêm hơn cảm nhận
thực tế của người mua. Độ trùng trung bình mới là thước đo thô.</p>

<h2>Nhánh xử lý: lexical hay hybrid</h2>
<p>Spec trang 10 mô tả Adaptive Gate: BM25 chạy trước, kết quả yếu thì <i>leo thang</i> gọi
Vector k-NN (hybrid). Bảng dưới cho thấy mỗi ngôn ngữ thực tế đi nhánh nào.</p>
<div class="scroll"><table>
<tr><th>Nhánh</th><th class=num>lexical (thuần từ khoá)</th><th class=num>hybrid (có semantic)</th></tr>
{mode_rows}
</table></div>

<h2>Tách riêng tác động của tham số <code>lang</code></h2>
<p>Câu hỏi: kết quả lệch là vì <b>chuỗi query đổi ngôn ngữ</b>, hay vì <b>chính tham số
<code>lang</code></b>? Để tách, cùng ngày hôm nay chạy thêm một nhánh đối chứng: <b>y hệt chuỗi
query Anh/Hàn đó</b>, nhưng gửi <code>lang=vi</code>. Chuỗi query giống nhau, chỉ khác mỗi
<code>lang</code> - nên phần chênh đo được là do riêng tham số này.</p>
<p class="note">Đối chứng phải chạy cùng ngày mới dùng được: bộ 14/09 tuy cùng thiết kế nhưng
cách 3 ngày, mà riêng biến động kết quả trong một ngày đã đo được tới 20,6%.</p>
<div class="scroll"><table>
<tr><th>Ngôn ngữ</th><th class=num>Số keyword so được</th><th class=num>Trùng trung bình (Jaccard)</th>
<th class=num>Đổi quá nửa kết quả</th></tr>
{lang_only_rows}
</table></div>
<p class="note">Jaccard = phần giao chia phần hợp của hai tập SKU. 100% nghĩa là đổi lang không
ảnh hưởng gì; càng thấp thì tham số lang càng làm méo kết quả.</p>

<h3>Vậy cái nào mới là nguyên nhân chính?</h3>
<p>Đặt ba phép đo cạnh nhau, tất cả cùng một thước: <b>bao nhiêu % SKU trong top-20 bản tiếng
Việt còn xuất hiện lại</b>.</p>
<div class="scroll"><table>
<tr><th>Phép đo</th><th class=num>Tiếng Anh</th><th class=num>Tiếng Hàn</th></tr>
<tr><td><b>A.</b> Chỉ đổi chuỗi query, giữ <code>lang=vi</code></td>
<td class=num>{ctrl_en:.1f}%</td><td class=num>{ctrl_ko:.1f}%</td></tr>
<tr><td><b>B.</b> Đổi chuỗi query <i>và</i> đổi <code>lang</code> (đường người dùng thật đi)</td>
<td class=num>{full_en:.1f}%</td><td class=num>{full_ko:.1f}%</td></tr>
<tr><td>Chênh giữa B và A = phần do riêng <code>lang</code></td>
<td class=num>{d_en:+.1f} điểm</td><td class=num>{d_ko:+.1f} điểm</td></tr>
</table></div>
<p>Đọc ra hai điều. <b>Thứ nhất, nguyên nhân chính là chuỗi query, không phải tham số
<code>lang</code>.</b> Chỉ riêng việc gõ bằng tiếng Anh/Hàn đã kéo độ trùng xuống còn
{ctrl_en:.1f}% / {ctrl_ko:.1f}%; gửi thêm <code>lang</code> đúng chỉ nhích được
{d_en:+.1f} / {d_ko:+.1f} điểm.</p>
<p><b>Thứ hai, <code>lang</code> vẫn đảo kết quả rất mạnh, nhưng đảo theo kiểu trung tính.</b>
Bảng Jaccard phía trên cho thấy đổi <code>lang</code> làm thay khoảng 30% tập kết quả, và gần
500 keyword bị thay quá nửa. Nó xáo kết quả thật sự - chỉ là xáo mà không kéo gần hay đẩy xa
bản tiếng Việt một cách hệ thống. Nói cách khác: <code>lang</code> đang ảnh hưởng tới
<i>tập sản phẩm trả về</i>, chứ không đơn thuần là ngôn ngữ hiển thị.</p>

<h2>Dòng nào là bằng chứng dùng được</h2>
<p>Bản tiếng Việt không phải lúc nào cũng đúng - QA đã soát tay và đánh dấu sẵn. Nếu một keyword
mà <b>bản tiếng Việt đã Fail</b>, thì bản dịch có lệch theo cũng không nói lên điều gì về khả
năng xử lý đa ngữ: mốc đã sai từ đầu. Vì vậy tách hai nhóm:</p>
<div class="scroll"><table>
<tr><th>Nhóm</th><th class=num>Số keyword</th><th>Đọc thế nào</th></tr>
<tr><td><b>Bằng chứng dùng được</b></td><td class=num><b>{len(solid)}</b></td>
<td>Bản Việt đã Pass nhưng bản dịch ra khác - chênh này đến từ khâu xử lý đa ngữ.
Đây là nhóm nên đưa dev xem trước.</td></tr>
<tr><td>Chưa kết luận được</td><td class=num>{len(inconclusive)}</td>
<td>Bản Việt đang Fail hoặc chưa soát. Phải sửa cho bản Việt đúng đã, rồi mới đo lại đa ngữ.</td></tr>
</table></div>

<h2>Chi tiết keyword lệch</h2>
<p>Xếp nhóm <b>bằng chứng dùng được</b> lên trước, trong mỗi nhóm thì lệch nặng nhất lên đầu.</p>
{truncated}
<div class="scroll"><table>
<tr><th>Tiếng Việt (mốc)</th><th>Tiếng Anh</th><th>Tiếng Hàn</th></tr>
{"".join(body)}
</table></div>
</div></body></html>"""

    (ROOT / args.out_html).write_text(doc, encoding="utf-8")

    print(f"Keyword đối chiếu được : {len(findings)}")
    print(f"  có ít nhất 1 NN lệch : {len(divergent)} "
          f"({len(divergent)/max(len(findings),1)*100:.1f}%)")
    print(f"    bằng chứng dùng được (bản Việt đã Pass): {len(solid)}")
    print(f"    chưa kết luận được  (bản Việt Fail/chưa soát): {len(inconclusive)}")
    print(f"  lỗi gọi API          : {n_err}")
    print()
    for lg, o in sorted(stats.items(), key=lambda kv: -kv[1]["mean"]):
        print(f"  {LANG_NAME[lg]:10} trùng TB {o['mean']:5.1f}% | trung vị {o['median']:5.1f}% | "
              f"≥70% {o['ge70']:5.1f}% | 0%: {o['zero_n']:4} ({o['zero']:.1f}%) | lệch {o['divergent']}")
    print()
    print("  resolvedMode:")
    for k, lbl in (("vi", "VI"), ("en", "EN"), ("ko", "KO")):
        c = modes[k]
        tot = sum(c.values()) or 1
        print(f"    {lbl}: lexical {c.get('lexical',0):5} ({c.get('lexical',0)/tot*100:5.1f}%) | "
              f"hybrid {c.get('hybrid',0):5} ({c.get('hybrid',0)/tot*100:5.1f}%)")
    if en_ko:
        print(f"\n  Anh <-> Hàn trùng nhau trung bình: {statistics.mean(en_ko):.1f}%")
    for lg in ORDER:
        v = lang_only[lg]
        if v:
            print(f"  Tác động RIÊNG của lang ({lg}): trùng TB {statistics.mean(v):.1f}% "
                  f"trên {len(v)} keyword")
    print(f"\n-> {ROOT / args.out_html}")
    print(f"-> {ROOT / args.out_json}")


if __name__ == "__main__":
    main()
