# -*- coding: utf-8 -*-
"""In dữ liệu một lô ảnh để tự chấm: keyword + top-N của từng cơ chế.

    python scripts/review_batch.py --from 1 --count 12 [--top 5]

Dùng cho vòng chấm thủ công: xem ảnh gốc (images/excel_keywords/...) rồi đối
chiếu với danh sách tên sản phẩm in ra đây.
"""
import argparse, glob, json, os, sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        _s.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, 'results', 'excel_top40')
MANIFEST = os.path.join(ROOT, 'images', 'excel_keywords', 'manifest.json')
MODES = [('vector', 'Vector'), ('vector_titan', 'Titan'),
         ('vector_titan_multi', 'TitanMulti'), ('caption', 'NovaLite')]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='start', type=int, default=1)
    ap.add_argument('--count', type=int, default=12)
    ap.add_argument('--top', type=int, default=5)
    ap.add_argument('--paths-only', action='store_true')
    args = ap.parse_args()

    man = sorted(json.load(open(MANIFEST, encoding='utf-8')), key=lambda r: r['excel_row'])
    batch = man[args.start - 1: args.start - 1 + args.count]
    runs = {}
    for f in glob.glob(os.path.join(RESULTS, '*', '*.json')):
        d = json.load(open(f, encoding='utf-8'))
        runs.setdefault(d['image_id'], {})[d['mode_requested']] = d

    if args.paths_only:
        for r in batch:
            print(os.path.join(ROOT, 'images', r['file']).replace('\\', '/'))
        return

    for r in batch:
        b = runs.get(r['image_id'], {})
        print('=' * 100)
        print('%s | No %s | keyword: "%s" | %s' % (r['image_id'], r['stt'], r['keyword'], r['file']))
        cap = (b.get('caption', {}).get('caption') or {})
        if cap:
            print('   NovaLite đọc ảnh thành: "%s" (outcome %s)' % (cap.get('query'), cap.get('outcome')))
        for mode, label in MODES:
            d = b.get(mode)
            if not d or not d['ok']:
                print('  %-10s: (không có kết quả)' % label)
                continue
            items = d['top'][:args.top]
            head = '  %-10s tổng %-4s %5dms' % (label, d['total_hits'], d['took_ms'])
            print(head)
            for p in items:
                print('        %2d. %-62s tồn %s' % (p['no'], p['name'][:62], p['stock_qty']))
            if not items:
                print('        (rỗng)')


if __name__ == '__main__':
    main()
