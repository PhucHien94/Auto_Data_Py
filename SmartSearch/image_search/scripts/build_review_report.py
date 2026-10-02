# -*- coding: utf-8 -*-
"""Bao cao TU CHAM: ket qua tra ve co khop voi anh dau vao khong + hieu nang.

    python scripts/build_review_report.py

Doc cache/auto_review.json (diem cham tay cho tung anh x tung co che) + ket qua
tho, sinh dashboard/auto_review_report.html — MOT FILE RIENG, khong dinh gi toi
dashboard cham diem cua QA.

Thang diem moi o (anh, co che):
  2 = ĐẠT      — it nhat 2/3 ket qua dau dung mat hang trong anh
  1 = MỘT PHẦN — co ket qua dung nhung lan nhieu thu khac, hoac dung nganh sai loai
  0 = KHÔNG ĐẠT— khong ket qua nao trong top dau khop voi anh
"""
import json, glob, os, statistics, sys, collections
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        _s.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REVIEW = os.path.join(ROOT, 'cache', 'auto_review.json')
RESULTS = os.path.join(ROOT, 'results', 'excel_top40')
MANIFEST = os.path.join(ROOT, 'images', 'excel_keywords', 'manifest.json')
OUT = os.path.join(ROOT, 'dashboard', 'auto_review_report.html')

MODES = [('v', 'vector', 'Vector', '--vector'),
         ('t', 'vector_titan', 'Titan', '--titan'),
         ('tm', 'vector_titan_multi', 'Titan Multi', '--tmulti'),
         ('n', 'caption', 'NovaLite', '--nova')]
LABEL = {2: 'Đạt', 1: 'Một phần', 0: 'Không đạt'}


def pct(x, n):
    return 100.0 * x / n if n else 0


def main():
    rv = json.load(open(REVIEW, encoding='utf-8'))
    man = {r['image_id']: r for r in json.load(open(MANIFEST, encoding='utf-8'))}
    runs = {}
    for p in glob.glob(os.path.join(RESULTS, '*', '*.json')):
        r = json.load(open(p, encoding='utf-8'))
        runs.setdefault(r['image_id'], {})[r['mode_requested']] = r

    ids = sorted(rv, key=lambda i: man[i]['excel_row'])
    n = len(ids)

    stats = {}
    for key, mode, label, _ in MODES:
        sc = [rv[i][key] for i in ids]
        took = sorted(runs[i][mode]['took_ms'] for i in ids)
        tot = [runs[i][mode]['total_hits'] for i in ids]
        stats[key] = {
            'label': label, 'pass': sc.count(2), 'part': sc.count(1), 'fail': sc.count(0),
            'avg': sum(sc) / n,
            'p50': took[len(took) // 2], 'p95': took[int(.95 * (len(took) - 1))],
            'min': took[0], 'max': took[-1], 'mean': round(statistics.mean(took)),
            'short': sum(1 for t in tot if t < 40),
        }

    rows = []
    for i in ids:
        m = man[i]
        rows.append({
            'id': i, 'stt': m['stt'], 'keyword': m['keyword'], 'lang': m['lang'],
            'img': '../images/' + m['file'].replace('\\', '/'),
            'note': rv[i].get('note', ''),
            'scores': {k: rv[i][k] for k, _, _, _ in MODES},
            'took': {k: runs[i][mode]['took_ms'] for k, mode, _, _ in MODES},
            'total': {k: runs[i][mode]['total_hits'] for k, mode, _, _ in MODES},
            'top1': {k: (runs[i][mode]['top'][0]['name'] if runs[i][mode]['top'] else '—')
                     for k, mode, _, _ in MODES},
            'caption': (runs[i]['caption'].get('caption') or {}).get('query') or '',
        })

    payload = {'rows': rows, 'stats': stats, 'n': n,
               'modes': [[k, lab, css] for k, _, lab, css in MODES],
               'built': datetime.now().strftime('%Y-%m-%d %H:%M'),
               'all_fail': [r['keyword'] for r in rows if max(r['scores'].values()) == 0],
               'all_pass': sum(1 for r in rows if min(r['scores'].values()) == 2)}

    html = TEMPLATE.replace('__DATA__', json.dumps(payload, ensure_ascii=False).replace('</', '<\\/'))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, 'w', encoding='utf-8').write(html)
    print('Đã ghi: %s' % OUT)
    for k, _, label, _ in MODES:
        s = stats[k]
        print('  %-12s đạt %3d (%.0f%%) · một phần %2d · không đạt %2d · điểm TB %.2f · p50 %d ms'
              % (label, s['pass'], pct(s['pass'], n), s['part'], s['fail'], s['avg'], s['p50']))


TEMPLATE = r'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Image Search — Báo cáo tự chấm</title>
<style>
:root{color-scheme:light;
  --bg:#f6f6f4;--surface:#fcfcfb;--surface-2:#f0f0ed;--line:#dedcd6;
  --text:#14140f;--text-2:#52514e;--muted:#7b7a74;
  --vector:#2a78d6;--titan:#eb6834;--tmulti:#4a3aa7;--nova:#1baf7a;
  --good:#1a7f45;--warn:#9a6a00;--bad:#b3261e;
  --shadow:0 1px 2px rgba(0,0,0,.05),0 4px 14px rgba(0,0,0,.05)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;
  --bg:#121210;--surface:#1a1a19;--surface-2:#232321;--line:#35342f;
  --text:#f7f7f2;--text-2:#c3c2b7;--muted:#8e8d84;
  --vector:#3987e5;--titan:#d95926;--tmulti:#9085e9;--nova:#199e70;
  --good:#4cc07d;--warn:#d9a441;--bad:#e66767;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 4px 14px rgba(0,0,0,.35)}}
:root[data-theme="dark"]{color-scheme:dark;
  --bg:#121210;--surface:#1a1a19;--surface-2:#232321;--line:#35342f;
  --text:#f7f7f2;--text-2:#c3c2b7;--muted:#8e8d84;
  --vector:#3987e5;--titan:#d95926;--tmulti:#9085e9;--nova:#199e70;
  --good:#4cc07d;--warn:#d9a441;--bad:#e66767;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 4px 14px rgba(0,0,0,.35)}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:1500px;margin:0 auto;padding:22px 20px 70px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:28px 0 10px}
.sub{color:var(--text-2);font-size:13px}
.mono{font-variant-numeric:tabular-nums}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;
  padding:16px;box-shadow:var(--shadow);margin-bottom:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:12px}
.tile h3{margin:0 0 10px;font-size:13px;display:flex;align-items:center;gap:7px}
.dot{width:10px;height:10px;border-radius:3px;flex:none}
.dot.striped{background-image:repeating-linear-gradient(45deg,rgba(255,255,255,.55) 0 2px,transparent 2px 4px)}
.big{font-size:30px;font-weight:650;letter-spacing:-.02em}
.row{display:flex;justify-content:space-between;gap:10px;padding:3px 0;font-size:12px;color:var(--text-2)}
.row b{color:var(--text)}
.bar{height:16px;border-radius:5px;overflow:hidden;display:flex;margin:8px 0 4px;background:var(--surface-2)}
.bar i{display:block;height:100%}
.bar .ok{background:var(--good)}.bar .pa{background:var(--warn)}.bar .no{background:var(--bad)}
.legend{display:flex;gap:14px;font-size:11.5px;color:var(--text-2);flex-wrap:wrap}
.legend i{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:4px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{position:sticky;top:0;background:var(--surface);z-index:2;font-size:11.5px;color:var(--text-2);
  text-transform:uppercase;letter-spacing:.03em}
td.c,th.c{text-align:center}
tr:hover td{background:var(--surface-2)}
.thumb{width:44px;height:44px;border-radius:7px;border:1px solid var(--line);object-fit:contain;
  background:var(--surface);padding:2px}
.sc{display:inline-block;min-width:74px;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:650}
.sc2{background:color-mix(in oklab,var(--good) 18%,transparent);color:var(--good)}
.sc1{background:color-mix(in oklab,var(--warn) 20%,transparent);color:var(--warn)}
.sc0{background:color-mix(in oklab,var(--bad) 16%,transparent);color:var(--bad)}
.note{color:var(--text-2);font-size:12px;max-width:520px}
.kw{font-weight:650}
.filters{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:10px 0 14px}
select{font:inherit;font-size:12.5px;color:var(--text);background:var(--surface);
  border:1px solid var(--line);border-radius:8px;padding:6px 9px}
.pill{font-size:11.5px;padding:3px 9px;border-radius:999px;background:var(--surface-2);
  border:1px solid var(--line);color:var(--text-2)}
.lat{display:grid;grid-template-columns:96px 1fr 180px;gap:12px;align-items:center;margin-bottom:9px}
.track{position:relative;height:20px}
.track::before{content:"";position:absolute;left:0;right:0;top:9px;height:2px;background:var(--surface-2)}
.rng{position:absolute;top:9px;height:2px;opacity:.45;border-radius:2px}
.box{position:absolute;top:5px;height:10px;border-radius:4px}
.pt{position:absolute;top:2px;width:16px;height:16px;border-radius:50%;margin-left:-8px;
  box-shadow:0 0 0 2px var(--surface)}
.warnbox{border-left:3px solid var(--warn);padding-left:12px;margin:10px 0;color:var(--text-2);font-size:13px}
</style></head><body><div class="wrap">
<h1>Image Search — báo cáo tự chấm kết quả</h1>
<div class="sub" id="sub"></div>

<h2>Cách chấm</h2>
<div class="card" style="font-size:13px;color:var(--text-2)">
  Mỗi ảnh đầu vào được <b>mở ra xem tận mắt</b>, rồi đối chiếu với danh sách sản phẩm mà từng
  cơ chế trả về. Thang điểm cho mỗi ô (ảnh × cơ chế):
  <div style="margin-top:8px">
    <span class="sc sc2">Đạt</span> ít nhất 2 trong 3 kết quả đầu đúng mặt hàng có trong ảnh<br>
    <span class="sc sc1" style="margin-top:4px">Một phần</span> có kết quả đúng nhưng lẫn nhiều thứ khác,
      hoặc đúng ngành nhưng sai loại (ví dụ ảnh <i>ức gà</i> → trả <i>xương gà</i>)<br>
    <span class="sc sc0" style="margin-top:4px">Không đạt</span> không kết quả nào ở top đầu khớp với ảnh
  </div>
  <div class="warnbox" style="margin-top:12px">
    Đây là đánh giá của một người đọc ảnh và tên sản phẩm, không phải đo bằng ground-truth SKU.
    Ranh giới giữa <i>Đạt</i> và <i>Một phần</i> có phần chủ quan — hãy đọc cột ghi chú để tự kiểm lại
    những ca sát ranh giới. Điểm mạnh của cách này là bắt được lỗi ngữ nghĩa mà chỉ số kỹ thuật
    (totalHits, độ trễ) không thể hiện.
  </div>
</div>

<h2>Kết quả có khớp với ảnh không</h2>
<div class="tiles" id="tiles"></div>

<h2>Hiệu năng</h2>
<div class="card" id="lat"></div>

<h2>Chi tiết từng ảnh</h2>
<div class="filters">
  <label>Lọc <select id="f"><option value="all">Tất cả</option>
    <option value="anyfail">Có ít nhất 1 cơ chế không đạt</option>
    <option value="allfail">Cả 4 đều không đạt</option>
    <option value="allpass">Cả 4 đều đạt</option></select></label>
  <label>Sắp xếp <select id="s"><option value="stt">Theo STT</option>
    <option value="worst">Kém nhất trước</option></select></label>
  <span class="pill" id="count"></span>
</div>
<div class="card" style="padding:0;overflow:auto;max-height:80vh"><table id="tb"></table></div>
</div>
<script id="__d" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('__d').textContent);
const M = DATA.modes, R = DATA.rows, S = DATA.stats, N = DATA.n;
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const nf = (x) => x === null || x === undefined ? '—' : x.toLocaleString('vi-VN');
const SC = ['Không đạt', 'Một phần', 'Đạt'];

document.getElementById('sub').innerHTML =
  `${N} ảnh × ${M.length} cơ chế = ${N * M.length} ô đã chấm · sinh lúc ${esc(DATA.built)}`;

document.getElementById('tiles').innerHTML = M.map(([k, lab, css]) => {
  const s = S[k], p = (x) => (100 * x / N).toFixed(0);
  return `<div class="card tile">
    <h3><span class="dot${k === 'tm' ? ' striped' : ''}" style="background:var(${css})"></span>${lab}</h3>
    <div class="big">${p(s.pass)}%</div>
    <div class="sub" style="margin-bottom:8px">số ảnh trả kết quả ĐẠT</div>
    <div class="bar"><i class="ok" style="width:${p(s.pass)}%"></i><i class="pa" style="width:${p(s.part)}%"></i><i class="no" style="width:${p(s.fail)}%"></i></div>
    <div class="legend"><span><i class="ok" style="background:var(--good)"></i>${s.pass} đạt</span>
      <span><i class="pa" style="background:var(--warn)"></i>${s.part} một phần</span>
      <span><i class="no" style="background:var(--bad)"></i>${s.fail} không đạt</span></div>
    <div class="row" style="margin-top:8px"><span>Điểm trung bình (0–2)</span><b class="mono">${s.avg.toFixed(2)}</b></div>
    <div class="row"><span>Thời gian phản hồi p50</span><b class="mono">${nf(s.p50)} ms</b></div>
    <div class="row"><span>Ảnh trả &lt; 40 kết quả</span><b class="mono">${s.short}</b></div>
  </div>`;
}).join('');

const maxL = Math.max(...M.map(([k]) => S[k].max)) * 1.04;
document.getElementById('lat').innerHTML =
  `<div class="sub" style="margin-bottom:12px">Chấm = p50 · khối đậm = p50→p95 · vạch mảnh = nhanh nhất→chậm nhất</div>`
  + M.map(([k, lab, css]) => {
    const s = S[k], p = (v) => (100 * v / maxL).toFixed(2);
    return `<div class="lat"><div style="font-size:12.5px;display:flex;align-items:center;gap:7px">
      <span class="dot${k === 'tm' ? ' striped' : ''}" style="background:var(${css})"></span>${lab}</div>
      <div class="track">
        <div class="rng" style="left:${p(s.min)}%;width:${p(s.max) - p(s.min)}%;background:var(${css})"></div>
        <div class="box${k === 'tm' ? ' striped' : ''}" style="left:${p(s.p50)}%;width:${p(s.p95) - p(s.p50)}%;background:var(${css})"></div>
        <div class="pt" style="left:${p(s.p50)}%;background:var(${css})"></div>
      </div>
      <div class="mono" style="font-size:12px;color:var(--text-2);text-align:right">
        p50 <b style="color:var(--text)">${nf(s.p50)}</b> · p95 <b style="color:var(--text)">${nf(s.p95)}</b> ms</div>
    </div>`;
  }).join('')
  + `<div class="sub" style="margin-top:8px">0 ms → ${nf(Math.round(maxL))} ms</div>`;

function render() {
  const f = document.getElementById('f').value, srt = document.getElementById('s').value;
  let rows = R.filter((r) => {
    const v = M.map(([k]) => r.scores[k]);
    if (f === 'anyfail') return Math.min(...v) === 0;
    if (f === 'allfail') return Math.max(...v) === 0;
    if (f === 'allpass') return Math.min(...v) === 2;
    return true;
  });
  if (srt === 'worst') rows = [...rows].sort((a, b) =>
    M.reduce((s, [k]) => s + a.scores[k], 0) - M.reduce((s, [k]) => s + b.scores[k], 0));
  document.getElementById('count').textContent = `${rows.length} ảnh`;
  document.getElementById('tb').innerHTML =
    `<thead><tr><th>#</th><th>Ảnh</th><th>Keyword</th>`
    + M.map(([, lab]) => `<th class="c">${lab}</th>`).join('')
    + `<th>Nhận xét</th></tr></thead><tbody>`
    + rows.map((r) => `<tr>
        <td class="mono">${r.stt}</td>
        <td><img class="thumb" loading="lazy" src="${esc(r.img)}" alt=""></td>
        <td><span class="kw">${esc(r.keyword)}</span><br><span class="sub">${esc(r.lang)}</span></td>
        ${M.map(([k]) => `<td class="c"><span class="sc sc${r.scores[k]}">${SC[r.scores[k]]}</span>
           <div class="sub mono" style="margin-top:3px">${nf(r.took[k])} ms</div></td>`).join('')}
        <td class="note">${esc(r.note)}</td></tr>`).join('')
    + `</tbody>`;
}
['f', 's'].forEach((id) => { document.getElementById(id).onchange = render; });
render();
</script></body></html>
'''

if __name__ == '__main__':
    main()
