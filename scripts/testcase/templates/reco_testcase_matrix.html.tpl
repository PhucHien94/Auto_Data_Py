<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MART Recommendation — Ma trận Test Case</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script>
        tailwind.config = { theme: { extend: { colors: { mart: { red: '#e60012', dark: '#1e293b', blue: '#0284c7' } } } } }
    </script>
    <style>
        table.tc { width: 100%; border-collapse: collapse; font-size: .75rem; }
        table.tc th, table.tc td { border: 1px solid #e2e8f0; padding: .35rem .5rem; vertical-align: top; text-align: left; }
        table.tc thead th { background: #f1f5f9; position: sticky; top: 0; z-index: 2; white-space: nowrap; }
        table.tc tbody tr:hover { background: #f8fafc; cursor: pointer; }
        .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
        /* nghia tieng Viet cua cac tu tieng Anh do dashboard tu dat ra */
        .gl { display: block; font-weight: 400; font-size: 10px; color: #94a3b8; font-style: italic; }
    </style>
</head>
<body class="bg-slate-100 text-slate-800 font-sans min-h-screen flex flex-col">

<header class="bg-mart-dark text-white shadow-lg sticky top-0 z-50">
    <div class="max-w-[1800px] mx-auto px-4 py-3 flex flex-col md:flex-row justify-between items-center gap-3">
        <div class="flex items-center space-x-3">
            <div class="bg-mart-red p-2 rounded-xl font-black text-lg tracking-wider shadow-md">MART</div>
            <div>
                <h1 class="text-lg font-bold leading-tight">Ma trận Test Case — Recommendation</h1>
                <p class="text-xs text-slate-400">Sinh từ REQ DE05 v0.2 · 3 trục precondition (điều kiện tiên quyết): Segment (phân khúc) × Zone (vùng gợi ý) × (IND, Engine trả về rỗng)</p>
            </div>
        </div>
        <div class="flex items-center gap-2 text-xs" id="hdr-stats"></div>
    </div>
</header>

<main class="max-w-[1800px] mx-auto px-4 py-6 flex-1 w-full">

    <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-4 mb-4">
        <div class="flex items-start justify-between gap-4 flex-wrap">
            <div class="flex-1 min-w-[320px]">
                <h2 class="font-bold text-slate-900 mb-1 text-sm"><i class="fa-solid fa-diagram-project mr-1.5 text-mart-blue"></i>Vì sao không tổ hợp thô</h2>
                <p class="text-xs text-slate-600 leading-relaxed">
                    Chọn nhiều trong 26 segment nghĩa là <b class="mono">2<sup>26</sup> × 16 zone × 2 IND × 2 Empty = 4.294.967.296</b> tổ hợp — không chạy được.
                    Nhưng output của engine <b>chỉ phụ thuộc vào tập audience (đối tượng) mà khách khớp trong phạm vi zone (vùng gợi ý) đó</b>, nên các tổ hợp khác nhau
                    mà cùng tập audience là một lớp tương đương.
                    Quét mù cả 26 × 16 cũng sai hướng: một segment chỉ có rule ở <b>1–4 zone</b> (5 segment không có rule ở đâu cả),
                    nên ở những zone còn lại kết quả luôn y hệt nhau. <b>IND</b> cũng chỉ sống ở đúng <b>HOME-Z2</b> — zone duy nhất có rule IND.
                    Vì vậy 4 bộ dưới đây dựng theo đích cần chứng minh, không quét tràn.
                </p>
            </div>
            <div class="flex-1 min-w-[320px]">
                <h2 class="font-bold text-slate-900 mb-1 text-sm"><i class="fa-solid fa-user-check mr-1.5 text-indigo-600"></i>Hồ sơ khách phải có thật</h2>
                <p class="text-xs text-slate-600 leading-relaxed">
                    <b>S-01…S-06 là một phân hoạch</b>: chưa đăng nhập &rarr; S-06 Visitor; đã đăng nhập &rarr; S-01…S-04 theo hạng, không hạng &rarr; S-05.
                    Nên <b>không tồn tại khách "không thuộc segment nào"</b>. 20 segment còn lại đều đòi hỏi tài khoản hoặc lịch sử đơn hàng
                    nên luôn được ghép kèm một segment nền (mặc định <b>S-04 Silver</b> — đông nhất và chỉ xuất hiện ở đúng 1 rule).
                    Hồ sơ mâu thuẫn (ví dụ S-08 cần 0 đơn hàng nhưng S-12 cần đã có đơn) được <b>đánh dấu blocker chứ không xoá</b>,
                    vì nó cho thấy cặp rule đó không bao giờ thật sự tranh nhau &mdash; một phát hiện cần hỏi Mart.
                </p>
            </div>
            <div class="flex-1 min-w-[320px]">
                <h2 class="font-bold text-slate-900 mb-1 text-sm"><i class="fa-solid fa-circle-check mr-1.5 text-emerald-600"></i>Bảo đảm phủ (tự kiểm tra khi sinh)</h2>
                <div id="cov-panel" class="text-xs text-slate-600 space-y-0.5"></div>
            </div>
        </div>
        <div id="suite-panel" class="grid grid-cols-1 md:grid-cols-4 gap-2 mt-4"></div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border border-slate-200 p-4 mb-4">
        <div class="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3 items-end">
            <div>
                <label class="block text-xs font-semibold text-slate-600 mb-1">Bộ test</label>
                <select id="f-suite" class="w-full border border-slate-300 rounded-lg text-xs p-2"></select>
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-600 mb-1">Zone <span class="font-normal text-slate-400">(vùng gợi ý)</span></label>
                <select id="f-zone" class="w-full border border-slate-300 rounded-lg text-xs p-2"></select>
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-600 mb-1">Segment (phân khúc) có trong input (đầu vào)</label>
                <select id="f-seg" class="w-full border border-slate-300 rounded-lg text-xs p-2"></select>
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-600 mb-1">IND <span class="font-normal text-slate-400">(có lịch sử duyệt/mua)</span></label>
                <select id="f-ind" class="w-full border border-slate-300 rounded-lg text-xs p-2">
                    <option value="">Tất cả</option><option value="1">Có lịch sử</option><option value="0">Không</option>
                </select>
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-600 mb-1">Engine (bộ máy gợi ý) trả về rỗng</label>
                <select id="f-empty" class="w-full border border-slate-300 rounded-lg text-xs p-2">
                    <option value="">Tất cả</option><option value="1">Có (chạy nhánh If empty)</option><option value="0">Không</option>
                </select>
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-600 mb-1">Scope <span class="font-normal text-slate-400">(phạm vi test)</span></label>
                <select id="f-scope" class="w-full border border-slate-300 rounded-lg text-xs p-2">
                    <option value="">Tất cả</option>
                    <option value="v1">Chạy được v1 (không vướng mắc)</option>
                    <option value="blocked">Có blocker (vướng mắc)</option>
                </select>
            </div>
            <div class="lg:col-span-4">
                <label class="block text-xs font-semibold text-slate-600 mb-1">Tìm (ID, rule, title/tiêu đề, kết quả...)</label>
                <input id="f-q" type="text" placeholder="vd: R-025, HORECA, Hide, Taste of Vietnam" class="w-full border border-slate-300 rounded-lg text-xs p-2">
            </div>
            <div>
                <label class="block text-xs font-semibold text-slate-600 mb-1">Số dòng / trang</label>
                <select id="f-size" class="w-full border border-slate-300 rounded-lg text-xs p-2">
                    <option>50</option><option>100</option><option>250</option><option>1000</option>
                </select>
            </div>
            <div class="flex gap-2">
                <button id="btn-csv" class="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg p-2">
                    <i class="fa-solid fa-file-csv mr-1"></i>Tải CSV (đang lọc)
                </button>
                <button id="btn-reset" class="bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-semibold rounded-lg px-3">Reset</button>
            </div>
        </div>
        <div id="filter-info" class="mt-3 text-xs text-slate-500"></div>
    </div>

    <div class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div class="overflow-auto" style="max-height:72vh">
            <table class="tc">
                <thead><tr>
                    <th>Test case ID</th>
                    <th>Bộ</th>
                    <th>Zone<span class="gl">vùng gợi ý</span></th>
                    <th>Input: Segments<span class="gl">đầu vào: phân khúc</span></th>
                    <th>IND<span class="gl">có lịch sử</span></th>
                    <th>Empty<span class="gl">engine rỗng</span></th>
                    <th>Rule thắng<span class="gl">quy tắc áp dụng</span></th>
                    <th>P<span class="gl">priority<br>độ ưu tiên</span></th>
                    <th>Mechanism<span class="gl">cơ chế</span></th>
                    <th>Zone title<span class="gl">tiêu đề zone</span></th>
                    <th>Kết quả mong đợi</th>
                    <th>Rule bị bỏ qua<span class="gl">cũng khớp nhưng thua</span></th>
                    <th>Blocker<span class="gl">vướng mắc</span></th>
                </tr></thead>
                <tbody id="tbody"></tbody>
            </table>
        </div>
        <div class="flex items-center justify-between p-3 border-t border-slate-200 bg-slate-50 text-xs">
            <div id="page-info" class="text-slate-500"></div>
            <div class="flex gap-1">
                <button id="pg-first" class="px-2 py-1 border border-slate-300 rounded bg-white">&laquo;</button>
                <button id="pg-prev"  class="px-2 py-1 border border-slate-300 rounded bg-white">&lsaquo;</button>
                <span id="pg-cur" class="px-3 py-1"></span>
                <button id="pg-next" class="px-2 py-1 border border-slate-300 rounded bg-white">&rsaquo;</button>
                <button id="pg-last" class="px-2 py-1 border border-slate-300 rounded bg-white">&raquo;</button>
            </div>
        </div>
    </div>
</main>

<div id="drawer" class="fixed inset-y-0 right-0 w-full md:w-[720px] bg-white shadow-2xl border-l border-slate-200 z-[60] hidden overflow-y-auto">
    <div id="drawer-body" class="p-5"></div>
</div>

<footer class="bg-slate-800 text-slate-400 text-xs py-3 text-center border-t border-slate-700">
    MART Online Renewal &mdash; ma trận test case Recommendation, sinh bằng <span class="mono">scripts/testcase/gen_reco_testcase_matrix.py</span>
</footer>

<script>
/*__TCDATA__*/

const CASES = TCDATA.cases;
const ZONES = TCDATA.zones, SEGS = TCDATA.segments, RULES = TCDATA.rules;
const zoneById = {}, segById = {}, ruleById = {};
ZONES.forEach(z => zoneById[z.id] = z);
SEGS.forEach(s => segById[s.id] = s);
RULES.forEach(r => ruleById[r.id] = r);

function esc(s) {
    return String(s == null ? '' : s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function statusClass(st) {
    if (!st) return 'bg-slate-100 text-slate-600';
    if (st.indexOf('READY') === 0) return 'bg-emerald-100 text-emerald-800';
    if (st.indexOf('PARTIAL') === 0) return 'bg-amber-100 text-amber-800';
    if (st.indexOf('NEEDS') === 0) return 'bg-rose-100 text-rose-800';
    if (st.indexOf('ROADMAP') === 0) return 'bg-sky-100 text-sky-800';
    if (st.indexOf('NOT IN') === 0) return 'bg-slate-300 text-slate-700';
    if (st.indexOf('PROPOSED') === 0) return 'bg-violet-100 text-violet-800';
    return 'bg-slate-100 text-slate-600';
}
function badge(st) {
    return '<span class="px-1.5 py-0.5 rounded text-[10px] font-bold whitespace-nowrap ' + statusClass(st) + '">' + esc(st || '-') + '</span>';
}
// Ba truong hop khong co rule thang — phan biet ro vi y nghia QA khac han nhau
const KIND_LABEL = {
    'zone-default': '<span class="text-amber-700 font-normal">zone không có rule<br>→ Zone Register</span>',
    'no-match':     '<span class="text-rose-600 font-normal">KHÔNG rule nào khớp<br>→ REQ chưa định nghĩa</span>',
    'not-rendered': '<span class="text-slate-500 font-normal">zone không render</span>'
};

// ---------- header + panels ----------
(function initPanels() {
    const blocked = CASES.filter(c => c.exp.blockers.length).length;
    document.getElementById('hdr-stats').innerHTML =
        [['Tổng case', CASES.length, 'text-mart-blue'],
         ['Chạy được v1', CASES.length - blocked, 'text-emerald-400'],
         ['Có blocker (vướng mắc)', blocked, 'text-rose-400'],
         ['Zone (vùng)', ZONES.length, 'text-amber-400'],
         ['Rule (quy tắc)', RULES.length, 'text-purple-400']]
        .map(([k, v, c]) => '<div class="bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700 text-center">' +
            '<span class="block font-bold text-sm ' + c + '">' + v + '</span><span class="text-slate-400">' + k + '</span></div>').join('');

    const cv = TCDATA.coverage;
    const ok = (a, b) => a === b ? '<i class="fa-solid fa-circle-check text-emerald-600"></i>' : '<i class="fa-solid fa-triangle-exclamation text-amber-500"></i>';
    document.getElementById('cov-panel').innerHTML =
        '<div>' + ok(cv.rules_won, cv.rules_total) + ' Mỗi rule (quy tắc) được làm rule <b>thắng</b> ít nhất 1 lần: <b>' + cv.rules_won + '/' + cv.rules_total + '</b>' +
            (cv.rules_never_win.length ? ' <span class="text-rose-600">(không bao giờ thắng: ' + cv.rules_never_win.join(', ') + ')</span>' : '') + '</div>' +
        '<div>' + ok(cv.empty_branch_hit, cv.empty_branch_total) + ' Nhánh <b>If empty</b> (khi engine trả về rỗng) của mỗi rule được kích hoạt: <b>' + cv.empty_branch_hit + '/' + cv.empty_branch_total + '</b></div>' +
        '<div>' + ok(cv.pairs_hit, cv.pairs_needed) + ' Mọi <b>cặp audience</b> (đối tượng) cùng zone được đặt tranh Priority (độ ưu tiên): <b>' + cv.pairs_hit + '/' + cv.pairs_needed + '</b></div>' +
        '<div>' + ok(cv.segzone_hit, cv.segzone_needed) + ' Mọi <b>segment × zone mà segment đó có rule</b>: <b>' + cv.segzone_hit + '/' + cv.segzone_needed + '</b></div>' +
        '<div>' + ok(cv.seg_hit, cv.seg_needed) + ' Mọi <b>segment</b> đều được kiểm ít nhất 1 lần: <b>' + cv.seg_hit + '/' + cv.seg_needed + '</b></div>';

    const counts = {};
    CASES.forEach(c => counts[c.suite] = (counts[c.suite] || 0) + 1);
    document.getElementById('suite-panel').innerHTML = Object.keys(TCDATA.suites).sort().map(k =>
        '<div class="border border-slate-200 rounded-lg p-2.5 bg-slate-50">' +
        '<div class="flex items-baseline justify-between"><span class="font-black text-mart-blue">Bộ ' + k + '</span>' +
        '<span class="font-bold text-slate-700">' + (counts[k] || 0) + '</span></div>' +
        '<div class="text-[11px] text-slate-600 leading-snug mt-0.5">' + esc(TCDATA.suites[k]) + '</div></div>').join('');
})();

// ---------- filters ----------
const F = { suite: 'f-suite', zone: 'f-zone', seg: 'f-seg', ind: 'f-ind', empty: 'f-empty', scope: 'f-scope', q: 'f-q', size: 'f-size' };
let page = 1;

(function initFilters() {
    document.getElementById('f-suite').innerHTML = '<option value="">Tất cả</option>' +
        Object.keys(TCDATA.suites).sort().map(k => '<option value="' + k + '">Bộ ' + k + ' — ' + esc(TCDATA.suites[k]) + '</option>').join('');
    document.getElementById('f-zone').innerHTML = '<option value="">Tất cả</option>' +
        ZONES.map(z => '<option value="' + z.id + '">' + esc(z.id) + ' — ' + esc(z.title || z.mech) + '</option>').join('');
    document.getElementById('f-seg').innerHTML = '<option value="">Tất cả</option>' +
        SEGS.map(s => '<option value="' + s.id + '">' + esc(s.id) + ' ' + esc(s.name) + '</option>').join('');
    Object.values(F).forEach(id => {
        const el = document.getElementById(id);
        el.addEventListener(id === 'f-q' ? 'input' : 'change', () => { page = 1; render(); });
    });
    document.getElementById('btn-reset').onclick = () => {
        Object.values(F).forEach(id => { const e = document.getElementById(id); if (id !== 'f-size') e.value = ''; });
        page = 1; render();
    };
    document.getElementById('pg-first').onclick = () => { page = 1; render(); };
    document.getElementById('pg-prev').onclick  = () => { page = Math.max(1, page - 1); render(); };
    document.getElementById('pg-next').onclick  = () => { page = page + 1; render(); };
    document.getElementById('pg-last').onclick  = () => { page = 1e9; render(); };
    document.getElementById('btn-csv').onclick  = downloadCsv;
})();

function filtered() {
    const v = k => document.getElementById(F[k]).value;
    const q = v('q').trim().toLowerCase();
    return CASES.filter(c => {
        if (v('suite') && c.suite !== v('suite')) return false;
        if (v('zone') && c.zone !== v('zone')) return false;
        if (v('seg') && c.segs.indexOf(v('seg')) < 0) return false;
        if (v('ind') !== '' && String(c.ind) !== v('ind')) return false;
        if (v('empty') !== '' && String(c.empty) !== v('empty')) return false;
        if (v('scope') === 'v1' && c.exp.blockers.length) return false;
        if (v('scope') === 'blocked' && !c.exp.blockers.length) return false;
        if (q) {
            const hay = [c.id, c.zone, c.segs.join(' '), c.exp.win, c.exp.title, c.exp.outcome,
                         c.exp.mech, c.intent, c.exp.blockers.join(' ')].join(' ').toLowerCase();
            if (hay.indexOf(q) < 0) return false;
        }
        return true;
    });
}

function render() {
    const rows = filtered();
    const size = parseInt(document.getElementById('f-size').value, 10);
    const pages = Math.max(1, Math.ceil(rows.length / size));
    page = Math.min(page, pages);
    const slice = rows.slice((page - 1) * size, page * size);

    document.getElementById('filter-info').innerHTML =
        '<b>' + rows.length + '</b> / ' + CASES.length + ' case khớp bộ lọc · ' +
        '<b>' + rows.filter(c => !c.exp.blockers.length).length + '</b> chạy được v1 · ' +
        '<b class="text-rose-600">' + rows.filter(c => c.exp.blockers.length).length + '</b> có blocker (vướng mắc)';

    document.getElementById('tbody').innerHTML = slice.map((c, i) => {
        const w = c.exp.win ? ruleById[c.exp.win] : null;
        const blk = c.exp.blockers.length;
        return '<tr onclick="openDrawer(\'' + c.id + '\')"' + (blk ? ' style="background:#fff7f7"' : '') + '>' +
            '<td class="mono font-bold">' + esc(c.id) + '</td>' +
            '<td class="text-center font-bold text-mart-blue">' + c.suite + '</td>' +
            '<td class="mono">' + esc(c.zone) + '</td>' +
            '<td>' + (c.segs.length ? esc(c.segs.join(', ')) : '<span class="text-slate-400">(không có)</span>') + '</td>' +
            '<td class="text-center">' + (c.ind ? '<i class="fa-solid fa-check text-emerald-600"></i>' : '<span class="text-slate-300">–</span>') + '</td>' +
            '<td class="text-center">' + (c.empty ? '<i class="fa-solid fa-check text-rose-600"></i>' : '<span class="text-slate-300">–</span>') + '</td>' +
            '<td class="mono font-bold">' + (w ? esc(w.id) : KIND_LABEL[c.exp.kind] || '<span class="text-rose-600">không khớp</span>') + '</td>' +
            '<td class="text-center">' + (w ? w.prio : '') + '</td>' +
            '<td class="mono">' + esc(c.exp.mech) + '</td>' +
            '<td>' + esc(c.exp.title) + '</td>' +
            '<td>' + esc(c.exp.outcome) + '</td>' +
            '<td class="mono text-slate-500">' + esc(c.exp.losers.join(', ')) + '</td>' +
            '<td>' + (blk ? '<span class="text-rose-700 font-semibold">' + esc(c.exp.blockers.join(' | ')) + '</span>' : '<span class="text-emerald-600">–</span>') + '</td>' +
            '</tr>';
    }).join('');

    document.getElementById('page-info').textContent =
        'Hiển thị ' + (rows.length ? ((page - 1) * size + 1) : 0) + '–' + Math.min(page * size, rows.length) + ' trong ' + rows.length;
    document.getElementById('pg-cur').textContent = page + ' / ' + pages;
}

function openDrawer(id) {
    const c = CASES.find(x => x.id === id);
    const z = zoneById[c.zone];
    const zr = RULES.filter(r => r.zone === c.zone).sort((a, b) => a.prio - b.prio);
    const auds = new Set(c.segs); if (c.ind) auds.add('IND');

    let seenWinner = false;
    const trace = zr.map(r => {
        const m = r.audKey === 'ALL' ? true : auds.has(r.audKey);
        let verdict, cls = '';
        if (!c.visible) { verdict = '<span class="text-slate-400">zone không render</span>'; cls = 'opacity:.5'; }
        else if (seenWinner) { verdict = m ? '<span class="text-rose-600">khớp nhưng bị bỏ qua</span>' : '<span class="text-slate-400">không được xét</span>'; cls = 'opacity:.55'; }
        else if (m) { verdict = '<b class="text-emerald-700">MATCH — dừng tại đây</b>'; cls = 'background:#ecfdf5'; seenWinner = true; }
        else verdict = '<span class="text-slate-400">không khớp</span>';
        return '<tr style="' + cls + '"><td class="text-center"><b>' + r.prio + '</b></td><td class="mono font-bold">' + esc(r.id) +
            '</td><td>' + esc(r.aud) + '</td><td class="mono">' + esc(r.mech) + '</td><td>' + esc(r.title) +
            '</td><td>' + esc(r.ifEmpty) + '</td><td>' + badge(r.status) + '</td><td>' + verdict + '</td></tr>';
    }).join('');

    document.getElementById('drawer-body').innerHTML =
        '<div class="flex justify-between items-start mb-4">' +
            '<div><div class="mono font-black text-xl text-slate-900">' + esc(c.id) + '</div>' +
            '<div class="text-xs text-slate-500">Bộ ' + c.suite + ' — ' + esc(TCDATA.suites[c.suite]) + '</div>' +
            '<div class="text-xs text-slate-600 mt-1">' + esc(c.intent) + '</div></div>' +
            '<button onclick="document.getElementById(\'drawer\').classList.add(\'hidden\')" class="text-slate-400 hover:text-slate-700 text-xl px-2">&times;</button>' +
        '</div>' +

        '<div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Precondition (điều kiện tiên quyết) — Zone (vùng gợi ý)</div>' +
        '<table class="tc mb-4"><tbody>' +
            '<tr><th style="width:38%">Zone (vùng gợi ý)</th><td>' + esc(z.id) + ' — ' + esc(z.title) + '</td></tr>' +
            '<tr><th>Page / Position / Channel<span class="gl">trang / vị trí / kênh</span></th><td>' + esc(z.page) + ' / ' + esc(z.pos) + ' / ' + esc(z.channel) + '</td></tr>' +
            '<tr><th>Show when<span class="gl">điều kiện zone được hiển thị</span></th><td>' + esc(z.showWhen) + (c.visible ? ' <span class="text-emerald-600">(thoả)</span>' : ' <span class="text-rose-600">(KHÔNG thoả — case này kiểm tra nhánh đó)</span>') + '</td></tr>' +
            '<tr><th>Default mechanism / If empty / Max items<span class="gl">cơ chế mặc định / khi rỗng / số SP tối đa</span></th><td><code>' + esc(z.mech) + '</code> / ' + esc(z.ifEmpty) + ' / ' + esc(z.max) + '</td></tr>' +
            '<tr><th>Zone v1 status<span class="gl">trạng thái sẵn sàng cho v1</span></th><td>' + badge(z.status) + '</td></tr>' +
        '</tbody></table>' +

        '<div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Input (đầu vào)</div>' +
        '<table class="tc mb-4"><tbody>' +
            '<tr><th style="width:38%">Segment (phân khúc) khách thuộc về</th><td>' +
                (c.segs.length ? c.segs.map(s => '<div><b class="mono">' + esc(s) + '</b> ' + esc(segById[s].name) + ' ' + badge(segById[s].status) + '</div>').join('') : '<i class="text-slate-400">không thuộc segment đặc thù nào</i>') + '</td></tr>' +
            '<tr><th>IND — có lịch sử duyệt/mua</th><td>' + (c.ind ? '<b class="text-emerald-700">Có</b>' : 'Không') + '</td></tr>' +
            '<tr><th>Engine (bộ máy gợi ý) trả về rỗng</th><td>' + (c.empty ? '<b class="text-rose-700">Có</b> — kiểm tra nhánh If empty' : 'Không') + '</td></tr>' +
        '</tbody></table>' +

        '<div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Expected output (kết quả mong đợi)</div>' +
        '<table class="tc mb-4"><tbody>' +
            '<tr><th style="width:38%">Rule thắng<span class="gl">quy tắc được áp dụng</span></th><td>' + (c.exp.win ? '<b class="mono">' + esc(c.exp.win) + '</b> (Priority ' + ruleById[c.exp.win].prio + ') ' + badge(ruleById[c.exp.win].status) : '<b class="text-rose-600">không rule nào khớp</b>') + '</td></tr>' +
            '<tr><th>Mechanism<span class="gl">cơ chế sinh gợi ý</span></th><td><code>' + esc(c.exp.mech) + '</code></td></tr>' +
            '<tr><th>Zone title hiển thị</th><td><b>"' + esc(c.exp.title) + '"</b></td></tr>' +
            '<tr><th>What products to show<span class="gl">sản phẩm hiển thị — nguyên văn REQ</span></th><td>' + esc(c.exp.show) + '</td></tr>' +
            '<tr><th>If empty →<span class="gl">khi engine trả về rỗng</span></th><td>' + esc(c.exp.ifEmpty) + '</td></tr>' +
            '<tr><th>Kết quả hiển thị</th><td><b>' + esc(c.exp.outcome) + '</b></td></tr>' +
            '<tr><th>Lý do</th><td>' + esc(c.exp.reason) + '</td></tr>' +
        '</tbody></table>' +

        (c.exp.blockers.length ? '<div class="bg-rose-50 border-l-4 border-rose-500 p-3 rounded-r-lg mb-4 text-xs text-rose-900">' +
            '<b>Blocker (vướng mắc) / ngoài scope (phạm vi) v1:</b><ul class="list-disc ml-4 mt-1">' +
            c.exp.blockers.map(b => '<li>' + esc(b) + '</li>').join('') + '</ul></div>' : '') +

        '<div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 mb-1">Duyệt rule theo Priority (độ ưu tiên) — ' + zr.length + ' rule</div>' +
        (zr.length ? '<table class="tc"><thead><tr><th>P<span class="gl">ưu tiên</span></th><th>Rule<span class="gl">quy tắc</span></th><th>Audience<span class="gl">đối tượng</span></th><th>Mech<span class="gl">cơ chế</span></th><th>Zone title<span class="gl">tiêu đề</span></th><th>If empty<span class="gl">khi rỗng</span></th><th>Status<span class="gl">trạng thái</span></th><th>Kết quả</th></tr></thead><tbody>' + trace + '</tbody></table>'
                   : '<div class="text-xs text-slate-500">Zone này không có rule nào ở sheet 5 — dùng cấu hình mặc định ở Zone Register.</div>');

    document.getElementById('drawer').classList.remove('hidden');
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') document.getElementById('drawer').classList.add('hidden'); });

// Trung khop 1-1 voi CSV_HEADER trong gen_reco_testcase_matrix.py
const CSV_HEAD = ['Test case ID','Bộ test','Mục tiêu',
    'PRE: Zone (vùng gợi ý)','PRE: Page (trang)','PRE: Position (vị trí)',
    'PRE: Channel (kênh)','PRE: Show when (điều kiện hiển thị zone)',
    'PRE: Zone v1 status (trạng thái)','PRE: Max items (số sản phẩm tối đa)',
    'IN: Segments (phân khúc khách)','IN: Số segment',
    'IN: IND (có lịch sử duyệt/mua)','IN: Engine trả về rỗng','IN: Zone có hiển thị',
    'OUT: Rule thắng','OUT: Priority (độ ưu tiên)','OUT: Audience (đối tượng)',
    'OUT: Mechanism (cơ chế)','OUT: Zone title (tiêu đề zone)',
    'OUT: What products to show (sản phẩm hiển thị — nguyên văn REQ)',
    'OUT: If empty (khi engine trả về rỗng)',
    'OUT: Kết quả hiển thị','OUT: Lý do','OUT: Rule cùng khớp bị bỏ qua',
    'Rule v1 status (trạng thái)','Trong scope v1 (phạm vi v1)','Blocker (vướng mắc)'];

function downloadCsv() {
    const rows = filtered();
    const q = v => '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"';
    const lines = [CSV_HEAD.map(q).join(',')];
    rows.forEach(c => {
        const z = zoneById[c.zone], w = c.exp.win ? ruleById[c.exp.win] : null;
        lines.push([c.id, c.suite, c.intent, z.id, z.page, z.pos, z.channel, z.showWhen, z.status, z.max,
            c.segs.join(', ') || '(không có)', c.segs.length, c.ind ? 'Có' : 'Không', c.empty ? 'Có' : 'Không', c.visible ? 'Có' : 'Không',
            // dung chung nhan voi CSV sinh tu Python, khong hard-code lai de khoi lech
            w ? w.id : (TCDATA.kindLabel[c.exp.kind] || '(không có rule nào khớp)'),
            w ? w.prio : '', w ? w.aud : '',
            c.exp.mech, c.exp.title, c.exp.show, c.exp.ifEmpty, c.exp.outcome, c.exp.reason, c.exp.losers.join(', '),
            w ? w.status : '', c.exp.blockers.length ? 'Không' : 'Có', c.exp.blockers.join(' | ')].map(q).join(','));
    });
    const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'reco_testcase_matrix_filtered.csv';
    a.click();
    URL.revokeObjectURL(a.href);
}

render();
</script>
</body>
</html>
