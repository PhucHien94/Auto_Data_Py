# -*- coding: utf-8 -*-
"""Trang xem lai goi y cua Claude (suggest_verdicts.py) truoc khi QA duyet.

    python scripts/build_suggest_review.py --prev-results results/_archive/excel_top40_before_rerun_20260924 [--open]

Chi de XEM: moi anh hien goi y dat/khong dat tung co che, do chac, top-10 san pham
(o do = bi coi la khong lien quan) va lua chon cua QA lan truoc de doi chieu.
Sua lua chon van lam tren dashboard chinh (image_search_dashboard.html).
"""
import argparse, json, os, sys, webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import suggest_verdicts as S  # noqa: E402
from build_image_dashboard import load_img_index  # noqa: E402

ROOT = S.ROOT
OUT = os.path.join(ROOT, 'dashboard', 'image_search_suggest_review.html')
# ten bien mau CSS cua tung co che, lay tu scripts/lib/modes.json (2026-09-29)
SHORT = {m: x['css'].lstrip('-') for m, x in S._INFO.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prev-results', required=True)
    ap.add_argument('--suggest', default=None)
    ap.add_argument('--open', action='store_true')
    args = ap.parse_args()

    cur = S.load_runs(S.RESULTS)
    rnd = max((d.get('round') or d['ran_at'][:10]) for b in cur.values() for d in b.values())
    # co che cua lan chay nay (config.mjs), khong phai danh sach cung
    MODES = [m for m in S.RUN_MODES if any(m in b for b in cur.values())]
    sug_path = args.suggest or os.path.join(ROOT, 'dashboard', 'image_search_verdicts_%s_claude_suggest.json' % rnd.replace('-', ''))
    sug = json.load(open(sug_path, encoding='utf-8'))
    model = dict(sug['model'])
    # co che moi chua co mo hinh rieng -> hien mo hinh muon, cv_acc = None (chua do duoc)
    for m in MODES:
        if m not in model:
            model[m] = dict(S.model_for(sug['model'], m), cv_acc=None, borrowed=S.BORROW[m])
    state = json.load(open(S.STATE, encoding='utf-8'))
    prev_round = sorted(r for r in state['rounds'] if r != rnd)[-1]
    old = state['rounds'][prev_round]['verdicts']
    man = {r['image_id']: r for r in json.load(open(S.MANIFEST, encoding='utf-8'))}
    prev = S.load_runs(args.prev_results)
    tree = S.Tree()
    img = load_img_index()

    rows = []
    for iid in sorted(cur, key=lambda i: man.get(i, {}).get('excel_row', 1e9)):
        if iid not in man or iid not in sug['verdicts']:
            continue
        kw = man[iid]['keyword']
        terms = S.terms_for(kw)
        v_old = old.get(iid, {})
        acc = S.accepted_from(v_old, prev.get(iid, {})) if v_old else set()
        hits = S.catalog_name_hits([prev.get(iid, {}), cur[iid]], terms)
        cats = S.reference(iid, kw, hits, acc, tree)
        modes = {}
        for m in MODES:
            d = cur[iid].get(m)
            f = S.features(d, terms, acc, cats, tree)
            score = S.SCORE(f, model[m]['weights'])
            modes[m] = {
                'ok': m in sug['verdicts'][iid],
                'unsure': abs(score - model[m]['threshold']) < 0.1 or m == 'caption' or bool(model[m].get('borrowed')),
                'p10': round(f['p10_strict'] * min(10, f['n'])), 'n10': min(10, f['n']), 'p40': round(f['p40_strict'] * 100),
                'n': f['n'], 'took': d.get('took_ms') if d else None, 'total': d.get('total_hits') if d else None,
                'err': None if d and d.get('ok') else (d.get('http_status') if d else 'chưa chạy'),
                'items': [{'name': it['name'], 'rel': r,
                           'img': ('../result_images/' + img[it['sku']]) if it['sku'] in img else None}
                          for it, r in zip(S.top(d, 10), f['strict'][:10])],
            }
        rows.append({
            'id': iid, 'stt': man[iid]['stt'], 'kw': kw, 'lang': man[iid]['lang'],
            'q': '../images/' + man[iid]['file'].replace('\\', '/'),
            'sv': sug['verdicts'][iid], 'sp': sug['performance'].get(iid, []),
            'ov': v_old.get('verdict', []), 'op': v_old.get('performance', []), 'on': v_old.get('note', ''),
            'qa': iid in set(sug.get('reviewed_ids', [])),
            'modes': modes,
        })

    meta = {'round': rnd, 'prev': prev_round, 'model': model,
            'labels': S.LABEL, 'short': SHORT, 'modes': MODES,
            'prev_modes': sorted({m for b in prev.values() for m in b})}
    html = HTML.replace('/*DATA*/', 'const ROWS=%s;const META=%s;' % (
        json.dumps(rows, ensure_ascii=False), json.dumps(meta, ensure_ascii=False)))
    open(OUT, 'w', encoding='utf-8').write(html)
    print('Trang review:', OUT, '·', len(rows), 'anh')
    if args.open:
        webbrowser.open('file:///' + OUT.replace('\\', '/'))


HTML = r'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Duyệt gợi ý Image Search</title>
<style>
:root{
  color-scheme: light;
  --bg:#f6f6f4; --surface:#fcfcfb; --surface-2:#f0f0ed; --line:#dedcd6;
  --text:#14140f; --text-2:#52514e; --muted:#7b7a74;
  --vector:#2a78d6; --titan:#eb6834; --tmulti:#4a3aa7; --tmct:#eb6834; --nova:#1baf7a;
  --good:#1a7f45; --good-bg:#e3f3e9; --warn:#9a6a00; --warn-bg:#fbf0d6; --bad:#b3261e; --bad-bg:#fbe4e2;
  --shadow:0 1px 2px rgba(0,0,0,.05),0 4px 14px rgba(0,0,0,.05);
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  color-scheme: dark;
  --bg:#121210; --surface:#1a1a19; --surface-2:#232321; --line:#35342f;
  --text:#f7f7f2; --text-2:#c3c2b7; --muted:#8e8d84;
  --vector:#3987e5; --titan:#d95926; --tmulti:#9085e9; --tmct:#d95926; --nova:#199e70;
  --good:#4cc07d; --good-bg:#16301f; --warn:#d9a441; --warn-bg:#352a12; --bad:#e66767; --bad-bg:#3a1a19;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 4px 14px rgba(0,0,0,.35);
}}
:root[data-theme="dark"]{
  color-scheme: dark;
  --bg:#121210; --surface:#1a1a19; --surface-2:#232321; --line:#35342f;
  --text:#f7f7f2; --text-2:#c3c2b7; --muted:#8e8d84;
  --vector:#3987e5; --titan:#d95926; --tmulti:#9085e9; --tmct:#d95926; --nova:#199e70;
  --good:#4cc07d; --good-bg:#16301f; --warn:#d9a441; --warn-bg:#352a12; --bad:#e66767; --bad-bg:#3a1a19;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 4px 14px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:20px 16px 80px}
h1{font-size:20px;margin:0 0 2px}
.sub{color:var(--text-2);font-size:13px}
.mono{font-variant-numeric:tabular-nums}
.banner{margin:14px 0;padding:10px 14px;border-radius:10px;background:var(--warn-bg);color:var(--text);
  border:1px solid var(--line);font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin:14px 0}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;box-shadow:var(--shadow)}
.tile h3{margin:0 0 8px;font-size:13px;display:flex;gap:7px;align-items:center}
.dot{width:10px;height:10px;border-radius:3px;flex:none}
.dot.striped{background-image:repeating-linear-gradient(45deg,rgba(255,255,255,.55) 0 2px,transparent 2px 4px)}
.big{font-size:26px;font-weight:650;letter-spacing:-.02em}
.row{display:flex;justify-content:space-between;gap:8px;font-size:12px;color:var(--text-2);padding:2px 0}
.row b{color:var(--text);font-weight:600}
.bar{position:sticky;top:0;z-index:10;background:var(--bg);border-bottom:1px solid var(--line);
  padding:10px 0;margin-bottom:14px;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.bar button,.bar input,.bar select{font:inherit;font-size:13px;color:var(--text);background:var(--surface);
  border:1px solid var(--line);border-radius:8px;padding:6px 10px}
.bar button{cursor:pointer}
.bar button[aria-pressed="true"]{background:var(--text);color:var(--bg);border-color:var(--text)}
.bar .count{color:var(--text-2);font-size:12px;margin-left:auto}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:12px;
  box-shadow:var(--shadow);display:grid;grid-template-columns:150px 1fr;gap:14px}
.qimg{width:150px;height:150px;object-fit:contain;border-radius:10px;border:1px solid var(--line);background:#fff}
.kw{font-weight:650;font-size:15px}
.meta{color:var(--muted);font-size:12px}
.cmp{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;font-size:12px;margin:8px 0 4px;align-items:center}
.cmp .lab{color:var(--text-2)}
.chip{display:inline-flex;gap:5px;align-items:center;font-size:12px;padding:2px 8px;border-radius:999px;
  border:1px solid var(--line);background:var(--surface-2);margin:0 4px 3px 0}
.chip.new{border-color:var(--text);font-weight:600}
.chip.gone{text-decoration:line-through;color:var(--muted)}
.chg{font-size:11px;font-weight:600;padding:1px 7px;border-radius:999px;background:var(--warn-bg);color:var(--warn);margin-left:6px}
.oldnote{font-size:12px;color:var(--text-2);white-space:pre-wrap;margin-top:2px}
.mrow{display:grid;grid-template-columns:210px 1fr;gap:10px;align-items:center;padding:8px 0;border-top:1px solid var(--line)}
.mhead{display:flex;flex-direction:column;gap:3px;font-size:12px}
.mname{display:flex;gap:6px;align-items:center;font-weight:600;font-size:13px}
.verd{display:inline-flex;gap:4px;align-items:center;font-weight:600;font-size:12px;padding:1px 8px;border-radius:6px;width:max-content}
.verd.ok{background:var(--good-bg);color:var(--good)}
.verd.no{background:var(--bad-bg);color:var(--bad)}
.unsure{font-size:11px;color:var(--warn);font-weight:600}
.stat{color:var(--text-2)}
.thumbs{display:grid;grid-template-columns:repeat(10,minmax(0,1fr));gap:6px}
.th{position:relative;border-radius:8px;border:2px solid transparent;background:#fff;aspect-ratio:1;overflow:hidden}
.th img{width:100%;height:100%;object-fit:contain;display:block}
.th.miss{display:flex;align-items:center;justify-content:center;font-size:9px;color:#7b7a74;padding:3px;text-align:center}
.th.bad{border-color:var(--bad)}
.th .x{position:absolute;top:2px;right:2px;width:16px;height:16px;border-radius:50%;background:var(--bad);color:#fff;
  font-size:11px;line-height:16px;text-align:center;font-weight:700}
.th .no{position:absolute;left:2px;bottom:2px;font-size:10px;background:rgba(0,0,0,.55);color:#fff;border-radius:4px;padding:0 4px}
.tip{position:fixed;z-index:50;pointer-events:none;background:var(--text);color:var(--bg);font-size:12px;
  padding:6px 9px;border-radius:7px;max-width:320px;box-shadow:var(--shadow)}
.empty{color:var(--muted);padding:30px;text-align:center}
@media (max-width:760px){
  .card{grid-template-columns:1fr}
  .qimg{width:110px;height:110px}
  .mrow{grid-template-columns:1fr}
  .thumbs{grid-template-columns:repeat(5,minmax(0,1fr))}
}
</style></head><body><div class="wrap">
<h1>Duyệt gợi ý đánh giá Image Search</h1>
<div class="sub" id="sub"></div>
<div class="banner">Đây là <b>gợi ý của Claude</b>, học từ lựa chọn của bạn lần <span id="prevd"></span>. Trang này chỉ để xem.
  Muốn sửa thì làm ở <a href="image_search_dashboard.html">dashboard chính</a>: các lựa chọn gợi ý đã được điền sẵn ở hàng <b>Lần <span id="curd"></span></b>.
  Ô sản phẩm <b>viền đỏ, có dấu ✕</b> là sản phẩm bị coi là không liên quan tới ảnh.</div>
<div class="tiles" id="tiles"></div>
<div class="bar" id="bar">
  <button data-f="all" aria-pressed="true">Tất cả</button>
  <button data-f="unsure">Cần xem kỹ</button>
  <button data-f="changed">Khác lần trước</button>
  <button data-f="none">Không cái nào đạt</button>
  <select id="mode"><option value="">Mọi cơ chế</option></select>
  <input id="q" type="search" placeholder="Tìm keyword…" aria-label="Tìm keyword">
  <span class="count" id="count"></span>
</div>
<div id="list"></div>
</div>
<div class="tip" id="tip" hidden></div>
<script>
/*DATA*/
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ddmm = (d) => d.slice(8, 10) + '/' + d.slice(5, 7);
const L = (m) => m === 'none' ? 'Không cái nào đạt' : META.labels[m];
const dot = (m) => `<span class="dot${m === 'vector_titan_multi' ? ' striped' : ''}" style="background:var(--${META.short[m]})"></span>`;
const same = (a, b) => a.length === b.length && a.every((x) => b.includes(x));
// Chi so tren co che co o CA 2 lan (lan 28/09 bo Titan, them Titan Multi Caption Type)
const COMMON = new Set(META.modes.filter((m) => META.prev_modes.includes(m)));
const inCommon = (xs) => { const k = xs.filter((m) => COMMON.has(m)); return k.length ? k : ['none']; };
const changed = (r) => !same(inCommon(r.sv), inCommon(r.ov));
const unsureAny = (r) => META.modes.some((m) => m !== 'caption' && r.modes[m].unsure);

$('#sub').textContent = `Lần chạy ${ddmm(META.round)} · ${ROWS.length} ảnh × ${META.modes.length} cơ chế · so với đánh giá của bạn lần ${ddmm(META.prev)}`;
$('#prevd').textContent = ddmm(META.prev); $('#curd').textContent = ddmm(META.round);

// ---- tiles: moi co che mot o, cung mot thang (so anh dat) ----
const tiles = META.modes.map((m) => {
  const now = ROWS.filter((r) => r.sv.includes(m)).length;
  const before = ROWS.filter((r) => r.ov.includes(m)).length;
  const uns = ROWS.filter((r) => r.modes[m].unsure).length;
  const perf = ROWS.filter((r) => r.sp.includes(m)).length;
  const d = now - before;
  return `<div class="tile"><h3>${dot(m)}${esc(L(m))}</h3>
    <div class="big mono">${now}<span style="font-size:14px;color:var(--text-2);font-weight:500"> / ${ROWS.length} ảnh đạt</span></div>
    <div class="row"><span>Bạn chấm lần ${ddmm(META.prev)}</span><b class="mono">${before} (${d >= 0 ? '+' : ''}${d})</b></div>
    <div class="row"><span>Nhanh nhất trong số đạt</span><b class="mono">${perf}</b></div>
    <div class="row"><span>Cần xem kỹ</span><b class="mono">${m === 'caption' ? 'tất cả' : uns}</b></div>
    <div class="row"><span>Khớp với bạn (kiểm tra chéo)</span><b class="mono">${META.model[m].cv_acc == null ? 'chưa đo — mượn ngưỡng ' + esc(META.labels[META.model[m].borrowed] || '') : Math.round(100 * META.model[m].cv_acc) + '%'}</b></div></div>`;
});
const nNone = ROWS.filter((r) => r.sv.includes('none')).length;
const nChg = ROWS.filter(changed).length;
tiles.push(`<div class="tile"><h3>Tổng quan</h3>
  <div class="big mono">${nChg}<span style="font-size:14px;color:var(--text-2);font-weight:500"> ảnh khác lần ${ddmm(META.prev)}</span></div>
  <div class="row"><span>Không cái nào đạt</span><b class="mono">${nNone}</b></div>
  <div class="row"><span>Có ô cần xem kỹ (trừ NovaLite)</span><b class="mono">${ROWS.filter(unsureAny).length}</b></div></div>`);
$('#tiles').innerHTML = tiles.join('');
META.modes.forEach((m) => $('#mode').insertAdjacentHTML('beforeend', `<option value="${m}">${esc(L(m))}</option>`));

// ---- danh sach ----
let F = 'all';
function chips(sel, other) {
  if (!sel.length) return '<span class="meta">—</span>';
  return sel.map((m) => `<span class="chip${other && !other.includes(m) ? ' new' : ''}">${m === 'none' ? '' : dot(m)}${esc(L(m))}</span>`).join('');
}
function card(r) {
  const mrows = META.modes.map((m) => {
    const x = r.modes[m];
    const th = x.items.map((it, i) => `<div class="th${it.rel ? '' : ' bad'}${it.img ? '' : ' miss'}" data-tip="${esc('#' + (i + 1) + ' ' + it.name + (it.rel ? '' : ' — bị coi là không liên quan'))}">
      ${it.img ? `<img loading="lazy" src="${esc(it.img)}" alt="">` : esc(it.name.slice(0, 30))}
      ${it.rel ? '' : '<span class="x">✕</span>'}<span class="no">${i + 1}</span></div>`).join('');
    return `<div class="mrow"><div class="mhead">
      <span class="mname">${dot(m)}${esc(L(m))}${r.sp.includes(m) ? ' <span class="chip" title="Nhanh nhất trong số đạt">⚡ hiệu năng</span>' : ''}</span>
      <span class="verd ${x.ok ? 'ok' : 'no'}">${x.ok ? '✓ Đạt' : '✕ Không đạt'}</span>
      ${x.unsure ? '<span class="unsure">⚠ cần xem kỹ</span>' : ''}
      <span class="stat mono">${x.err ? 'lỗi ' + esc(x.err) : `${x.n < 10 ? `chỉ ${x.n} KQ, đúng ${x.p10}/${x.n10}` : `top10 đúng ${x.p10}/10`} ${x.n <= 10 ? '' : ` · ${x.n < 40 ? 'đúng' : 'top40'} ${x.p40}%`} · ${x.took ?? '—'} ms · ${x.total ?? 0} KQ`}</span>
    </div><div class="thumbs">${th || '<span class="meta">không có kết quả</span>'}</div></div>`;
  }).join('');
  return `<div class="card"><div><img class="qimg" loading="lazy" src="${esc(r.q)}" alt="Ảnh tìm kiếm ${esc(r.kw)}"></div>
    <div style="min-width:0">
      <div class="kw">${r.stt}. ${esc(r.kw)} <span class="chip">${esc(r.lang)}</span>${r.qa ? '<span class="chip">✓ bạn đã duyệt</span>' : ''}${changed(r) ? '<span class="chg">khác lần trước</span>' : ''}</div>
      <div class="meta">${esc(r.id)}</div>
      <div class="cmp">
        <span class="lab">${r.qa ? 'Bạn duyệt' : 'Gợi ý'} ${ddmm(META.round)}</span><span>${chips(r.sv, r.ov)}</span>
        <span class="lab">Bạn chấm ${ddmm(META.prev)}</span><span>${chips(r.ov)}</span>
      </div>
      ${r.on ? `<div class="oldnote"><b>Ghi chú của bạn ${ddmm(META.prev)}:</b> ${esc(r.on)}</div>` : ''}
      ${mrows}
    </div></div>`;
}
function render() {
  const mode = $('#mode').value, q = $('#q').value.trim().toLowerCase();
  const rows = ROWS.filter((r) => {
    if (F === 'unsure' && !unsureAny(r)) return false;
    if (F === 'changed' && !changed(r)) return false;
    if (F === 'none' && !r.sv.includes('none')) return false;
    // Chon co che: "Cần xem kỹ" -> o cua co che do sat nguong; "Khác lần trước" -> co che do doi dat/khong dat
    if (mode && F === 'unsure' && !r.modes[mode].unsure) return false;
    if (mode && F === 'changed' && r.sv.includes(mode) === r.ov.includes(mode)) return false;
    if (q && !(r.kw.toLowerCase().includes(q) || String(r.stt) === q)) return false;
    return true;
  });
  $('#count').textContent = `${rows.length} / ${ROWS.length} ảnh`;
  $('#list').innerHTML = rows.map(card).join('') || '<div class="empty">Không có ảnh nào khớp bộ lọc.</div>';
}
document.querySelectorAll('#bar button').forEach((b) => b.onclick = () => {
  F = b.dataset.f;
  document.querySelectorAll('#bar button').forEach((x) => x.setAttribute('aria-pressed', x === b));
  render();
});
$('#mode').onchange = render; $('#q').oninput = render;
// tooltip ten san pham
const tip = $('#tip');
document.addEventListener('mouseover', (e) => {
  const t = e.target.closest('[data-tip]');
  if (!t) { tip.hidden = true; return; }
  tip.textContent = t.dataset.tip; tip.hidden = false;
});
document.addEventListener('mousemove', (e) => {
  if (tip.hidden) return;
  const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8);
  tip.style.left = x + 'px'; tip.style.top = (e.clientY + 16) + 'px';
});
render();
</script></body></html>
'''

if __name__ == '__main__':
    main()
