# -*- coding: utf-8 -*-
"""De xuat phan quyet cho lan chay moi, hoc tu cach QA da danh gia lan truoc.

    python scripts/suggest_verdicts.py --learn-from 2026-09-22 2026-09-24 \
        --prev-results results/_archive/excel_top40_before_rerun_20260924 results/_archive/excel_top40_run20260924
    python scripts/suggest_verdicts.py ... --write      # ghi file export de --apply

Moi san pham trong top-K duoc coi la LIEN QUAN neu:
  - ten chua keyword (hoac tu tuong duong voi keyword KR/EN), hoac
  - QA da chap nhan no o lan truoc (nam trong top-20 cua co che QA chon dat), hoac
  - nganh cap 4 cua no la nganh dich cua keyword (nganh chiem da so trong hai nguon tren).
Tu do tinh ty le lien quan o top-1/5/10/20/40 cho moi co che, roi hoc nguong
(theo tung co che) sao cho khop nhat voi lua chon lan truoc cua QA.

Hieu nang: QA chon co che NHANH NHAT trong so cac co che dat (123/127 lan 22/09).
"""
import argparse, collections, glob, json, os, re, sys, unicodedata
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        _s.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, 'results', 'excel_top40')
MANIFEST = os.path.join(ROOT, 'images', 'excel_keywords', 'manifest.json')
STATE = os.path.join(ROOT, 'dashboard', 'verdict_state.json')
TREE = os.path.join(ROOT, 'cache', 'category_tree.json')
# Nhan cua MOI co che tung chay (scripts/lib/modes.json); co che cua lan chay moi
# = MODES trong config.mjs (2026-09-29: khong khai cung nua - lan 28/09 doi bo co che).
_INFO = {x['mode']: x for x in json.load(open(os.path.join(ROOT, 'scripts', 'lib', 'modes.json'), encoding='utf-8'))['modes']}
LABEL = {m: x['label'] for m, x in _INFO.items()}
KNOWN = set(_INFO)
RUN_MODES = re.findall(r"'([a-z_]+)'", re.search(r"export const MODES = \[([^\]]*)\]",
                       open(os.path.join(ROOT, 'scripts', 'config.mjs'), encoding='utf-8').read()).group(1))
# Co che moi chua co phan quyet nao de hoc -> muon mo hinh cua co che gan no nhat,
# va LUON danh dau "can xem ky" (khong phai du doan da duoc kiem chung).
BORROW = {'vector_titan_multi_caption_type': 'vector_titan_multi'}

# Keyword khong phai tieng Viet -> cac cum tieng Viet tuong duong trong ten san pham
ALIASES = {
    '우유': ['sữa tươi', 'sữa'], '코코넛': ['dừa'], '참치': ['cá ngừ'], '사과': ['táo'],
    '과자': ['bánh', 'snack'], '세제': ['nước giặt', 'bột giặt', 'nước rửa chén', 'tẩy rửa'],
    '젤리': ['thạch', 'kẹo dẻo', 'jelly'], '만두': ['há cảo', 'mandu', 'bánh xếp', 'sủi cảo'],
    '두부': ['đậu hũ', 'đậu phụ', 'tàu hủ', 'tofu'], 'yogurt': ['sữa chua', 'yogurt'],
}
LEVEL = 4


def strip_accents(s):
    s = unicodedata.normalize('NFD', s.lower()).replace('đ', 'd')
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def load_runs(root):
    runs = {}
    for f in glob.glob(os.path.join(root, '*', '*.json')):
        d = json.load(open(f, encoding='utf-8'))
        runs.setdefault(d['image_id'], {})[d['mode_requested']] = d
    return runs


def terms_for(keyword):
    kw = keyword.strip().lower()
    return ALIASES.get(kw) or ALIASES.get(keyword.strip()) or [kw]


def name_hit(name, terms):
    n = ' ' + strip_accents(name) + ' '
    for t in terms:
        t = strip_accents(t)
        # khop theo tu (khong de "ca" khop "cam"); cum nhieu tu khop nguyen cum
        if re.search(r'(?<![a-z0-9])' + re.escape(t) + r'(?![a-z0-9])', n):
            return True
    return False


class Tree:
    def __init__(self):
        t = json.load(open(TREE, encoding='utf-8'))
        self.paths = t['sku_paths']

    def cat(self, sku, level=LEVEL):
        p = self.paths.get(sku)
        if not p:
            return None
        return p[min(level, len(p)) - 1]


def top(d, k=40):
    return d['top'][:k] if d and d.get('ok') else []


def reference(image_id, keyword, catalog_hits, accepted_skus, tree):
    """Nganh dich = cac nganh cap 4 chiem >=15% trong (sp khop ten + sp QA da chap nhan)."""
    cats = collections.Counter()
    for sku in list(accepted_skus) + list(catalog_hits):
        c = tree.cat(sku)
        if c:
            cats[c] += 1
    total = sum(cats.values())
    return {c for c, n in cats.items() if total and n / total >= 0.15}


def features(d, terms, accepted, target_cats, tree):
    items = top(d)
    rel, strict = [], []
    for it in items:
        c = tree.cat(it['sku'])
        hit = name_hit(it['name'], terms) or (c in target_cats)
        # CHAT (de liet ke "sp la" trong ghi chu): QA chon co che "dat" KHONG co nghia la duyet
        # tung sp trong top-20 cua no (22/09 Titan dat ma QA van ghi "dau hao xen vao").
        strict.append(bool(hit or (c is None and it['sku'] in accepted)))
        # LONG (de cham dat/khong dat): tinh ca sp QA da chap nhan lan truoc. QA cho "dat" du
        # co vai sp la, nen thuoc do long khop voi lua chon cua QA hon (86.7% vs 80.6% khi dung CHAT).
        rel.append(bool(hit or it['sku'] in accepted))
    # Chia cho so ket qua THAT SU tra ve (toi da k): tu 24/09 vector co nguong tuong dong,
    # nhieu anh chi tra 3-6 KQ — tra it ma dung het la tot, khong duoc chia cho 10/20 co dinh.
    p = lambda xs, k: (sum(xs[:k]) / min(k, len(items))) if items else 0.0
    return {'top1': 1.0 if rel[:1] == [True] else 0.0, 'p5': p(rel, 5), 'p10': p(rel, 10), 'p20': p(rel, 20),
            'p40': p(rel, 40), 'n': len(items), 'rel': rel,
            'strict': strict, 'p10_strict': p(strict, 10), 'p40_strict': p(strict, 40)}


def catalog_name_hits(runs_list, terms):
    """SKU khop ten keyword, gom tu moi ket qua da thay (khong can doc ca catalog)."""
    hits = set()
    for runs in runs_list:
        for d in runs.values():
            for it in top(d):
                if name_hit(it['name'], terms):
                    hits.add(it['sku'])
    return hits


def accepted_from(verdict, runs_prev, exclude=None, k=20):
    acc = set()
    for m in verdict.get('verdict', []):
        if m in KNOWN and m != exclude:
            acc |= {it['sku'] for it in top(runs_prev.get(m), k)}
    return acc


SCORE = lambda f, w: w[0] * f['top1'] + w[1] * f['p5'] + w[2] * f['p10'] + w[3] * f['p20'] + w[4] * f['p40']
WEIGHTS = [(0, 1, 0, 0, 0), (0, 0, 1, 0, 0), (0, 0, 0, 1, 0), (0, 0, 0, 0, 1),
           (.2, .3, .3, .2, 0), (.1, .2, .3, .2, .2), (0, .3, .4, .3, 0), (.3, .4, .3, 0, 0)]


def fit(samples):
    """samples: [(mode, feat, label)] -> {mode: (weights, threshold)} theo do chinh xac cao nhat."""
    model = {}
    for m in sorted({mm for mm, _, _ in samples}):
        xs = [(f, y) for mm, f, y in samples if mm == m]
        best = None
        for w in WEIGHTS:
            scores = sorted({round(SCORE(f, w), 3) for f, _ in xs} | {0.0, 1.01})
            for th in scores:
                acc = sum((SCORE(f, w) >= th) == y for f, y in xs) / len(xs)
                if not best or acc > best[0] + 1e-9:
                    best = (acc, w, th)
        model[m] = {'weights': best[1], 'threshold': best[2], 'train_acc': round(best[0], 3)}
    return model


def model_for(model, m):
    return model.get(m) or model[BORROW[m]]


def predict(model, m, f):
    mm = model_for(model, m)
    return SCORE(f, mm['weights']) >= mm['threshold']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--learn-from', nargs='+', default=['2026-09-22'],
                    help='cac vong QA da danh gia xong (hoc tu tat ca); vong CUOI la moc so sanh')
    ap.add_argument('--prev-results', nargs='+', required=True,
                    help='thu muc ket qua tho tuong ung tung vong --learn-from, dung thu tu')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--out', default=None)
    ap.add_argument('--reviewed', help='file export QA da duyet tay o lan chay moi')
    ap.add_argument('--redo-from', type=int, default=10**9, help='STT tu day tro di: lam lai goi y (truoc do giu ban QA)')
    ap.add_argument('--keep', nargs='*', default=[], help='image_id QA da sua tay o doan lam lai -> van giu')
    args = ap.parse_args()

    man = {r['image_id']: r for r in json.load(open(MANIFEST, encoding='utf-8'))}
    tree = Tree()
    if len(args.learn_from) != len(args.prev_results):
        sys.exit('--learn-from va --prev-results phai cung so luong, cung thu tu')
    rounds = json.load(open(STATE, encoding='utf-8'))['rounds']
    learn = [(r, rounds[r]['verdicts'], load_runs(d)) for r, d in zip(args.learn_from, args.prev_results)]
    for r, _, pr in learn:  # chong nham thu muc: ket qua tho phai dung ngay cua vong
        got = {(d.get('round') or d['ran_at'][:10]) for b in pr.values() for d in b.values()}
        if got != {r}:
            sys.exit('Thu muc ket qua cho vong %s lai la lan chay %s' % (r, sorted(got)))
    # vong cuoi = moc so sanh + nguon "sp QA da chap nhan" khi de xuat
    last_round, verdicts, prev = learn[-1]
    cur = load_runs(RESULTS)
    rnd = max((d.get('round') or d['ran_at'][:10]) for b in cur.values() for d in b.values())
    MODES = [m for m in RUN_MODES if any(m in b for b in cur.values())]

    # ---- lua chon QA da duyet tay o lan chay MOI (file export), neu co ----
    reviewed, keep_ids = {}, set()
    if args.reviewed:
        rv = json.load(open(args.reviewed, encoding='utf-8'))
        keep_ids = {i for i in rv['verdicts'] if i in man and man[i]['stt'] < args.redo_from} | set(args.keep)
        reviewed = {i: {'verdict': rv['verdicts'].get(i, []), 'performance': rv['performance'].get(i, []),
                        'note': rv['notes'].get(i, '')} for i in keep_ids}

    # ---- hoc: (1) lan truoc: features tren KET QUA LAN TRUOC, nhan = lua chon cua QA;
    #          (2) cac anh QA vua duyet tay o lan moi: features tren ket qua moi ----
    # Nhom kiem tra cheo = image_id: cung 1 anh o 2 vong phai nam cung 1 phan, khong thi ro ri.
    samples = []  # (nhom anh, (mode, feat, label))
    for lr, lv, lprev in learn:
        for iid, v in lv.items():
            if iid not in lprev or iid not in man:
                continue
            terms = terms_for(man[iid]['keyword'])
            hits = catalog_name_hits([lprev[iid], cur.get(iid, {})], terms)
            for m in lprev[iid]:
                # bo chinh co che dang xet khoi tap "QA da chap nhan" -> tranh tu khop voi chinh no
                acc = accepted_from(v, lprev[iid], exclude=m)
                cats = reference(iid, man[iid]['keyword'], hits, acc, tree)
                f = features(lprev[iid].get(m), terms, acc, cats, tree)
                samples.append((iid, (m, f, m in v.get('verdict', []))))
    for iid, v in reviewed.items():
        if iid not in cur:
            continue
        terms = terms_for(man[iid]['keyword'])
        hits = catalog_name_hits([prev.get(iid, {}), cur[iid]], terms)
        acc = accepted_from(verdicts.get(iid, {}), prev.get(iid, {})) if iid in verdicts else set()
        cats = reference(iid, man[iid]['keyword'], hits, acc, tree)
        for m in MODES:
            f = features(cur[iid].get(m), terms, acc, cats, tree)
            samples.append((iid, (m, f, m in v['verdict'])))
    model = fit([x for _, x in samples])

    # kiem tra cheo 5 phan theo anh
    ids = sorted({g for g, _ in samples})
    correct = total = 0
    per_mode = collections.Counter()
    for fold in range(5):
        test = set(ids[fold::5])
        mdl = fit([x for g, x in samples if g not in test])
        for g, (m, f, y) in samples:
            if g in test and m in mdl:
                ok = predict(mdl, m, f) == y
                correct += ok; total += 1; per_mode[(m, ok)] += 1
    print('Mo hinh (hoc tren cac vong %s + %d anh QA duyet tay lan moi):' % (', '.join(args.learn_from), len(reviewed)))
    for m in model:
        cv = per_mode[(m, True)] / max(1, per_mode[(m, True)] + per_mode[(m, False)])
        model[m]['cv_acc'] = round(cv, 3)
        n = sum(1 for _, (mm, _, _) in samples if mm == m)
        print('  %-24s %3d mau  w=%s nguong=%.3f  khop-train=%.1f%%  khop-cheo=%.1f%%' % (
            LABEL.get(m, m), n, model[m]['weights'], model[m]['threshold'], 100 * model[m]['train_acc'], 100 * cv))
    for m in MODES:
        if m not in model:
            print('  %-24s CHUA CO du lieu hoc -> dung mo hinh %s, moi o deu danh dau can xem ky' % (LABEL.get(m, m), LABEL[BORROW[m]]))
    print('  Tong khop kiem tra cheo: %.1f%% (%d/%d o)' % (100 * correct / total, correct, total))

    # ---- de xuat cho lan chay moi ----
    out_v, out_p, out_n, changes = {}, {}, {}, collections.Counter()
    for iid in sorted(cur, key=lambda i: man.get(i, {}).get('excel_row', 1e9)):
        if iid not in man:
            continue
        if iid in reviewed:  # QA da duyet tay -> giu nguyen
            out_v[iid], out_n[iid] = reviewed[iid]['verdict'], reviewed[iid]['note']
            if reviewed[iid]['performance']:
                out_p[iid] = reviewed[iid]['performance']
            changes['QA da duyet (giu nguyen)'] += 1
            continue
        kw = man[iid]['keyword']
        terms = terms_for(kw)
        v_old = verdicts.get(iid, {})
        acc = accepted_from(v_old, prev.get(iid, {})) if v_old else set()
        hits = catalog_name_hits([prev.get(iid, {}), cur[iid]], terms)
        cats = reference(iid, kw, hits, acc, tree)
        passed, detail = [], []
        for m in MODES:
            d = cur[iid].get(m)
            f = features(d, terms, acc, cats, tree)
            ok = bool(d and d.get('ok')) and predict(model, m, f)
            if ok:
                passed.append(m)
            bad = [it['name'] for it, r in zip(top(d, 20), f['strict'][:20]) if not r]
            # sat nguong -> QA nen xem ky; NovaLite luon it chac (QA cham theo dung SP/brand)
            mm = model_for(model, m)
            unsure = abs(SCORE(f, mm['weights']) - mm['threshold']) < 0.1 or m == 'caption' or m not in model
            detail.append((m, f, ok, bad, unsure))
        verdict = passed or ['none']
        tk = {m: cur[iid][m]['took_ms'] for m in passed if cur[iid].get(m) and cur[iid][m].get('took_ms') is not None}
        perf = [min(tk, key=tk.get)] if tk else []
        # chi so tren co che co o CA 2 lan (lan 28/09 bo Titan -> khong tinh la "khac")
        common = set(MODES) & {m for m in (prev.get(iid) or {})}
        old_set = set(v_old.get('verdict', [])) & common or {'none'}
        verdict_cmp = set(verdict) & common or {'none'}
        changes['giong lan %s' % last_round if verdict_cmp == old_set else 'khac lan %s' % last_round] += 1
        # Ghi chu: diem lien quan + san pham la trong top-20 cua co che, theo giong ghi chu cua QA
        lines = ['[Claude gợi ý — cần QA duyệt]']
        for m, f, ok, bad, unsure in detail:
            changes['o sat nguong'] += unsure and m != 'caption' and m in model
            n10 = min(10, f['n'])
            why = (' (cần xem kỹ — cơ chế mới, dùng ngưỡng %s)' % LABEL[BORROW[m]]) if m not in model else ' (cần xem kỹ)'
            head = '%s %s%s: ' % (LABEL.get(m, m), 'đạt' if ok else 'không đạt', why if unsure else '')
            if f['n'] == 0:
                s = head + 'không trả kết quả'
            else:
                s = head + ('top10 đúng %d/10' % round(f['p10_strict'] * n10) if f['n'] >= 10
                            else 'chỉ trả %d KQ, đúng %d/%d' % (f['n'], round(f['p10_strict'] * n10), n10))
                if bad:
                    s += (' · sp lạ top20: ' if f['n'] >= 20 else ' · sp lạ: ') \
                        + ', '.join(shorten(b) for b in bad[:4]) + (' …' if len(bad) > 4 else '')
            lines.append('- ' + s)
        out_v[iid], out_n[iid] = verdict, '\n'.join(lines)
        if perf:
            out_p[iid] = perf
    print('\nDe xuat lan %s: %d anh · %s' % (rnd, len(out_v), dict(changes)))
    cnt = collections.Counter(m for v in out_v.values() for m in v)
    print('  So anh dat theo co che:', {LABEL.get(m, m): cnt[m] for m in MODES + ['none']})

    if args.write:
        out = args.out or os.path.join(ROOT, 'dashboard', 'image_search_verdicts_%s_claude_suggest.json' % rnd.replace('-', ''))
        # Giu ban cu: dashboard can no de nhan ra dong goi y cu con nam trong trinh duyet QA
        if os.path.exists(out):
            arch = os.path.join(ROOT, 'results', '_archive', 'suggest_versions')
            os.makedirs(arch, exist_ok=True)
            import shutil
            shutil.copy2(out, os.path.join(arch, 'suggest_%s.json' % datetime.fromtimestamp(os.path.getmtime(out)).strftime('%Y%m%d_%H%M%S')))
        json.dump({'kind': 'image_search_verdicts', 'report_id': 'excel_top40', 'round': rnd, 'store': 'nsg',
                   'exported_at': datetime.now().isoformat(timespec='seconds'), 'source': 'claude_suggest',
                   'model': model, 'borrowed': {m: BORROW[m] for m in MODES if m not in model},
                   'learned_from': args.learn_from, 'reviewed_ids': sorted(reviewed), 'verdicts': out_v, 'performance': out_p, 'notes': out_n},
                  open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print('Da ghi', out)


def shorten(name, n=5):
    w = name.split()
    return ' '.join(w[:n]) + ('…' if len(w) > n else '')


if __name__ == '__main__':
    main()
