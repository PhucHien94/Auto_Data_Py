# -*- coding: utf-8 -*-
"""Bo keyword hien tai phu duoc bao nhieu nganh hang THAT, thieu cho nao, bu bang gi.

    python scripts/build_category_tree.py          # (chay 1 lan) dung cache cay nganh
    python scripts/category_coverage.py --level 3
    python scripts/category_coverage.py --level 3 --suggest 2 --out gaps.json

Cay nganh lay tu ProductInfo (category_full_path, 451 nganh toi 5 cap) chu KHONG
phai truong `cat` cua full_store_catalog — truong do chi co 2 cap/48 nhanh, do
do phu tren no la do tren ban do thu nho.

Do phu: moi keyword -> top-10 ket qua co che `vector` -> nganh (o cap dang xet)
cua tung san pham -> nganh xuat hien nhieu nhat la nganh keyword do THUC SU kiem
tra. Nganh chi thap thoang 1-2 san pham trong top-10 tinh la "cham", khong tinh
la phu.

De xuat keyword cho nganh trong, theo thu tu uu tien:
  1. tu khoa trong log tim kiem 6 thang ma phan lon san pham khop roi vao nganh do
  2. chinh TEN NGANH (vd "Rượu Vang") — khach van go nhu vay, va no chac chan
     dung nganh; kem theo luot tim thuc te neu log co
"""
import argparse, collections, json, os, re, sys, unicodedata

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        _s.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(ROOT))
TREE = os.path.join(ROOT, 'cache', 'category_tree.json')
TERMS = os.path.join(REPO, 'data', 'common_data', 'nsg_search_terms_6m.merged.ndjson')
MANIFEST = os.path.join(ROOT, 'images', 'excel_keywords', 'manifest.json')
RESULTS = os.path.join(ROOT, 'results', 'excel_top40')

NOT_REAL = ('Khac', 'Virtual cat', 'SPECIAL CATEGORIES', 'Giao 60 Phút')


def norm(s):
    s = unicodedata.normalize('NFD', str(s or '')).replace('đ', 'd').replace('Đ', 'D')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9\s]', ' ', s.lower())).strip()


def load_tree():
    if not os.path.exists(TREE):
        sys.exit('Thieu %s — chay scripts/build_category_tree.py truoc.' % TREE)
    d = json.load(open(TREE, encoding='utf-8'))
    return d['categories'], d['sku_paths']


def at_level(path, level):
    parts = path.split(' / ')
    return ' / '.join(parts[:level]) if len(parts) >= level else None


def coverage(sku_paths, level):
    """image_id -> nganh chu dao o cap `level`, va tap nganh duoc cham."""
    man = {r['image_id']: r for r in json.load(open(MANIFEST, encoding='utf-8'))}
    dominant, touched = {}, set()
    for iid, m in man.items():
        f = os.path.join(RESULTS, 'vector', iid + '.json')
        if not os.path.exists(f):
            continue
        d = json.load(open(f, encoding='utf-8'))
        if not d['ok']:
            continue
        cats = []
        for p in d['top'][:10]:
            for path in sku_paths.get(p['sku'], []):
                c = at_level(path, level)
                if c and not any(c.startswith(x) for x in NOT_REAL):
                    cats.append(c)
        if not cats:
            continue
        # mot san pham thuoc nhieu nganh -> dem theo san pham, khong theo lan xuat hien
        dominant[iid] = (m['keyword'], collections.Counter(cats).most_common(1)[0][0])
        touched.update(cats)
    return dominant, touched


def load_terms():
    score, hits = collections.Counter(), {}
    with open(TERMS, encoding='utf-8') as fh:
        for line in fh:
            try:
                o = json.loads(line)
            except Exception:
                continue
            q = norm(o.get('q'))
            if not q:
                continue
            score[q] += o.get('score') or 0
            hits[q] = max(hits.get(q, 0), o.get('latest_hits') or 0)
    return score, hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--level', type=int, default=3, help='cap nganh de do do phu (1..5)')
    ap.add_argument('--min-products', type=int, default=10)
    ap.add_argument('--suggest', type=int, default=0)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    cats, sku_paths = load_tree()
    dominant, touched = coverage(sku_paths, args.level)
    dom = {v[1] for v in dominant.values()}

    real = {c: n for c, n in cats.items()
            if c.count(' / ') + 1 == args.level and n >= args.min_products
            and not any(c.startswith(x) for x in NOT_REAL)}
    covered = {c: n for c, n in real.items() if c in dom}
    gaps = {c: n for c, n in real.items() if c not in dom}
    prods = sum(real.values())

    print('CÂY NGÀNH (ProductInfo): %d ngành mọi cấp · cấp %d có %d ngành (>=%d sp: %d)'
          % (len(cats), args.level, sum(1 for c in cats if c.count(' / ') + 1 == args.level),
             args.min_products, len(real)))
    print('BỘ TEST: %d keyword\n' % len(dominant))
    print('Phủ theo SỐ NGÀNH cấp %d : %d/%d (%.0f%%)  — chạm thêm %d ngành nữa'
          % (args.level, len(covered), len(real), 100.0 * len(covered) / max(1, len(real)),
             len([c for c in gaps if c in touched])))
    print('Phủ theo KHỐI SẢN PHẨM  : %d/%d (%.1f%%)'
          % (sum(covered.values()), prods, 100.0 * sum(covered.values()) / max(1, prods)))

    print('\n=== %d NGÀNH CÒN TRỐNG (>=%d sp) ===' % (len(gaps), args.min_products))
    for c, n in sorted(gaps.items(), key=lambda kv: -kv[1]):
        print('  %-72s %5d sp  %s' % (c[:72], n, 'chạm' if c in touched else 'KHÔNG chạm'))

    if not args.suggest:
        return

    score, hits = load_terms()
    used = {norm(v[0]) for v in dominant.values()}

    # Ten san pham -> ung vien tu khoa. Lay n-gram 1..3 tu tu ten san pham TRONG
    # nganh do, roi cham diem bang luot tim that trong log. Chi giu ung vien ma
    # phan lon san pham chua no nam dung nganh dang xet (do chinh xac), neu khong
    # "hop" hay "goi" se thang moi nganh.
    cat_names = json.load(open(os.path.join(REPO, 'SmartSearch', 'full_store_catalog', 'nsg.json'),
                               encoding='utf-8'))
    sku2name = {p['sku']: norm(p.get('name')) for p in cat_names}
    cat_skus = collections.defaultdict(set)
    for sku, paths in sku_paths.items():
        for path in paths:
            c = at_level(path, args.level)
            if c:
                cat_skus[c].add(sku)

    def ngrams(text, n_max=3):
        w = [x for x in text.split() if len(x) > 1]
        for n in range(1, n_max + 1):
            for i in range(len(w) - n + 1):
                yield ' '.join(w[i:i + n])

    # bao nhieu san pham TOAN KHO chua cum tu nay (de tinh do chinh xac)
    global_count = collections.Counter()
    for sku, nm in sku2name.items():
        for g in set(ngrams(nm)):
            global_count[g] += 1

    print('\n=== ĐỀ XUẤT KEYWORD CHO %d NGÀNH TRỐNG ===' % len(gaps))
    out = {}
    for c, n in sorted(gaps.items(), key=lambda kv: -kv[1]):
        leaf = c.split(' / ')[-1]
        in_cat = collections.Counter()
        for sku in cat_skus.get(c, ()):
            nm = sku2name.get(sku)
            if nm:
                for g in set(ngrams(nm)):
                    in_cat[g] += 1
        cands = []
        for g, freq in in_cat.items():
            if freq < 3 or g in used:
                continue
            prec = freq / float(global_count.get(g, freq))
            sc = score.get(g, 0)
            if prec < 0.5 or sc <= 0:
                continue
            cands.append((sc, prec, freq, g))
        cands.sort(reverse=True)

        picks = []
        nleaf = norm(leaf)
        if nleaf not in used:
            picks.append({'keyword': leaf.lower(), 'nguon': 'tên ngành',
                          'score': score.get(nleaf, 0), 'hits': hits.get(nleaf, 0),
                          'do_chinh_xac': 1.0})
            used.add(nleaf)
        for sc, prec, freq, g in cands:
            if len(picks) >= max(1, args.suggest):
                break
            picks.append({'keyword': g, 'nguon': 'tên sản phẩm + log',
                          'score': sc, 'hits': hits.get(g, 0), 'do_chinh_xac': round(prec, 2)})
            used.add(g)
        out[c] = picks
        print('\n  %s  (%d sp)' % (c, n))
        for p in picks:
            print('     %-30s %-20s score %-9d hits %-5d chính xác %.0f%%'
                  % (p['keyword'], p['nguon'], p['score'], p['hits'], 100 * p['do_chinh_xac']))

    if args.out:
        json.dump(out, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print('\nĐã ghi: %s' % args.out)


if __name__ == '__main__':
    main()
