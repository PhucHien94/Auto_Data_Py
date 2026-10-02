#!/usr/bin/env python3
"""Tự đánh giá kết quả search Actual dưới GÓC ĐỘ NGƯỜI MUA HÀNG, rồi xuất 1
file HTML để QA dò lại.

GIỚI HẠN PHẢI NÓI TRƯỚC: script này KHÔNG "hiểu" ngữ nghĩa như con người. Nó
chấm bằng các luật tường minh dựa trên chữ trong tên/danh mục/thương hiệu sản
phẩm. Vì vậy:
  - Nó ĐÚNG cao ở nhóm query gõ thẳng tên/thương hiệu sản phẩm.
  - Nó KHÔNG tự chấm được nhóm query theo ngữ nghĩa/nhu cầu ("đồ ăn cho người
    giảm cân" -> "gạo lứt" là đúng nhưng không trùng chữ nào). Nhóm này được
    đẩy sang CẦN THẢO LUẬN thay vì chấm bừa thành Fail.
Mọi phán quyết đều kèm LÝ DO để người đọc bác bỏ được.

Usage:
  python scripts/automation/auto_review_actual.py \
    --actual SmartSearch/test_data/json/actual/NSG_ActualData_all_20260907_160705.json \
    --out SmartSearch/client_report/AutoReview_Actual_NSG_20260908.html
"""
import argparse
import html
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

NON_LATIN = re.compile(r"[ᄀ-ᇿ぀-ヿ㐀-䶿一-鿿가-힯Ѐ-ӿ]")

# Từ chức năng tiếng Việt - không mang thông tin sản phẩm, loại khỏi phép đo
# trùng chữ (nếu tính, query "sữa cho bé" sẽ "khớp" mọi sản phẩm có chữ "cho").
STOPWORDS = {
    "va", "hoac", "la", "cua", "cho", "voi", "tai", "trong", "khi", "sau", "truoc", "de",
    "duoc", "khong", "co", "mot", "cac", "nhung", "nay", "do", "nen", "the", "san", "pham",
    "theo", "tu", "den", "neu", "hay", "vao", "ra", "len", "xuong", "nhu", "boi", "vi", "ma",
    "thi", "day", "kia", "moi", "rat", "qua", "con", "chi", "ban", "loai", "gi", "nao",
}

# Query mô tả NHU CẦU/NGỮ CẢNH chứ không nêu tên sản phẩm cụ thể. Với nhóm này,
# trùng chữ là thước đo SAI (sản phẩm đúng thường không chứa chữ nào của query),
# nên luôn đẩy sang "cần thảo luận" để người quyết định.
INTENT_MARKERS = [
    "cho người", "cho bé", "cho trẻ", "cho mẹ", "dành cho", "phù hợp",
    "giảm cân", "tăng cân", "ăn kiêng", "eat clean", "healthy", "lành mạnh",
    "bồi bổ", "hỗ trợ", "tăng cường", "chế độ", "thực đơn", "bữa",
    "quà", "tặng", "biếu", "lễ", "tết", "sinh nhật", "cưới",
    "du lịch", "dã ngoại", "cắm trại", "picnic", "văn phòng", "năm học",
    "nấu", "làm bánh", "chuẩn bị", "trang trí", "dụng cụ", "đồ dùng",
    "mùa hè", "mùa đông", "thời tiết",
]


def strip_accents(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d").replace("Đ", "D")


def toks(s):
    """Token bỏ dấu, hạ chữ thường, bỏ từ chức năng và token 1 ký tự."""
    t = re.split(r"[^a-z0-9]+", strip_accents(s).lower())
    return [x for x in t if len(x) >= 2 and x not in STOPWORDS]


def product_text(p):
    return " ".join(str(p.get(k) or "") for k in ("name", "category", "brand"))


def _edit_le(a, b, k):
    """Khoảng cách sửa lỗi <= k (Levenshtein rút gọn)."""
    if abs(len(a) - len(b)) > k:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > k:
            return False
        prev = cur
    return prev[-1] <= k


def coverage(qt, p):
    """Tỷ lệ token của query xuất hiện trong tên/danh mục/thương hiệu sản phẩm.

    Khớp MỞ chứ không so chữ nguyên vẹn - sửa 2 dạng chấm oan phát hiện khi
    dò mẫu thật (kết quả ĐÚNG mà bị chấm sai):
      - gõ sai chính tả: "pepci" -> "Pepsi", "nuowc" -> "Nước"  => cho phép
        sai 1 ký tự với token >= 4, sai 2 ký tự với token >= 7.
      - viết liền/tách khác: "redbull" -> "Red Bull"  => so thêm bản nối liền
        toàn bộ token của query với bản nối liền của tên sản phẩm.
    """
    if not qt:
        return 0.0
    ptoks = toks(product_text(p))
    pt = set(ptoks)
    if not pt:
        return 0.0
    joined = "".join(ptoks)
    hit = 0
    for q in qt:
        ok = q in pt or any(w.startswith(q) and len(q) >= 4 for w in pt)
        if not ok and len(q) >= 4:
            k = 2 if len(q) >= 7 else 1
            ok = any(_edit_le(q, w, k) for w in pt if abs(len(w) - len(q)) <= k)
        if not ok and len(q) >= 5:
            ok = q in joined          # "redbull" nằm trong "redbulleurope..."
        hit += 1 if ok else 0
    # query viết liền nhiều từ: "redbull" vs sản phẩm "Red Bull"
    if hit == 0 and len(qt) == 1 and len(qt[0]) >= 6 and qt[0] in joined:
        hit = 1
    return hit / len(qt)


def review(sc):
    """Trả (verdict, reason, chỉ số). verdict: pass | fail | discuss."""
    q = (sc.get("query") or "").strip()
    results = sc.get("search_results") or []
    qt = toks(q)
    n = len(results)

    if sc.get("api_error"):
        return "fail", f"API lỗi: {sc['api_error'][:60]}", {}
    if n == 0:
        return "fail", "Không trả về sản phẩm nào - người mua không thấy gì để chọn.", {"n": 0}

    top = results[:10]
    covs = [coverage(qt, p) for p in top]
    cov1 = covs[0] if covs else 0.0
    cov_avg = sum(covs) / len(covs) if covs else 0.0
    n_full = sum(1 for c in covs if c >= 0.999)
    cats = Counter(p.get("category") or "?" for p in top)
    top_cat, top_cat_n = cats.most_common(1)[0]
    cat_conc = top_cat_n / len(top)

    m = {"n": n, "cov_top1": round(cov1, 2), "cov_avg_top10": round(cov_avg, 2),
         "full_match_top10": n_full, "cat_concentration": round(cat_conc, 2), "top_cat": top_cat}

    # 1) Query ngoại ngữ: không thể chấm bằng trùng chữ tiếng Việt.
    if NON_LATIN.search(q):
        return "discuss", ("Query ngoại ngữ - không chấm được bằng đối chiếu chữ; "
                           "cần người biết tiếng đó xác nhận kết quả có đúng ý không."), m
    # 2) Query mô tả nhu cầu/ngữ cảnh: sản phẩm đúng thường không chứa chữ nào
    #    của query, nên trùng chữ là thước đo sai.
    # Khớp NGUYÊN TỪ, không phải chuỗi con: marker "quà" từng khớp nhầm vào
    # trong chữ "quần" khiến "móc quần áo" bị coi là query mô tả nhu cầu.
    ql = strip_accents(q).lower()
    if any(re.search(r"(?<![a-z0-9])" + re.escape(strip_accents(k).lower()) + r"(?![a-z0-9])", ql)
           for k in INTENT_MARKERS):
        return "discuss", ("Query mô tả NHU CẦU chứ không nêu tên sản phẩm - đúng/sai phụ thuộc "
                           "nghiệp vụ (sản phẩm phù hợp thường không trùng chữ với query), "
                           "cần người quyết định."), m
    if not qt:
        return "discuss", "Query quá ngắn/không có từ khoá có nghĩa để đối chiếu.", m

    # 3) Chấm được bằng trùng chữ
    if n_full >= 5:
        return "pass", (f"{n_full}/10 sản phẩm đầu chứa ĐỦ từ khoá trong tên/danh mục/thương hiệu "
                        f"- người mua thấy đúng thứ mình gõ."), m
    if cov1 >= 0.999 and cov_avg >= 0.5:
        return "pass", (f"Sản phẩm đầu tiên khớp đủ từ khoá và {int(cov_avg*100)}% mức khớp trung bình "
                        f"ở top-10 - kết quả bám sát query."), m
    if cov1 < 0.001 and cov_avg < 0.2:
        ex = top[0].get("name", "")[:55]
        return "fail", (f"Không sản phẩm nào ở top-10 liên quan tới từ khoá (sản phẩm đầu: \"{ex}\") "
                        f"- người mua gõ xong không thấy thứ mình cần."), m
    if cov1 < 0.001:
        ex = top[0].get("name", "")[:55]
        return "fail", (f"Sản phẩm ĐẦU TIÊN không liên quan từ khoá (\"{ex}\") dù phía dưới có sản phẩm "
                        f"khớp - vị trí đầu là chỗ người mua nhìn trước nhất."), m
    if cov_avg >= 0.5:
        return "pass", (f"Mức khớp trung bình top-10 đạt {int(cov_avg*100)}% - phần lớn kết quả bám query."), m
    return "discuss", (f"Khớp một phần (đầu {int(cov1*100)}%, trung bình top-10 {int(cov_avg*100)}%) - "
                       f"chưa đủ rõ để tự kết luận, cần người xem."), m


def esc(s):
    return html.escape(str(s if s is not None else ""))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--actual", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--store", default="NSG (Nam Sài Gòn)")
    args = p.parse_args()

    data = json.loads(Path(args.actual).read_text(encoding="utf-8"))
    rows = []
    for sc in data["scenarios"]:
        v, reason, m = review(sc)
        rows.append({
            "test_id": sc.get("test_id"), "query": sc.get("query"), "verdict": v, "reason": reason,
            "metrics": m, "resolved_mode": (sc.get("response_meta") or {}).get("resolvedMode"),
            "top": [{"name": x.get("name"), "category": x.get("category"), "brand": x.get("brand")}
                    for x in (sc.get("search_results") or [])[:5]],
        })

    total = len(rows)
    cnt = Counter(r["verdict"] for r in rows)
    print(f"Tổng {total} query -> pass {cnt['pass']} | fail {cnt['fail']} | cần thảo luận {cnt['discuss']}")

    order = {"fail": 0, "discuss": 1, "pass": 2}
    rows.sort(key=lambda r: (order[r["verdict"]], r["test_id"] or ""))

    def card(r):
        vlabel = {"pass": "ĐẠT", "fail": "CHƯA ĐẠT", "discuss": "CẦN THẢO LUẬN"}[r["verdict"]]
        prods = "".join(
            f"<li>{esc(t['name'])}<span class='muted'> — {esc(t['category'])}"
            f"{' · ' + esc(t['brand']) if t.get('brand') else ''}</span></li>" for t in r["top"]) or "<li class='muted'>(không có sản phẩm)</li>"
        mm = r["metrics"]
        met = (f"khớp top-1: {int(mm.get('cov_top1',0)*100)}% · trung bình top-10: {int(mm.get('cov_avg_top10',0)*100)}%"
               f" · khớp đủ: {mm.get('full_match_top10',0)}/10 · tập trung danh mục: {int(mm.get('cat_concentration',0)*100)}%"
               f" · {mm.get('n',0)} kết quả") if mm else ""
        return f"""
    <div class="card {r['verdict']}" data-verdict="{r['verdict']}" data-q="{esc((r['query'] or '').lower())}">
      <div class="chead">
        <span class="v {r['verdict']}">{vlabel}</span>
        <span class="q">"{esc(r['query'])}"</span>
        <span class="tid">{esc(r['test_id'])}</span>
        {f'<span class="mode">{esc(r["resolved_mode"])}</span>' if r.get('resolved_mode') else ''}
      </div>
      <div class="reason">{esc(r['reason'])}</div>
      <div class="met">{esc(met)}</div>
      <ol class="prods">{prods}</ol>
    </div>"""

    cards = "".join(card(r) for r in rows)
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    out = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tự đánh giá kết quả search — {esc(args.store)}</title>
<style>
 :root {{ --ink:#1a1f2b; --muted:#6b7280; --line:#e3e6ec; --soft:#f7f8fa;
   --ok:#15803d; --okbg:#ecfdf5; --no:#b91c1c; --nobg:#fef2f2; --dis:#b45309; --disbg:#fffbeb; }}
 *{{box-sizing:border-box}} body{{margin:0;background:#fff;color:var(--ink);
   font:14px/1.55 "Segoe UI",-apple-system,Roboto,Arial,sans-serif}}
 .wrap{{max-width:1080px;margin:0 auto;padding:26px 22px 60px}}
 h1{{font-size:23px;margin:0 0 6px}} .muted{{color:var(--muted)}} .small{{font-size:12px}}
 .note{{background:var(--soft);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:14px 0;font-size:13px}}
 .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:16px 0}}
 .kpi{{border:1px solid var(--line);border-radius:10px;padding:13px 15px;background:var(--soft)}}
 .kpi .n{{font-size:25px;font-weight:700}} .kpi .l{{font-size:12px;color:var(--muted)}}
 .kpi.ok{{background:var(--okbg);border-color:#bbf7d0}} .kpi.ok .n{{color:var(--ok)}}
 .kpi.no{{background:var(--nobg);border-color:#fecaca}} .kpi.no .n{{color:var(--no)}}
 .kpi.dis{{background:var(--disbg);border-color:#fde68a}} .kpi.dis .n{{color:var(--dis)}}
 .bar{{position:sticky;top:0;background:rgba(255,255,255,.97);padding:10px 0;border-bottom:1px solid var(--line);
   display:flex;gap:8px;flex-wrap:wrap;align-items:center;z-index:5}}
 .tab{{border:1px solid var(--line);background:#fff;border-radius:20px;padding:6px 14px;font-size:13px;cursor:pointer}}
 .tab.active{{background:var(--ink);color:#fff;border-color:var(--ink)}}
 input.s{{flex:1;min-width:200px;padding:7px 12px;border:1px solid var(--line);border-radius:8px;font-size:13px}}
 .card{{border:1px solid var(--line);border-left-width:4px;border-radius:9px;padding:12px 15px;margin:10px 0}}
 .card.pass{{border-left-color:var(--ok)}} .card.fail{{border-left-color:var(--no)}} .card.discuss{{border-left-color:var(--dis)}}
 .chead{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
 .v{{font-size:11px;font-weight:700;padding:2px 9px;border-radius:20px}}
 .v.pass{{background:var(--okbg);color:var(--ok)}} .v.fail{{background:var(--nobg);color:var(--no)}}
 .v.discuss{{background:var(--disbg);color:var(--dis)}}
 .q{{font-weight:600}} .tid,.mode{{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--muted)}}
 .reason{{margin:6px 0 3px;font-size:13px}} .met{{font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}}
 ol.prods{{margin:7px 0 0;padding-left:20px;font-size:12.5px;color:#333}}
 ol.prods li{{margin:1px 0}}
 @media print{{ .bar{{display:none}} .card{{page-break-inside:avoid}} }}
</style></head><body><div class="wrap">
 <h1>Tự đánh giá kết quả tìm kiếm dưới góc độ người mua</h1>
 <p class="muted">Cửa hàng {esc(args.store)} · {total:,} truy vấn · lập lúc {now}</p>

 <div class="note">
   <b>Đây là bản chấm TỰ ĐỘNG để dò nhanh, không phải kết luận cuối.</b> Máy không hiểu ngữ nghĩa như người;
   nó đối chiếu từ khoá với <i>tên / danh mục / thương hiệu</i> của sản phẩm trả về. Vì vậy:
   <ul style="margin:6px 0 0">
     <li>Nhóm gõ thẳng <b>tên hoặc thương hiệu sản phẩm</b> — chấm khá tin cậy.</li>
     <li>Nhóm mô tả <b>nhu cầu/ngữ cảnh</b> ("đồ ăn cho người giảm cân") — máy <b>không tự kết luận</b>,
         vì sản phẩm đúng (gạo lứt) thường không trùng chữ nào với query. Đẩy hết sang <i>Cần thảo luận</i>.</li>
     <li>Nhóm <b>ngoại ngữ</b> — cũng đẩy sang <i>Cần thảo luận</i>, cần người biết tiếng đó xác nhận.</li>
   </ul>
   Mỗi phán quyết đều kèm <b>lý do</b> và <b>5 sản phẩm đầu</b> để anh bác bỏ được ngay khi thấy sai.
 </div>

 <div class="kpis">
   <div class="kpi"><div class="n">{total:,}</div><div class="l">Tổng truy vấn</div></div>
   <div class="kpi ok"><div class="n">{cnt['pass']:,}</div><div class="l">Đạt — {round(cnt['pass']/total*100,1)}%</div></div>
   <div class="kpi no"><div class="n">{cnt['fail']:,}</div><div class="l">Chưa đạt — {round(cnt['fail']/total*100,1)}%</div></div>
   <div class="kpi dis"><div class="n">{cnt['discuss']:,}</div><div class="l">Cần thảo luận — {round(cnt['discuss']/total*100,1)}%</div></div>
 </div>

 <div class="bar">
   <button class="tab active" data-f="all">Tất cả ({total})</button>
   <button class="tab" data-f="fail">Chưa đạt ({cnt['fail']})</button>
   <button class="tab" data-f="discuss">Cần thảo luận ({cnt['discuss']})</button>
   <button class="tab" data-f="pass">Đạt ({cnt['pass']})</button>
   <input class="s" id="s" placeholder="Tìm theo từ khoá hoặc test id...">
   <span class="muted small" id="shown"></span>
 </div>
 <div id="list">{cards}</div>
<script>
let f='all', q='';
const cards=[...document.querySelectorAll('.card')];
function render(){{
  let n=0;
  cards.forEach(c=>{{
    const okF = f==='all' || c.dataset.verdict===f;
    const okQ = !q || c.dataset.q.includes(q) || c.textContent.toLowerCase().includes(q);
    const show = okF && okQ;
    c.style.display = show ? '' : 'none';
    if(show) n++;
  }});
  document.getElementById('shown').textContent = 'Hiển thị '+n+' mục';
}}
document.querySelectorAll('.tab').forEach(b=>b.addEventListener('click',e=>{{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  e.currentTarget.classList.add('active'); f=e.currentTarget.dataset.f; render();
}}));
document.getElementById('s').addEventListener('input',e=>{{q=e.target.value.toLowerCase().trim(); render();}});
render();
</script></div></body></html>"""
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(out, encoding="utf-8")
    print(f"-> {dest} ({dest.stat().st_size/1048576:.2f} MB)")


if __name__ == "__main__":
    main()
