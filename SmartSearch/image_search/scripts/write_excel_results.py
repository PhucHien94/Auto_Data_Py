# -*- coding: utf-8 -*-
"""Do ket qua 4 co che image search vao file Excel keyword.

    python scripts/write_excel_results.py [--xlsx <file>] [--out <file>]

Doc results/excel_top40/<mode>/<image_id>.json do run-excel-top40.mjs sinh ra:
  - Sheet 'Top100_Keywords': moi co che them cot tong ket + MOT o chua top-40,
    nam ngay trong dong cua keyword do (khong tach sheet rieng).
    MOI LAN CHAY MOT KHOI COT RIENG (user 2026-09-24): tieu de mang tien to
    "[dd/mm]" theo ngay chay. Lan chay moi -> them khoi moi ben phai, khoi cua
    cac lan truoc giu nguyen de doi chieu. Chay lai trong CUNG ngay -> ghi de
    dung khoi cua ngay do.
  - Sheet 'Run_Info'       : tham so chay + canh bao khi doc so
  - results/excel_top40/top40_flat.csv: bang dai cho dashboard, 1 dong = 1 san pham

File dang mo trong Excel thi ghi ra <ten>_results.xlsx ben canh, khong ghi de.
"""
import argparse, json, os, re, sys, glob, csv
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, 'results', 'excel_top40')
IMG_INDEX = os.path.join(ROOT, 'result_images', 'index.csv')
MANIFEST = os.path.join(ROOT, 'images', 'excel_keywords', 'manifest.json')
TOP_N = 40

# Co che cua lan chay = MODES trong scripts/config.mjs (nguon duy nhat, runner
# cung doc no); nhan + mau lay tu scripts/lib/modes.json. User 2026-09-28 doi
# bo co che (bo Titan, them Titan Multi Caption Type) - khong khai cung o day nua.
# So co che giu nguyen 4 nen moi khoi van rong BLOCK_W cot nhu cac khoi cu.
_MJ = json.load(open(os.path.join(ROOT, 'scripts', 'lib', 'modes.json'), encoding='utf-8'))
_INFO = {x['mode']: x for x in _MJ['modes']}
_cfg = open(os.path.join(ROOT, 'scripts', 'config.mjs'), encoding='utf-8').read()
_run_modes = re.findall(r"'([a-z_]+)'", re.search(r"export const MODES = \[([^\]]*)\]", _cfg).group(1))
MODES = [(m, _INFO[m]['label']) for m in _run_modes]
MODE_FILL = {m: x['xlsx'] for m, x in _INFO.items()}
HEAD_FILL = 'C00000'
BASE_COL = 12  # L - ngay sau K "Ghi chu"; khoi ket qua dau tien bat dau o day
# Khoi dau tien (L..AF) duoc ghi truoc khi co tien to ngay -> do la lan 22/09
LEGACY_ROUND = '2026-09-22'

WHITE_BOLD = Font(bold=True, color='FFFFFFFF', sz=11, name='Calibri')
SMALL = Font(sz=8, name='Calibri')
CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)
TOP_WRAP = Alignment(horizontal='left', vertical='top', wrap_text=True)
THIN = Border(*[Side(style='thin', color='FFD9D9D9')] * 4)


def top_line(p):
    """Mot dong trong o top-40: No | SKU | Ten san pham | Ton kho."""
    stock = p['stock_qty'] if p['in_stock'] else '%s (hết)' % (p['stock_qty'] or 0)
    return '%d | %s | %s | %s' % (p['no'], p['sku'], p['name'], stock)


def load_runs():
    runs = {}
    for f in glob.glob(os.path.join(RESULTS, '*', '*.json')):
        d = json.load(open(f, encoding='utf-8'))
        runs.setdefault(d['image_id'], {})[d['mode_requested']] = d
    return runs


def load_manifest():
    """image_id -> vi tri HIEN TAI trong sheet.

    Ket qua tho co field excel_row, nhung do la so dong LUC CHAY. Chen/xoa dong
    trong Excel sau do la no sai ngay, va ghi theo no thi ca khoi ket qua lech
    dong (da dinh 2026-09-22: xoa 1 dong o giua lam 13 dong duoi lech +1).
    manifest.json do extract_excel_images.py sinh ra doc anchor that cua file
    Excel hien tai, nen day moi la nguon dung.
    """
    if not os.path.exists(MANIFEST):
        sys.exit('Thieu %s — chay scripts/extract_excel_images.py truoc.' % MANIFEST)
    return {r['image_id']: r for r in json.load(open(MANIFEST, encoding='utf-8'))}


def load_image_index():
    idx = {}
    if not os.path.exists(IMG_INDEX):
        return idx
    with open(IMG_INDEX, encoding='utf-8') as fh:
        for r in csv.DictReader(fh):
            idx[r['sku']] = r['file']
    return idx


def round_tag(rnd):
    """'2026-09-24' -> '[24/09] '"""
    return '[%s/%s] ' % (rnd[8:10], rnd[5:7])


def block_headers(tag):
    """Danh sach tieu de cua MOT khoi ket qua, theo dung thu tu cot."""
    per_mode = ['{} – Tổng KQ (API)', '{} – Số KQ trả về', '{} – tookMs']
    heads = [('Ảnh test (file)', HEAD_FILL), ('imageRef (sha256)', HEAD_FILL)]
    for mode, label in MODES:
        hs = [h.format(label) for h in per_mode]
        if mode == 'caption':
            hs += ['NovaLite – Query sinh ra', 'NovaLite – Outcome']
        hs.append('%s – Top %d (No | SKU | Tên sản phẩm | Tồn)' % (label, TOP_N))
        heads += [(h, MODE_FILL[mode]) for h in hs]
    heads.append(('Ngày chạy', HEAD_FILL))
    return [(tag + h, f) for h, f in heads]


BLOCK_W = len(block_headers(''))


def find_block(ws, rnd):
    """Cot bat dau cua khoi thuoc lan chay rnd; chua co thi tra cot trong dau tien sau cac khoi."""
    tag = round_tag(rnd)
    col = BASE_COL
    while ws.cell(1, col).value:
        if str(ws.cell(1, col).value).startswith(tag):
            return col, True
        col += BLOCK_W
    return col, False


def tag_legacy_block(ws):
    """Khoi L..AF cu khong co tien to ngay -> gan '[22/09] ' vao tieu de (chi tieu de,
    du lieu giu nguyen) va dien cot 'Ngay chay' con trong cho cac dong co ket qua."""
    first = str(ws.cell(1, BASE_COL).value or '')
    if not first or first.startswith('['):
        return False
    tag = round_tag(LEGACY_ROUND)
    for c in range(BASE_COL, BASE_COL + BLOCK_W):
        v = ws.cell(1, c).value
        if v:
            ws.cell(1, c).value = tag + str(v)
    date_col = BASE_COL + BLOCK_W - 1
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, BASE_COL).value and not ws.cell(r, date_col).value:
            ws.cell(r, date_col, LEGACY_ROUND).alignment = CENTER
    return True


def style_header(ws, row, first_col, headers, fill):
    for i, h in enumerate(headers):
        c = ws.cell(row=row, column=first_col + i, value=h)
        c.font, c.alignment = WHITE_BOLD, CENTER
        c.fill = PatternFill('solid', fgColor=fill)
        c.border = THIN


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--xlsx', default=os.path.join(ROOT, 'ImageSearch_TopKeywords_100_20260921.xlsx'))
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    runs, img_idx, manifest = load_runs(), load_image_index(), load_manifest()
    if not runs:
        sys.exit('Chua co ket qua trong results/excel_top40 - chay node scripts/run-excel-top40.mjs truoc.')

    wb = openpyxl.load_workbook(args.xlsx)
    ws = wb['Top100_Keywords']
    kept_images = len(ws._images)

    # ---------------------------------------------------- cot ket qua tren sheet chinh
    # Top-40 nam ngay trong dong cua keyword do: moi co che mot o, moi dong trong o
    # la "No | SKU | Ten san pham | Ton kho". Moi lan chay mot khoi cot rieng.
    # 'round' (run-excel-top40.mjs --round): anh bo sung ghi vao khoi cua vong do; cot 'Ngay chay' van la ngay that
    rnd = max((d.get('round') or d['ran_at'][:10]) for by_mode in runs.values() for d in by_mode.values())
    tagged_legacy = tag_legacy_block(ws)
    base, existed = find_block(ws, rnd)
    tag = round_tag(rnd)
    for i, (h, fill) in enumerate(block_headers(tag)):
        style_header(ws, 1, base + i, [h], fill)
    col = base + 2
    mode_col = {}
    for mode, label in MODES:
        mode_col[mode] = col
        col += 6 if mode == 'caption' else 4
    tail_col = col
    last_col = tail_col

    top_cols = {m: mode_col[m] + (5 if m == 'caption' else 3) for m, _ in MODES}
    widths = {base: 26, base + 1: 22, tail_col: 18}
    for c in range(base + 2, tail_col):
        widths.setdefault(c, 16)
    widths[mode_col['caption'] + 3] = 34
    for c in top_cols.values():
        widths[c] = 74
    for c, w in widths.items():
        ws.column_dimensions[get_column_letter(c)].width = w

    # Xoa sach vung ket qua CUA LAN CHAY NAY truoc khi ghi: dong nao khong con ket
    # qua (keyword bi xoa, anh bi go) phai trong. Khoi cua cac lan khac khong dung toi.
    for r in range(2, ws.max_row + 1):
        for c in range(base, last_col + 1):
            ws.cell(r, c).value = None

    filled_rows, orphans, mismatched = 0, [], []
    for image_id, by_mode in sorted(runs.items()):
        any_run = next(iter(by_mode.values()))
        pos = manifest.get(image_id)
        if not pos:
            orphans.append((image_id, any_run['keyword']))
            continue
        r = pos['excel_row']
        # Chot chan: keyword o dong do phai dung voi keyword da chay
        here = str(ws.cell(r, 3).value or '').strip()
        if here != str(any_run['keyword']).strip():
            mismatched.append((image_id, r, any_run['keyword'], here))
        ws.cell(r, base, os.path.basename(any_run['image_file'])).alignment = CENTER
        refs = {d['image_ref'] for d in by_mode.values() if d.get('image_ref')}
        ws.cell(r, base + 1, '; '.join(sorted(refs))).alignment = CENTER
        ws.cell(r, tail_col, any_run['ran_at'][:10]).alignment = CENTER
        max_lines = 0
        for mode, _ in MODES:
            d = by_mode.get(mode)
            c = mode_col[mode]
            if not d:
                ws.cell(r, c, 'chua chay').alignment = CENTER
                continue
            if not d['ok']:
                ws.cell(r, c, 'LOI HTTP %s' % d['http_status']).alignment = CENTER
                continue
            ws.cell(r, c, d['total_hits']).number_format = '#,##0'
            ws.cell(r, c + 1, d['returned']).number_format = '#,##0'
            ws.cell(r, c + 2, d['took_ms']).number_format = '#,##0'
            for k in range(3):
                ws.cell(r, c + k).alignment = CENTER
            if mode == 'caption':
                cap = d.get('caption') or {}
                ws.cell(r, c + 3, cap.get('query') or '').alignment = Alignment(vertical='center', wrap_text=True)
                ws.cell(r, c + 4, cap.get('outcome') or '').alignment = CENTER
            lines = [top_line(p) for p in d['top'][:TOP_N]]
            cell = ws.cell(r, top_cols[mode], '\n'.join(lines) if lines else '(không có kết quả)')
            cell.alignment = TOP_WRAP
            cell.font = SMALL
            max_lines = max(max_lines, len(lines))
        # Excel chan chieu cao o 409.5pt; 40 dong font 8 vua khit trong tran do.
        if max_lines:
            need = max_lines * 10.2 + 4
            cur = ws.row_dimensions[r].height or 15
            ws.row_dimensions[r].height = min(409.5, max(cur, need))
        filled_rows += 1

    all_last = find_block(ws, '0000-00-00')[0] - 1   # cot cuoi cua khoi cuoi cung
    ws.auto_filter.ref = 'A1:%s%d' % (get_column_letter(all_last), ws.max_row)

    # ------------------------------------------- bang dai cho dashboard (CSV, khong phai sheet)
    # Excel chi hien top-40 ngay trong dong keyword. Dashboard can dang bang thi
    # doc file nay hoac doc thang results/excel_top40/<mode>/<id>.json.
    if 'Top40_Results' in wb.sheetnames:
        del wb['Top40_Results']
    flat = os.path.join(RESULTS, 'top40_flat.csv')
    cols = ['stt', 'excel_row', 'keyword', 'lang', 'image_id', 'image_file', 'co_che', 'image_mode',
            'total_hits', 'no', 'sku', 'product_name', 'in_stock', 'stock_qty', 'price',
            'brand', 'category', 'result_image_file', 'image_url']
    n_flat = 0
    with open(flat, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for image_id, by_mode in sorted(runs.items()):
            pos = manifest.get(image_id)
            if not pos:
                continue
            for mode, label in MODES:
                d = by_mode.get(mode)
                if not d or not d['ok']:
                    continue
                for p in d['top'][:TOP_N]:
                    w.writerow([pos['stt'], pos['excel_row'], d['keyword'], d['lang'], image_id,
                                os.path.basename(d['image_file']), label, mode, d['total_hits'],
                                p['no'], p['sku'], p['name'], 'Y' if p['in_stock'] else 'N',
                                p['stock_qty'], p['price'], p['brand'], p['category'],
                                img_idx.get(p['sku'], ''), p['image_url']])
                    n_flat += 1

    # ---------------------------------------------------- sheet thong tin lan chay
    if 'Run_Info' in wb.sheetnames:
        del wb['Run_Info']
    info = wb.create_sheet('Run_Info')
    any_run = next(iter(next(iter(runs.values())).values()))
    lines = [
        ('MART Smart Search — Image Search: kết quả 4 cơ chế', ''),
        ('', ''),
        ('Ngày chạy', any_run['ran_at'][:19].replace('T', ' ')),
        ('Các lần chạy trong sheet', ' · '.join(
            '%s cột %s..%s' % (str(ws.cell(1, c).value)[1:6], get_column_letter(c), get_column_letter(c + BLOCK_W - 1))
            for c in range(BASE_COL, all_last + 1, BLOCK_W))
            + ' — mỗi lần chạy một khối cột, tiêu đề có tiền tố [dd/mm]; khối mới nhất nằm bên phải.'),
        ('Endpoint', any_run['api']),
        ('Cách gọi', 'multipart/form-data: image=<file> + params=<json>, gọi từ page context của dev console (cùng cookie/origin)'),
        ('params', json.dumps(any_run['params'], ensure_ascii=False)),
        ('Biến đã ghim', 'storeId=nsg (Nam Sài Gòn) · lang=vi · sort=relevance · page=1 · pageSize=100'),
        ('', ''),
        ('Cơ chế', 'imageMode gửi lên API'),
        ('Vector', 'vector — vector ảnh chính của sản phẩm'),
        ('Titan', 'vector_titan — Titan G1 (Sydney), trường image_vector_titan_v1, chỉ ảnh chính. Chỉ có ở khối 22/09 và 24/09 (bỏ từ lần chạy 28/09)'),
        ('Titan Multi', 'vector_titan_multi — Titan G1 trên NHIỀU ảnh của sản phẩm (gallery), thêm 2026-09-22'),
        ('Titan Multi Caption Type', 'vector_titan_multi_caption_type — thêm từ lần chạy 28/09, thay vị trí cột của Titan trong khối mới'),
        ('NovaLite (img to text)', 'caption — Nova Lite đọc ảnh ra câu tìm kiếm rồi search như text'),
        ('', ''),
        ('ĐỌC KỸ trước khi dùng số', ''),
        ('Tổng KQ (API) = totalHits', 'Với vector và vector_titan, totalHits luôn đúng 200 ở mọi ảnh — đây là trần top-K của tìm kiếm vector, KHÔNG phải tổng sản phẩm khớp. Chỉ totalHits của NovaLite (search text) mới là tổng thật.'),
        ('Số KQ trả về', 'Số sản phẩm API thực trả trong 1 trang (pageSize=100). Excel chỉ hiện top-40 đầu.'),
        ('Cột Top 40', 'Nằm ngay trong dòng của keyword, mỗi dòng trong ô là: No | SKU | Tên sản phẩm | Tồn kho. Ô bị cắt bớt vì Excel chặn chiều cao dòng ở 409.5pt — bấm vào ô để xem đủ trên thanh công thức, hoặc mở bảng dài ở results/excel_top40/top40_flat.csv.'),
        ('imageRef', 'Hash sha256 của chính file ảnh. Dán lại ref để gọi API thì ĐƯỢC, miễn giữ nguyên imageMode của lượt upload gốc và đặt ref trong params (để thành field riêng của form thì nhận 400 INVALID_QUERY). Đổi sang imageMode khác thì nhận 410 IMAGE_REF_EXPIRED vì backend cache embedding theo cặp (hash ảnh, imageMode) — đo trên ảnh hash mới tinh, xem scripts/inspect-imageref-fresh.mjs. Vì vậy mỗi cơ chế vẫn cần một lượt upload riêng. imageRef của cả 4 cơ chế trùng nhau chứng tỏ cả 4 chạy trên cùng một ảnh.'),
        ('tookMs', 'Thời gian backend tự báo, không gồm thời gian upload ảnh.'),
        ('', ''),
        ('Ảnh kết quả', 'result_images/<sku>.webp — tải sẵn cho dashboard, bảng tra ở result_images/index.csv'),
        ('Ảnh đầu vào', 'images/excel_keywords/ — trích từ chính các ảnh nhúng ở cột J của sheet Top100_Keywords'),
        ('Response thô', 'results/excel_top40/<imageMode>/<image_id>.json — giữ nguyên 100 sản phẩm + facets'),
        ('Bảng dài (dashboard)', 'results/excel_top40/top40_flat.csv — 1 dòng = 1 sản phẩm, đủ cột để pivot'),
        ('Script', 'scripts/run-excel-top40.mjs (chạy) · scripts/fetch-result-images.mjs (tải ảnh) · scripts/write_excel_results.py (đổ vào Excel)'),
    ]
    for i, (k, v) in enumerate(lines, start=1):
        a = info.cell(i, 1, k)
        b = info.cell(i, 2, v)
        a.font = Font(bold=True, sz=12 if i == 1 else 11)
        b.alignment = Alignment(wrap_text=True, vertical='top')
    info.column_dimensions['A'].width = 26
    info.column_dimensions['B'].width = 110

    out = args.out or args.xlsx
    try:
        wb.save(out)
    except PermissionError:
        out = os.path.splitext(args.xlsx)[0] + '_results.xlsx'
        wb.save(out)
        print('File goc dang mo trong Excel -> ghi ra ban canh ben.')

    print('Da ghi: %s' % out)
    print('  Top100_Keywords: lan chay %s -> %s khoi cot %s..%s, %d dong co ket qua'
          % (rnd, 'ghi de' if existed else 'THEM MOI', get_column_letter(base), get_column_letter(last_col), filled_rows))
    if tagged_legacy:
        print('  Khoi cu L..%s: gan tien to %s vao tieu de (du lieu giu nguyen)'
              % (get_column_letter(BASE_COL + BLOCK_W - 1), round_tag(LEGACY_ROUND).strip()))
    print('  Bang dai cho dashboard: %s (%d dong)' % (flat, n_flat))
    print('  Anh nhung giu lai: %d' % kept_images)
    if orphans:
        print('  %d ket qua KHONG con dong nao trong sheet (keyword da bi xoa?), bo qua:' % len(orphans))
        for i, k in orphans:
            print('     %s  %s' % (i, k))
    if mismatched:
        print('  %d dong LECH keyword — dung ngay, kiem tra lai:' % len(mismatched))
        for i, r, want, got in mismatched:
            print('     %s: dong %d dang la "%s", ky vong "%s"' % (i, r, got, want))


if __name__ == '__main__':
    main()
