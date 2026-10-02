#!/usr/bin/env python3
"""Phân nhóm BUG + DISCUSSION mà QA đã ghi, xuất ra JSON + HTML để đưa dev/BA.

Vì sao phân nhóm: 103 bug rời rạc thì dev sửa từng cái; gom lại thì thấy rõ
mỗi nhóm là MỘT lỗi gốc - ví dụ 9 keyword cùng hỏi "zero result kèm recommend?"
là một quyết định nghiệp vụ duy nhất, không phải 9 việc.

Phân loại theo DẤU HIỆU TRONG CHÍNH NỘI DUNG GHI CHÚ của QA, không đoán từ
kết quả search. ĐA NHÃN: một ghi chú nêu 2 vấn đề (vd "thiếu sp" + "recommend
k hợp lý") thì thuộc cả 2 nhóm - gán 1 nhãn duy nhất sẽ làm mất việc phải sửa.

Usage:
  python scripts/automation/classify_findings.py \
    --out-json SmartSearch/test_data/exports/findings_classified_20260909.json \
    --out-html SmartSearch/test_data/exports/findings_classified_20260909.html
"""
import argparse
import html
import json
import re
import sys
import unicodedata
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

COMPARE_DIR = Path("SmartSearch/test_data/compare")


def fold(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.replace("đ", "d").replace("Đ", "D")).lower()


# --- Nhóm BUG -------------------------------------------------------------
# Mỗi nhóm: (mã, tên, mô tả việc dev phải làm, danh sách pattern trên note đã
# bỏ dấu). Thứ tự trong file = thứ tự hiển thị, không phải thứ tự ưu tiên
# (đa nhãn nên không cần ưu tiên).
BUG_GROUPS = [
    ("missing_sku", "Thiếu sản phẩm",
     "Sản phẩm CÓ trong catalog và còn hàng nhưng search không trả về. Nghi vấn thiếu index "
     "hoặc điều kiện lọc quá chặt - xem thêm exports/missing_from_search_index_*.json.",
     [r"thieu sp", r"thieu san pham", r"thieu nhieu sp", r"k tim thay", r"khong tim thay",
      r"chua hien thi sp", r"dang k hien thi", r"k thay hien thi", r"actual thieu",
      r"thieu mat", r"can hien thi them", r"can bo sung", r"thieu cac san pham",
      r"so luong result lech", r"lech nhieu so voi prod",
      # QA 2026-09-14: 2 biến thể chữ chưa có luật - "khong thay hien thi"
      # (bản đầy đủ của "k thay hien thi") và "thieu cac sp" (viết tắt của
      # "thieu cac san pham"). Chỉ là cách viết khác của DẤU HIỆU ĐÃ CÓ.
      r"khong thay hien thi", r"thieu cac sp"]),
    ("wrong_results", "Sai hẳn bộ kết quả",
     "Top kết quả không liên quan gì tới từ khoá - người dùng gõ xong không thấy thứ mình cần. "
     "Đây là nhóm nghiêm trọng nhất với trải nghiệm mua hàng.",
     [r"sai bo result", r"sai bo ket qua", r"sai search result", r"search result dang sai",
      r"search result k dung", r"search result chua dung", r"result bi sai", r"result k dung",
      r"result chua dung", r"result hien tai k dung", r"actual result dang sai",
      r"dang hien thi cac san pham k lien quan", r"can hien thi cac san pham",
      r"hien thi cac san pham", r"can hien thi sp", r"o top 1"]),
    ("wrong_ranking", "Sai thứ tự ưu tiên",
     "Sản phẩm đúng CÓ trong kết quả nhưng bị xếp sau sản phẩm kém liên quan hơn. "
     "Sửa ở tầng xếp hạng (boost/scoring), không phải tầng index.",
     [r"can uu tien", r"uu tien", r"can uu ten", r"dang bi day xuong", r"bi day phia sau",
      r"dang xep sau", r"dang hien thi sau", r"dang hien thi truoc", r"len truoc", r"len tren",
      r"len dau", r"len hang dau", r"nen hien thi sau", r"thu tu hien thi", r"dang top",
      # QA 2026-09-14: chỉ đích danh hạng của sản phẩm đúng ("dang o no.16")
      # -> khiếu nại về THỨ HẠNG. Bắt buộc có chữ số ngay sau để không nuốt
      # mọi câu chứa "dang o".
      r"dang o no\.?\s*\d"]),
    ("irrelevant_shown", "Hiển thị sản phẩm không liên quan",
     "Kết quả có lẫn sản phẩm sai ngữ cảnh cần loại bỏ hoặc đẩy xuống cuối "
     "(vd search 'sensodyne' ra xúc xích, search 'mỹ phẩm' ra thực phẩm).",
     [r"k nen hien thi", r"khong nen hien thi", r"k hien thi", r"khong hien thi",
      r"chu k phai", r"cung dang hien thi", r"k phai la do an", r"k lien quan den",
      r"co nen hien thi"]),
    ("semantic_gap", "Thiếu mở rộng ngữ nghĩa / từ đồng nghĩa",
     "Engine chưa hiểu quan hệ đồng nghĩa hoặc quan hệ nhu cầu - từ địa phương "
     "(cải cúc = tần ô), biến thể (gel/sáp/xịt vuốt tóc), hoặc cụm mô tả nhu cầu.",
     [r"can de xuat them", r"de xuat them", r"can hien thi tan o", r"tuong tu cho",
      r"cac loai", r"theo ngu nghia", r"xuat xu", r"co ten"]),
    ("promo_stock", "Sản phẩm khuyến mãi / hết hàng hiển thị sai chỗ",
     "SKU tặng 1đ hoặc sản phẩm đã hết hàng vẫn chiếm vị trí top.",
     [r"san pham tang", r"1d", r"het hang", r"con hang"]),
    ("needs_confirm", "Cần xác nhận dữ liệu / nghiệp vụ trước",
     "QA chưa chốt được đây là lỗi hay không - phải xác nhận sản phẩm có tồn tại trong "
     "danh mục hay quy tắc nghiệp vụ là gì trước khi giao dev.",
     [r"need_discuss", r"co san pham.*k\?", r"can check lai", r"chua xac dinh"]),
    ("recommend_quality", "Chất lượng khối Recommend",
     "Phần gợi ý (recommendations) trả về sản phẩm không hợp lý, hoặc cần đẩy "
     "sản phẩm liên quan sang khối này thay vì trộn vào kết quả chính.",
     [r"recommend", r"day qua recommend"]),
]

# --- Nhóm DISCUSSION -----------------------------------------------------
DISCUSSION_GROUPS = [
    ("zero_or_recommend", "Zero result hay trả recommend?",
     "Khi không có sản phẩm khớp: hiển thị 0 kết quả kèm gợi ý, hay trả sản phẩm gần đúng? "
     "MỘT quyết định nghiệp vụ áp cho cả nhóm - chốt một lần là xong hết.",
     [r"zero result", r"hien thi 0", r"neu k co result"]),
    ("scope_search_vs_recommend", "Sản phẩm liên quan: search result hay recommend?",
     "Sản phẩm cùng nhóm/liên quan (rượu khi search bia, đậu phộng khi search đậu bắp) "
     "nên nằm trong kết quả chính hay tách sang khối gợi ý?",
     [r"co nen hien thi", r"co nen show", r"co nen nam trong", r"hay o section recommend",
      r"hay toan bo day qua", r"xem xet co hien thi", r"co hien thi cac san pham",
      r"can day qua recommend", r"co hien thi cac loai", r"co hien thi trong result",
      r"api recommend", r"hay day het ve", r"nam rieng o",
      # QA hỏi thẳng "... ở search result hay recommend" (2026-09-10) - chuỗi
      # nguyên văn, hẹp, không kéo nhầm ghi chú khác vào nhóm này.
      r"search result hay recommend", r"recommend hay search result",
      # QA 2026-09-14: 10 ghi chú mới đều là CÙNG 1 câu hỏi phạm vi, viết theo
      # 3 kiểu: hỏi thẳng ("co bao gom X trong search result k"), nêu vế
      # recommend ("hay o recommendation"), hoặc kể sản phẩm gần nghĩa engine
      # đang trả kèm ("hien thi them ...", "xen ke ...").
      r"co bao gom", r"trong search result k", r"co nam trong search result",
      r"hay o recommendation", r"hien thi them", r"xen ke",
      # Kiểu thứ 4: QA chỉ LIỆT KÊ các sản phẩm gần nghĩa engine đang trả kèm
      # ("dang hien thi kho ca mai, kho ca chi vang, ...") mà không nói rõ
      # "them"/"xen ke". Buộc phải có dấu phẩy (= một danh sách) nên không
      # nuốt các câu "dang hien thi ..." đơn lẻ của nhóm khác.
      r"dang hien thi \w+ \w+ \w+,",
      # File khách 17/09 hỏi cùng câu đó nhưng viết "... hien thi o/trong
      # search result hay khong / dung k" - thêm hai chuỗi nguyên văn, hẹp.
      r"hien thi (o|trong) search result", r"co hien thi cac sp",
      r"trong search result dung k"]),
    ("ambiguous_keyword", "Từ khoá nhập nhằng - ưu tiên nghĩa nào?",
     "Từ khoá có 2 nghĩa hợp lệ ('ca' = cá hay mắc ca, 'ga' = gà hay nước có ga). "
     "Cần quy tắc chọn nghĩa ưu tiên.",
     [r"uu tien.*truoc hay", r"dang hien thi truoc", r"thu tu hien thi", r"theo ngu nghia",
      # File khách mô tả hiện tượng "trùng keyword"/"matching 'tăng'" - cùng
      # bản chất: một chuỗi khớp hai nghĩa, cần quy tắc chọn nghĩa.
      r"trung keyword", r"matching '"]),
    ("out_of_stock_policy", "Chính sách hàng hết tồn",
     "Sản phẩm hết hàng có nên tiếp tục chiếm vị trí đầu kết quả?",
     [r"het hang"]),
    ("expected_undefined", "Chưa xác định được kết quả mong đợi",
     "QA chưa chốt được đúng/sai cho query này, cần BA/nghiệp vụ định nghĩa trước.",
     [r"chua xac dinh", r"can trao doi", r"need_discuss", r"can thao luan",
      r"can discuss"]),
]


# Vài mục mà luật KHÔNG thể nhận ra vì ghi chú chỉ liệt kê sản phẩm mong đợi
# chứ không nói dạng lỗi. Đọc tay và gán ở đây, KHÔNG bịa thêm pattern rộng
# (pattern rộng sẽ kéo nhầm hàng chục mục khác vào sai nhóm).
MANUAL = {
    "NSG-ALL-0006": ["semantic_gap"],        # "giỏ quà tết" - liệt kê nhóm sản phẩm mong đợi
    "NSG-ALL-0030": ["wrong_ranking"],       # "hop qua tết kinh đô" - chỉ dán list kết quả hiện tại
    "NSG-ALL-0010": ["semantic_gap"],        # "đồ ăn cho người giảm cân" - nêu tiêu chí sản phẩm
    "NSG-ALL-0042": ["wrong_results"],       # "nước hoa nam" -> đang ra nước dùng
    "NSG-ALL-0047": ["expected_undefined"],  # "củ hành tím" - ghi chú để trống
    "NSG-ALL-1209": ["wrong_results"],       # "oshi lays" -> đang ra ô liu, gối
    "NSG-ALL-0504": ["ambiguous_keyword"],   # "muoi" -> cà phê muối xếp sau vá gỗ
    "NSG-ALL-0506": ["irrelevant_shown"],    # "tương ớt hàn quốc" -> ra sp không có nguồn gốc HQ
    # Bug QA ghi 16/09 - luật không bắt được vì ghi chú mô tả HIỆN TƯỢNG
    # (liệt kê sản phẩm lạ) chứ không dùng từ khoá nào của bộ luật.
    "NSG-ALL-0063": ["irrelevant_shown"],    # "gói hút ẩm" -> ra xịt ngăn mùi, khăn giấy, sữa tắm
    "NSG-ALL-0022": ["missing_sku"],         # "nho" -> thiếu nhiều sp vị nho
    "NSG-ALL-0071": ["irrelevant_shown"],    # "thức ăn dặm cho bé" -> ra thức ăn cho chó mèo
    "NSG-ALL-0065": ["irrelevant_shown", "wrong_ranking"],  # "tổ iến" -> thú nhồi bông xếp TRÊN sp yến
    "NSG-ALL-0026": ["missing_sku"],         # "comfort" -> thiếu sp Comfort (nước xả, băng vs Sofy Skin Comfort)
    "NSG-ALL-0028": ["missing_sku"],         # "mắm" -> thiếu sp chứa keyword mắm (xốt Barona, cơm chiên Yorihada)
}


def match_groups(note, groups, test_id=None):
    f = fold(note)
    hits = [g[0] for g in groups if any(re.search(p, f) for p in g[3])]
    codes = {g[0] for g in groups}
    for m in MANUAL.get(test_id or "", []):
        if m in codes and m not in hits:
            hits.append(m)
    return hits


def load(kind, store):
    p = COMPARE_DIR / f"{kind}_notes_{store}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("entries", {})


def esc(s):
    return html.escape(str(s if s is not None else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--store", default="nsg")
    ap.add_argument("--report",
                    default="SmartSearch/test_data/compare/run_all_20260909_112622/compare_report.html",
                    help="dùng để lấy trạng thái Pass/Fail và nhóm truy vấn hiện tại")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--out-html", required=True)
    args = ap.parse_args()

    bugs = load("bug", args.store)
    disc = load("discussion", args.store)

    # trạng thái hiện tại của từng scenario, để biết bug nào còn đang Failed
    status = {}
    rp = Path(args.report)
    if rp.exists():
        for line in rp.read_text(encoding="utf-8").splitlines():
            if line.startswith("const scenarios = ["):
                for s in json.loads(line[len("const scenarios = "):].rstrip().rstrip(";")):
                    status[s["test_id"]] = {"pass_fail": s.get("pass_fail_status"),
                                            "asis_cat": s.get("asis_match_category"),
                                            "dimension": s.get("dimension")}
                break

    def build(entries, groups, label):
        by_group = OrderedDict((g[0], []) for g in groups)
        unmatched = []
        for tid, v in sorted(entries.items(), key=lambda x: x[1].get("query") or ""):
            note = v.get("note") or ""
            hits = match_groups(note, groups, tid)
            row = {"test_id": tid, "query": v.get("query"),
                   "dimension": (status.get(tid) or {}).get("dimension") or v.get("dimension"),
                   "note": note.strip(),
                   "pass_fail": (status.get(tid) or {}).get("pass_fail"),
                   "asis_match": (status.get(tid) or {}).get("asis_cat"),
                   "has_screenshot": bool(v.get("screenshot")),
                   "markedAt": v.get("markedAt"), "groups": hits,
                   "manuallyAssigned": tid in MANUAL}
            if hits:
                for h in hits:
                    by_group[h].append(row)
            else:
                unmatched.append(row)
        print(f"\n=== {label}: {len(entries)} mục ===")
        for code, name, _desc, _pat in groups:
            print(f"   {name:46} {len(by_group[code]):3}")
        print(f"   {'(chưa khớp nhóm nào - cần đọc tay)':46} {len(unmatched):3}")
        return by_group, unmatched

    bug_g, bug_un = build(bugs, BUG_GROUPS, "BUG")
    dis_g, dis_un = build(disc, DISCUSSION_GROUPS, "DISCUSSION")

    payload = {
        "generatedDate": datetime.now().strftime("%Y-%m-%d"),
        "store": args.store,
        "method": ("Phân nhóm theo dấu hiệu trong CHÍNH NỘI DUNG ghi chú của QA. ĐA NHÃN: "
                   "một ghi chú nêu 2 vấn đề thì thuộc cả 2 nhóm, nên tổng các nhóm > số mục."),
        "bugTotal": len(bugs), "discussionTotal": len(disc),
        "bugGroups": [{"code": c, "name": n, "action": d, "count": len(bug_g[c]), "items": bug_g[c]}
                      for c, n, d, _ in BUG_GROUPS],
        "bugUnclassified": bug_un,
        "discussionGroups": [{"code": c, "name": n, "action": d, "count": len(dis_g[c]), "items": dis_g[c]}
                             for c, n, d, _ in DISCUSSION_GROUPS],
        "discussionUnclassified": dis_un,
    }
    oj = Path(args.out_json)
    oj.parent.mkdir(parents=True, exist_ok=True)
    oj.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n-> {oj}")

    # ---- HTML ----
    def sect(title, groups_data, unclassified, tone):
        parts = []
        for g in groups_data:
            if not g["count"]:
                continue
            rows = "".join(
                f"<tr><td class='q'>{esc(i['query'])}</td>"
                f"<td class='m'>{esc(i['test_id'])}</td>"
                f"<td><span class='pf {i['pass_fail']}'>{esc(i['pass_fail'])}</span></td>"
                f"<td class='n'>{esc(i['note'][:400])}"
                f"{'<span class=img> có ảnh</span>' if i['has_screenshot'] else ''}"
                f"{'<div class=also>cũng thuộc: ' + esc(', '.join(x for x in i['groups'] if x != g['code'])) + '</div>' if len(i['groups']) > 1 else ''}"
                f"</td></tr>" for i in g["items"])
            parts.append(f"""
  <details class="grp {tone}" open>
    <summary><b>{esc(g['name'])}</b> <span class="cnt">{g['count']}</span></summary>
    <p class="act">{esc(g['action'])}</p>
    <table><thead><tr><th>Từ khoá</th><th>Test ID</th><th>Trạng thái</th><th>Ghi chú của QA</th></tr></thead>
    <tbody>{rows}</tbody></table>
  </details>""")
        if unclassified:
            rows = "".join(f"<tr><td class='q'>{esc(i['query'])}</td><td class='m'>{esc(i['test_id'])}</td>"
                           f"<td class='n'>{esc(i['note'][:400])}</td></tr>" for i in unclassified)
            parts.append(f"""
  <details class="grp warn">
    <summary><b>Chưa khớp nhóm nào</b> <span class="cnt">{len(unclassified)}</span></summary>
    <p class="act">Bộ luật phân nhóm không nhận ra dạng vấn đề - cần người đọc và xếp nhóm tay.</p>
    <table><thead><tr><th>Từ khoá</th><th>Test ID</th><th>Ghi chú</th></tr></thead><tbody>{rows}</tbody></table>
  </details>""")
        return f"<h2>{title}</h2>" + "".join(parts)

    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    out = f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phân nhóm Bug &amp; Discussion — Smart Search</title>
<style>
 :root{{--ink:#1a1f2b;--muted:#667085;--line:#e4e7ec;--soft:#f8f9fb}}
 *{{box-sizing:border-box}} body{{margin:0;background:#fff;color:var(--ink);
   font:14px/1.55 "Segoe UI",-apple-system,Roboto,Arial,sans-serif}}
 .wrap{{max-width:1160px;margin:0 auto;padding:26px 22px 70px}}
 h1{{font-size:23px;margin:0 0 4px}} h2{{font-size:18px;margin:30px 0 10px;padding-bottom:6px;
   border-bottom:2px solid var(--line)}}
 .muted{{color:var(--muted)}} .small{{font-size:12.5px}}
 .note{{background:var(--soft);border:1px solid var(--line);border-radius:9px;padding:12px 16px;margin:14px 0;font-size:13px}}
 .kpis{{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}}
 .kpi{{border:1px solid var(--line);border-radius:9px;padding:11px 16px;background:var(--soft);min-width:130px}}
 .kpi .n{{font-size:24px;font-weight:700}} .kpi .l{{font-size:12px;color:var(--muted)}}
 details.grp{{border:1px solid var(--line);border-left-width:4px;border-radius:8px;margin:10px 0;padding:10px 14px}}
 details.grp.bug{{border-left-color:#dc2626}} details.grp.dis{{border-left-color:#2563eb}}
 details.grp.warn{{border-left-color:#d97706;background:#fffbeb}}
 summary{{cursor:pointer;font-size:15px}} summary b{{margin-right:6px}}
 .cnt{{background:var(--ink);color:#fff;border-radius:20px;padding:1px 9px;font-size:12px;font-weight:700}}
 .act{{margin:8px 0 10px;font-size:13px;color:#374151}}
 table{{width:100%;border-collapse:collapse;font-size:13px}}
 th{{text-align:left;background:var(--soft);padding:7px 9px;border-bottom:1px solid var(--line);font-size:11.5px;
   text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}}
 td{{padding:7px 9px;border-bottom:1px solid #f1f3f6;vertical-align:top}}
 td.q{{font-weight:600;white-space:nowrap}} td.m{{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:var(--muted);white-space:nowrap}}
 td.n{{white-space:pre-wrap;color:#374151}}
 .pf{{font-size:11px;font-weight:700;padding:1px 8px;border-radius:20px;white-space:nowrap}}
 .pf.failed{{background:#fef2f2;color:#b91c1c}} .pf.passed{{background:#ecfdf5;color:#15803d}}
 .pf.discussion{{background:#eff6ff;color:#1d4ed8}}
 .img{{font-size:11px;color:#7c3aed;margin-left:6px}}
 .also{{font-size:11.5px;color:var(--muted);margin-top:3px;font-style:italic}}
</style></head><body><div class="wrap">
 <h1>Phân nhóm Bug &amp; Discussion — Smart Search</h1>
 <p class="muted">Cửa hàng {esc(args.store.upper())} · lập lúc {now}</p>

 <div class="kpis">
   <div class="kpi"><div class="n">{len(bugs)}</div><div class="l">Bug đã ghi</div></div>
   <div class="kpi"><div class="n">{len([g for g in payload['bugGroups'] if g['count']])}</div><div class="l">Nhóm bug</div></div>
   <div class="kpi"><div class="n">{len(disc)}</div><div class="l">Cần thảo luận</div></div>
   <div class="kpi"><div class="n">{len([g for g in payload['discussionGroups'] if g['count']])}</div><div class="l">Nhóm thảo luận</div></div>
 </div>

 <div class="note">
   <b>Cách phân nhóm:</b> dựa trên <i>dấu hiệu trong chính nội dung ghi chú của QA</i>, không suy ra từ kết quả search.<br>
   <b>Một mục có thể thuộc nhiều nhóm</b> — nhiều ghi chú nêu 2 vấn đề cùng lúc (ví dụ vừa thiếu sản phẩm,
   vừa sai thứ tự). Vì vậy tổng số của các nhóm lớn hơn số mục thực tế. Mục thuộc nhiều nhóm có ghi
   <i>"cũng thuộc: ..."</i> ở cuối ghi chú.<br>
   <b>Mục đích:</b> gom để thấy mỗi nhóm là <b>một lỗi gốc</b> cần một hướng sửa, thay vì {len(bugs)} việc rời rạc.
 </div>

 {sect("Bug — theo nhóm nguyên nhân", payload["bugGroups"], bug_un, "bug")}
 {sect("Cần thảo luận — theo chủ đề quyết định", payload["discussionGroups"], dis_un, "dis")}
</div></body></html>"""
    oh = Path(args.out_html)
    oh.write_text(out, encoding="utf-8")
    print(f"-> {oh}")


if __name__ == "__main__":
    main()
