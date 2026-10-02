"""
Tự chấm độ liên quan kết quả search theo thang 0-5 (thay cho QA duyệt tay), cho cả Dev (Actual)
và Prod (As-Is cache). Kết hợp hai lớp:

  1) Luật cố định theo file intent (AI viết 1 lần / query, lưu bền) -> chấm được phần lớn cặp.
  2) AI chấm lại các cặp (query, sp) mà luật không chắc -> điểm lưu bền theo (query, SKU),
     lần chạy sau chỉ phải chấm sp mới xuất hiện.

Thang điểm 0-5 (rubric đầy đủ: .claude/agents/search-judge.md):
  5 = đúng loại sp VÀ thỏa mọi ràng buộc trong query (brand, xuất xứ, size, vị, biến thể)
  4 = đúng loại sp nhưng lệch một ràng buộc (brand/size/xuất xứ khác)
  3 = sp thay thế cùng họ, khách vẫn chấp nhận (vd "dưa hấu" -> dưa lưới, dưa lê)
  2 = liên quan nhưng sai loại, không thay thế được (cùng ngành hàng / sp bổ trợ)
  1 = chỉ cùng ngành hàng rộng, liên quan yếu
  0 = không liên quan, hoặc chỉ trùng chữ (vd "roi" -> "Ba Rọi", "nước hoa" -> "nước hoa hồng")
Tồn kho KHÔNG ảnh hưởng điểm.

Từ đồng nghĩa (SmartSearch/test_data/judge/synonyms_nsg.json): intent được mở rộng lúc chạy, vd type
"thịt heo" khớp luôn "thịt lợn" (equiv -> 5/4), "bột giặt" nhận "xà phòng giặt" (substitute -> 3). Từ trần dễ
trùng chữ ("thơm", "quả") không cho điểm bằng luật mà đẩy cặp sang AI. --synonyms '' để tắt.

Kết luận 1 keyword: FAILED nếu 0 kết quả hoặc có sp điểm < --min-ok (mặc định 3, tức sp không chấp nhận
được) trong top-K (mặc định 10, 0 = toàn bộ; catalog chỉ có N<K sp điểm>=min-ok thì xét top-N). Cũng FAILED
nếu catalog có sp đúng hoàn toàn (điểm 5) mà top-K không có sp điểm 5 nào (vd "bia corona" toàn bia hãng
khác dù mart có Corona). Kèm nDCG@10 (ideal lấy từ catalog) và P@10 (tỉ lệ sp điểm>=min-ok).

Schema intent (SmartSearch/test_data/judge/query_intents_nsg.json, key = query normalize):
  {"kind": "exact|brand|typo|concept|foreign",
   "interpretation": "AI hiểu query là gì",
   "type": [["sữa tươi"]],                 # loại sp: AND giữa nhóm, OR trong nhóm (bản cũ gọi là "core")
   "constraints": [{"name": "brand", "terms": ["vinamilk"]}],   # thiếu -> điểm 4 thay vì 5
   "accept": ["dưa lưới", "dưa lê"],        # tùy chọn: sp thay thế cùng họ khách chấp nhận -> điểm 3
   "cats": ["THỰC PHẨM TƯƠI SỐNG"],         # tùy chọn: thuộc ngành hàng này cũng tính đúng loại (điểm 3)
   "exclude": ["nước hoa hồng"],           # tùy chọn: tên chứa từ này -> 0 (trùng chữ)
   "require_cats": ["Trái Cây"],           # tùy chọn: đúng loại phải thuộc ngành hàng này
   "related_cats": ["Rau Củ"]}             # tùy chọn: thêm ngành hàng tính điểm 1

Usage:
  # query chưa có intent (agent viết intent)
  python scripts/automation/judge_search_results.py --actual <Actual.json> --missing
  # chấm luật + xuất hàng đợi các cặp cần AI chấm (judge_queue.json trong thư mục run)
  python scripts/automation/judge_search_results.py --actual <Actual.json> --label part1vi
  # nạp điểm AI (list [{key, score, reason_vi}]) vào cache rồi chấm lại
  python scripts/automation/judge_search_results.py --apply-ai <ai_scores.json>
"""
import argparse
import html
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUDGE_DIR = ROOT / "SmartSearch" / "test_data" / "judge"
INTENTS_PATH = JUDGE_DIR / "query_intents_nsg.json"
AI_SCORES_PATH = JUDGE_DIR / "ai_scores_nsg_v5.json"   # thang 0-5 (bản thang 0-3 cũ: ai_scores_nsg.json)
SYNONYMS_PATH = JUDGE_DIR / "synonyms_nsg.json"
SCORES = (0, 1, 2, 3, 4, 5)
CATALOG_PATH = ROOT / "SmartSearch" / "full_store_catalog" / "nsg.json"
ASIS_DIR = ROOT / "SmartSearch" / "test_data" / "json" / "actual"

# Kiểu bỏ dấu cũ/mới ("hoà" vs "hòa", "thuỷ" vs "thủy") - đưa về một dạng,
# không thì "Hòa Bình" trong tên sp sẽ không khớp intent viết "hoà".
_TONE_PAIRS = {
    "òa": "oà", "óa": "oá", "ỏa": "oả", "õa": "oã", "ọa": "oạ",
    "òe": "oè", "óe": "oé", "ỏe": "oẻ", "õe": "oẽ", "ọe": "oẹ",
    "ùy": "uỳ", "úy": "uý", "ủy": "uỷ", "ũy": "uỹ", "ụy": "uỵ",
}
_TONE_RE = re.compile("|".join(_TONE_PAIRS))
# từ quá chung, trùng nhau không chứng minh được gì -> không đưa cặp vào hàng đợi AI vì nó
_STOP = {"trái", "quả", "củ", "rau", "đồ", "cho", "và", "các", "loại", "hộp", "gói", "chai", "lon",
         "túi", "bộ", "set", "size", "màu", "giao", "mẫu", "ngẫu", "nhiên", "cái", "ea", "kg", "g",
         "ml", "l", "the", "of", "a"}


def norm_text(s):
    s = unicodedata.normalize("NFC", str(s or "")).lower()
    s = s.replace("’", "'").replace("‘", "'")
    s = _TONE_RE.sub(lambda m: _TONE_PAIRS[m.group(0)], s)
    return " ".join(s.split())


def norm_query(q):
    # khớp đúng normalize_query() của compare_results.py (key cache As-Is)
    return " ".join(str(q or "").strip().lower().split())


def pair_key(query, sku):
    return f"{norm_query(query)}||{sku}"


_pattern_cache = {}


def term_regex(term):
    t = norm_text(term)
    if t not in _pattern_cache:
        # ranh giới từ Unicode: "nho" không ăn vào "nhoi", "mì" không ăn vào "mìn"
        _pattern_cache[t] = re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)")
    return _pattern_cache[t]


def find_any(ntext, terms):
    return next((t for t in terms if term_regex(t).search(ntext)), None)


def match_groups(ntext, groups):
    """ntext đã norm_text. ok khi MỌI nhóm có ít nhất một term xuất hiện."""
    matched = []
    for g in groups:
        hit = find_any(ntext, g)
        if hit is None:
            return False, matched
        matched.append(hit)
    return True, matched


def cat_match(cat, cats):
    c = norm_text(cat)
    return next((x for x in cats or [] if norm_text(x) in c), None)


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def intent_type(intent):
    return intent.get("type") or intent["core"]


def load_synonyms(path):
    if not path or not Path(path).exists():
        return []
    out = []
    for g in load_json(path).get("groups", []):
        out.append({"terms": [norm_text(t) for t in g["terms"]], "rel": g.get("rel", "equiv"),
                    "oneway": bool(g.get("oneway")), "risky": {norm_text(t) for t in g.get("risky") or []},
                    "not_in": [norm_text(t) for t in g.get("not_in") or []]})
    return out


def _inside(t, s, e, phrase):
    return any(m.start() <= s and e <= m.end() for m in term_regex(phrase).finditer(t))


def term_variants(term, syn):
    """Các biến thể của term khi thay MỘT cụm đồng nghĩa -> [(variant, rel, risky)].
    Cụm dài nhất thắng: 'bắp cải' không bị thay thành 'ngô cải'; từ nằm trong 'not_in' không thay
    ('quả' trong 'hiệu quả')."""
    t = norm_text(term)
    hits = []
    for g in syn:
        for m in (g["terms"][:1] if g["oneway"] else g["terms"]):
            for mo in term_regex(m).finditer(t):
                s, e = mo.span()
                if not any(_inside(t, s, e, ni) for ni in g["not_in"]):
                    hits.append((s, e, g, m))
    hits.sort(key=lambda h: h[0] - h[1])
    kept = []
    for h in hits:
        if not any(k[0] <= h[0] and h[1] <= k[1] and k[1] - k[0] > h[1] - h[0] for k in kept):
            kept.append(h)
    out = []
    for s, e, g, m in kept:
        for m2 in g["terms"]:
            if m2 != m:
                v = t[:s] + m2 + t[e:]
                out.append((v, g["rel"], v in g["risky"]))   # risky chỉ khi biến thể là từ trần đứng một mình
    return out


def expand_intent(intent, syn):
    """Mở rộng intent theo từ điển đồng nghĩa (không ghi lại file intent).
    equiv -> thêm vào cùng nhóm OR của type / constraint; substitute -> vào accept (điểm 3);
    từ trần risky -> chỉ thêm vào vocab hàng đợi AI."""
    it = dict(intent)
    added, vocab = [], set()
    if not syn:
        it["_syn_added"], it["_syn_vocab"] = added, vocab
        return it
    groups = intent_type(intent)
    accept = [norm_text(a) for a in intent.get("accept") or []]

    def grow(terms, label_sub=True):
        out = [norm_text(x) for x in terms]
        for t in terms:
            for v, rel, risky in term_variants(t, syn):
                if risky or (rel == "substitute" and (not label_sub or len(groups) > 1)):
                    vocab.add(v)
                elif rel == "equiv":
                    if v not in out:
                        out.append(v)
                        added.append(f"{t} = {v}")
                elif v not in accept:
                    accept.append(v)
                    added.append(f"{t} ≈ {v}")
        return out

    it["type"] = [grow(g) for g in groups]
    it.pop("core", None)
    it["constraints"] = [dict(c, terms=grow(c["terms"], label_sub=False)) for c in intent.get("constraints") or []]
    it["accept"] = grow(accept, label_sub=False) if accept else accept
    it["_syn_added"], it["_syn_vocab"] = added, vocab
    return it


def rule_score(ntext, cat, intent, type_cats):
    """Trả (score, reason_vi, matched). cat = ngành hàng catalog (None nếu sku ngoài catalog)."""
    groups = intent_type(intent)
    ok, matched = match_groups(ntext, groups)
    via_cat = None
    if not ok and intent.get("cats"):
        via_cat = cat_match(cat, intent["cats"])
        ok = via_cat is not None
    if ok and intent.get("exclude"):
        bad = find_any(ntext, intent["exclude"])
        if bad:
            return 0, f"Trùng chữ nhưng là '{bad}', không phải sp cần tìm", [bad]
    # sku không có trong catalog thì bỏ qua điều kiện ngành hàng, không phạt oan
    if ok and intent.get("require_cats") and cat is not None and not cat_match(cat, intent["require_cats"]):
        return 0, f"Trùng chữ '{', '.join(matched)}' nhưng sai ngành hàng ({cat})", matched
    if ok:
        failed = [c["name"] for c in intent.get("constraints") or [] if not find_any(ntext, c["terms"])]
        if via_cat:
            return 3, f"Thuộc ngành hàng '{via_cat}', tên không nêu rõ loại sp", [f"[ngành] {via_cat}"]
        if failed:
            return 4, f"Đúng loại ({', '.join(matched)}) nhưng không thỏa: {', '.join(failed)}", matched
        return 5, f"Đúng loại ({', '.join(matched)}) và thỏa mọi ràng buộc", matched
    alt = find_any(ntext, intent.get("accept") or [])
    if alt:
        return 3, f"Sp thay thế chấp nhận được ({alt})", [alt]
    if cat and (cat in type_cats or cat_match(cat, intent.get("related_cats"))):
        return 2, f"Cùng ngành hàng ({cat}) nhưng sai loại sp", []
    return 0, "Không liên quan", []


def strip_accents(s):
    s = unicodedata.normalize("NFD", s.replace("đ", "d"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def tokens(s):
    ws = {w for w in re.findall(r"\w+", norm_text(s)) if len(w) >= 2 and w not in _STOP}
    # thêm bản bỏ dấu: query "chay" phải bắt được "Chày"/"Chảy" để AI xét nghĩa khác của query thiếu dấu
    return ws | {strip_accents(w) for w in ws}


def needs_ai(query, intent, name, rs):
    """Cặp luật không chắc -> AI chấm lại."""
    if rs >= 4:
        return False
    if intent.get("kind") in ("concept", "foreign"):
        return True   # luật theo danh sách từ yếu với query khái niệm / ngoại ngữ
    vocab = tokens(query) | {w for g in intent_type(intent) for t in g for w in tokens(t)}
    vocab |= {w for t in intent.get("_syn_vocab") or () for w in tokens(t)}   # từ đồng nghĩa risky
    return bool(tokens(name) & vocab)   # có trùng từ -> có thể là trùng chữ, cũng có thể luật thiếu đồng nghĩa


def dcg(scores):
    return sum((2 ** s - 1) / math.log2(i + 2) for i, s in enumerate(scores))


def judge_side(items, query, intent, k_eff, ideal, sku_cat, type_cats, ai_scores, queue, min_ok=3, depth=0):
    rows = []
    for it in (items[:depth] if depth else items):
        sku = str(it.get("sku"))
        name = it.get("name") or ""
        cat = sku_cat.get(sku)
        rs, reason, _ = rule_score(norm_text(f"{name} {it.get('brand') or ''}"), cat, intent, type_cats)
        key = pair_key(query, sku)
        ai = ai_scores.get(key)
        row = {"rank": it.get("rank"), "sku": sku, "name": name, "cat": cat,
               "rule_score": rs, "score": rs, "reason": reason, "source": "luật"}
        if ai is not None:
            row.update(score=ai["score"], reason=ai.get("reason_vi", ""), source="AI")
        elif needs_ai(query, intent, name, rs):
            row["pending_ai"] = True
            queue.setdefault(key, {"key": key, "query": query, "interpretation": intent.get("interpretation"),
                                   "type": intent_type(intent), "constraints": intent.get("constraints") or [],
                                   "name": name, "brand": it.get("brand"), "category": cat,
                                   "rule_score": rs, "rule_reason": reason})
        rows.append(row)
    scores = [r["score"] for r in rows]
    bad_in_k = [r for r in rows[:k_eff] if r["score"] < min_ok]
    if not rows:
        verdict, reason = "FAILED", "0 kết quả"
    elif bad_in_k:
        verdict = "FAILED"
        n0 = sum(1 for r in bad_in_k if r["score"] == 0)
        reason = (f"top-{k_eff}: {n0} sp không liên quan (0), {len(bad_in_k) - n0} sp sai loại / không chấp nhận được (1-{min_ok - 1})"
                  f" - đầu tiên #{bad_in_k[0]['rank']}")
    elif ideal and ideal[0] == 5 and not any(r["score"] == 5 for r in rows[:k_eff]):
        verdict = "FAILED"
        reason = f"mart có {ideal.count(5)} sp đúng hoàn toàn nhưng top-{k_eff} không có sp nào"
    else:
        verdict, reason = "PASSED", f"top-{min(k_eff, len(rows))} đều điểm >= {min_ok}"
    return {
        "verdict": verdict, "reason": reason, "total": len(items),
        "ndcg10": None,   # tính ở main() khi đã có cả 2 bên
        "p10": round(sum(s >= min_ok for s in scores[:10]) / min(10, len(scores)), 2) if scores else 0.0,
        "dist10": dict(Counter(scores[:10])),
        "pending_ai": sum(1 for r in rows[:10] if r.get("pending_ai")),
        "items": rows,
    }


def apply_ai(path, ai_path):
    new = load_json(path)
    doc = load_json(ai_path) if Path(ai_path).exists() else {"scores": {}}
    n = 0
    for e in new:
        if e.get("score") not in SCORES or "||" not in e.get("key", ""):
            sys.exit(f"Dòng sai định dạng: {e}")
        doc["scores"][e["key"]] = {"score": e["score"], "reason_vi": e.get("reason_vi", ""),
                                   "name": e.get("name"), "by": e.get("by", "claude"),
                                   "at": datetime.now().isoformat(timespec="seconds")}
        n += 1
    Path(ai_path).parent.mkdir(parents=True, exist_ok=True)
    Path(ai_path).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Đã nạp {n} điểm AI -> {ai_path} (tổng {len(doc['scores'])})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--actual", help="file *_ActualData_*.json (kết quả Dev)")
    ap.add_argument("--intents", default=str(INTENTS_PATH))
    ap.add_argument("--ai-scores", default=str(AI_SCORES_PATH))
    ap.add_argument("--synonyms", default=str(SYNONYMS_PATH), help="từ điển đồng nghĩa; '' = không dùng")
    ap.add_argument("--apply-ai", help="file JSON [{key, score, reason_vi}] do AI chấm -> nạp vào cache")
    ap.add_argument("--asis-cache", default=None, help="mặc định theo lang của file Actual")
    ap.add_argument("--topk", type=int, default=10, help="số sp đầu được xét để kết luận PASSED/FAILED (mặc định 10, 0 = toàn bộ)")
    ap.add_argument("--depth", type=int, default=0, help="số sp đầu được chấm điểm và đưa vào hàng đợi AI (mặc định 0 = toàn bộ)")
    ap.add_argument("--min-ok", type=int, default=3, choices=SCORES[1:],
                    help="điểm tối thiểu mỗi sp trong top-K để keyword PASSED (mặc định 3 = chấp nhận được)")
    ap.add_argument("--label", default=None)
    ap.add_argument("--missing", action="store_true", help="chỉ in các query chưa có intent rồi thoát")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if args.apply_ai:
        apply_ai(args.apply_ai, args.ai_scores)
        if not args.actual:
            return
    if not args.actual:
        sys.exit("cần --actual")

    actual = load_json(args.actual)
    lang = actual.get("lang", "vi")
    intents = (load_json(args.intents) if Path(args.intents).exists() else {}).get("intents", {})
    ai_scores = (load_json(args.ai_scores) if Path(args.ai_scores).exists() else {}).get("scores", {})
    syn = load_synonyms(args.synonyms)

    scenarios = actual["scenarios"]
    missing = [s for s in scenarios if norm_query(s["query"]) not in intents]
    if args.missing:
        out = [{"test_id": s["test_id"], "query": s["query"], "qa_note": (s.get("note") or "")[:200]}
               for s in missing]
        print(json.dumps(out, ensure_ascii=False, indent=1))
        print(f"\n{len(missing)}/{len(scenarios)} query chưa có intent -> agent cần ghi vào {args.intents}",
              file=sys.stderr)
        return
    if missing:
        sys.exit(f"{len(missing)} query chưa có intent (vd: {[s['query'] for s in missing[:5]]}). "
                 f"Chạy --missing rồi cho agent search-judge ghi intent trước.")

    asis_path = Path(args.asis_cache) if args.asis_cache else (
        ASIS_DIR / ("AsIs_NSG_cache.json" if lang in ("vi", "") else f"AsIs_NSG_cache_{lang}.json"))
    asis = load_json(asis_path)["entries"] if asis_path.exists() else {}
    catalog = [p for p in (load_json(CATALOG_PATH) if CATALOG_PATH.exists() else [])
               if p.get("visibility_search", True) and p.get("status", 1) == 1]
    for p in catalog:
        p["_n"] = norm_text(f"{p.get('name', '')} {p.get('brand') or ''}")
    sku_cat = {str(p.get("sku")): p.get("cat") or "" for p in catalog}

    results, queue = [], {}
    for s in scenarios:
        intent = expand_intent(intents[norm_query(s["query"])], syn)
        # ngành hàng của các sp catalog đúng loại -> sp khác cùng ngành hàng = điểm 1
        type_hits = [p for p in catalog if match_groups(p["_n"], intent_type(intent))[0]]
        cc = Counter(p.get("cat") or "" for p in type_hits)
        type_cats = {c for c, n in cc.items() if c and n >= max(2, 0.1 * len(type_hits))}
        # điểm theo sku: catalog (luật) rồi ghi đè bằng điểm thấy trong kết quả Dev/Prod (có cả điểm AI)
        sku_score = {}
        for p in catalog:
            sc = rule_score(p["_n"], p.get("cat") or "", intent, type_cats)[0]
            if sc:
                sku_score[str(p.get("sku"))] = sc
        cat_scores = sorted(sku_score.values(), reverse=True)
        n_ok = sum(1 for x in cat_scores if x >= args.min_ok)
        topk = args.topk or len(cat_scores) + 10 ** 6   # 0 = xét toàn bộ kết quả
        k_eff = min(topk, n_ok) if n_ok else topk
        common = (s["query"], intent, k_eff, cat_scores, sku_cat, type_cats, ai_scores, queue, args.min_ok, args.depth)
        dev = judge_side(s.get("search_results") or [], *common)
        a = asis.get(norm_query(s["query"]))
        prod = judge_side(a.get("search_results") or [], *common) if a is not None else None
        # nDCG: ideal = top-10 trên tập sp đã biết (catalog + kết quả 2 bên), mỗi sku tính 1 lần,
        # để sp ngoài snapshot catalog không làm nDCG > 1
        for side in (dev, prod):
            for it in (side or {}).get("items", []):
                sku_score[it["sku"]] = it["score"]
        idcg = dcg(sorted(sku_score.values(), reverse=True)[:10])
        for side in (dev, prod):
            if side:
                side["ndcg10"] = round(dcg([it["score"] for it in side["items"][:10]]) / idcg, 3) if idcg else None
        if n_ok == 0:
            for side in (dev, prod):
                if side:
                    side["verdict"], side["reason"] = "N/A", "catalog mart không có sp nào đúng loại"
        results.append({
            "test_id": s["test_id"], "query": s["query"], "qa_note": s.get("note"),
            "kind": intent.get("kind"), "interpretation": intent.get("interpretation"),
            "type": intent_type(intent), "constraints": intent.get("constraints") or [],
            "synonyms": intent["_syn_added"],
            "catalog_ok": n_ok, "k_eff": k_eff, "dev": dev, "prod": prod,
        })

    label = args.label or actual.get("batchRange") or "run"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else JUDGE_DIR / f"run_{label}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    def cnt(side, v):
        return sum(1 for r in results if r[side] and r[side]["verdict"] == v)

    def avg(side, f):
        xs = [r[side][f] for r in results if r[side] and r[side][f] is not None and r[side]["verdict"] != "N/A"]
        return round(sum(xs) / len(xs), 3) if xs else None

    summary = {
        "generated": datetime.now().isoformat(timespec="seconds"), "label": label,
        "actual_file": str(Path(args.actual)), "asis_cache": str(asis_path), "topk": args.topk or "all", "depth": args.depth or "all",
        "min_ok": args.min_ok,
        "synonyms_file": args.synonyms or None, "synonym_groups": len(syn),
        "intents_expanded": sum(1 for r in results if r["synonyms"]),
        "total": len(results),
        "dev": {v: cnt("dev", v) for v in ("PASSED", "FAILED", "N/A")},
        "prod": {v: cnt("prod", v) for v in ("PASSED", "FAILED", "N/A")},
        "dev_ndcg10": avg("dev", "ndcg10"), "prod_ndcg10": avg("prod", "ndcg10"),
        "dev_p10": avg("dev", "p10"), "prod_p10": avg("prod", "p10"),
        "prod_missing": sum(1 for r in results if r["prod"] is None),
        "dev_fail_prod_pass": sum(1 for r in results if r["dev"]["verdict"] == "FAILED"
                                  and r["prod"] and r["prod"]["verdict"] == "PASSED"),
        "ai_scored_pairs": sum(1 for r in results for sd in ("dev", "prod") if r[sd]
                               for it in r[sd]["items"] if it["source"] == "AI"),
        "pending_ai": len(queue),
    }
    failed = [{"test_id": r["test_id"], "query": r["query"], "kind": r["kind"],
               "interpretation": r["interpretation"], "dev_reason": r["dev"]["reason"],
               "dev_ndcg10": r["dev"]["ndcg10"],
               "prod_verdict": r["prod"]["verdict"] if r["prod"] else None,
               "prod_ndcg10": r["prod"]["ndcg10"] if r["prod"] else None}
              for r in results if r["dev"]["verdict"] == "FAILED"]
    (out_dir / "judge_results.json").write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "failed_cases.json").write_text(json.dumps(failed, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "judge_queue.json").write_text(json.dumps(list(queue.values()), ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    (out_dir / "judge_report.html").write_text(render_html(summary, results), encoding="utf-8")

    print(f"Dev : {summary['dev']}  nDCG@10={summary['dev_ndcg10']}  P@10={summary['dev_p10']}")
    print(f"Prod: {summary['prod']}  nDCG@10={summary['prod_ndcg10']}  P@10={summary['prod_p10']}"
          f"  (không có cache: {summary['prod_missing']})")
    print(f"Dev FAILED nhưng Prod PASSED: {summary['dev_fail_prod_pass']}")
    print(f"Cặp đã có điểm AI: {summary['ai_scored_pairs']} | cặp chờ AI chấm: {len(queue)}"
          f" -> {out_dir / 'judge_queue.json'}")
    print(f"Report: {out_dir / 'judge_report.html'}")


SCORE_CLS = {s: f"s{s}" for s in SCORES}


def render_html(summary, results):
    e = html.escape

    def items_table(side):
        if side is None:
            return "<div class='muted'>Không có dữ liệu Prod trong cache</div>"
        if not side["items"]:
            return "<div class='bad'>0 kết quả</div>"
        trs = "".join(
            f"<tr class='{SCORE_CLS[it['score']]}'><td>{it['rank']}</td><td><b>{it['score']}</b>"
            f"{'<sup>?</sup>' if it.get('pending_ai') else ''}</td><td>{e(str(it['name']))}</td>"
            f"<td>{e(it['reason'])} <span class='src'>{it['source']}</span></td></tr>" for it in side["items"])
        return (f"<table class='items'><tr><th>#</th><th>Điểm</th><th>Tên sp</th><th>Lý do</th></tr>{trs}</table>")

    def badge(side):
        if side is None:
            return "<span class='b na'>—</span>"
        cls = {"PASSED": "pass", "FAILED": "fail"}.get(side["verdict"], "na")
        nd = "" if side["ndcg10"] is None else f"<div class='muted'>nDCG {side['ndcg10']:.2f} · P@10 {side['p10']:.0%}</div>"
        return f"<span class='b {cls}'>{side['verdict']}</span>{nd}<div class='muted'>{e(side['reason'])}</div>"

    def dots(side):
        if not side:
            return ""
        return "".join(f"<i class='d {SCORE_CLS[it['score']]}'></i>" for it in side["items"][:10])

    rows = []
    for r in results:
        d, p = r["dev"], r["prod"]
        flags = ["devfail" if d["verdict"] == "FAILED" else ""]
        if d["verdict"] == "FAILED" and p and p["verdict"] == "PASSED":
            flags.append("worse")
        if p and d["ndcg10"] is not None and p["ndcg10"] is not None and d["ndcg10"] < p["ndcg10"] - 0.1:
            flags.append("ndcgworse")
        spec = "loại: " + " AND ".join("(" + " | ".join(g) + ")" for g in r["type"])
        if r.get("synonyms"):
            spec += " · đồng nghĩa: " + "; ".join(r["synonyms"])
        if r["constraints"]:
            spec += " · ràng buộc: " + "; ".join(f"{c['name']}=({' | '.join(c['terms'])})" for c in r["constraints"])
        rows.append(f"""
<tr class="row {' '.join(flags)}" onclick="this.nextElementSibling.classList.toggle('open')">
 <td>{e(r['test_id'])}</td><td><b>{e(r['query'])}</b></td><td>{e(r['kind'] or '')}</td>
 <td>{e(r['interpretation'] or '')}<div class='muted'>{e(spec)}</div></td>
 <td>{badge(d)}<div>{dots(d)}</div></td><td>{badge(p)}<div>{dots(p)}</div></td>
</tr>
<tr class="detail"><td colspan="6">
 <div class='muted'>QA note: {e(r['qa_note'] or '')}</div>
 <div class="two"><div><h4>Dev ({len(d["items"])} sp)</h4>{items_table(d)}</div><div><h4>Prod ({len(p["items"]) if p else 0} sp)</h4>{items_table(p)}</div></div>
</td></tr>""")
    s = summary

    def f3(x):
        return "—" if x is None else f"{x:.3f}"
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Search Judge {e(s['label'])}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:16px;background:#fafafa;color:#222;font-size:14px}}
table{{border-collapse:collapse;width:100%}} th,td{{border-bottom:1px solid #ddd;padding:6px;text-align:left;vertical-align:top}}
tr.row{{cursor:pointer}} tr.row:hover{{background:#f0f4ff}} tr.row.devfail td:nth-child(2){{color:#c62828}}
tr.detail{{display:none}} tr.detail.open{{display:table-row}}
.items tr.s0 td{{background:#ffcdd2}} .items tr.s1 td{{background:#ffe0b2}} .items tr.s2 td{{background:#fff3c4}} .items tr.s3 td{{background:#f1f8e9}} .items tr.s4 td{{background:#e3f2e5}} .items tr.s5 td{{background:#c8e6c9}}
i.d{{display:inline-block;width:10px;height:10px;border-radius:2px;margin:3px 2px 0 0}}
i.s0{{background:#e53935}} i.s1{{background:#fb8c00}} i.s2{{background:#fdd835}} i.s3{{background:#aed581}} i.s4{{background:#66bb6a}} i.s5{{background:#2e7d32}}
.b{{padding:2px 8px;border-radius:10px;font-weight:600;font-size:12px}} .pass{{background:#c8e6c9;color:#1b5e20}}
.fail{{background:#ef9a9a;color:#7f0000}} .na{{background:#e0e0e0;color:#555}}
.muted{{color:#777;font-size:12px}} .bad{{color:#c62828;font-weight:600}} .src{{color:#999;font-size:11px}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:12px}} @media(max-width:800px){{.two{{grid-template-columns:1fr}}}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}} .card{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:10px 14px}}
.card b{{font-size:20px;display:block}} button{{margin-right:6px;padding:4px 10px}}
</style></head><body>
<h2>Search Judge — {e(s['label'])}</h2>
<div class="muted">Sinh lúc {e(s['generated'])} · Actual: {e(s['actual_file'])}<br>
Thang điểm: <i class="d s5"></i>5 đúng loại + đủ ràng buộc · <i class="d s4"></i>4 đúng loại, lệch ràng buộc ·
<i class="d s3"></i>3 thay thế chấp nhận được · <i class="d s2"></i>2 liên quan, sai loại ·
<i class="d s1"></i>1 cùng ngành hàng rộng · <i class="d s0"></i>0 không liên quan / trùng chữ.
FAILED = có sp điểm &lt; {s['min_ok']} trong top-{s['topk']} (catalog có ít hơn thì top-N). Nguồn điểm: luật hoặc AI. <sup>?</sup> = chờ AI chấm.</div>
<div class="cards">
 <div class="card">Tổng<b>{s['total']}</b></div>
 <div class="card">Dev PASSED / FAILED / N/A<b>{s['dev']['PASSED']} / <span style="color:#c62828">{s['dev']['FAILED']}</span> / {s['dev']['N/A']}</b></div>
 <div class="card">Prod PASSED / FAILED<b>{s['prod']['PASSED']} / {s['prod']['FAILED']}</b></div>
 <div class="card">nDCG@10 Dev / Prod<b>{f3(s['dev_ndcg10'])} / {f3(s['prod_ndcg10'])}</b></div>
 <div class="card">P@10 Dev / Prod<b>{f3(s['dev_p10'])} / {f3(s['prod_p10'])}</b></div>
 <div class="card">Dev fail – Prod pass<b style="color:#c62828">{s['dev_fail_prod_pass']}</b></div>
 <div class="card">Cặp AI chấm / chờ<b>{s['ai_scored_pairs']} / {s['pending_ai']}</b></div>
</div>
<div><button onclick="f('all')">Tất cả</button><button onclick="f('devfail')">Dev FAILED</button>
<button onclick="f('worse')">Dev fail – Prod pass</button><button onclick="f('ndcgworse')">nDCG Dev kém Prod &gt;0.1</button>
<span class="muted">Bấm vào dòng để xem toàn bộ sp và lý do từng sp</span></div>
<table><tr><th>ID</th><th>Query</th><th>Loại</th><th>AI hiểu là</th><th>Dev</th><th>Prod</th></tr>
{''.join(rows)}</table>
<script>
function f(c){{document.querySelectorAll('tr.row').forEach(r=>{{const show=c==='all'||r.classList.contains(c);
r.style.display=show?'':'none';r.nextElementSibling.classList.remove('open');}});}}
</script></body></html>"""


if __name__ == "__main__":
    main()
