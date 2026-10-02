# -*- coding: utf-8 -*-
"""So bản dịch KO/EN/RU/ZH/JA với baseline TIẾNG VIỆT và dựng report các keyword
CÙNG NGHĨA nhưng RA KẾT QUẢ KHÁC.

Cách đo (giống compare_results.py để số liệu đọc quen mắt):
  - Mốc so sánh là top-20 SKU của bản TIẾNG VIỆT.
  - overlap% = bao nhiêu SKU trong top-20 tiếng Việt cũng xuất hiện ở bản dịch.
  - Xếp loại: IDENTICAL (trùng cả tập lẫn thứ tự) / SAME_SET (cùng tập, khác
    thứ tự) / HIGH >=70 / PARTIAL >=30 / LOW >0 / NONE =0 / ZERO (bản dịch 0 KQ).

CẢNH BÁO DIỄN GIẢI - in ngay trong report, không giấu:
  Bản dịch do người làm tay, nên "khác kết quả" CÓ THỂ do engine yếu, mà cũng
  CÓ THỂ do từ dịch chưa khớp cách gọi trong catalog. Vì vậy report chỉ nêu
  "khác biệt cần review", KHÔNG tự gán nhãn bug. Cột bản dịch luôn hiển thị
  cạnh kết quả để người đọc tự kiểm chứng.

Các dòng mà cả 4 bản dịch đều TRÙNG NGUYÊN VĂN chuỗi tiếng Việt (brand thuần
như "an lac") được tách riêng: chúng không kiểm chứng được gì về đa ngôn ngữ.
"""
import argparse
import html
import json
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[2]
LANG_NAME = {"ko": "Tiếng Hàn", "en": "Tiếng Anh", "ru": "Tiếng Nga",
             "zh": "Tiếng Trung", "ja": "Tiếng Nhật"}
LANG_ORDER = ["ko", "en", "ru", "zh", "ja"]


def classify(vi_skus, other_skus):
    """Trả về (mã, overlap%) - mốc là top-20 của bản tiếng Việt."""
    if other_skus is None:
        return "ERROR", 0.0
    if not vi_skus:
        return ("BOTH_ZERO", 100.0) if not other_skus else ("VI_ZERO", 0.0)
    if not other_skus:
        return "ZERO", 0.0
    top20 = vi_skus[:20]
    oset = set(other_skus)
    pct = round(sum(1 for s in top20 if s in oset) / len(top20) * 1000) / 10
    if vi_skus == other_skus:
        return "IDENTICAL", pct
    if set(vi_skus) == oset:
        return "SAME_SET", pct
    if pct >= 70:
        return "HIGH", pct
    if pct >= 30:
        return "PARTIAL", pct
    if pct > 0:
        return "LOW", pct
    return "NONE", pct


# thứ tự nghiêm trọng: càng đầu càng đáng xem
SEVERITY = ["ZERO", "NONE", "LOW", "PARTIAL", "HIGH", "SAME_SET", "IDENTICAL",
            "BOTH_ZERO", "VI_ZERO", "ERROR"]
SEV_RANK = {c: i for i, c in enumerate(SEVERITY)}
BADGE = {
    "ZERO": ("0 kết quả", "#b91c1c", "#fef2f2"),
    "NONE": ("không trùng SKU nào", "#b91c1c", "#fef2f2"),
    "LOW": ("trùng rất ít", "#c2410c", "#fff7ed"),
    "PARTIAL": ("trùng một phần", "#a16207", "#fefce8"),
    "HIGH": ("trùng cao", "#15803d", "#f0fdf4"),
    "SAME_SET": ("cùng tập, khác thứ tự", "#0369a1", "#f0f9ff"),
    "IDENTICAL": ("giống hệt", "#15803d", "#f0fdf4"),
    "BOTH_ZERO": ("cả hai 0 KQ", "#57534e", "#fafaf9"),
    "VI_ZERO": ("bản Việt 0 KQ", "#7c3aed", "#faf5ff"),
    "ERROR": ("lỗi gọi API", "#57534e", "#fafaf9"),
}


def esc(s):
    return html.escape(str(s if s is not None else ""))


def strip_diacritics(s):
    """Bỏ dấu tiếng Việt + hạ chữ thường, để so brand viết không dấu với query có dấu."""
    s = unicodedata.normalize("NFD", str(s).strip().casefold().replace("đ", "d"))
    return "".join(c for c in s if not unicodedata.combining(c))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", default="SmartSearch/test_data/json/actual/NSG_ActualData_all_20260914_090421.json")
    ap.add_argument("--raw", default="SmartSearch/test_data/multilang/multilang_raw.ndjson")
    ap.add_argument("--translations", default="SmartSearch/test_data/multilang/translations.json")
    ap.add_argument("--out-html", default="SmartSearch/test_data/multilang/multilang_report.html")
    ap.add_argument("--out-json", default="SmartSearch/test_data/multilang/multilang_findings.json")
    ap.add_argument("--max-rows", type=int, default=400,
                    help="số dòng tối đa render trong bảng chi tiết (mặc định 400)")
    ap.add_argument("--compare-report",
                    default="SmartSearch/test_data/compare/run_all_20260914_093918/compare_report.html",
                    help="compare_report.html của bộ tiếng Việt - dùng để biết CHÍNH bản tiếng "
                         "Việt của keyword đó có đạt không. Không có nó thì mọi khác biệt đều bị "
                         "quy cho ngoại ngữ, kể cả khi bản tiếng Việt mới là bản sai.")
    args = ap.parse_args()

    # --- baseline tiếng Việt ---
    base = json.loads((ROOT / args.baseline).read_text(encoding="utf-8"))
    vi = {}
    for s in base["scenarios"]:
        vi[s["test_id"]] = {
            "query": s["query"],
            "skus": [str(p["sku"]) for p in (s.get("search_results") or [])],
            "names": [p.get("name") for p in (s.get("search_results") or [])][:20],
            "dimension": s.get("dimension"),
        }

    tr = {i["test_id"]: i for i in
          json.loads((ROOT / args.translations).read_text(encoding="utf-8"))["items"]}

    # --- kết quả crawl đa ngôn ngữ ---
    # File NDJSON ghi nối thêm: một dòng hỏng ở lần chạy trước được BÙ bằng dòng
    # mới ở lần chạy sau. Nên dòng sau luôn đè dòng trước cho cùng
    # (test_id, lang), và chỉ đếm lỗi trên trạng thái CUỐI CÙNG - nếu không sẽ
    # báo "376 lỗi" trong khi thực tế chúng đã được bù xong.
    rows = defaultdict(dict)
    with open(ROOT / args.raw, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            prev = rows[r["test_id"]].get(r["lang"])
            # giữ dòng thành công; chỉ để dòng lỗi đứng lại khi chưa có bản tốt
            if prev is not None and prev.get("error") is None and r.get("error"):
                continue
            rows[r["test_id"]][r["lang"]] = r
    n_err = sum(1 for per in rows.values() for r in per.values() if r.get("error"))

    findings = []
    for tid, per_lang in rows.items():
        if tid not in vi:
            continue           # keyword đã bị remove khỏi bộ test
        v = vi[tid]
        t = tr.get(tid, {})
        # brand thuần: mọi bản dịch y hệt chuỗi tiếng Việt -> không kiểm chứng được gì.
        # So sánh sau khi BỎ DẤU, vì bản dịch brand viết không dấu ("an lac")
        # trong khi query gốc có dấu ("an lạc") - so nguyên văn sẽ không khớp.
        untranslated = all(
            strip_diacritics(t.get(lg) or "") == strip_diacritics(v["query"])
            for lg in LANG_ORDER if t.get(lg))
        langs = {}
        for lg in LANG_ORDER:
            r = per_lang.get(lg)
            if not r:
                continue
            code, pct = classify(v["skus"], r.get("skus"))
            langs[lg] = {
                "query": r.get("query"), "code": code, "overlap_pct": pct,
                "n": len(r.get("skus") or []), "mode": r.get("resolved_mode"),
                "top5": (r.get("names") or [])[:5], "error": r.get("error"),
            }
        if not langs:
            continue
        worst = min((SEV_RANK[x["code"]] for x in langs.values()), default=99)
        findings.append({
            "test_id": tid, "vi_query": v["query"], "dimension": v["dimension"],
            "vi_n": len(v["skus"]), "vi_top5": v["names"][:5],
            "vi_mode": None, "untranslated": untranslated,
            "langs": langs, "worst_rank": worst,
            "worst_code": SEVERITY[worst] if worst < len(SEVERITY) else "ERROR",
        })

    findings.sort(key=lambda x: (x["worst_rank"], -sum(
        1 for l in x["langs"].values() if l["code"] in ("ZERO", "NONE", "LOW"))))

    testable = [f for f in findings if not f["untranslated"]]
    brandonly = [f for f in findings if f["untranslated"]]

    # --- thống kê ---
    per_lang_stats = {lg: Counter() for lg in LANG_ORDER}
    for f in testable:
        for lg, d in f["langs"].items():
            per_lang_stats[lg][d["code"]] += 1

    DIVERGENT = {"ZERO", "NONE", "LOW", "PARTIAL"}
    divergent = [f for f in testable
                 if any(d["code"] in DIVERGENT for d in f["langs"].values())]

    # --- CHỐT QUAN TRỌNG: bản tiếng Việt của chính keyword đó có đạt không? ---
    # Phép đo ở trên lấy bản tiếng Việt làm mốc, tức NGẦM COI nó đúng. Thực tế
    # nhiều keyword bản tiếng Việt cũng sai (vd "dầu dừa" ra tinh dầu hoa poppy,
    # "cân" ra nước cân bằng). Với những keyword đó, "ngoại ngữ lệch" KHÔNG
    # chứng minh được gì - có khi ngoại ngữ còn đúng hơn. Tách ra để không thổi
    # phồng con số.
    vi_status = {}
    crpath = ROOT / args.compare_report
    if crpath.exists():
        for line in open(crpath, encoding="utf-8"):
            if line.startswith("const scenarios = ["):
                for s in json.loads(line[len("const scenarios = "):].rstrip().rstrip(";")):
                    vi_status[s["test_id"]] = (
                        s.get("pass_fail_status") == "passed"
                        and not s.get("bug_note") and not s.get("discussion_note"))
                break
    for f in findings:
        f["vi_baseline_ok"] = vi_status.get(f["test_id"])
    solid = [f for f in divergent if f.get("vi_baseline_ok") is True]
    inconclusive = [f for f in divergent if f.get("vi_baseline_ok") is False]
    thin = [f for f in divergent if f["vi_n"] < 5]

    # --- ĐỘ TRÙNG SKU THẬT ---------------------------------------------------
    # Bảng đếm theo nhóm ở trên dễ bị đọc nhầm: "lệch 60%" KHÔNG có nghĩa là
    # "chỉ khớp 40% SKU", vì nhóm "trùng một phần" (30-70%) cũng bị tính là lệch.
    # Bảng này đưa con số overlap thô để người đọc tự đánh giá.
    overlap_stats = {}
    for lg in LANG_ORDER:
        vals = [f["langs"][lg]["overlap_pct"] for f in testable if lg in f["langs"]]
        if not vals:
            continue
        n = len(vals)
        overlap_stats[lg] = {
            "mean": statistics.mean(vals), "median": statistics.median(vals),
            "ge70": sum(1 for v in vals if v >= 70) / n * 100,
            "ge50": sum(1 for v in vals if v >= 50) / n * 100,
            "ge30": sum(1 for v in vals if v >= 30) / n * 100,
            "zero": sum(1 for v in vals if v == 0) / n * 100,
            "zero_n": sum(1 for v in vals if v == 0), "n": n,
        }
    ov_rows = "".join(
        f"<tr><td><b>{LANG_NAME[lg]}</b></td>"
        f"<td class=num><b>{o['mean']:.1f}%</b></td><td class=num>{o['median']:.1f}%</td>"
        f"<td class=num>{o['ge70']:.1f}%</td><td class=num>{o['ge50']:.1f}%</td>"
        f"<td class=num>{o['ge30']:.1f}%</td>"
        f"<td class=num><b>{o['zero']:.1f}%</b> <span class=pc>({o['zero_n']})</span></td></tr>"
        for lg, o in sorted(overlap_stats.items(), key=lambda kv: -kv[1]["mean"]))

    (ROOT / args.out_json).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / args.out_json).write_text(json.dumps({
        "generated": "2026-09-14", "store": "nsg",
        "method": "query dịch tay VI->KO/EN/RU/ZH/JA, lang=vi cố định, so top-20 SKU với bản tiếng Việt",
        "counts": {"total": len(findings), "testable": len(testable),
                   "brand_only": len(brandonly), "divergent": len(divergent),
                   "solid_evidence": len(solid),
                   "inconclusive_vi_baseline_bad": len(inconclusive),
                   "thin_vi_baseline": len(thin),
                   "api_errors": n_err},
        "per_lang": {lg: dict(c) for lg, c in per_lang_stats.items()},
        "overlap_stats": overlap_stats,
        "findings": findings,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------------- HTML ----------------
    def badge(code, pct=None):
        label, fg, bg = BADGE[code]
        extra = f" {pct}%" if pct is not None and code not in ("IDENTICAL", "BOTH_ZERO", "ERROR") else ""
        return (f'<span class="bdg" style="color:{fg};background:{bg};border-color:{fg}33">'
                f'{esc(label)}{extra}</span>')

    head_cells = "".join(f"<th>{LANG_NAME[lg]}</th>" for lg in LANG_ORDER)
    body_rows = []
    # Ưu tiên hiển thị nhóm BẰNG CHỨNG CHẮC (bản tiếng Việt đạt mà ngoại ngữ lệch),
    # vì đó mới là phần dùng được để giao dev.
    render_list = sorted(solid, key=lambda x: (x["worst_rank"], -x["vi_n"]))
    for f in render_list[: args.max_rows]:
        tds = []
        for lg in LANG_ORDER:
            d = f["langs"].get(lg)
            if not d:
                tds.append('<td class="na">—</td>')
                continue
            top = "<br>".join(esc(x)[:54] for x in d["top5"][:3]) or "<i>không có kết quả</i>"
            tds.append(
                f'<td><div class="q">{esc(d["query"])}</div>'
                f'{badge(d["code"], d["overlap_pct"])}'
                f'<div class="meta">{d["n"]} sp · {esc(d["mode"] or "-")}</div>'
                f'<div class="top">{top}</div></td>')
        vitop = "<br>".join(esc(x)[:54] for x in f["vi_top5"][:3]) or "<i>không có kết quả</i>"
        body_rows.append(
            f'<tr><td class="vi"><div class="q vq">{esc(f["vi_query"])}</div>'
            f'<div class="meta">{esc(f["test_id"])} · {esc(f["dimension"])}</div>'
            f'<div class="meta">{f["vi_n"]} sp</div>'
            f'<div class="top">{vitop}</div></td>{"".join(tds)}</tr>')

    stat_rows = []
    for lg in LANG_ORDER:
        c = per_lang_stats[lg]
        tot = sum(c.values()) or 1
        div = sum(c[k] for k in DIVERGENT)
        stat_rows.append(
            f"<tr><td><b>{LANG_NAME[lg]}</b></td>"
            f"<td class=num>{c['IDENTICAL']}</td><td class=num>{c['SAME_SET']}</td>"
            f"<td class=num>{c['HIGH']}</td><td class=num>{c['PARTIAL']}</td>"
            f"<td class=num>{c['LOW']}</td><td class=num>{c['NONE']}</td>"
            f"<td class=num>{c['ZERO']}</td>"
            f"<td class=num><b>{div}</b> <span class=pc>({div / tot * 100:.1f}%)</span></td></tr>")

    truncated = ("" if len(render_list) <= args.max_rows else
                 f'<p class="note">Bảng hiển thị {args.max_rows} dòng lệch nặng nhất trong '
                 f'{len(render_list)} keyword thuộc nhóm bằng chứng chắc chắn. '
                 f'Toàn bộ nằm ở file JSON kèm theo.</p>')

    html_doc = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Đối chiếu Search đa ngôn ngữ - NSG</title><style>
:root{{--bg:#fbfaf8;--fg:#1c1917;--mut:#78716c;--line:#e7e5e4;--card:#fff;--acc:#9a3412}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}}
.wrap{{max-width:1400px;margin:0 auto;padding:28px 20px 60px}}
h1{{font-size:26px;margin:0 0 4px;letter-spacing:-.02em}}
h2{{font-size:18px;margin:34px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--acc);display:inline-block}}
.sub{{color:var(--mut);margin:0 0 20px}}
.warn{{background:#fffbeb;border:1px solid #fcd34d;border-left:4px solid #d97706;padding:14px 16px;border-radius:8px;margin:18px 0}}
.warn b{{color:#92400e}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px;min-width:150px}}
.card.hl{{border-color:#9a3412;background:#fff7ed}}
.card .n{{font-size:26px;font-weight:650;letter-spacing:-.02em}}
.card .l{{color:var(--mut);font-size:12px}}
table{{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}}
th,td{{padding:9px 11px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top;font-size:13px}}
th{{background:#f5f5f4;font-weight:600;font-size:12px;color:#57534e;position:sticky;top:0}}
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
<h1>Đối chiếu Search đa ngôn ngữ</h1>
<p class="sub">Cửa hàng NSG · 14/09/2026 · cùng một ý nghĩa, viết bằng 5 ngôn ngữ, đối chiếu với kết quả bản tiếng Việt</p>

<div class="warn">
<b>Đọc số liệu này thế nào.</b> Bản dịch do QA làm tay. Khi một dòng cho kết quả khác,
nguyên nhân có thể là engine chưa xử lý được ngoại ngữ, <b>mà cũng có thể là từ dịch chưa
trùng cách gọi trong catalog</b>. Vì vậy đây là danh sách <b>khác biệt cần review</b>,
không phải danh sách bug. Cột bản dịch luôn để cạnh kết quả để đối chiếu lại từng dòng.
</div>

<div class="cards">
<div class="card"><div class="n">{len(testable)}</div><div class="l">keyword kiểm chứng được</div></div>
<div class="card hl"><div class="n">{len(solid)}</div><div class="l">bằng chứng chắc chắn</div></div>
<div class="card"><div class="n">{len(inconclusive)}</div><div class="l">không kết luận được</div></div>
<div class="card"><div class="n">{len(brandonly)}</div><div class="l">brand giữ nguyên (không tính)</div></div>
<div class="card"><div class="n">{n_err}</div><div class="l">lỗi gọi API</div></div>
</div>

<h2>Con số nào dùng được, con số nào không</h2>
<p>Phép đo này lấy kết quả bản tiếng Việt làm mốc, tức <b>ngầm coi bản tiếng Việt là đúng</b>.
Giả định đó không phải lúc nào cũng đúng. Ví dụ có thật trong bộ này:</p>
<div class="scroll"><table>
<tr><th>Query tiếng Việt</th><th>Top-1 mà bản tiếng Việt trả về</th><th>Nhận xét</th></tr>
<tr><td><b>dầu dừa</b></td><td>Tinh Dầu UNA PIANTA Hương Hoa Poppy 120ml</td><td>khớp nhầm chữ "dầu"</td></tr>
<tr><td><b>dưa hâu</b></td><td>Sáp Thơm Farcent Hương Hoa Hồng 170g</td><td>không liên quan</td></tr>
<tr><td><b>bông so đũa</b></td><td>Xà Bông Cục Enchanteur Charming 90g</td><td>khớp nhầm chữ "bông"</td></tr>
<tr><td><b>cân</b></td><td>Nước Cân Bằng Vedette 280ml</td><td>khớp nhầm cụm "cân bằng"</td></tr>
</table></div>
<p>Với <b>bông so đũa</b>, cả ba bản Hàn/Anh/Nga đều trả về hoa tươi Dalat Hasfarm — tức
<b>bản ngoại ngữ còn đúng hơn bản tiếng Việt</b>. Nếu chỉ đọc "số keyword lệch" thì những
ca như vậy bị tính ngược.</p>
<p>Vì vậy tôi tách {len(divergent)} keyword có lệch thành hai nhóm, dựa trên trạng thái
Pass/Fail và ghi chú bug/discussion mà QA đã chấm cho chính bản tiếng Việt trong đợt 14/09:</p>
<div class="scroll"><table>
<tr><th>Nhóm</th><th class=num>Số keyword</th><th>Dùng được để làm gì</th></tr>
<tr><td><b>Bản tiếng Việt ĐẠT, ngoại ngữ lệch</b></td><td class=num><b>{len(solid)}</b></td>
<td>Bằng chứng thật về việc engine xử lý ngoại ngữ yếu. <b>Đây là phần giao cho dev.</b></td></tr>
<tr><td>Bản tiếng Việt vốn đã có vấn đề</td><td class=num>{len(inconclusive)}</td>
<td>Không kết luận được — mốc so sánh đã hỏng sẵn, ngoại ngữ có khi còn đúng hơn.</td></tr>
</table></div>
<p class="note">Thêm {len(thin)} keyword có bản tiếng Việt trả về dưới 5 sản phẩm — mốc so sánh
quá mỏng, tỷ lệ trùng dễ nhảy mạnh chỉ vì một hai SKU.</p>

<h2>Độ trùng SKU thật</h2>
<p>Đây là con số thô, đọc thẳng: <b>trung bình bao nhiêu phần trăm SKU trong top-20 bản tiếng Việt
cũng xuất hiện ở bản dịch</b>. Xem bảng này trước bảng phân nhóm bên dưới.</p>
<div class="scroll"><table>
<tr><th>Ngôn ngữ</th><th class=num>Trùng trung bình</th><th class=num>Trung vị</th>
<th class=num>Số keyword trùng ≥70%</th><th class=num>≥50%</th><th class=num>≥30%</th>
<th class=num>Không trùng SKU nào</th></tr>
{ov_rows}
</table></div>
<p class="note">Cột cuối là chỗ đáng lo nhất: keyword mà bản dịch không lấy lại được
một sản phẩm nào của bản tiếng Việt.</p>

<h2>Mức độ khớp theo từng ngôn ngữ</h2>
<p><b>Đọc bảng dưới cẩn thận.</b> Cột "Lệch" gộp cả nhóm <i>trùng một phần</i> (30–70% SKU),
nên "lệch 60%" <b>KHÔNG</b> có nghĩa là "chỉ khớp 40% SKU" — độ trùng SKU thật nằm ở bảng ngay trên.
Bảng này đếm số keyword rơi vào từng mức, dùng để biết vấn đề phân bố ra sao.</p>
<div class="scroll"><table>
<tr><th>Ngôn ngữ</th><th class=num>Giống hệt</th><th class=num>Cùng tập</th><th class=num>Trùng cao</th>
<th class=num>Một phần</th><th class=num>Rất ít</th><th class=num>Không trùng</th><th class=num>0 KQ</th>
<th class=num>Lệch (cần review)</th></tr>
{"".join(stat_rows)}
</table></div>
<p class="note">"Lệch" = tổng của Một phần + Rất ít + Không trùng + 0 KQ. Mốc đối chiếu là top-20 SKU của bản tiếng Việt.</p>

<h2>Chi tiết: bản tiếng Việt đạt nhưng ngoại ngữ lệch</h2>
<p class="note">Chỉ liệt kê nhóm bằng chứng chắc chắn. Sắp xếp theo mức lệch nặng nhất.</p>
{truncated}
<div class="scroll"><table>
<tr><th>Tiếng Việt (mốc)</th>{head_cells}</tr>
{"".join(body_rows)}
</table></div>

<h2>Phát hiện phụ: tham số <code>lang</code> làm đổi kết quả</h2>
<p>Khi thăm dò API trước khi chạy bộ này, tôi phát hiện tham số <code>lang</code> trên URL
không chỉ đổi ngôn ngữ hiển thị tên sản phẩm mà <b>đổi cả tập kết quả trả về</b>:</p>
<div class="scroll"><table>
<tr><th>Query</th><th>vi so với en</th><th>vi so với ko</th><th>vi so với ru</th></tr>
<tr><td><b>sữa</b></td><td>1/10 SKU trùng</td><td><b>0/10 SKU trùng</b></td><td>2/10 SKU trùng</td></tr>
<tr><td><b>milk</b></td><td>4/10 SKU trùng</td><td>6/10 SKU trùng</td><td>6/10 SKU trùng</td></tr>
<tr><td><b>우유</b></td><td>giống hệt</td><td>giống hệt</td><td>giống hệt</td></tr>
<tr><td><b>молоко</b></td><td>giống hệt</td><td>giống hệt</td><td>giống hệt</td></tr>
<tr><td><b>nước mắm</b></td><td>cùng tập, khác thứ tự</td><td>cùng tập, khác thứ tự</td><td>cùng tập, khác thứ tự</td></tr>
</table></div>
<p>API đã được kiểm tra là ổn định (gọi lại 3 lần cho kết quả y hệt), nên khác biệt này là thật.
Bộ test này cố ý giữ <code>lang=vi</code> cho mọi request nên không bị ảnh hưởng, nhưng
người dùng thật đổi ngôn ngữ hiển thị trên app <b>sẽ thấy tập sản phẩm khác đi</b> — cần dev xác nhận
đây là thiết kế có chủ đích hay lỗi.</p>
<p><b>Đính chính về tiếng Nhật.</b> Bản đầu của báo cáo này viết "tiếng Nhật không dùng được" —
điều đó SAI trong bối cảnh bài test. HTTP 400 chỉ xảy ra khi đặt <code>lang=ja</code> hoặc
<code>lang=jp</code> trên URL, mà thiết kế ở đây giữ <code>lang=vi</code> cho mọi request nên
không bao giờ chạm tới đường đó. Query viết bằng tiếng Nhật gửi kèm <code>lang=vi</code>
<b>chạy hoàn toàn bình thường</b> — đã kiểm chứng: 牛乳 ra sữa tươi, 豚バラ肉 ra ba rọi xông khói,
歯ブラシ ra bàn chải đánh răng. Vì vậy tiếng Nhật đã được bổ sung đầy đủ vào bộ test này.</p>
<p>Điểm còn lại vẫn đúng và vẫn đáng báo dev: <b>locale <code>ja</code>/<code>jp</code> bị API từ chối</b>,
trong khi vi/en/ko/ru/zh được chấp nhận. Nếu ứng dụng có kế hoạch hỗ trợ giao diện tiếng Nhật thì
đây là việc chặn, nhưng nó KHÔNG ảnh hưởng tới khả năng tìm kiếm bằng từ khoá tiếng Nhật.</p>

<h2>Phát hiện quan trọng nhất: catalog thiếu dữ liệu localize cho tiếng Nga và tiếng Trung</h2>
<p>Cùng một SKU, API trả về tên sản phẩm khác nhau tuỳ <code>lang</code> — tức catalog có nhiều
trường tên theo ngôn ngữ. Nhưng đo thực tế trên 6 truy vấn phổ thông cho thấy độ phủ rất chênh lệch:</p>
<div class="scroll"><table>
<tr><th>lang</th><th class=num>Tên có chữ viết riêng của ngôn ngữ đó</th><th>Kết luận</th></tr>
<tr><td><code>vi</code></td><td class=num>118/120 có dấu tiếng Việt</td><td>Đầy đủ</td></tr>
<tr><td><code>ko</code></td><td class=num>61/81 có chữ Hàn</td><td>Có thật, nhưng còn <b>20 dòng rơi về tiếng Việt</b></td></tr>
<tr><td><code>en</code></td><td class=num>—</td><td>Có thật, nhưng còn <b>19/78 dòng rơi về tiếng Việt</b></td></tr>
<tr><td><code>ru</code></td><td class=num><b>0/120 có chữ Nga</b></td><td><b>Không có dữ liệu tiếng Nga — trả về tên tiếng Anh</b></td></tr>
<tr><td><code>zh</code></td><td class=num><b>0/120 có chữ Trung</b></td><td><b>Không có dữ liệu tiếng Trung — trả về tên tiếng Anh</b></td></tr>
</table></div>
<p>Ví dụ SKU <code>8935049017301</code>:</p>
<div class="scroll"><table>
<tr><th>lang</th><th>Tên sản phẩm API trả về</th></tr>
<tr><td><code>vi</code></td><td>Sữa Tươi Tiệt Trùng Có Đường Nutimilk Hộp 1L</td></tr>
<tr><td><code>ko</code></td><td>Nutimilk 100% 순수 가당 멸균 생우유 1L</td></tr>
<tr><td><code>en</code></td><td>Nutimilk UHT Sweetened Milk 1L</td></tr>
<tr><td><code>ru</code></td><td>Nutimilk UHT Sweetened Milk 1L <i>(rơi về tiếng Anh)</i></td></tr>
<tr><td><code>zh</code></td><td>Nutimilk UHT Sweetened Milk 1L <i>(rơi về tiếng Anh)</i></td></tr>
</table></div>
<p><b>Vì sao điều này quan trọng khi đọc bảng lệch ở trên.</b> Toàn bộ 13.129 tên sản phẩm thu được
ở bản tiếng Việt đều <b>không chứa một ký tự Hàn/Trung/Nga nào</b>. Nghĩa là khi giữ
<code>lang=vi</code>, truy vấn tiếng Hàn/Nga/Trung <b>không thể khớp bằng so khớp từ khoá</b> —
chúng chỉ còn cách dựa vào tầng ngữ nghĩa. Đây là lý do cấu trúc khiến 3 ngôn ngữ này lệch
nhiều hơn tiếng Anh, chứ không đơn thuần là engine kém.</p>
<p><b>Việc cần dev xác nhận, xếp theo mức ưu tiên:</b></p>
<ol>
<li><b>Locale <code>ja</code>/<code>jp</code> bị từ chối</b> (HTTP 400) — chỉ ảnh hưởng giao diện tiếng Nhật, KHÔNG ảnh hưởng tìm kiếm bằng từ khoá tiếng Nhật (đã kiểm chứng chạy tốt với <code>lang=vi</code>).</li>
<li><b>Tiếng Nga và tiếng Trung chưa có dữ liệu localize</b> — người dùng chọn 2 ngôn ngữ này đang nhìn thấy tên sản phẩm tiếng Anh. Là thiếu dữ liệu hay là thiết kế chấp nhận được?</li>
<li><b>Độ phủ tiếng Hàn/Anh chưa trọn</b> — vẫn còn khoảng 25% dòng rơi về tên tiếng Việt.</li>
<li><b>Tham số <code>lang</code> đổi cả tập kết quả</b> (bảng ngay trên) — cần xác nhận có chủ đích hay không.</li>
</ol>

<h2>Phạm vi và cách chọn mẫu</h2>
<p>Bộ gốc có 2.355 keyword. Đem đi dịch <b>1.561</b> keyword tiếng Việt có dấu. Loại 794 keyword vì:</p>
<ul>
<li><b>57</b> thuộc nhóm <code>misspelling</code> — dịch một từ gõ sai là vô nghĩa.</li>
<li><b>69</b> vốn đã là ngoại ngữ (<code>라면</code>, <code>わさび</code>) — không có bản tiếng Việt gốc để làm mốc.</li>
<li><b>174</b> viết không dấu nhưng đã có bản có dấu tương đương trong bộ (<code>sua</code> / <code>sữa</code>) — loại không mất dữ liệu.</li>
<li><b>494</b> là brand thuần (<code>anlene</code>, <code>chivas</code>), từ tiếng Anh sẵn (<code>beer</code>, <code>cheese</code>),
hoặc nhập nhằng vì thiếu dấu (<code>co</code>, <code>cay</code>, <code>cat</code>).</li>
</ul>
<p class="note">Mỗi keyword gọi 5 request (KO/EN/RU/ZH/JA) với pageSize=50, tham số lang giữ nguyên "vi".</p>
</div></body></html>"""

    (ROOT / args.out_html).write_text(html_doc, encoding="utf-8")

    print(f"Tổng keyword có dữ liệu     : {len(findings)}")
    print(f"  - kiểm chứng được         : {len(testable)}")
    print(f"  - brand giữ nguyên (bỏ)   : {len(brandonly)}")
    print(f"  - CÓ LỆCH                 : {len(divergent)} "
          f"({len(divergent) / max(len(testable), 1) * 100:.1f}%)")
    print(f"      * bản VN ĐẠT -> bằng chứng chắc : {len(solid)}")
    print(f"      * bản VN đã hỏng -> bỏ qua      : {len(inconclusive)}")
    print(f"      * bản VN <5 sp -> mốc quá mỏng  : {len(thin)}")
    print(f"  - lỗi gọi API             : {n_err}")
    print()
    for lg in LANG_ORDER:
        c = per_lang_stats[lg]
        tot = sum(c.values()) or 1
        div = sum(c[k] for k in DIVERGENT)
        print(f"  {LANG_NAME[lg]:10} giống hệt {c['IDENTICAL']:4} | cùng tập {c['SAME_SET']:4} | "
              f"cao {c['HIGH']:4} | phần {c['PARTIAL']:4} | ít {c['LOW']:4} | "
              f"không trùng {c['NONE']:4} | 0KQ {c['ZERO']:4} | LỆCH {div:4} ({div / tot * 100:.1f}%)")
    print(f"\n-> {ROOT / args.out_html}")
    print(f"-> {ROOT / args.out_json}")


if __name__ == "__main__":
    main()
