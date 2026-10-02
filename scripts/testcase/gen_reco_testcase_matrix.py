# -*- coding: utf-8 -*-
r"""Sinh ma tran test case cho Recommendation tu REQ, kem dashboard HTML + CSV.

    python scripts\testcase\gen_reco_testcase_matrix.py
    python scripts\testcase\gen_reco_testcase_matrix.py --check   # exit 1 neu output lech REQ

BA TRUC PRECONDITION (dung dung 3 truc tren man hinh Rule Simulator):
    1. Segment khach hang  - 26 segment, chon nhieu
    2. Zone                - 16 zone
    3. Dieu kien phu       - IND (co lich su duyet/mua) va Engine tra ve rong

To hop tho la 2^26 x 16 x 2 x 2 = 4.29 ty case -> khong chay duoc. Output cua
engine chi phu thuoc vao TAP AUDIENCE MA KHACH KHOP trong pham vi zone do, nen
ta phan hoach theo lop tuong duong. 5 bo duoi day phu kin moi lop:

  A. 44 rule x lam rule thang + 26 segment x roi ve Default, moi thu x Empty{0,1}
  B. Cap audience tranh priority  moi cap (Ai, Aj) cung zone x Empty{0,1}
  C. Max contention       tat ca audience dac thu cua zone cung luc x Empty{0,1}
  E. Show-when cua zone khong thoa  1 case / zone co dieu kien

HO SO KHACH PHAI CO THAT: S-01..S-06 la mot phan hoach (chua dang nhap -> S-06;
da dang nhap -> S-01..S-04 theo hang, khong hang -> S-05), nen KHONG ton tai khach
"khong thuoc segment nao" — bo D cu da bi go bo. 20 segment con lai deu doi hoi tai
khoan/don hang nen luon duoc ghep kem mot segment nen. Ho so mau thuan (vi du 0 don
hang + >=3 don hang) duoc danh dau BLOCKER chu khong xoa, vi no cung la phat hien
can hoi Mart.

Bao dam phu:
  - Moi rule trong 44 rule deu duoc lam rule THANG it nhat 1 lan (decision coverage).
  - Moi cap rule cung zone deu duoc dat canh tranh (pairwise priority coverage).
  - Moi nhanh If empty cua moi rule deu duoc kich hoat.
  - Moi segment deu duoc kiem o MOI zone no co rule, cong 1 zone dai dien
    de xac nhan no roi ve ALL - Default dung cach.

Expected result suy ra bang chinh thuat toan first-match-wins cua REQ, khong doan.
Cho nao REQ chua dinh nghia thi danh dau BLOCKER chu khong tu bia.

QUY UOC NGON NGU (yeu cau cua QA lead):
  - Chu tieng Anh LAY NGUYEN VAN TU REQ thi giu nguyen, khong dich: title cua rule,
    "what products to show", gia tri "If empty", audience label, ten mechanism,
    v1 status, Page / Position / Channel.
  - Chu tieng Anh do dashboard tu dat ra thi kem nghia tieng Viet trong ngoac.
  - Moi chu tieng Viet deu viet CO DAU. Rieng phan in ra console giu ASCII de
    khong vo tren cp1252 khi chay `python script.py` khong set PYTHONIOENCODING.
"""
import argparse
import csv
import io
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sync_reco_dashboard_data import find_req, load_req  # noqa: E402

OUT_DIR = os.path.join("Recommendation", "testcases")
OUT_HTML = os.path.join(OUT_DIR, "reco_testcase_matrix_dashboard.html")
OUT_CSV = os.path.join(OUT_DIR, "reco_testcase_matrix.csv")
TPL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "reco_testcase_matrix.html.tpl")

READY = "READY"
SUITES = {
    "A": "Mỗi rule thắng 1 lần + mỗi segment rơi về Default 1 lần",
    "B": "Cặp audience (đối tượng) tranh Priority (độ ưu tiên)",
    "C": "Max contention (tranh chấp tối đa) — khớp tất cả audience của zone",
    "E": "Show when (điều kiện hiển thị zone) không thoả",
}

# ---- Mô hình khách hàng hợp lệ (suy ra từ điều kiện ở sheet 3 của REQ) ----
# S-01..S-06 là một PHÂN HOẠCH: mọi khách thuộc đúng một trong sáu.
#   chưa đăng nhập            -> S-06 Visitor
#   đã đăng nhập, có hạng     -> S-01 Diamond / S-02 Platinum / S-03 Gold / S-04 Silver
#   đã đăng nhập, không hạng  -> S-05 General / Guest
# => KHÔNG tồn tại khách "không thuộc segment nào". 20 segment còn lại đều đòi hỏi
#    tài khoản hoặc lịch sử đơn hàng nên không bao giờ đứng một mình được.
BASE_SEGMENTS = ["S-01", "S-02", "S-03", "S-04", "S-05", "S-06"]
GUEST = "S-06"                 # chưa đăng nhập -> không thể kèm segment nào khác
# S-04 Silver làm segment nền mặc định: đông nhất (1.747.620 tài khoản) và chỉ xuất
# hiện ở đúng 1 rule (R-043 @ OVERLAY) nên gần như không che khuất segment cần đo.
DEFAULT_BASE = "S-04"

# Mâu thuẫn rút thẳng từ cột "System condition" của sheet 3.
ZERO_ORDER = {"S-07", "S-08", "S-09"}                     # 0 đơn hàng online
HAS_ORDER = {"S-10", "S-11", "S-12", "S-15", "S-17",      # bắt buộc đã có đơn
             "S-19", "S-22", "S-25", "S-26"}
FEW_ORDER = {"S-13"}                                      # Tourist: <= 1 đơn
MANY_ORDER = {"S-10", "S-17"}                             # >= 3 đơn


def make_profile(auds):
    """Bổ sung segment nền để hồ sơ khách là hồ sơ có thật."""
    segs = [a for a in auds if a != "IND"]
    if GUEST in segs or any(a in BASE_SEGMENTS for a in segs):
        return segs
    return [DEFAULT_BASE] + segs


def profile_conflicts(segs):
    """Các mâu thuẫn khiến hồ sơ khách không thể dựng được trên hệ thống thật."""
    out = []
    ss = set(segs)
    bases = [a for a in segs if a in BASE_SEGMENTS]
    if len(bases) > 1:
        out.append("Hồ sơ mâu thuẫn: một khách chỉ thuộc đúng 1 trong %s" % ", ".join(BASE_SEGMENTS))
    if GUEST in ss and len(ss) > 1:
        out.append("Hồ sơ mâu thuẫn: S-06 Visitor là khách chưa đăng nhập nên không có hồ sơ để thuộc segment khác")
    if "S-08" in ss and "S-09" in ss:
        out.append("Hồ sơ mâu thuẫn: S-08 đăng ký trong tháng này, S-09 đăng ký trước tháng này")
    if ss & ZERO_ORDER and ss & HAS_ORDER:
        out.append("Hồ sơ mâu thuẫn: %s yêu cầu 0 đơn hàng, %s yêu cầu đã có đơn"
                   % (", ".join(sorted(ss & ZERO_ORDER)), ", ".join(sorted(ss & HAS_ORDER))))
    if ss & FEW_ORDER and ss & MANY_ORDER:
        out.append("Hồ sơ mâu thuẫn: S-13 Tourist tối đa 1 đơn, %s cần tối thiểu 3 đơn"
                   % ", ".join(sorted(ss & MANY_ORDER)))
    if "S-13" in ss and bases and bases[0] not in ("S-04", "S-05"):
        out.append("Hồ sơ mâu thuẫn: S-13 Tourist yêu cầu hạng Guest/Silver, không phải %s" % bases[0])
    return out

KIND_CSV = {
    "zone-default": "(zone không có rule — dùng Zone Register)",
    "no-match": "(KHÔNG rule nào khớp — REQ chưa định nghĩa)",
    "not-rendered": "(zone không render — không vẽ ra)",
}


class Engine(object):
    """Mo phong dung co che first-match-wins cua REQ (sheet 5)."""

    def __init__(self, req):
        self.zones = req["zones"]
        self.segments = req["segments"]
        self.rules = req["rules"]
        self.zone_by_id = dict((z["id"], z) for z in self.zones)
        self.rules_by_zone = {}
        for z in self.zones:
            self.rules_by_zone[z["id"]] = sorted(
                [r for r in self.rules if r["zone"] == z["id"]], key=lambda r: r["prio"])

    def audiences_of(self, zone_id):
        """Cac audience dac thu cua zone (bo ALL - Default vi luon khop)."""
        return [r["audKey"] for r in self.rules_by_zone[zone_id] if r["audKey"] != "ALL"]

    def resolve(self, zone_id, segs, ind):
        matched, winner = [], None
        for r in self.rules_by_zone[zone_id]:
            if r["audKey"] == "ALL":
                ok = True
            elif r["audKey"] == "IND":
                ok = bool(ind)
            else:
                ok = r["audKey"] in segs
            if ok:
                matched.append(r)
                if winner is None:
                    winner = r
        return winner, matched


def expected(engine, zone_id, segs, ind, empty, zone_visible=True):
    """Dung ket qua mong doi + danh sach blocker (cho REQ chua dinh nghia)."""
    z = engine.zone_by_id[zone_id]
    zone_rules = engine.rules_by_zone[zone_id]
    blockers = []

    if z["status"] and not z["status"].startswith(READY):
        blockers.append("Zone %s ngoài v1: %s" % (zone_id, z["status"]))

    if not zone_visible:
        return {
            "kind": "not-rendered",
            "win": None, "matched": [], "losers": [],
            "outcome": "Zone KHÔNG render (không vẽ ra trên trang)",
            "mech": "-", "title": "-", "show": "-",
            "ifEmpty": "-", "max": z["max"] or "-",
            "reason": "Điều kiện Show when (hiển thị zone) không thoả: %s" % (z["showWhen"] or "-"),
            "blockers": blockers,
        }

    winner, matched = engine.resolve(zone_id, segs, ind)

    if not zone_rules:
        # Zone khong co rule nao o sheet 5 -> roi ve cau hinh mac dinh Zone Register
        mech = z["mech"] or "-"
        if mech == "hide":
            outcome = "Ẩn zone (mechanism mặc định của zone = hide)"
        elif empty:
            outcome = "Engine trả về rỗng → dùng If empty của zone: %s" % (z["ifEmpty"] or "-")
        else:
            outcome = "Hiển thị tối đa %s sản phẩm từ mechanism (cơ chế) %s" % (z["max"] or "-", mech)
        blockers.append("Zone không có rule nào ở sheet 5 — phải dùng cấu hình mặc định ở Zone Register")
        return {
            "kind": "zone-default",
            "win": None, "matched": [], "losers": [],
            "outcome": outcome, "mech": mech, "title": z["title"] or "-",
            "show": "(REQ không mô tả ở mức rule)", "ifEmpty": z["ifEmpty"] or "-",
            "max": z["max"] or "-",
            "reason": "Zone không có rule — dùng cấu hình mặc định ở Zone Register",
            "blockers": blockers,
        }

    if winner is None:
        blockers.append(
            "Zone %s không có rule ALL — Default; REQ không định nghĩa khách ngoài %s thì hiển thị gì"
            % (zone_id, "/".join(engine.audiences_of(zone_id))))
        return {
            "kind": "no-match",
            "win": None, "matched": [], "losers": [],
            "outcome": "KHÔNG XÁC ĐỊNH — không rule nào khớp",
            "mech": "-", "title": "-", "show": "-", "ifEmpty": "-", "max": z["max"] or "-",
            "reason": "Khách không thuộc audience (đối tượng) nào của zone, mà zone lại thiếu rule ALL — Default",
            "blockers": blockers,
        }

    if winner["status"] and not winner["status"].startswith(READY):
        blockers.append("Rule %s ngoài v1: %s" % (winner["id"], winner["status"]))

    if empty:
        fb = (winner["ifEmpty"] or "").strip()
        if fb in ("", "-", "—"):
            outcome = "KHÔNG XÁC ĐỊNH — REQ để trống nhánh If empty"
            blockers.append("Rule %s không định nghĩa nhánh If empty (khi engine trả về rỗng)" % winner["id"])
        elif fb.lower() == "hide":
            outcome = "Ẩn zone hoàn toàn"
        else:
            outcome = "Hiển thị tối đa %s sản phẩm từ nguồn fallback (dự phòng): %s" % (z["max"] or "-", fb)
    else:
        outcome = "Hiển thị tối đa %s sản phẩm từ mechanism (cơ chế) %s, title (tiêu đề) \"%s\"" % (
            z["max"] or "-", winner["mech"], winner["title"] or "-")

    losers = [r["id"] for r in matched if r["id"] != winner["id"]]
    reason = "Priority (độ ưu tiên) %s là rule khớp đầu tiên" % winner["prio"]
    if losers:
        reason += "; thắng %d rule cũng khớp: %s" % (len(losers), ", ".join(losers))

    return {
        "kind": "rule",
        "win": winner["id"], "matched": [r["id"] for r in matched], "losers": losers,
        "outcome": outcome, "mech": winner["mech"], "title": winner["title"] or "-",
        "show": winner["show"] or "-", "ifEmpty": winner["ifEmpty"] or "-",
        "max": z["max"] or "-", "reason": reason, "blockers": blockers,
    }


def build_cases(req):
    engine = Engine(req)
    zones = req["zones"]
    segs_all = [s["id"] for s in req["segments"]]
    cases = []
    counters = dict((k, 0) for k in SUITES)

    def add(suite, zone_id, segs, ind, empty, zone_visible=True, intent=""):
        counters[suite] += 1
        exp = expected(engine, zone_id, segs, ind, empty, zone_visible)
        exp["blockers"] = profile_conflicts(segs) + exp["blockers"]
        cases.append({
            "id": "TC-RECO-%s%04d" % (suite, counters[suite]),
            "suite": suite,
            "zone": zone_id,
            "segs": list(segs),
            "ind": 1 if ind else 0,
            "empty": 1 if empty else 0,
            "visible": 1 if zone_visible else 0,
            "intent": intent,
            "exp": exp,
        })

    # ---- A1: moi RULE duoc lam rule THANG dung 1 lan (decision coverage) ----
    # Dung ho so toi thieu khien rule do khop dau tien; co kiem chung bang engine
    # chu khong tin suong.
    for z in zones:
        for r in engine.rules_by_zone[z["id"]]:
            segs, ind = None, False
            if r["audKey"] == "IND":
                cand, ind = [[b] for b in BASE_SEGMENTS if b != GUEST], True
            elif r["audKey"] == "ALL":
                cand = [[b] for b in BASE_SEGMENTS]
            else:
                cand = [make_profile([r["audKey"]])]
                # neu segment nen mac dinh lai trung rule uu tien cao hon thi doi nen
                cand += [[b, r["audKey"]] for b in BASE_SEGMENTS
                         if b != GUEST and r["audKey"] not in BASE_SEGMENTS]
            for c in cand:
                w, _ = engine.resolve(z["id"], c, ind)
                if w and w["id"] == r["id"]:
                    segs = c
                    break
            if segs is None:
                # khong dung duoc ho so nao khien rule nay thang -> rule chet, van ghi
                # lai 1 case de bao cao
                segs = cand[0]
            for empty in (False, True):
                add("A", z["id"], segs, ind, empty,
                    intent="Làm %s (Priority %s, %s) thành rule thắng"
                           % (r["id"], r["prio"], r["aud"]))

    # ---- A2: moi segment roi ve ALL - Default o zone khong co rule cua no ----
    # Kiem he thong KHONG phan loai nham segment vao mot rule khong lien quan.
    zone_of_seg = {}
    for r in req["rules"]:
        if r["audKey"] not in ("ALL", "IND"):
            zone_of_seg.setdefault(r["audKey"], set()).add(r["zone"])
    for sid in segs_all:
        own = zone_of_seg.get(sid, set())
        rep = next((z["id"] for z in zones
                    if z["id"] not in own and engine.rules_by_zone[z["id"]]), None)
        if rep is None:
            continue
        for empty in (False, True):
            add("A", rep, make_profile([sid]), False, empty,
                intent="%s không có rule ở %s — phải rơi về ALL — Default" % (sid, rep))

    # ---- B: moi cap audience dac thu trong cung zone ----
    for z in zones:
        auds = engine.audiences_of(z["id"])
        seen = []
        for a in auds:                      # giu thu tu priority, bo trung
            if a not in seen:
                seen.append(a)
        for a1, a2 in itertools.combinations(seen, 2):
            segs = make_profile([a1, a2])
            ind = "IND" in (a1, a2)
            for empty in (False, True):
                add("B", z["id"], segs, ind, empty,
                    intent="Tranh Priority (độ ưu tiên) giữa %s và %s" % (a1, a2))

    # ---- C: tat ca audience dac thu cua zone cung luc ----
    for z in zones:
        auds = []
        for a in engine.audiences_of(z["id"]):
            if a not in auds:
                auds.append(a)
        if len(auds) < 2:
            continue
        segs = make_profile(auds)
        ind = "IND" in auds
        for empty in (False, True):
            add("C", z["id"], segs, ind, empty,
                intent="Khách khớp TẤT CẢ %d audience (đối tượng) của zone" % len(auds))

    # ---- E: show-when cua zone khong thoa ----
    for z in zones:
        sw = (z["showWhen"] or "").strip()
        if sw.lower().startswith("always") or sw in ("", "-", "—"):
            continue
        add("E", z["id"], [DEFAULT_BASE], False, False, zone_visible=False,
            intent="Điều kiện Show when (hiển thị zone) không thoả")

    return cases, engine


def coverage(cases, req, engine):
    """Kiem tra cac bao dam phu da neu o docstring."""
    rules = req["rules"]
    won = set(c["exp"]["win"] for c in cases if c["exp"]["win"])
    empty_branch = set(c["exp"]["win"] for c in cases
                       if c["empty"] and c["exp"]["win"])
    pairs_needed, pairs_hit = set(), set()
    for z in req["zones"]:
        auds = []
        for a in engine.audiences_of(z["id"]):
            if a not in auds:
                auds.append(a)
        for a, b in itertools.combinations(auds, 2):
            pairs_needed.add((z["id"], a, b))
    for c in cases:
        auds = set(c["segs"]) | (set(["IND"]) if c["ind"] else set())
        zauds = [a for a in engine.audiences_of(c["zone"]) if a in auds]
        uniq = []
        for a in zauds:
            if a not in uniq:
                uniq.append(a)
        for a, b in itertools.combinations(uniq, 2):
            pairs_hit.add((c["zone"], a, b))
    # Moi (segment, zone) MA SEGMENT DO CO RULE deu phai duoc kiem. Khong yeu cau
    # quet het 26x16 vi segment khong co rule o zone nao thi ket qua luon giong nhau
    # (roi ve ALL - Default) - quet het chi tao ban sao, da duoc bo A2 kiem 1 lan.
    seg_zone_needed = set((r["zone"], r["audKey"]) for r in req["rules"]
                          if r["audKey"] not in ("ALL", "IND"))
    seg_zone_hit = set((c["zone"], x) for c in cases for x in c["segs"])
    seg_needed = set(s["id"] for s in req["segments"])
    seg_hit = set(x for c in cases for x in c["segs"])

    return {
        "rules_total": len(rules),
        "rules_won": len(won),
        "rules_never_win": sorted(set(r["id"] for r in rules) - won),
        "empty_branch_total": len(rules),
        "empty_branch_hit": len(empty_branch),
        "pairs_needed": len(pairs_needed),
        "pairs_hit": len(pairs_needed & pairs_hit),
        "pairs_missing": sorted(pairs_needed - pairs_hit)[:10],
        "segzone_needed": len(seg_zone_needed),
        "segzone_hit": len(seg_zone_needed & seg_zone_hit),
        "seg_needed": len(seg_needed),
        "seg_hit": len(seg_needed & seg_hit),
        "dup_classes": None,
    }


# Tieng Anh giu nguyen khi la thuat ngu REQ; kem nghia tieng Viet trong ngoac khi la
# chu do dashboard tu dat ra.
CSV_HEADER = [
    "Test case ID", "Bộ test", "Mục tiêu",
    "PRE: Zone (vùng gợi ý)", "PRE: Page (trang)", "PRE: Position (vị trí)",
    "PRE: Channel (kênh)", "PRE: Show when (điều kiện hiển thị zone)",
    "PRE: Zone v1 status (trạng thái)", "PRE: Max items (số sản phẩm tối đa)",
    "IN: Segments (phân khúc khách)", "IN: Số segment",
    "IN: IND (có lịch sử duyệt/mua)", "IN: Engine trả về rỗng", "IN: Zone có hiển thị",
    "OUT: Rule thắng", "OUT: Priority (độ ưu tiên)", "OUT: Audience (đối tượng)",
    "OUT: Mechanism (cơ chế)", "OUT: Zone title (tiêu đề zone)",
    "OUT: What products to show (sản phẩm hiển thị — nguyên văn REQ)",
    "OUT: If empty (khi engine trả về rỗng)",
    "OUT: Kết quả hiển thị", "OUT: Lý do", "OUT: Rule cùng khớp bị bỏ qua",
    "Rule v1 status (trạng thái)", "Trong scope v1 (phạm vi v1)", "Blocker (vướng mắc)",
]


def to_rows(cases, req):
    zone_by_id = dict((z["id"], z) for z in req["zones"])
    rule_by_id = dict((r["id"], r) for r in req["rules"])
    rows = []
    for c in cases:
        z = zone_by_id[c["zone"]]
        w = rule_by_id.get(c["exp"]["win"]) if c["exp"]["win"] else None
        rows.append([
            c["id"], c["suite"], c["intent"],
            z["id"], z["page"], z["pos"], z["channel"], z["showWhen"], z["status"], z["max"],
            ", ".join(c["segs"]) if c["segs"] else "(không có)", len(c["segs"]),
            "Có" if c["ind"] else "Không", "Có" if c["empty"] else "Không",
            "Có" if c["visible"] else "Không",
            (w["id"] if w else KIND_CSV.get(c["exp"]["kind"], "(không có rule nào khớp)")),
            (w["prio"] if w else ""), (w["aud"] if w else ""),
            c["exp"]["mech"], c["exp"]["title"], c["exp"]["show"], c["exp"]["ifEmpty"],
            c["exp"]["outcome"], c["exp"]["reason"], ", ".join(c["exp"]["losers"]),
            (w["status"] if w else ""),
            "Không" if c["exp"]["blockers"] else "Có",
            " | ".join(c["exp"]["blockers"]),
        ])
    return rows


def render(cases, req, cov):
    with io.open(TPL, encoding="utf-8") as f:
        tpl = f.read()
    payload = {
        "cases": cases,
        "zones": req["zones"],
        "segments": req["segments"],
        "rules": req["rules"],
        "suites": SUITES,
        "kindLabel": KIND_CSV,
        "coverage": cov,
    }
    data = "        const TCDATA = %s;\n" % json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if "/*__TCDATA__*/" not in tpl:
        raise SystemExit("template thieu moc /*__TCDATA__*/: %s" % TPL)
    return tpl.replace("/*__TCDATA__*/", data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xlsx", default=None)
    ap.add_argument("--check", action="store_true", help="khong ghi; exit 1 neu output lech REQ")
    a = ap.parse_args()

    xlsx = a.xlsx or find_req()
    req = load_req(xlsx)
    cases, engine = build_cases(req)
    cov = coverage(cases, req, engine)
    html = render(cases, req, cov)
    rows = to_rows(cases, req)

    # Console giu ASCII de khong vo tren cp1252.
    print("REQ  : %s" % xlsx)
    for k in sorted(SUITES):
        n = len([c for c in cases if c["suite"] == k])
        print("  bo %s: %5d case" % (k, n))
    print("  TONG : %5d case" % len(cases))
    print("phu   : rule thang %d/%d | nhanh If-empty %d/%d | cap priority %d/%d"
          % (cov["rules_won"], cov["rules_total"], cov["empty_branch_hit"], cov["empty_branch_total"],
             cov["pairs_hit"], cov["pairs_needed"]))
    print("        segment co rule x zone %d/%d | segment duoc kiem %d/%d"
          % (cov["segzone_hit"], cov["segzone_needed"], cov["seg_hit"], cov["seg_needed"]))
    if cov["rules_never_win"]:
        print("  rule KHONG BAO GIO thang: %s" % ", ".join(cov["rules_never_win"]))
    blocked = len([c for c in cases if c["exp"]["blockers"]])
    print("case co blocker (ngoai scope v1 / REQ chua dinh nghia): %d" % blocked)

    if a.check:
        old = io.open(OUT_HTML, encoding="utf-8").read() if os.path.isfile(OUT_HTML) else ""
        if old == html:
            print("OK   : dashboard test case da khop REQ")
            return
        print("LECH : dashboard test case chua khop REQ - chay lai khong co --check")
        sys.exit(1)

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    io.open(OUT_HTML, "w", encoding="utf-8", newline="\n").write(html)
    with io.open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        w.writerows(rows)
    print("wrote: %s (%.0f KB)" % (OUT_HTML, len(html.encode("utf-8")) / 1024.0))
    print("wrote: %s (%d dong)" % (OUT_CSV, len(rows)))


if __name__ == "__main__":
    main()
