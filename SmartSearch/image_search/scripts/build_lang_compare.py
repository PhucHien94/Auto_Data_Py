# -*- coding: utf-8 -*-
"""So sanh ket qua image search giua cac ngon ngu payload (vi / en / ko) - user 2026-09-29.

    node scripts/run-excel-top40.mjs --round 2026-09-28 --lang en --out results/excel_top40_lang/en
    node scripts/run-excel-top40.mjs --round 2026-09-28 --lang ko --out results/excel_top40_lang/ko
    node scripts/fetch-result-images.mjs          # tai anh SP cua ca vi + cac ngon ngu
    python scripts/build_lang_compare.py [--open]

Moc so sanh = ket qua vi (results/excel_top40). Voi moi (anh, co che, ngon ngu):
  trung@k = |topk_vi ∩ topk_lang| / max(|topk_vi|, |topk_lang|)   (ca 2 rong -> 100%)
  lech@k  = 100% - trung@k
Dung max() chu khong phai |topk_vi|: ngon ngu khac tra IT ket qua hon cung la lech.
Them 'dung_qa': ti le SP trong top10 thuoc tap SP QA da chap nhan o vi (top-20 cua cac co
che QA chon dat vong hien tai) - de biet ket qua lech di theo huong dung hay sai.

tookMs KHONG so duoc giua ngon ngu: backend cache embedding theo (hash anh, co che), nen
ngon ngu chay sau nhanh hon han (do 2026-09-29: ko ~100ms vs vi ~1-2s).
"""
import argparse, json, os, sys, webbrowser
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_image_dashboard import (load_runs, load_manifest, load_img_index, load_state,  # noqa: E402
                                   MODE_INFO, set_modes, current_round, RESULTS, OUT_DIR)
import build_image_dashboard as B  # noqa: E402

ROOT = os.path.dirname(OUT_DIR)
LANG_ROOT = os.path.join(ROOT, 'results', 'excel_top40_lang')
OUT = os.path.join(OUT_DIR, 'image_search_lang_compare.html')
LANG_LABEL = {'vi': 'Tiếng Việt', 'en': 'Tiếng Anh', 'ko': 'Tiếng Hàn'}


def load_dir(d):
    old = B.RESULTS
    B.RESULTS = d
    try:
        return load_runs()
    finally:
        B.RESULTS = old


def ids(d, k):
    return [p['sku'] for p in (d.get('top') or [])[:k]] if d and d.get('ok') else []


def overlap(a, b):
    if not a and not b:
        return 1.0
    return len(set(a) & set(b)) / max(len(a), len(b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--open', action='store_true')
    args = ap.parse_args()

    vi = load_runs()
    langs = {'vi': vi}
    for l in sorted(os.listdir(LANG_ROOT)) if os.path.isdir(LANG_ROOT) else []:
        if os.path.isdir(os.path.join(LANG_ROOT, l)):
            langs[l] = load_dir(os.path.join(LANG_ROOT, l))
    others = [l for l in langs if l != 'vi']
    if not others:
        sys.exit('Chua co ket qua ngon ngu khac trong results/excel_top40_lang/')
    set_modes(vi)
    modes = [m for m, _ in B.MODES]
    man, img, state = load_manifest(), load_img_index(), load_state()
    rnd = current_round(vi)
    verdicts = state['rounds'].get(rnd, {}).get('verdicts', {})

    rows = []
    for iid in sorted(vi, key=lambda i: man.get(i, {}).get('excel_row', 1e9)):
        if iid not in man:
            continue
        v = verdicts.get(iid, {})
        # tap SP QA da chap nhan o vi: top-20 cua cac co che QA chon dat
        accepted = set()
        for m in v.get('verdict', []):
            accepted |= set(ids(vi[iid].get(m), 20))
        row = {'id': iid, 'stt': man[iid]['stt'], 'kw': man[iid]['keyword'], 'kwlang': man[iid]['lang'],
               'q': '../images/' + man[iid]['file'].replace('\\', '/'), 'qa': v.get('verdict', []),
               'modes': {}}
        for m in modes:
            per = {}
            for l, runs in langs.items():
                d = (runs.get(iid) or {}).get(m)
                t10 = ids(d, 10)
                per[l] = {
                    'ok': bool(d and d.get('ok')), 'http': d.get('http_status') if d else None,
                    'n': d.get('returned') if d else None, 'total': d.get('total_hits') if d else None,
                    'cap': ((d or {}).get('caption') or {}).get('query'),
                    'good': (sum(s in accepted for s in t10) / len(t10)) if (t10 and accepted) else None,
                    'items': [{'sku': p['sku'], 'name': p['name'],
                               'img': ('../result_images/' + img[p['sku']]) if p['sku'] in img else None}
                              for p in ((d or {}).get('top') or [])[:10]],
                }
                if l != 'vi':
                    dv = vi[iid].get(m)
                    per[l]['ov10'] = overlap(ids(dv, 10), t10)
                    per[l]['ov40'] = overlap(ids(dv, 40), ids(d, 40))
                    per[l]['top1'] = bool(ids(dv, 1)) and ids(dv, 1) == ids(d, 1)
                    per[l]['in_vi40'] = [s in set(ids(dv, 40)) for s in t10]
            row['modes'][m] = per
        rows.append(row)

    # ---- tong hop ----
    def mean(xs):
        xs = [x for x in xs if x is not None]
        return sum(xs) / len(xs) if xs else None

    summary = {}
    for l in others:
        for m in modes:
            cells = [r['modes'][m][l] for r in rows if r['modes'][m][l]['ok'] and r['modes'][m]['vi']['ok']]
            summary[l + '|' + m] = {
                'n': len(cells),
                'dev10': 1 - mean([c['ov10'] for c in cells]), 'dev40': 1 - mean([c['ov40'] for c in cells]),
                'top1_changed': sum(not c['top1'] for c in cells) / len(cells) if cells else None,
                'big': sum(c['ov10'] <= 0.5 for c in cells),
                'zero': sum((c['n'] or 0) == 0 for c in cells),
                'zero_vi': sum((r['modes'][m]['vi']['n'] or 0) == 0 for r in rows),
                'good': mean([c['good'] for c in cells]),
                'good_vi': mean([r['modes'][m]['vi']['good'] for r in rows]),
                'errors': sum(1 for r in rows if not r['modes'][m][l]['ok']),
            }
        summary[l + '|all'] = {
            'dev10': mean([summary[l + '|' + m]['dev10'] for m in modes]),
            'dev40': mean([summary[l + '|' + m]['dev40'] for m in modes]),
            'top1_changed': mean([summary[l + '|' + m]['top1_changed'] for m in modes]),
        }
    for r in rows:
        r['dev'] = {}
        for l in others:
            ov = mean([r['modes'][m][l].get('ov10') for m in modes if r['modes'][m][l]['ok']])
            r['dev'][l] = None if ov is None else 1 - ov  # anh chua chay / loi het -> khong tinh

    meta = {'round': rnd, 'built_at': datetime.now().strftime('%Y-%m-%d %H:%M'), 'langs': list(langs),
            'others': others, 'lang_label': LANG_LABEL,
            'modes': [[m, MODE_INFO.get(m, {}).get('label', m)] for m in modes],
            'ran_at': {l: sorted({d['ran_at'][:16].replace('T', ' ') for b in runs.values() for d in b.values()})[::max(1, 1)][-1]
                       for l, runs in langs.items()},
            'n': len(rows)}
    data = json.dumps({'rows': rows, 'summary': summary, 'meta': meta}, ensure_ascii=False).replace('</', '<\\/')
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as fh:
        fh.write(HTML.replace('__DATA__', data))
    print('Dashboard so sanh ngon ngu:', OUT)
    for l in others:
        s = summary[l + '|all']
        print('  %s vs vi: lech top10 %.1f%% · top40 %.1f%% · top1 doi %.1f%%' % (l, 100 * s['dev10'], 100 * s['dev40'], 100 * s['top1_changed']))
        for m in modes:
            x = summary[l + '|' + m]
            print('     %-34s lech10 %5.1f%%  lech40 %5.1f%%  top1 doi %5.1f%%  anh lech>=50%%: %3d  loi: %d' % (
                m, 100 * x['dev10'], 100 * x['dev40'], 100 * (x['top1_changed'] or 0), x['big'], x['errors']))
        worst = sorted(rows, key=lambda r: -(r['dev'][l] or 0))[:8]
        print('     lech nhat:', ', '.join('%s (%.0f%%)' % (r['kw'], 100 * r['dev'][l]) for r in worst))
    if args.open:
        webbrowser.open('file:///' + OUT.replace('\\', '/'))


HTML = r'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Image Search — So sánh ngôn ngữ</title>
<style>
:root{
  color-scheme: light;
  --bg:#f6f6f4; --surface:#fcfcfb; --surface-2:#f0f0ed; --line:#dedcd6;
  --text:#14140f; --text-2:#52514e; --muted:#7b7a74;
  --vi:#2a78d6; --en:#eb6834; --ko:#1baf7a;
  --good:#1a7f45; --good-bg:#e3f3e9; --warn:#9a6a00; --warn-bg:#fbf0d6; --bad:#b3261e; --bad-bg:#fbe4e2;
  --shadow:0 1px 2px rgba(0,0,0,.05),0 4px 14px rgba(0,0,0,.05);
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  color-scheme: dark;
  --bg:#121210; --surface:#1a1a19; --surface-2:#232321; --line:#35342f;
  --text:#f7f7f2; --text-2:#c3c2b7; --muted:#8e8d84;
  --vi:#3987e5; --en:#d95926; --ko:#199e70;
  --good:#4cc07d; --good-bg:#16301f; --warn:#d9a441; --warn-bg:#352a12; --bad:#e66767; --bad-bg:#3a1a19;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 4px 14px rgba(0,0,0,.35);
}}
:root[data-theme="dark"]{
  color-scheme: dark;
  --bg:#121210; --surface:#1a1a19; --surface-2:#232321; --line:#35342f;
  --text:#f7f7f2; --text-2:#c3c2b7; --muted:#8e8d84;
  --vi:#3987e5; --en:#d95926; --ko:#199e70;
  --good:#4cc07d; --good-bg:#16301f; --warn:#d9a441; --warn-bg:#352a12; --bad:#e66767; --bad-bg:#3a1a19;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 4px 14px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:20px 16px 80px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:0 0 8px}
.sub{color:var(--text-2);font-size:13px}
.note{margin:12px 0;padding:10px 14px;border-radius:10px;background:var(--warn-bg);border:1px solid var(--line);font-size:13px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow);margin-bottom:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin:14px 0}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;box-shadow:var(--shadow)}
.tile h3{margin:0 0 6px;font-size:13px;display:flex;align-items:center;gap:7px}
.big{font-size:28px;font-weight:650;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.row{display:flex;justify-content:space-between;gap:8px;font-size:12.5px;color:var(--text-2);padding:2px 0}
.row b{color:var(--text);font-variant-numeric:tabular-nums}
.dot{width:10px;height:10px;border-radius:3px;display:inline-block;flex:none}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
th{font-size:11.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em;font-weight:600}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.tw{overflow-x:auto}
.track{background:var(--surface-2);border-radius:4px;height:8px;min-width:80px;overflow:hidden}
.fill{height:100%;border-radius:0 4px 4px 0}
.badge{display:inline-block;font-size:11.5px;font-weight:650;padding:1px 7px;border-radius:999px;font-variant-numeric:tabular-nums;white-space:nowrap}
.b-lo{background:var(--good-bg);color:var(--good)} .b-mid{background:var(--warn-bg);color:var(--warn)} .b-hi{background:var(--bad-bg);color:var(--bad)}
.bar{position:sticky;top:0;z-index:10;background:var(--bg);border-bottom:1px solid var(--line);padding:10px 0;margin-bottom:12px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.bar select,.bar input,.bar button{font:inherit;font-size:13px;color:var(--text);background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
.bar button{cursor:pointer}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;margin-bottom:10px;box-shadow:var(--shadow)}
.chead{display:flex;gap:12px;padding:10px 12px;cursor:pointer;align-items:center}
.chead:hover{background:var(--surface-2)}
.qimg{width:64px;height:64px;object-fit:contain;border-radius:8px;border:1px solid var(--line);background:#fff;flex:none}
.kw{font-weight:650} .kw small{font-weight:400;color:var(--muted);margin-left:6px}
.devs{display:flex;flex-wrap:wrap;gap:4px 10px;margin-top:4px;font-size:12px;color:var(--text-2)}
.body{border-top:1px solid var(--line);padding:10px 12px}
.mblock{margin-bottom:14px}
.mblock h4{margin:0 0 6px;font-size:13px}
.lrow{display:grid;grid-template-columns:150px 1fr;gap:10px;align-items:start;margin-bottom:6px}
.lab{font-size:12px;color:var(--text-2)} .lab b{color:var(--text)}
.th{display:grid;grid-template-columns:repeat(10,minmax(48px,1fr));gap:5px}
.it{position:relative;border:2px solid transparent;border-radius:7px;background:#fff;aspect-ratio:1;overflow:hidden}
.it img{width:100%;height:100%;object-fit:contain}
.it.off{border-color:var(--bad)}
.it .nm{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:9px;color:#333;padding:3px;text-align:center}
.cap{font-size:11.5px;color:var(--text-2);margin-top:2px}
.jump{color:var(--text);text-decoration:underline;cursor:pointer}
#tip{position:fixed;z-index:50;pointer-events:none;background:var(--text);color:var(--bg);font-size:12px;padding:6px 9px;border-radius:7px;max-width:320px;opacity:0}
#tip.on{opacity:1}
</style></head><body><div class="wrap">
<h1 id="title"></h1>
<div class="sub" id="sub"></div>
<div class="note" id="note"></div>
<div class="tiles" id="tiles"></div>
<div class="panel"><h2>Độ lệch so với tiếng Việt, theo cơ chế</h2><div class="tw" id="bymode"></div></div>
<div class="panel"><h2>Keyword lệch nhiều nhất</h2><div class="tw" id="worst"></div></div>
<div class="bar">
  <label>Ngôn ngữ <select id="f-lang"></select></label>
  <label>Sắp xếp <select id="f-sort"><option value="dev">Lệch nhiều nhất trước</option><option value="stt">Theo STT</option></select></label>
  <input id="f-q" placeholder="Tìm keyword…">
  <button id="b-open">Mở tất cả</button><button id="b-close">Thu tất cả</button>
  <span class="sub" id="count"></span>
</div>
<div id="cards"></div>
</div><div id="tip"></div>
<script id="payload" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('payload').textContent);
const ROWS = D.rows, S = D.summary, M = D.meta;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const P = (x) => x == null ? '—' : (100 * x).toFixed(1).replace('.', ',') + '%';
const ddmm = (d) => d ? d.slice(8, 10) + '/' + d.slice(5, 7) + '/' + d.slice(0, 4) : '';
const lvl = (dev) => dev == null ? '' : dev < 0.2 ? 'b-lo' : dev < 0.5 ? 'b-mid' : 'b-hi';
const dot = (l) => `<span class="dot" style="background:var(--${l})"></span>`;
const LL = (l) => `${l.toUpperCase()}`;

$('#title').textContent = `Image Search — so sánh ngôn ngữ payload (${M.langs.map(LL).join(' / ')}) · vòng ${ddmm(M.round)}`;
$('#sub').innerHTML = `${M.n} ảnh × ${M.modes.length} cơ chế · mốc so sánh: <b>VI</b> · chạy: `
  + M.langs.map((l) => `${LL(l)} ${esc(M.ran_at[l])}`).join(' · ') + ` · sinh lúc ${esc(M.built_at)}`;
$('#note').innerHTML = `<b>Cách đọc:</b> với mỗi ảnh và mỗi cơ chế, so top-10 (và top-40) SKU của ngôn ngữ khác với VI.
  <b>Lệch = 100% − |SKU chung| ÷ max(số KQ VI, số KQ ngôn ngữ kia)</b> — trả ít kết quả hơn cũng tính là lệch.
  Ô viền đỏ = SP không có trong top-40 của VI. "Trùng tập QA duyệt" = tỉ lệ SP top-10 nằm trong tập SP bạn đã chấp nhận ở VI (top-20 của các cơ chế bạn chọn đạt) — ước lượng lệch sang đúng hay sai.
  <b>Không so thời gian phản hồi</b>: backend cache embedding theo (ảnh, cơ chế) nên ngôn ngữ chạy sau nhanh hơn hẳn.`;

$('#tiles').innerHTML = M.others.map((l) => {
  const a = S[l + '|all'];
  return `<div class="tile"><h3>${dot(l)} ${LL(l)} so với VI · ${esc(M.lang_label[l] || l)}</h3>
    <div class="big">${P(a.dev10)}</div><div class="sub" style="margin-bottom:6px">lệch trung bình top-10 (4 cơ chế)</div>
    <div class="row"><span>Lệch top-40</span><b>${P(a.dev40)}</b></div>
    <div class="row"><span>Ảnh đổi sản phẩm top-1</span><b>${P(a.top1_changed)}</b></div></div>`;
}).join('');

$('#bymode').innerHTML = `<table><thead><tr><th>Cơ chế</th><th>Ngôn ngữ</th><th class="n">Lệch top-10</th><th></th><th class="n">Lệch top-40</th>
  <th class="n">Top-1 đổi</th><th class="n">Ảnh lệch ≥50%</th><th class="n">Ảnh 0 KQ (VI → lang)</th><th class="n">Trùng tập QA duyệt (VI → lang)</th><th class="n">Lỗi gọi</th></tr></thead><tbody>`
  + M.modes.map(([m, label], i) => M.others.map((l, j) => { const x = S[l + '|' + m];
    return `<tr>${j === 0 ? `<td rowspan="${M.others.length}"><b>${i + 1}. ${esc(label)}</b></td>` : ''}<td>${dot(l)} ${LL(l)}</td>
      <td class="n"><span class="badge ${lvl(x.dev10)}">${P(x.dev10)}</span></td>
      <td style="width:18%"><div class="track"><div class="fill" style="width:${(100 * x.dev10).toFixed(1)}%;background:var(--${l})"></div></div></td>
      <td class="n">${P(x.dev40)}</td><td class="n">${P(x.top1_changed)}</td><td class="n">${x.big}/${x.n}</td>
      <td class="n">${x.zero_vi} → ${x.zero}</td><td class="n">${P(x.good_vi)} → <b>${P(x.good)}</b></td><td class="n">${x.errors}</td></tr>`; }).join('')).join('')
  + '</tbody></table>';

function renderWorst() {
  const l = $('#f-lang').value === 'all' ? M.others[0] : $('#f-lang').value;
  const top = [...ROWS].sort((a, b) => (b.dev[l] ?? 0) - (a.dev[l] ?? 0)).slice(0, 15);
  $('#worst').innerHTML = `<div class="sub" style="margin-bottom:6px">Xếp theo ${dot(l)} ${LL(l)} (đổi ở ô Ngôn ngữ bên dưới) · lệch top-10 trung bình 4 cơ chế</div>
    <table><thead><tr><th>#</th><th>Keyword</th>${M.others.map((o) => `<th class="n">${LL(o)} trung bình</th>`).join('')}
    ${M.modes.map(([, lab]) => `<th class="n">${esc(lab)} (${LL(l)})</th>`).join('')}</tr></thead><tbody>`
    + top.map((r, i) => `<tr><td>${i + 1}</td><td><span class="jump" data-id="${r.id}">${esc(r.kw)}</span> <span class="sub">${esc(r.id)}</span></td>
      ${M.others.map((o) => `<td class="n"><span class="badge ${lvl(r.dev[o])}">${P(r.dev[o])}</span></td>`).join('')}
      ${M.modes.map(([m]) => { const c = r.modes[m][l]; return `<td class="n">${c.ok ? P(1 - c.ov10) : 'lỗi ' + esc(c.http)}</td>`; }).join('')}</tr>`).join('')
    + '</tbody></table>';
  document.querySelectorAll('.jump').forEach((el) => el.onclick = () => {
    open.add(el.dataset.id); $('#f-q').value = ''; renderCards();
    document.getElementById('c-' + el.dataset.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

$('#f-lang').innerHTML = `<option value="all">Cả ${M.others.map(LL).join(' + ')}</option>` + M.others.map((l) => `<option value="${l}">Chỉ ${LL(l)}</option>`).join('');
const open = new Set();
const shownLangs = () => $('#f-lang').value === 'all' ? M.others : [$('#f-lang').value];

function itemsHTML(c, lang) {
  if (!c.ok) return `<div class="sub">lỗi HTTP ${esc(c.http)}</div>`;
  if (!c.items.length) return `<div class="sub">0 kết quả</div>`;
  return `<div class="th">${c.items.map((it, i) => `<div class="it${lang !== 'vi' && c.in_vi40 && !c.in_vi40[i] ? ' off' : ''}" data-tip="#${i + 1} ${esc(it.name)} · ${esc(it.sku)}${lang !== 'vi' && c.in_vi40 && !c.in_vi40[i] ? ' · KHÔNG có trong top-40 VI' : ''}">
    ${it.img ? `<img loading="lazy" src="${esc(it.img)}" alt="">` : `<span class="nm">${esc(it.name)}</span>`}</div>`).join('')}</div>`;
}

function cardHTML(r) {
  const ls = shownLangs(), isOpen = open.has(r.id);
  const devs = ls.map((l) => `<span>${dot(l)} ${LL(l)} lệch <span class="badge ${lvl(r.dev[l])}">${P(r.dev[l])}</span></span>`).join('')
    + M.modes.map(([m, lab]) => `<span>${esc(lab)}: ${ls.map((l) => { const c = r.modes[m][l]; return c.ok ? P(1 - c.ov10) : 'lỗi'; }).join(' / ')}</span>`).join('');
  let body = '';
  if (isOpen) body = `<div class="body">` + M.modes.map(([m, lab]) => {
    const langsHere = ['vi', ...ls];
    return `<div class="mblock"><h4>${esc(lab)}${r.qa.includes(m) ? ' <span class="badge b-lo">QA chấm đạt ở VI</span>' : ''}</h4>`
      + langsHere.map((l) => { const c = r.modes[m][l];
        return `<div class="lrow"><div class="lab">${dot(l)} <b>${LL(l)}</b> · ${c.ok ? (c.n ?? 0) + ' KQ' : 'lỗi'}${l !== 'vi' && c.ok ? `<br>lệch top-10 <span class="badge ${lvl(1 - c.ov10)}">${P(1 - c.ov10)}</span><br>top-1 ${c.top1 ? 'giữ nguyên' : '<b>đổi</b>'}` : ''}
          ${c.good != null ? `<br>trùng tập QA duyệt: ${P(c.good)}` : ''}${c.cap ? `<div class="cap">NovaLite đọc: “${esc(c.cap)}”</div>` : ''}</div>
          <div>${itemsHTML(c, l)}</div></div>`; }).join('') + '</div>';
  }).join('') + '</div>';
  return `<div class="card" id="c-${r.id}"><div class="chead" data-id="${r.id}">
    <img class="qimg" loading="lazy" src="${esc(r.q)}" alt="">
    <div style="flex:1;min-width:0"><div class="kw">${r.stt}. ${esc(r.kw)}<small>${esc(r.id)} · ${esc(r.kwlang)}</small></div><div class="devs">${devs}</div></div>
    <span class="sub">${isOpen ? '▲' : '▼'}</span></div>${body}</div>`;
}

function renderCards() {
  const q = $('#f-q').value.trim().toLowerCase(), ls = shownLangs();
  let rows = ROWS.filter((r) => !q || r.kw.toLowerCase().includes(q) || r.id.includes(q));
  const score = (r) => Math.max(...ls.map((l) => r.dev[l] ?? 0));
  if ($('#f-sort').value === 'dev') rows = [...rows].sort((a, b) => score(b) - score(a));
  $('#cards').innerHTML = rows.map(cardHTML).join('');
  $('#count').textContent = `${rows.length}/${ROWS.length} ảnh`;
  document.querySelectorAll('.chead').forEach((el) => el.onclick = () => {
    const id = el.dataset.id; open.has(id) ? open.delete(id) : open.add(id);
    el.parentElement.outerHTML = cardHTML(ROWS.find((r) => r.id === id));
    renderCards();
  });
}
$('#f-lang').onchange = () => { renderWorst(); renderCards(); };
$('#f-sort').onchange = renderCards; $('#f-q').oninput = renderCards;
$('#b-open').onclick = () => { ROWS.forEach((r) => open.add(r.id)); renderCards(); };
$('#b-close').onclick = () => { open.clear(); renderCards(); };
const tip = $('#tip');
document.addEventListener('mouseover', (e) => { const t = e.target.closest('[data-tip]'); if (!t) { tip.classList.remove('on'); return; } tip.textContent = t.dataset.tip; tip.classList.add('on'); });
document.addEventListener('mousemove', (e) => { if (!tip.classList.contains('on')) return; let x = e.clientX + 12, y = e.clientY + 12; if (x + tip.offsetWidth > innerWidth - 8) x = e.clientX - tip.offsetWidth - 12; if (y + tip.offsetHeight > innerHeight - 8) y = e.clientY - tip.offsetHeight - 12; tip.style.left = x + 'px'; tip.style.top = y + 'px'; });
renderWorst(); renderCards();
</script></body></html>
'''

if __name__ == '__main__':
    main()
