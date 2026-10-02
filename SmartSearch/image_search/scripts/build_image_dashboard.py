# -*- coding: utf-8 -*-
"""Dashboard so sanh cac co che image search (danh sach co che lay tu results/) + luu phan quyet "co che nao OK".

    python scripts/build_image_dashboard.py                  # sinh dashboard
    python scripts/build_image_dashboard.py --apply <export.json>   # nap phan quyet roi sinh lai
    python scripts/build_image_dashboard.py --open           # sinh xong mo luon

Vong doi phan quyet (giong compare_report.html cua repo):

    chon trong dropdown -> localStorage (thay ngay, chi trong may do)
        -> bam "Xuat ket qua" -> file JSON
        -> --apply file do  -> dashboard/verdict_state.json (nguon su that)
        -> sinh lai HTML    -> phan quyet nam san trong bao cao

Dashboard la BAN CHUP: no doc verdict_state.json luc SINH, khong phai luc mo.
Nap state xong ma khong sinh lai thi bao cao van hien so cu.
"""
import re, argparse, csv, glob, json, os, statistics, sys, webbrowser
from datetime import datetime

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        _s.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, 'results', 'excel_top40')
IMG_INDEX = os.path.join(ROOT, 'result_images', 'index.csv')
MANIFEST = os.path.join(ROOT, 'images', 'excel_keywords', 'manifest.json')
OUT_DIR = os.path.join(ROOT, 'dashboard')
OUT_HTML = os.path.join(OUT_DIR, 'image_search_dashboard.html')
STATE = os.path.join(OUT_DIR, 'verdict_state.json')

# Nhan/mau cua MOI co che tung chay nam o scripts/lib/modes.json (dung chung voi
# write_excel_results.py). Co che cua LAN CHAY HIEN TAI suy ra tu results/ trong
# set_modes() (user 2026-09-28 bo Titan, them Titan Multi Caption Type) - khong
# khai cung o day nua, nen doi MODES trong config.mjs la dashboard tu theo.
# Vong danh gia cu van hien dung nhan co che da bo nho mode_labels day du.
_MODES_JSON = json.load(open(os.path.join(ROOT, 'scripts', 'lib', 'modes.json'), encoding='utf-8'))
MODE_INFO = {x['mode']: x for x in _MODES_JSON['modes']}
RUN_NOTES = _MODES_JSON.get('run_notes', {})
MODES = []            # [(mode, label)] cua lan chay hien tai - set_modes()
VERDICT_OPTIONS = []  # Chon NHIEU co che (user 2026-09-22); 'none' khac han "chua danh gia"


def set_modes(runs):
    global MODES, VERDICT_OPTIONS
    present = {m for by_mode in runs.values() for m in by_mode}
    order = [m for m in MODE_INFO if m in present] + sorted(present - set(MODE_INFO))
    MODES = [(m, MODE_INFO.get(m, {}).get('label', m)) for m in order]
    VERDICT_OPTIONS = [(m, l) for m, l in MODES] + [('none', 'Không cái nào đạt')]


# Phan quyet tach theo LAN CHAY (user 2026-09-24): dev fix bug roi chay lai thi
# ket qua moi can dropdown danh gia moi, nhung lua chon cua lan truoc phai giu
# nguyen de doi chieu. Round = ngay chay (ran_at) cua bo ket qua. File state cu
# (truoc 2026-09-24) chi co mot 'verdicts' phang -> do la danh gia cho lan chay
# 2026-09-22.
LEGACY_ROUND = '2026-09-22'


def load_runs():
    runs = {}
    for f in glob.glob(os.path.join(RESULTS, '*', '*.json')):
        d = json.load(open(f, encoding='utf-8'))
        runs.setdefault(d['image_id'], {})[d['mode_requested']] = d
    return runs


def load_manifest():
    """image_id -> vi tri HIEN TAI trong sheet (dong, STT, keyword, ngon ngu).

    Khong dung field excel_row trong ket qua tho: do la so dong luc CHAY, chen
    hoac xoa dong trong Excel sau do la sai ngay.
    """
    if not os.path.exists(MANIFEST):
        sys.exit('Thieu %s — chay scripts/extract_excel_images.py truoc.' % MANIFEST)
    return {r['image_id']: r for r in json.load(open(MANIFEST, encoding='utf-8'))}


def load_img_index():
    idx = {}
    if os.path.exists(IMG_INDEX):
        with open(IMG_INDEX, encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                if r.get('file'):
                    idx[r['sku']] = r['file']
    return idx


def load_state():
    """{'updatedAt', 'rounds': {<ngay chay>: {'verdicts': {image_id: {...}}}}}"""
    if not os.path.exists(STATE):
        return {'updatedAt': None, 'rounds': {}}
    s = json.load(open(STATE, encoding='utf-8'))
    if 'rounds' not in s:
        s['rounds'] = {LEGACY_ROUND: {'verdicts': s.pop('verdicts', {})}} if s.get('verdicts') else {}
        s.pop('verdicts', None)
    return s


def round_verdicts(state, rnd):
    return state['rounds'].setdefault(rnd, {'verdicts': {}})['verdicts']


def current_round(runs):
    """Ngay chay moi nhat trong results/excel_top40 = round dang danh gia."""
    # 'round' (run-excel-top40.mjs --round) cho phep chay BO SUNG anh vao vong cu ma khong mo vong moi
    return max((d.get('round') or d['ran_at'][:10]) for by_mode in runs.values() for d in by_mode.values())


def save_state(state):
    os.makedirs(OUT_DIR, exist_ok=True)
    state['updatedAt'] = datetime.now().isoformat(timespec='seconds')
    with open(STATE, 'w', encoding='utf-8') as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)


def as_list(v):
    """File export cu ghi verdict la chuoi, ban moi ghi list -> quy ve list."""
    if not v:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def apply_export(path):
    """Nap file export tu dashboard vao verdict_state.json.

    Ba thu duoc nap: verdicts (co che cho KET QUA dat), performance (co che dat
    ve HIEU NANG), notes (ghi chu cua nguoi danh gia). Bo trong ca ba = xoa
    phan quyet cu, quay ve 'chua danh gia' — chon nham con go lai duoc.
    """
    payload = json.load(open(path, encoding='utf-8'))
    # File xuat tu dashboard truoc 2026-09-24 khong ghi round -> thuoc lan 22/09
    rnd = payload.get('round') or LEGACY_ROUND
    verdicts = payload.get('verdicts') or {}
    perf = payload.get('performance') or {}
    notes = payload.get('notes') or {}
    state = load_state()
    target = round_verdicts(state, rnd)
    applied = cleared = 0
    for image_id in set(verdicts) | set(perf) | set(notes):
        v, p, n = as_list(verdicts.get(image_id)), as_list(perf.get(image_id)), (notes.get(image_id) or '').strip()
        if v or p or n:
            target[image_id] = {
                'verdict': v, 'performance': p, 'note': n,
                'markedAt': datetime.now().isoformat(timespec='seconds'),
            }
            applied += 1
        elif image_id in target:
            del target[image_id]
            cleared += 1
    save_state(state)
    return applied, cleared, rnd


def stats_for(runs, mode):
    took, totals, ok = [], [], 0
    for by_mode in runs.values():
        d = by_mode.get(mode)
        if not d or not d['ok']:
            continue
        ok += 1
        if d['took_ms'] is not None:
            took.append(d['took_ms'])
        if d['total_hits'] is not None:
            totals.append(d['total_hits'])
    took.sort()
    pct = lambda xs, p: xs[min(len(xs) - 1, int(round((p / 100) * (len(xs) - 1))))] if xs else None
    return {
        'runs': ok,
        'p50': pct(took, 50), 'p95': pct(took, 95),
        'min': took[0] if took else None, 'max': took[-1] if took else None,
        'mean': round(statistics.mean(took)) if took else None,
        'total_median': round(statistics.median(totals)) if totals else None,
        'total_min': min(totals) if totals else None,
        'total_max': max(totals) if totals else None,
        'short': sum(1 for t in totals if t < 40),
    }


def build_payload(runs, img_idx, state, manifest, rnd):
    rows = []
    cur = state['rounds'].get(rnd, {}).get('verdicts', {})
    prev_rounds = sorted((r for r in state['rounds'] if r != rnd), reverse=True)
    known = [(i, b) for i, b in runs.items() if i in manifest]
    for image_id, by_mode in sorted(known, key=lambda kv: manifest[kv[0]]['excel_row']):
        any_run = next(iter(by_mode.values()))
        pos = manifest[image_id]
        row = {
            'image_id': image_id,
            'excel_row': pos['excel_row'],
            'stt': pos['stt'],
            'keyword': pos['keyword'],
            'lang': pos['lang'],
            'image_file': '../images/' + any_run['image_file'].replace('\\', '/'),
            'image_ref': any_run['image_ref'],
            'ran_at': any_run['ran_at'][:19].replace('T', ' '),
            'modes': {},
            'saved': {
                'v': as_list(cur.get(image_id, {}).get('verdict')),
                'p': as_list(cur.get(image_id, {}).get('performance')),
                'n': cur.get(image_id, {}).get('note') or '',
                # luc phan quyet duoc nap vao bao cao -> so voi luc QA sua trong trinh duyet
                't': cur.get(image_id, {}).get('markedAt') or '',
            },
            # Danh gia cac lan chay truoc: chi de xem, khong sua duoc tren dashboard
            'history': [{
                'round': pr,
                'v': as_list(state['rounds'][pr]['verdicts'][image_id].get('verdict')),
                'p': as_list(state['rounds'][pr]['verdicts'][image_id].get('performance')),
                'n': state['rounds'][pr]['verdicts'][image_id].get('note') or '',
            } for pr in prev_rounds if image_id in state['rounds'][pr]['verdicts']],
        }
        for mode, _ in MODES:
            d = by_mode.get(mode)
            if not d:
                row['modes'][mode] = None
                continue
            row['modes'][mode] = {
                'ok': d['ok'], 'http': d['http_status'],
                'total': d['total_hits'], 'returned': d['returned'],
                'took': d['took_ms'], 'client': d['client_ms'],
                'caption': (d.get('caption') or {}).get('query'),
                'outcome': (d.get('caption') or {}).get('outcome'),
                'reason': (d.get('caption') or {}).get('reason'),
                'items': [{
                    'no': p['no'], 'sku': p['sku'], 'name': p['name'],
                    'stock': p['stock_qty'], 'in_stock': p['in_stock'],
                    'img': ('../result_images/' + img_idx[p['sku']]) if p['sku'] in img_idx else None,
                } for p in d['top']],
            }
        rows.append(row)
    return rows


HTML = r'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Image Search — So sánh 4 cơ chế</title>
<style>
:root{
  color-scheme: light;
  --bg:#f6f6f4; --surface:#fcfcfb; --surface-2:#f0f0ed; --line:#dedcd6;
  --text:#14140f; --text-2:#52514e; --muted:#7b7a74;
  --vector:#2a78d6; --titan:#eb6834; --tmulti:#4a3aa7; --tmct:#eb6834; --nova:#1baf7a;
  --good:#1a7f45; --warn:#9a6a00; --bad:#b3261e;
  --shadow:0 1px 2px rgba(0,0,0,.05),0 4px 14px rgba(0,0,0,.05);
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  color-scheme: dark;
  --bg:#121210; --surface:#1a1a19; --surface-2:#232321; --line:#35342f;
  --text:#f7f7f2; --text-2:#c3c2b7; --muted:#8e8d84;
  --vector:#3987e5; --titan:#d95926; --tmulti:#9085e9; --tmct:#d95926; --nova:#199e70;
  --good:#4cc07d; --warn:#d9a441; --bad:#e66767;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 4px 14px rgba(0,0,0,.35);
}}
:root[data-theme="dark"]{
  color-scheme: dark;
  --bg:#121210; --surface:#1a1a19; --surface-2:#232321; --line:#35342f;
  --text:#f7f7f2; --text-2:#c3c2b7; --muted:#8e8d84;
  --vector:#3987e5; --titan:#d95926; --tmulti:#9085e9; --tmct:#d95926; --nova:#199e70;
  --good:#4cc07d; --warn:#d9a441; --bad:#e66767;
  --shadow:0 1px 2px rgba(0,0,0,.3),0 4px 14px rgba(0,0,0,.35);
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;}
h1{font-size:20px;margin:0 0 2px}
a{color:inherit}
.wrap{max-width:1600px;margin:0 auto;padding:20px 20px 80px}
.sub{color:var(--text-2);font-size:13px}
.mono{font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}

/* ---------- toolbar ---------- */
.bar{position:sticky;top:0;z-index:20;background:var(--bg);border-bottom:1px solid var(--line);
  padding:10px 0;margin-bottom:18px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.bar label{font-size:12px;color:var(--text-2);display:flex;gap:6px;align-items:center}
select,button{font:inherit;color:var(--text);background:var(--surface);border:1px solid var(--line);
  border-radius:8px;padding:6px 10px}
button{cursor:pointer}
button.primary{background:var(--text);color:var(--bg);border-color:var(--text);font-weight:600}
button.primary:disabled{opacity:.4;cursor:not-allowed}
.spacer{flex:1}
.runnote{font-size:13px;color:var(--text-2);background:var(--surface-2);border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:4px 0 10px}
.pill{font-size:12px;padding:3px 9px;border-radius:999px;background:var(--surface-2);
  border:1px solid var(--line);color:var(--text-2)}

/* ---------- summary ---------- */
.concl h2{margin:0 0 4px;font-size:15px}
.concl .lead{font-size:13px;color:var(--text-2);margin:0 0 10px}
.concl table{width:100%;border-collapse:collapse;font-size:13px}
.concl th,.concl td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
.concl th{font-size:11.5px;color:var(--muted);font-weight:600;text-transform:uppercase;letter-spacing:.03em}
.concl td.n{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.concl .pbar{height:8px;border-radius:0 4px 4px 0;min-width:2px}
.concl .ptrack{background:var(--surface-2);border-radius:4px;overflow:hidden;min-width:90px}
.concl .best{font-size:11px;font-weight:700;padding:1px 7px;border-radius:999px;background:color-mix(in oklab,var(--good) 14%,transparent);color:var(--good);margin-left:6px;white-space:nowrap}
.concl .foot{font-size:12px;color:var(--muted);margin-top:8px}
.concl-wrap{overflow-x:auto}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-bottom:14px}
.tile{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px;box-shadow:var(--shadow)}
.tile h3{margin:0 0 10px;font-size:13px;display:flex;align-items:center;gap:7px}
.dot{width:10px;height:10px;border-radius:3px;flex:none}
.dot.striped,.bbox.striped,.bfill.striped{background-image:repeating-linear-gradient(45deg,
  rgba(255,255,255,.55) 0 2px,transparent 2px 4px)}
.big{font-size:26px;font-weight:650;letter-spacing:-.02em}
.tile .row{display:flex;justify-content:space-between;gap:10px;padding:3px 0;font-size:12px;color:var(--text-2)}
.tile .row b{color:var(--text);font-weight:600}

.chart{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;
  margin-bottom:14px;box-shadow:var(--shadow)}
.chart h3{margin:0 0 3px;font-size:13px}
.chart .hint{color:var(--muted);font-size:12px;margin-bottom:12px}
.brow{display:grid;grid-template-columns:78px 1fr 190px;gap:12px;align-items:center;margin-bottom:10px}
.btrack{position:relative;height:22px}
.btrack::before{content:"";position:absolute;left:0;right:0;top:10px;height:2px;background:var(--surface-2)}
.brange{position:absolute;top:10px;height:2px;border-radius:2px;opacity:.45}
.bbox{position:absolute;top:6px;height:10px;border-radius:4px}
.bdot{position:absolute;top:3px;width:16px;height:16px;border-radius:50%;
  box-shadow:0 0 0 2px var(--surface);margin-left:-8px}
.blab{font-size:12px;color:var(--text-2);text-align:right;white-space:nowrap}
.blab b{color:var(--text)}
.baxis{display:grid;grid-template-columns:78px 1fr 190px;gap:12px;font-size:11px;color:var(--muted);
  margin-top:2px}
.baxis div:nth-child(2){display:flex;justify-content:space-between}

/* ---------- card ---------- */
/* overflow PHAI visible: panel cua dropdown bung ra ngoai day card, de hidden
   thi no bi cat mat (nhin nhu bam khong an). Bu lai phan bo goc bang cach cho
   chinh .chead / .cfoot / .cols bo goc. */
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;margin-bottom:16px;
  box-shadow:var(--shadow)}
.card:not(.open) .chead{border-radius:13px}
.card.open .chead{border-radius:13px 13px 0 0}
.card.open .cfoot{border-radius:0 0 13px 13px}
.card.judged{border-color:color-mix(in oklab,var(--good) 45%,var(--line))}
.chead{display:flex;gap:14px;align-items:flex-start;padding:14px 16px;border-bottom:1px solid var(--line);
  background:var(--surface-2);cursor:pointer;user-select:none}
.chead:hover{background:color-mix(in oklab,var(--text) 4%,var(--surface-2))}
.chead:focus-visible{outline:2px solid var(--vector);outline-offset:-2px}
.card:not(.open) .chead{border-bottom:0}
.chev{flex:none;width:18px;color:var(--muted);font-size:13px;margin-top:4px;transition:transform .12s}
.card.open .chev{transform:rotate(90deg)}
/* Thu gon: van phai doc duoc ngay ai hon ai -> 3 o tom tat, khong phai o trong */
.peek{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:8px}
@media (max-width:1400px){ .peek{grid-template-columns:repeat(2,1fr)} }
@media (max-width:900px){ .peek{grid-template-columns:1fr} }
.peek .pk{display:flex;gap:7px;align-items:baseline;font-size:12px;color:var(--text-2);min-width:0;
  overflow:hidden}
.peek .pk b{color:var(--text);white-space:nowrap}
.peek .pk>span:not(.p1){white-space:nowrap}
.peek .pk .p1{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.peek .pk.win b,.peek .pk.win{color:var(--good)}
.qimg{width:74px;height:74px;flex:none;border-radius:10px;border:1px solid var(--line);background:var(--surface);
  object-fit:contain;padding:4px}
.kw{font-size:16px;font-weight:650}
.meta{font-size:12px;color:var(--muted);margin-top:3px;word-break:break-all}
/* Khoi danh gia: MOT THANH NGANG chay het be ngang card, khong phai cot don
   ben phai. Cot ben phai lam card cao vong len va chua mot vung trong lon o
   giua — nhin thay ro trong anh chup user gui 2026-09-22. */
.review{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:10px;
  padding-top:10px;border-top:1px dashed var(--line)}
.rgroup{display:flex;align-items:center;gap:7px;flex:none}
.rgroup>span{font-size:11px;color:var(--muted);white-space:nowrap}
/* Dropdown chon nhieu: NUT + popup tu quan ly bang JS.
   Da thu <details>+<summary>: khi dong, Chrome van de lai mot hop layout cao
   ~78px cho phan noi dung, day ca hang danh gia phinh ra va tao khoang trong
   giua card (user bao "UI xau" 2026-09-22). Nut thuong thi cao dung bang chinh no. */
.ms{position:relative;flex:none;display:flex}   /* flex: bo qua text-node khoang trang
   giua cac the — de block thi khoang trang do tu tao mot dong cao ~20px, lam
   hang danh gia lech han so voi o ben canh */
.ms-btn{display:flex;align-items:center;gap:8px;height:30px;box-sizing:border-box;
  min-width:136px;max-width:240px;background:var(--surface);border:1px solid var(--line);
  border-radius:8px;padding:0 9px;font:inherit;font-size:12px;color:var(--text);cursor:pointer}
.ms-btn .txt{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left}
.ms-btn .car{color:var(--muted);font-size:10px;flex:none}
.ms-btn:hover{border-color:var(--text-2)}
.ms-btn[aria-expanded="true"]{border-color:var(--text-2);
  box-shadow:0 0 0 2px color-mix(in oklab,var(--vector) 22%,transparent)}
/* ten rieng, KHONG dung ".empty": class do da co san cho trang thai "khong co
   card nao khop bo loc" (padding:24px;text-align:center) -> nut bi phinh cao
   50px va chu bi can giua. Dung mat cong do moi tim ra. */
.ms-btn.ms-none .txt{color:var(--muted)}
.ms-panel{position:absolute;z-index:40;top:34px;left:0;min-width:196px;background:var(--surface);
  border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow);padding:5px}
.ms-panel label{display:flex;align-items:center;gap:8px;padding:5px 8px;border-radius:6px;
  font-size:12.5px;cursor:pointer;white-space:nowrap}
.ms-panel label:hover{background:var(--surface-2)}
.ms-panel input{accent-color:var(--vector);margin:0}
.ms-panel hr{border:0;border-top:1px solid var(--line);margin:4px 2px}
.note{flex:1;min-width:220px;height:30px;min-height:30px;resize:vertical;font:inherit;
  font-size:12px;line-height:1.35;color:var(--text);background:var(--surface);
  border:1px solid var(--line);border-radius:8px;padding:6px 9px}
.note:focus{outline:none;border-color:var(--text-2);
  box-shadow:0 0 0 2px color-mix(in oklab,var(--vector) 22%,transparent)}
.note.filled{border-color:color-mix(in oklab,var(--good) 50%,var(--line))}
.vstate{font-size:11px;color:var(--muted);flex:none;white-space:nowrap}
/* Nhan ngay cua moi hang danh gia + hang cua lan chay truoc (chi xem) */
.rtag{font-size:11px;font-weight:650;padding:2px 8px;border-radius:999px;flex:none;white-space:nowrap;
  background:color-mix(in oklab,var(--vector) 14%,transparent);color:var(--text)}
.review.prev{margin-top:6px;padding-top:6px}
.review.prev .rtag{background:var(--surface-2);color:var(--text-2);font-weight:600}
.ms-btn:disabled{cursor:default;opacity:.8;background:var(--surface-2)}
.ms-btn:disabled .car{visibility:hidden}
.pnote{flex:1;min-width:220px;font-size:12px;color:var(--text-2);white-space:pre-wrap}
.vstate.saved{color:var(--good)}
.vstate.pending{color:var(--warn)}

.cols{display:grid;grid-template-columns:repeat(4,1fr);gap:0}
@media (max-width:1400px){ .cols{grid-template-columns:repeat(2,1fr)} }
@media (max-width:800px){ .cols{grid-template-columns:1fr} }
.col{padding:12px 14px;border-right:1px solid var(--line);border-top:3px solid transparent}
.col:last-child{border-right:0}
.col.win{background:color-mix(in oklab,var(--good) 10%,transparent);border-top-color:var(--good)}
.mhead{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.mname{font-weight:650}
.okbadge{margin-left:auto;font-size:10.5px;font-weight:650;color:var(--good);
  border:1px solid color-mix(in oklab,var(--good) 55%,transparent);border-radius:999px;padding:2px 8px}
.okbadge.perf{color:var(--vector);border-color:color-mix(in oklab,var(--vector) 55%,transparent)}
.mstats{display:flex;gap:14px;font-size:12px;color:var(--text-2);margin-bottom:4px}
.mstats b{color:var(--text);font-size:14px;font-weight:650}
.capq{font-size:12px;color:var(--text-2);background:var(--surface-2);border:1px solid var(--line);
  border-radius:8px;padding:6px 8px;margin:6px 0}
.warnq{color:var(--warn)}
.items{list-style:none;margin:8px 0 0;padding:0;max-height:none}
.items li{display:flex;gap:9px;align-items:center;padding:5px 0;border-top:1px solid var(--line)}
.items li:first-child{border-top:0}
.rank{width:20px;flex:none;text-align:right;color:var(--muted);font-size:12px}
.thumb{width:40px;height:40px;flex:none;border-radius:7px;border:1px solid var(--line);object-fit:contain;
  background:var(--surface);padding:2px}
.thumb.miss{display:flex;align-items:center;justify-content:center;font-size:9px;color:var(--muted)}
.pname{flex:1;min-width:0;font-size:12.5px;line-height:1.35}
.psku{color:var(--muted);font-size:11px}
.stock{flex:none;font-size:11px;color:var(--text-2);text-align:right;min-width:52px}
.stock.out{color:var(--bad)}
.err{color:var(--bad);font-size:13px;padding:8px 0}
.empty{color:var(--muted);padding:24px;text-align:center}
.cfoot{border-top:1px solid var(--line);background:var(--surface-2);text-align:center;padding:8px;
  font-size:12px;color:var(--text-2);cursor:pointer;user-select:none}
.cfoot:hover{background:color-mix(in oklab,var(--text) 4%,var(--surface-2));color:var(--text)}

/* ---------- tooltip ---------- */
#tip{position:fixed;z-index:60;pointer-events:none;opacity:0;transition:opacity .1s;
  background:var(--surface);border:1px solid var(--line);border-radius:9px;padding:8px 10px;
  box-shadow:var(--shadow);font-size:12px;max-width:260px}
#tip b{display:block;margin-bottom:3px}
#toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(20px);z-index:70;
  background:var(--text);color:var(--bg);padding:10px 16px;border-radius:10px;font-size:13px;
  opacity:0;transition:.2s;pointer-events:none;max-width:88vw}
#toast.on{opacity:1;transform:translateX(-50%) translateY(0)}
</style></head><body>
<div class="wrap">
  <h1 id="title">Image Search — so sánh các cơ chế</h1>
  <div class="runnote" id="runnote"></div>
  <div class="sub" id="subtitle"></div>

  <div class="bar">
    <label>Lọc <select id="f-filter">
      <option value="all">Tất cả</option>
      <option value="todo">Chưa đánh giá</option>
      <option value="done">Đã đánh giá</option>
    </select></label>
    <label>Hiện cơ chế <select id="f-mode">
      <option value="all">Tất cả cơ chế</option>
    </select></label>
    <button id="btn-expand">Mở tất cả</button>
    <button id="btn-collapse">Thu tất cả</button>
    <label>Sắp xếp <select id="f-sort">
      <option value="stt">Theo STT keyword</option>
      <option value="nova">NovaLite ít kết quả nhất trước</option>
      <option value="slow">Chậm nhất trước</option>
    </select></label>
    <span class="spacer"></span>
    <span class="pill" id="tally"></span>
    <button id="btn-reset">Xoá lựa chọn chưa xuất</button>
    <button id="btn-export-legacy" hidden></button>
    <button class="primary" id="btn-export">Xuất kết quả đánh giá</button>
  </div>

  <div class="chart concl" id="conclusion"></div>
  <div class="tiles" id="tiles"></div>
  <div class="chart" id="latency"></div>
  <div id="cards"></div>
</div>
<div id="tip"></div><div id="toast"></div>
<script id="payload" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('payload').textContent);
const ROWS = DATA.rows, STATS = DATA.stats, META = DATA.meta;
// Co che cua lan chay nay [[mode, label, cssvar]] - suy ra tu results/, xem set_modes()
const MODES = DATA.modes;
// Ma hoa phu (soc cheo) cho co che de lan mau voi co che canh no
const STRIPED = new Set(DATA.striped);
const dotCls = (m) => 'dot' + (STRIPED.has(m) ? ' striped' : '');
document.getElementById('f-mode').insertAdjacentHTML('beforeend',
  MODES.map(([m, l]) => `<option value="${m}">Chỉ ${l}</option>`).join(''));
const VOPTS = DATA.verdict_options;                       // [[value,label],...]
// nhan cua MOI co che tung chay - hang danh gia lan truoc co the chon co che lan nay khong chay
const VLABEL = { ...DATA.mode_labels, ...Object.fromEntries(VOPTS) };
// Moi lan chay mot bo nho rieng: lua chon cho lan moi khong duoc de len lan truoc
const KEY = 'imgsearch_verdicts_' + META.report_id + '_' + META.round;
const ddmm = (d) => d ? d.slice(8, 10) + '/' + d.slice(5, 7) : '';

// localStorage giữ lựa chọn giữa các lần mở trên CÙNG máy này. Nguồn sự thật
// lâu dài vẫn là verdict_state.json: xuất file rồi --apply thì lựa chọn mới
// nằm trong chính báo cáo, mở ở máy khác cũng thấy.
let local = {};
try { local = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { local = {}; }
// Bo nho cu (truoc 2026-09-22) luu mot chuoi cho moi anh; nay la {v:[],p:[],n:''}
Object.keys(local).forEach((k) => {
  if (typeof local[k] === 'string') local[k] = { v: local[k] ? [local[k]] : [], p: [], n: '' };
});
const saveLocal = () => { try { localStorage.setItem(KEY, JSON.stringify(local)); } catch (e) {} };

// Ghi chu goi y cua Claude da duoc sua lai trong bao cao, nhung trinh duyet dang giu ban cu
// (QA sua do, chua xuat). Thay tung dong goi y CU ma QA chua dong vao bang dong cung co che
// o ban moi; dong QA tu viet/tu sua giu nguyen. Lua chon Ket qua / Hieu nang khong dong toi.
(() => {
  const STALE = META.stale_lines || {};
  const modeOf = (l) => (l.match(/^- (Titan Multi|Vector|Titan|NovaLite) (đạt|không đạt)/) || [])[1];
  let fixed = 0;
  ROWS.forEach((r) => {
    const l = local[r.image_id], stale = STALE[r.image_id];
    if (!l || !l.n || !stale) return;
    const fresh = {};
    r.saved.n.split('\n').forEach((x) => { const m = modeOf(x); if (m) fresh[m] = x; });
    const n = l.n.split('\n').map((x) => (stale.includes(x) && fresh[modeOf(x)]) ? fresh[modeOf(x)] : x).join('\n');
    if (n !== l.n) { l.n = n; fixed++; }
  });
  if (fixed) { saveLocal(); console.info('Cap nhat ghi chu goi y cu trong trinh duyet:', fixed); }
})();

// Ban trong bao cao MOI HON lan sua cuoi trong trinh duyet (vd Claude --apply sau khi QA
// xuat file, hoac sua ho QA) -> bo ban trong trinh duyet, hien ban bao cao. Ban luu truoc khi
// co moc thoi gian (khong co .t) coi nhu cu hon moi phan quyet da nap vao bao cao.
(() => {
  let dropped = 0;
  ROWS.forEach((r) => {
    const l = local[r.image_id];
    if (!l || !r.saved.t) return;
    const lt = l.t ? Date.parse(l.t) : 0, st = Date.parse(r.saved.t);
    if (st > lt) { delete local[r.image_id]; dropped++; }
  });
  if (dropped) { saveLocal(); console.info('Bo lua chon cu trong trinh duyet (bao cao moi hon):', dropped); }
})();

// Dashboard truoc 2026-09-24 luu lua chon duoi khoa KHONG co ngay. Lua chon chua
// xuat o do la cua lan 22/09 (luc doi sang khoa theo lan chay con 56 cai chua
// xuat) -> doc lai de hien o hang 22/09 va cho xuat rieng, khong de mat.
let legacyLocal = {};
if (META.round !== META.legacy_round) {
  try { legacyLocal = JSON.parse(localStorage.getItem('imgsearch_verdicts_' + META.report_id) || '{}'); } catch (e) { legacyLocal = {}; }
  Object.keys(legacyLocal).forEach((k) => {
    if (typeof legacyLocal[k] === 'string') legacyLocal[k] = { v: legacyLocal[k] ? [legacyLocal[k]] : [], p: [], n: '' };
  });
}
// Hang danh gia cac lan truoc cua mot anh; lan 22/09 uu tien ban chua xuat trong trinh duyet
const historyOf = (r) => {
  const hs = (r.history || []).map((h) => ({ ...h }));
  const l = legacyLocal[r.image_id];
  if (l) {
    let h = hs.find((x) => x.round === META.legacy_round);
    if (!h) { h = { round: META.legacy_round, v: [], p: [], n: '' }; hs.push(h); hs.sort((a, b) => b.round.localeCompare(a.round)); }
    const differs = !same(l.v || [], h.v) || !same(l.p || [], h.p) || (l.n || '') !== (h.n || '');
    if (differs) Object.assign(h, { v: l.v || [], p: l.p || [], n: l.n || '', pending: true });
  }
  return hs.filter((h) => h.v.length || h.p.length || (h.n || '').trim());
};
const blank = () => ({ v: [], p: [], n: '' });
const pick = (r) => local[r.image_id] || { v: r.saved.v, p: r.saved.p, n: r.saved.n };
const same = (a, b) => a.length === b.length && a.every((x) => b.includes(x));
const isPending = (r) => {
  if (!(r.image_id in local)) return false;
  const l = local[r.image_id];
  return !same(l.v, r.saved.v) || !same(l.p, r.saved.p) || (l.n || '') !== (r.saved.n || '');
};
const judged = (r) => { const s = pick(r); return s.v.length || s.p.length || (s.n || '').trim(); };
const editLocal = (id, fn) => {
  const r = ROWS.find((x) => x.image_id === id);
  if (!(id in local)) local[id] = { v: [...r.saved.v], p: [...r.saved.p], n: r.saved.n || '' };
  fn(local[id]);
  local[id].t = new Date().toISOString();
  saveLocal();
};

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const nf = (n) => n === null || n === undefined ? '—' : n.toLocaleString('vi-VN');

/* ---------------- tooltip ---------------- */
const tip = $('#tip');
function showTip(e, html) {
  tip.innerHTML = html; tip.style.opacity = 1;
  const r = tip.getBoundingClientRect();
  tip.style.left = Math.min(e.clientX + 14, innerWidth - r.width - 10) + 'px';
  tip.style.top = Math.min(e.clientY + 14, innerHeight - r.height - 10) + 'px';
}
const hideTip = () => { tip.style.opacity = 0; };

let toastTimer;
function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('on');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('on'), 3200);
}

/* ---------------- summary ---------------- */
function renderTiles() {
  const full = (d) => d ? d.slice(8, 10) + '/' + d.slice(5, 7) + '/' + d.slice(0, 4) : '';
  $('#title').textContent = `Image Search — so sánh ${MODES.length} cơ chế · lần chạy ${full(META.round)}`;
  document.title = `Image Search — ${MODES.length} cơ chế · ${full(META.round)}`;
  $('#runnote').innerHTML = `<b>Lần chạy ${full(META.round)}</b> · cơ chế: ${MODES.map(([, l]) => esc(l)).join(', ')}`
    + (META.run_note ? ` · ${esc(META.run_note)}` : '');
  $('#subtitle').innerHTML = `${ROWS.length} ảnh · ${ROWS.length * MODES.length} lượt gọi API · chạy ${esc(META.ran_at)} · `
    + `store <b>${esc(META.store)}</b> · lang <b>${esc(META.lang)}</b> · sinh lúc ${esc(META.built_at)}`
    + (META.prev_rounds.length ? ` · đánh giá lần trước (${META.prev_rounds.map(ddmm).join(', ')}) hiện ngay dưới hàng đánh giá của lần này, chỉ xem` : '');
  $('#tiles').innerHTML = MODES.map(([m, label, cssvar]) => {
    const s = STATS[m];
    return `<div class="tile">
      <h3><span class="${dotCls(m)}" style="background:var(${cssvar})"></span>${label}<span class="sub" style="font-weight:400"> · ${esc(META.mode_api[m])}</span></h3>
      <div class="big mono">${nf(s.p50)} ms</div>
      <div class="sub" style="margin-bottom:8px">thời gian phản hồi (p50)</div>
      <div class="row"><span>p95 / chậm nhất</span><b class="mono">${nf(s.p95)} / ${nf(s.max)} ms</b></div>
      <div class="row"><span>Tổng KQ (trung vị)</span><b class="mono">${nf(s.total_median)}</b></div>
      <div class="row"><span>Tổng KQ thấp nhất–cao nhất</span><b class="mono">${nf(s.total_min)}–${nf(s.total_max)}</b></div>
      <div class="row"><span>Ảnh trả &lt; 40 KQ</span><b class="mono">${nf(s.short)}</b></div>
      <div class="row"><span>Kết quả đạt</span><b class="mono" data-win="${m}">0</b></div>
      <div class="row"><span>Hiệu năng đạt</span><b class="mono" data-perf="${m}">0</b></div>
      ${s.total_min === 200 && s.total_max === 200
        ? '<div class="sub" style="margin-top:8px;color:var(--warn)">200 ở mọi ảnh là trần top-K của tìm kiếm vector, không phải tổng sản phẩm khớp — đừng so con số này với NovaLite.</div>'
        : ''}
    </div>`;
  }).join('');
}

function renderLatency() {
  // Ba cơ chế chênh nhau vài chục ms trên nền dao động hàng trăm ms, nên vẽ p50
  // thành 3 cột cạnh nhau sẽ ra 3 thanh gần bằng nhau — nhìn như có khác biệt
  // mà thật ra không. Vẽ dải phân bố: vạch mảnh = nhanh nhất→chậm nhất,
  // khối đậm = p50→p95, chấm = p50. Các dải chồng nhau chính là kết luận.
  const max = Math.max(...MODES.map(([m]) => STATS[m].max || 0)) * 1.04;
  const pct = (v) => (v / max) * 100;
  const bars = MODES.map(([m, label, cssvar]) => {
    const s = STATS[m];
    return `<div class="brow">
      <div style="font-size:12px;display:flex;align-items:center;gap:6px">
        <span class="${dotCls(m)}" style="background:var(${cssvar})"></span>${label}</div>
      <div class="btrack" data-mode="${m}">
        <div class="brange" style="left:${pct(s.min).toFixed(2)}%;width:${(pct(s.max) - pct(s.min)).toFixed(2)}%;background:var(${cssvar})"></div>
        <div class="bbox${STRIPED.has(m) ? ' striped' : ''}" style="left:${pct(s.p50).toFixed(2)}%;width:${(pct(s.p95) - pct(s.p50)).toFixed(2)}%;background:var(${cssvar})"></div>
        <div class="bdot" style="left:${pct(s.p50).toFixed(2)}%;background:var(${cssvar})"></div>
      </div>
      <div class="blab mono">p50 <b>${nf(s.p50)}</b> · p95 <b>${nf(s.p95)}</b> ms</div></div>`;
  }).join('');
  $('#latency').innerHTML = `<h3>Thời gian phản hồi backend (tookMs)</h3>
    <div class="hint">Chấm = p50, khối đậm = p50→p95, vạch mảnh = nhanh nhất→chậm nhất (${ROWS.length} lượt mỗi cơ chế).
      Không gồm thời gian upload ảnh — đây là số backend tự báo.</div>
    ${bars}
    <div class="baxis"><div></div><div><span>0 ms</span><span>${nf(Math.round(max))} ms</span></div><div></div></div>`;
  $('#latency').querySelectorAll('.btrack').forEach((el) => {
    const s = STATS[el.dataset.mode];
    const label = MODES.find(([m]) => m === el.dataset.mode)[1];
    el.onmousemove = (e) => showTip(e, `<b>${label}</b>p50 ${nf(s.p50)} ms · p95 ${nf(s.p95)} ms<br>`
      + `nhanh nhất ${nf(s.min)} ms · chậm nhất ${nf(s.max)} ms<br>trung bình ${nf(s.mean)} ms trên ${s.runs} lượt`);
    el.onmouseleave = hideTip;
  });
}

/* ---------------- cards ---------------- */
// Card thu gọn mặc định: mở hết mọi ảnh x mọi cơ chế x 40 sản phẩm cùng lúc là
// ~3.200 dòng kèm ảnh, cuộn tìm một keyword thành cực hình. Mở ra mới dựng
// danh sách sản phẩm, nên thu lại cũng trả luôn DOM đó về.
const expanded = new Set();
const currentShown = () => {
  const only = $('#f-mode').value;
  return only === 'all' ? MODES : MODES.filter(([m]) => m === only);
};

function modeCol(r, m, label, cssvar) {
  const d = r.modes[m];
  if (!d) return `<div class="col"><div class="mhead"><span class="${dotCls(m)}" style="background:var(${cssvar})"></span>
    <span class="mname">${label}</span></div><div class="err">chưa chạy</div></div>`;
  if (!d.ok) return `<div class="col"><div class="mhead"><span class="${dotCls(m)}" style="background:var(${cssvar})"></span>
    <span class="mname">${label}</span></div><div class="err">Lỗi HTTP ${d.http}</div></div>`;
  const sel = pick(r);
  const winV = sel.v.includes(m), winP = sel.p.includes(m);
  const win = winV ? ' win' : '';
  const shortWarn = d.total < 40 ? ' warnq' : '';
  const cap = d.caption
    ? `<div class="capq">Nova Lite đọc ảnh thành: <b>“${esc(d.caption)}”</b>${
        d.outcome && d.outcome !== 'query' ? ' · outcome: ' + esc(d.outcome) : ''}</div>`
    : (d.outcome ? `<div class="capq warnq">Nova Lite không sinh được câu tìm kiếm — outcome
        <b>${esc(d.outcome)}</b>${d.reason ? ' · reason <b>' + esc(d.reason) + '</b>' : ''}</div>` : '');
  const items = d.items.map((p) => `<li>
      <span class="rank mono">${p.no}</span>
      ${p.img ? `<img class="thumb" loading="lazy" src="${esc(p.img)}" alt="">`
              : `<span class="thumb miss">n/a</span>`}
      <span class="pname">${esc(p.name)}<br><span class="psku mono">${esc(p.sku)}</span></span>
      <span class="stock mono${p.in_stock ? '' : ' out'}">${p.in_stock ? 'tồn ' + nf(p.stock) : 'hết hàng'}</span>
    </li>`).join('');
  return `<div class="col${win}">
    <div class="mhead"><span class="${dotCls(m)}" style="background:var(${cssvar})"></span><span class="mname">${label}</span>
      ${winV ? '<span class="okbadge">✓ kết quả đạt</span>' : ''}
      ${winP ? '<span class="okbadge perf">✓ hiệu năng đạt</span>' : ''}</div>
    <div class="mstats">
      <span>Tổng KQ <b class="mono${shortWarn}">${nf(d.total)}</b></span>
      <span>Trả về <b class="mono">${nf(d.returned)}</b></span>
      <span>Phản hồi <b class="mono">${nf(d.took)} ms</b></span>
      <span>Hiện <b class="mono">${d.items.length}</b> SP</span>
    </div>${cap}${items ? `<ul class="items">${items}</ul>` : '<div class="err">Không có sản phẩm nào trả về</div>'}</div>`;
}

// Dòng tóm tắt lúc thu gọn — thu lại không có nghĩa là không thấy gì:
// vẫn đọc được tổng KQ, thời gian phản hồi và sản phẩm hạng 1 của mọi cơ chế.
function peekHTML(r, shown) {
  return `<div class="peek">` + shown.map(([m, label, cssvar]) => {
    const d = r.modes[m];
    const win = pick(r).v.includes(m) ? ' win' : '';
    if (!d || !d.ok) return `<div class="pk${win}"><span class="${dotCls(m)}" style="background:var(${cssvar})"></span>
      <span>${label}</span><b>${d ? 'lỗi ' + d.http : 'chưa chạy'}</b></div>`;
    const top1 = d.items[0] ? d.items[0].name : '—';
    return `<div class="pk${win}"><span class="${dotCls(m)}" style="background:var(${cssvar})"></span>
      <span>${label}</span><b class="mono">${nf(d.total)} KQ</b><b class="mono">${nf(d.took)} ms</b>
      <span class="p1" title="${esc(top1)}">#1 ${esc(top1)}</span></div>`;
  }).join('') + `</div>`;
}

// Mot dropdown chon nhieu: <details> + checkbox. Tom tat tren summary de thu
// gon van biet da chon gi, khong phai bung ra moi thay.
function multiSelect(id, kind, chosen, placeholder, readonly) {
  const labels = chosen.map((v) => VLABEL[v] || v);
  const boxes = VOPTS.map(([val, lab]) => (val === 'none' ? '<hr>' : '')
    + `<label><input type="checkbox" data-ms="${kind}"
      data-id="${id}" value="${val}"${chosen.includes(val) ? ' checked' : ''}> ${esc(lab)}</label>`).join('');
  const text = labels.join(', ') || placeholder;
  return `<span class="ms">
    <button type="button" class="ms-btn${labels.length ? '' : ' ms-none'}" aria-expanded="false"
      title="${esc(text)}"${readonly ? ' disabled' : ''}><span class="txt">${esc(text)}</span><span class="car">▾</span></button>
    ${readonly ? '' : `<div class="ms-panel" hidden>${boxes}</div>`}</span>`;
}

function cardHTML(r, shown) {
  const sel = pick(r);
  const open = expanded.has(r.image_id);
  const state = isPending(r)
    ? '<span class="vstate pending">chưa xuất — mới lưu trong trình duyệt</span>'
    : (judged(r) ? '<span class="vstate saved">đã lưu trong báo cáo</span>'
                 : '<span class="vstate">chưa đánh giá</span>');
  return `<div class="card${judged(r) ? ' judged' : ''}${open ? ' open' : ''}" data-id="${r.image_id}">
    <div class="chead" role="button" tabindex="0" aria-expanded="${open}"
         title="${open ? 'Thu gọn' : 'Mở xem đủ 40 sản phẩm của mọi cơ chế'}">
      <span class="chev">▶</span>
      <img class="qimg" loading="lazy" src="${esc(r.image_file)}" alt="">
      <div style="min-width:0;flex:1">
        <div class="kw">${r.stt}. ${esc(r.keyword)} <span class="pill">${esc(r.lang)}</span></div>
        <div class="meta">dòng Excel ${r.excel_row} · ${esc(r.image_id)} · ${esc(r.image_ref || '')}</div>
        ${open ? '' : peekHTML(r, shown)}
        <div class="review" onclick="event.stopPropagation()">
          <span class="rtag" title="Đánh giá cho lần chạy ${esc(META.round)} — kết quả đang hiện là của lần này">Lần ${ddmm(META.round)}</span>
          <div class="rgroup"><span>Kết quả</span>${multiSelect(r.image_id, 'v', sel.v, 'Chưa đánh giá')}</div>
          <div class="rgroup"><span>Hiệu năng</span>${multiSelect(r.image_id, 'p', sel.p, 'Chưa đánh giá')}</div>
          <textarea class="note${(sel.n || '').trim() ? ' filled' : ''}" data-note="${r.image_id}" rows="1"
            placeholder="Ghi chú của người đánh giá…">${esc(sel.n || '')}</textarea>
          ${state}
        </div>
        ${historyOf(r).map((h) => `<div class="review prev" onclick="event.stopPropagation()">
          <span class="rtag" title="Đánh giá cho lần chạy ${esc(h.round)} — chỉ xem, không sửa">Lần ${ddmm(h.round)}</span>
          <div class="rgroup"><span>Kết quả</span>${multiSelect(r.image_id, 'v', h.v, 'Chưa đánh giá', true)}</div>
          <div class="rgroup"><span>Hiệu năng</span>${multiSelect(r.image_id, 'p', h.p, 'Chưa đánh giá', true)}</div>
          <span class="pnote">${esc(h.n || '')}</span>
          ${h.pending ? '<span class="vstate pending">chưa xuất — mới lưu trong trình duyệt</span>' : ''}
        </div>`).join('')}
      </div>
    </div>
    ${open ? `<div class="cols" style="grid-template-columns:repeat(${shown.length},1fr)">
      ${shown.map(([m, l, c]) => modeCol(r, m, l, c)).join('')}</div>
      <div class="cfoot">▲ Thu gọn</div>` : ''}
  </div>`;
}

function bindCard(el) {
  const id = el.dataset.id;
  // Panel bung ra che mat o ben canh -> mo cai nay thi dong moi cai khac.
  el.querySelectorAll('.ms-btn').forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const panel = btn.nextElementSibling;
      const willOpen = panel.hidden;
      closeAllPanels();
      panel.hidden = !willOpen;
      btn.setAttribute('aria-expanded', String(willOpen));
    };
  });
  const head = el.querySelector('.chead');
  // Bấm vào khối đánh giá thì KHÔNG được coi là bấm mở/thu card
  const toggle = (e) => { if (e.target.closest('.review')) return; toggleCard(id); };
  head.onclick = toggle;
  const foot = el.querySelector('.cfoot');
  if (foot) foot.onclick = () => toggleCard(id);
  // CHỈ nhận phím khi chính header đang được focus. Ô ghi chú và các checkbox
  // nằm BÊN TRONG header, nên nếu không chặn ở đây thì mỗi dấu cách người dùng
  // gõ trong ghi chú sẽ nổi bọt lên đây và đóng/mở card — gõ được đúng một từ.
  head.onkeydown = (e) => {
    if (e.target !== head) return;
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleCard(id); }
  };
  el.querySelectorAll('input[data-ms]').forEach((box) => {
    box.onchange = () => {
      const kind = box.dataset.ms, val = box.value;
      editLocal(id, (st) => {
        let arr = st[kind];
        if (box.checked) {
          // "Không cái nào đạt" loại trừ các cơ chế, và ngược lại
          arr = val === 'none' ? ['none'] : [...arr.filter((x) => x !== 'none'), val];
        } else {
          arr = arr.filter((x) => x !== val);
        }
        st[kind] = arr;
      });
      const row = ROWS.find((r) => r.image_id === id);
      const l = local[id];
      if (same(l.v, row.saved.v) && same(l.p, row.saved.p) && (l.n || '') === (row.saved.n || '')) delete local[id];
      saveLocal();
      // Bộ lọc theo trạng thái đánh giá thì card có thể phải biến mất -> vẽ lại cả danh sách
      if ($('#f-filter').value !== 'all') renderCards(); else { replaceCard(id, true); renderTally(); }
    };
  });
  const note = el.querySelector('textarea[data-note]');
  if (note) {
    let t;
    note.oninput = () => {
      note.classList.toggle('filled', !!note.value.trim());
      clearTimeout(t);
      // Go phim thi khong ve lai card (mat con tro) — chi luu, tre 400ms
      t = setTimeout(() => {
        editLocal(id, (st) => { st.n = note.value; });
        const row = ROWS.find((r) => r.image_id === id);
        const l = local[id];
        if (same(l.v, row.saved.v) && same(l.p, row.saved.p) && (l.n || '') === (row.saved.n || '')) delete local[id];
        saveLocal(); renderTally();
      }, 400);
    };
  }
}

function replaceCard(id, keepPanels) {
  const old = document.querySelector(`.card[data-id="${id}"]`);
  if (!old) return;
  const openPanels = keepPanels
    ? [...old.querySelectorAll('.ms-panel')].map((d) => !d.hidden) : null;
  const tmp = document.createElement('div');
  tmp.innerHTML = cardHTML(ROWS.find((r) => r.image_id === id), currentShown());
  const fresh = tmp.firstElementChild;
  old.replaceWith(fresh);
  if (openPanels) [...fresh.querySelectorAll('.ms-panel')].forEach((d, i) => {
    d.hidden = !openPanels[i];
    d.previousElementSibling.setAttribute('aria-expanded', String(!!openPanels[i]));
  });
  bindCard(fresh);
  return fresh;
}

function toggleCard(id) {
  const wasOpen = expanded.has(id);
  wasOpen ? expanded.delete(id) : expanded.add(id);
  const fresh = replaceCard(id);
  // Thu một card đang dài cả màn hình sẽ kéo tụt nội dung phía dưới lên trên
  // chỗ đang nhìn -> kéo lại đầu card cho khỏi lạc.
  if (wasOpen && fresh && fresh.getBoundingClientRect().top < 0) {
    fresh.scrollIntoView({ block: 'start' });
  }
}

function renderCards() {
  const filter = $('#f-filter').value, sort = $('#f-sort').value;
  const shown = currentShown();
  let rows = ROWS.filter((r) => filter === 'all' || (filter === 'done' ? !!judged(r) : !judged(r)));
  if (sort === 'nova') rows = [...rows].sort((a, b) => (a.modes.caption?.total ?? 1e9) - (b.modes.caption?.total ?? 1e9));
  else if (sort === 'slow') rows = [...rows].sort((a, b) =>
    Math.max(...MODES.map(([m]) => b.modes[m]?.took ?? 0)) - Math.max(...MODES.map(([m]) => a.modes[m]?.took ?? 0)));
  else rows = [...rows].sort((a, b) => a.stt - b.stt);

  $('#cards').innerHTML = rows.length
    ? rows.map((r) => cardHTML(r, shown)).join('')
    : '<div class="empty">Không có ảnh nào khớp bộ lọc.</div>';
  $('#cards').querySelectorAll('.card').forEach(bindCard);
  renderTally();
}

// Ket luan (user 2026-09-29): moi co che dat bao nhieu % / TONG so testcase (moi anh = 1 case),
// ca ve ket qua lan hieu nang. Mau so la tong so anh cua lan chay, KHONG phai so anh da danh gia,
// nen con anh chua cham thi ti le dang thap hon thuc te -> ghi ro o chan bang.
function renderConclusion(cv, cp, done) {
  const N = ROWS.length;
  const pct = (x) => N ? 100 * x / N : 0;
  const fmt = (x) => pct(x).toFixed(1).replace('.', ',') + '%';
  const bestV = Math.max(...MODES.map(([m]) => cv[m] || 0));
  const bestP = Math.max(...MODES.map(([m]) => cp[m] || 0));
  const cell = (x, css, best) => `<td class="n">${x}/${N}</td><td class="n"><b>${fmt(x)}</b>${best && x ? '<span class="best">cao nhất</span>' : ''}</td>
      <td style="width:22%"><div class="ptrack"><div class="pbar" style="width:${pct(x).toFixed(1)}%;background:var(${css})"></div></div></td>`;
  const rows = MODES.map(([m, label, css], i) => `<tr><td><span class="${dotCls(m)}" style="background:var(${css})"></span> ${i + 1}. ${esc(label)}</td>
      ${cell(cv[m] || 0, css, (cv[m] || 0) === bestV)}${cell(cp[m] || 0, css, (cp[m] || 0) === bestP)}</tr>`).join('');
  const win = MODES.filter(([m]) => (cv[m] || 0) === bestV).map(([, l]) => l).join(', ');
  const fast = MODES.filter(([m]) => (cp[m] || 0) === bestP).map(([, l]) => l).join(', ');
  const none = cv.none || 0;
  $('#conclusion').innerHTML = `<h2>Kết luận lần ${ddmm(META.round)} — ${N} testcase (mỗi ảnh là 1 case)</h2>
    <p class="lead">Kết quả tốt nhất: <b>${esc(win)}</b> (${fmt(bestV)}) · Hiệu năng tốt nhất: <b>${esc(fast)}</b> (${fmt(bestP)})
      · Không cơ chế nào đạt: <b>${none}/${N}</b> (${fmt(none)})</p>
    <div class="concl-wrap"><table>
      <thead><tr><th>Cơ chế</th><th class="n" colspan="3">Kết quả đạt / tổng case</th><th class="n" colspan="3">Hiệu năng đạt / tổng case</th></tr></thead>
      <tbody>${rows}</tbody></table></div>
    <div class="foot">Tỉ lệ = số ảnh QA chọn cơ chế đó ÷ tổng ${N} ảnh. Một ảnh có thể đạt ở nhiều cơ chế nên các dòng cộng lại lớn hơn 100%.
      ${done < N ? `<b>Còn ${N - done} ảnh chưa đánh giá</b> — tỉ lệ vẫn tính trên tổng ${N}, sẽ tăng khi chấm xong.` : 'Đã đánh giá đủ ' + N + '/' + N + ' ảnh.'}</div>`;
}

function renderTally() {
  // Mot keyword co the chon nhieu co che -> tong cac cot se lon hon so keyword.
  const cv = {}, cp = {};
  let done = 0, pending = 0, notes = 0;
  ROWS.forEach((r) => {
    const s = pick(r);
    if (judged(r)) done++;
    if ((s.n || '').trim()) notes++;
    s.v.forEach((m) => { cv[m] = (cv[m] || 0) + 1; });
    s.p.forEach((m) => { cp[m] = (cp[m] || 0) + 1; });
    if (isPending(r)) pending++;
  });
  const parts = VOPTS.map(([val, lab]) => `${lab.replace(' đạt', '')} ${cv[val] || 0}`);
  $('#tally').textContent = `Lần ${ddmm(META.round)}: ${done}/${ROWS.length} đã đánh giá · kết quả: ${parts.join(' · ')}`
    + (notes ? ` · ${notes} ghi chú` : '') + (pending ? ` · ${pending} chưa xuất` : '');
  const N = ROWS.length;
  const pctx = (x) => N ? (100 * x / N).toFixed(1).replace('.', ',') + '%' : '—';
  document.querySelectorAll('[data-win]').forEach((el) => { const x = cv[el.dataset.win] || 0; el.textContent = `${x}/${N} · ${pctx(x)}`; });
  document.querySelectorAll('[data-perf]').forEach((el) => { const x = cp[el.dataset.perf] || 0; el.textContent = `${x}/${N} · ${pctx(x)}`; });
  renderConclusion(cv, cp, done);
  $('#btn-export').disabled = done === 0;
  const lp = ROWS.filter((r) => historyOf(r).some((h) => h.pending)).length;
  const lb = $('#btn-export-legacy');
  lb.hidden = !lp;
  lb.textContent = `Xuất đánh giá ${ddmm(META.legacy_round)} chưa xuất (${lp})`;
}

/* ---------------- export ---------------- */
$('#btn-export').onclick = () => {
  const verdicts = {}, performance = {}, notes = {};
  ROWS.forEach((r) => {
    const s = pick(r);
    if (s.v.length) verdicts[r.image_id] = s.v;
    if (s.p.length) performance[r.image_id] = s.p;
    if ((s.n || '').trim()) notes[r.image_id] = s.n.trim();
  });
  const payload = {
    kind: 'image_search_verdicts', report_id: META.report_id, round: META.round, store: META.store,
    exported_at: new Date().toISOString(), verdicts, performance, notes,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  const ts = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '').replace(/(\d{8})(\d{4})/, '$1_$2');
  a.download = `image_search_verdicts_${META.round.replace(/-/g, '')}_${ts}.json`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  toast('Đã tải file. Đưa cho Claude chạy: python scripts/build_image_dashboard.py --apply <file> — lựa chọn sẽ nằm sẵn trong báo cáo lần sau.');
};

$('#btn-export-legacy').onclick = () => {
  const verdicts = {}, performance = {}, notes = {};
  ROWS.forEach((r) => {
    const h = historyOf(r).find((x) => x.round === META.legacy_round && x.pending);
    if (!h) return;
    if (h.v.length) verdicts[r.image_id] = h.v;
    if (h.p.length) performance[r.image_id] = h.p;
    if ((h.n || '').trim()) notes[r.image_id] = h.n.trim();
  });
  const payload = {
    kind: 'image_search_verdicts', report_id: META.report_id, round: META.legacy_round, store: META.store,
    exported_at: new Date().toISOString(), verdicts, performance, notes,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `image_search_verdicts_${META.legacy_round.replace(/-/g, '')}_chuaxuat.json`;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  toast(`Đã tải đánh giá lần ${ddmm(META.legacy_round)}. Đưa cho Claude chạy --apply để lưu vào báo cáo.`);
};

$('#btn-reset').onclick = () => {
  if (!Object.keys(local).length) { toast('Không có lựa chọn nào chưa xuất.'); return; }
  if (!confirm('Xoá các lựa chọn chưa xuất (chỉ trong trình duyệt)? Phần đã lưu trong báo cáo giữ nguyên.')) return;
  local = {}; saveLocal(); renderCards();
};

$('#btn-expand').onclick = () => {
  document.querySelectorAll('.card').forEach((el) => expanded.add(el.dataset.id));
  renderCards();
};
$('#btn-collapse').onclick = () => { expanded.clear(); renderCards(); scrollTo({ top: 0 }); };

['#f-filter', '#f-sort', '#f-mode'].forEach((s) => { $(s).onchange = renderCards; });

function closeAllPanels() {
  document.querySelectorAll('.ms-panel:not([hidden])').forEach((p) => { p.hidden = true; });
  document.querySelectorAll('.ms-btn[aria-expanded="true"]').forEach((b) => b.setAttribute('aria-expanded', 'false'));
}
// Bam ra ngoai, hoac Esc, thi dong moi panel dang mo
document.addEventListener('click', (e) => { if (!e.target.closest('.ms')) closeAllPanels(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeAllPanels(); });
renderTiles(); renderLatency(); renderCards();
</script></body></html>
'''


SUGGEST_VERSIONS = os.path.join(ROOT, 'results', '_archive', 'suggest_versions')
GEN_LINE = re.compile(r'^- (Vector|Titan|Titan Multi|NovaLite) (đạt|không đạt)\b')


def stale_suggest_lines(rnd, rows):
    """Dong goi y Claude o cac BAN CU (suggest_verdicts.py ghi de nhieu lan) -> {image_id: [dong]}.

    Trinh duyet giu ghi chu QA dang sua do (localStorage) va de len ban trong bao cao, nen dong
    goi y da sua lai o ban moi khong hien. Dashboard dung danh sach nay de thay DUNG nhung dong
    cu QA chua dong vao bang dong moi; dong QA tu viet/tu sua khong khop -> giu nguyen.
    """
    old = {}
    for f in glob.glob(os.path.join(SUGGEST_VERSIONS, '*.json')):
        d = json.load(open(f, encoding='utf-8'))
        if d.get('round') != rnd:
            continue
        for iid, note in (d.get('notes') or {}).items():
            old.setdefault(iid, set()).update(l for l in note.split('\n') if GEN_LINE.match(l))
    out = {}
    for r in rows:
        cur = set(r['saved']['n'].split('\n'))
        lines = sorted(old.get(r['image_id'], set()) - cur)
        if lines:
            out[r['image_id']] = lines
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', metavar='EXPORT_JSON', help='nap file export tu dashboard vao verdict_state.json')
    ap.add_argument('--open', action='store_true', help='mo dashboard sau khi sinh')
    ap.add_argument('--out', default=OUT_HTML)
    args = ap.parse_args()

    if args.apply:
        applied, cleared, rnd_applied = apply_export(args.apply)
        print('Da nap phan quyet lan chay %s: %d luu, %d xoa -> %s' % (rnd_applied, applied, cleared, STATE))

    runs, img_idx, manifest = load_runs(), load_img_index(), load_manifest()
    if not runs:
        sys.exit('Chua co ket qua trong results/excel_top40 — chay node scripts/run-excel-top40.mjs truoc.')
    state = load_state()
    orphan = [i for i in runs if i not in manifest]
    set_modes(runs)
    rnd = current_round(runs)
    rows = build_payload(runs, img_idx, state, manifest, rnd)
    any_run = next(iter(next(iter(runs.values())).values()))

    payload = {
        'rows': rows,
        'stats': {m: stats_for(runs, m) for m, _ in MODES},
        'verdict_options': VERDICT_OPTIONS,
        'modes': [[m, l, MODE_INFO.get(m, {}).get('css', '--muted')] for m, l in MODES],
        'mode_labels': {m: x['label'] for m, x in MODE_INFO.items()},
        'striped': [m for m, x in MODE_INFO.items() if x.get('striped')],
        'meta': {
            'report_id': 'excel_top40',
            'store': any_run['params']['storeId'],
            'lang': any_run['params']['lang'],
            'ran_at': any_run['ran_at'][:10],
            'round': rnd,
            'legacy_round': LEGACY_ROUND,
            'prev_rounds': sorted((r for r in state['rounds'] if r != rnd), reverse=True),
            'built_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'mode_api': {m: m for m, _ in MODES},
            'state_updated': state.get('updatedAt'),
            'stale_lines': stale_suggest_lines(rnd, rows),
            'run_note': RUN_NOTES.get(rnd, ''),
        },
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    # </script> trong du lieu se cat som the script -> chen zero-width space an toan
    data = json.dumps(payload, ensure_ascii=False).replace('</', '<\\/')
    html = HTML.replace('__DATA__', data)
    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(html)
    # Ban "_view" de trinh chieu (user 2026-09-24): an cac nut xuat danh gia va
    # dong chu thich tran top-K 200 tren the Vector/Titan/Titan Multi
    view = html
    for a, b in [('<button id="btn-reset">', '<button id="btn-reset" hidden>'),
                 ('<button class="primary" id="btn-export">', '<button class="primary" id="btn-export" hidden>'),
                 ("lb.hidden = !lp;", "lb.hidden = true;"),
                 ("'<div class=\"sub\" style=\"margin-top:8px;color:var(--warn)\">200 ở mọi ảnh là trần top-K của tìm kiếm vector,"
                  " không phải tổng sản phẩm khớp — đừng so con số này với NovaLite.</div>'", "''")]:
        assert view.count(a) == 1, a
        view = view.replace(a, b)
    view_out = os.path.splitext(args.out)[0] + '_view.html'
    with open(view_out, 'w', encoding='utf-8') as fh:
        fh.write(view)

    if orphan:
        print('  %d ket qua khong con dong nao trong Excel, khong dua vao dashboard: %s'
              % (len(orphan), ', '.join(sorted(orphan))))
    print('Dashboard: %s' % args.out)
    print('  %d anh x %d co che · dang danh gia lan chay %s' % (len(rows), len(MODES), rnd))
    for r in sorted(state['rounds'], reverse=True):
        print('  phan quyet lan %s: %d' % (r, len(state['rounds'][r]['verdicts'])))
    if state.get('updatedAt'):
        print('  verdict_state.json cap nhat luc %s' % state['updatedAt'])
    if args.open:
        webbrowser.open('file:///' + args.out.replace('\\', '/'))


if __name__ == '__main__':
    main()
