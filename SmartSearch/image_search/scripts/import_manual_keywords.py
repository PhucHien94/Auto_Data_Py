# -*- coding: utf-8 -*-
"""Chen keyword + anh nhung tu mot file Excel khac vao sheet Top100_Keywords.

    python scripts/import_manual_keywords.py --src "C:/.../image_search.xlsx" --dry-run
    python scripts/import_manual_keywords.py --src "C:/.../image_search.xlsx"

Nguon: sheet co cot keyword + anh nhung theo tung dong (mac dinh Sheet1, cot B).
Dich : Top100_Keywords, chen vao RANH GIOI giua khoi ngon ngu --after-lang va
khoi ke tiep, giu nguyen thu tu cac khoi con lai.

Anh nhung cua sheet dich KHONG bi anh huong: openpyxl khong doi anchor khi
insert_rows, ma toan bo anh hien co deu nam TREN diem chen. Script tu kiem tra
lai dieu do sau khi chen va bao neu lech.
"""
import argparse, io, os, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xml.etree.ElementTree as ET
import openpyxl
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from PIL import Image as PILImage

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, 'reconfigure'):
        _s.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, 'ImageSearch_TopKeywords_100_20260921.xlsx')
SHEET = 'Top100_Keywords'
IMG_COL = 10          # J — cot anh cua sheet dich
MAX_IMG_PX = 150      # chieu cao anh khi dat vao sheet dich
NS = {'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
R_EMBED = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed'


def zip_path(target):
    """Target trong rels luc la '../media/x.png', luc la '/xl/media/x.png'."""
    return target.replace('../', 'xl/').lstrip('/')


def read_source(path, sheet_name, key_col, first_row):
    """Tra ve [(keyword, bytes anh, duoi file)] theo tung dong co ca chu lan anh."""
    z = zipfile.ZipFile(path)
    wb = openpyxl.load_workbook(path)
    ws = wb[sheet_name]
    idx = wb.sheetnames.index(sheet_name) + 1

    drawing = None
    for rel in ET.fromstring(z.read('xl/worksheets/_rels/sheet%d.xml.rels' % idx)):
        if rel.get('Type').endswith('/drawing'):
            drawing = zip_path(rel.get('Target'))
    if not drawing:
        sys.exit('Sheet nguon khong co anh nhung.')
    d_dir, d_base = os.path.split(drawing)
    rels = {r.get('Id'): zip_path(r.get('Target'))
            for r in ET.fromstring(z.read('%s/_rels/%s.rels' % (d_dir, d_base)))}

    by_row = {}
    for anchor in ET.fromstring(z.read(drawing)):
        frm = anchor.find('xdr:from', NS)
        blip = anchor.find('.//a:blip', NS)
        if frm is None or blip is None:
            continue
        by_row.setdefault(int(frm.find('xdr:row', NS).text) + 1, []).append(rels[blip.get(R_EMBED)])

    out = []
    for r in range(first_row, ws.max_row + 1):
        kw = ws.cell(r, key_col).value
        imgs = by_row.get(r) or []
        if not kw or not imgs:
            continue
        src = imgs[0]
        out.append((str(kw).strip(), z.read(src), os.path.splitext(src)[1] or '.png'))
    return out


def lang_boundary(ws, after_lang):
    """Dong dau tien KHONG con thuoc khoi ngon ngu do -> cho chen."""
    rows = [r for r in range(2, ws.max_row + 1) if ws.cell(r, 2).value == after_lang]
    if not rows:
        sys.exit('Khong thay khoi ngon ngu %s trong sheet dich.' % after_lang)
    return max(rows) + 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--src-sheet', default='Sheet1')
    ap.add_argument('--key-col', type=int, default=2, help='cot keyword cua file nguon (B=2)')
    ap.add_argument('--first-row', type=int, default=2)
    ap.add_argument('--target', default=TARGET)
    ap.add_argument('--after-lang', default='VI', help='chen ngay sau khoi ngon ngu nay')
    ap.add_argument('--lang', default='VI', help='gia tri cot Ngon ngu cho dong moi')
    ap.add_argument('--stt-start', type=int, default=101)
    ap.add_argument('--note', default='Bổ sung từ {src} (bộ test thủ công), không thuộc top 100 theo lượt tìm')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    items = read_source(args.src, args.src_sheet, args.key_col, args.first_row)
    if not items:
        sys.exit('Khong doc duoc dong nao co ca keyword lan anh o file nguon.')

    wb = openpyxl.load_workbook(args.target)
    ws = wb[SHEET]
    at = lang_boundary(ws, args.after_lang)
    imgs_before = sorted(im.anchor._from.row + 1 for im in ws._images)
    existing = {str(ws.cell(r, 3).value).strip().lower(): r for r in range(2, ws.max_row + 1)}

    print('Nguồn : %s (%d keyword có ảnh)' % (os.path.basename(args.src), len(items)))
    print('Đích  : %s — chèn tại dòng %d (ngay sau khối %s)' % (os.path.basename(args.target), at, args.after_lang))
    for i, (kw, blob, ext) in enumerate(items):
        dup = existing.get(kw.lower())
        print('   %s  %-38s %6.1f KB %s' % ('kw%03d' % (args.stt_start + i), kw[:38], len(blob) / 1024,
                                            ('(TRÙNG keyword ở dòng %d)' % dup) if dup else ''))
    if args.dry_run:
        print('\n--dry-run: chưa ghi gì.')
        return

    ws.insert_rows(at, amount=len(items))
    # openpyxl khong doi anchor anh khi chen dong -> phai tu doi, neu khong anh
    # cua khoi ben duoi se dung yen trong khi keyword tut xuong.
    from add_keywords import shift_image_anchors
    shifted = shift_image_anchors(ws, at, len(items))
    if shifted:
        print('  dời %d ảnh nhúng xuống %d dòng' % (shifted, len(items)))
    note = args.note.format(src=os.path.basename(args.src))
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    wrap = Alignment(vertical='center', wrap_text=True)
    keep = []   # giu tham chieu anh song den luc save

    for i, (kw, blob, ext) in enumerate(items):
        r = at + i
        ws.cell(r, 1, args.stt_start + i).alignment = center
        ws.cell(r, 2, args.lang).alignment = center
        ws.cell(r, 3, kw).alignment = wrap
        dup = existing.get(kw.lower())
        ws.cell(r, 11, note + (' · trùng keyword với dòng %d, ảnh khác' % dup if dup else '')).alignment = wrap

        bio = io.BytesIO(blob)
        with PILImage.open(io.BytesIO(blob)) as probe:
            w, h = probe.size
        scale = min(1.0, MAX_IMG_PX / float(h))
        img = XLImage(bio)
        img.width, img.height = int(w * scale), int(h * scale)
        img.anchor = '%s%d' % (get_column_letter(IMG_COL), r)
        ws.add_image(img)
        keep.append((bio, img))
        ws.row_dimensions[r].height = max(ws.row_dimensions[r].height or 0, img.height * 0.78)

    ws.auto_filter.ref = 'A1:%s%d' % (get_column_letter(ws.max_column), ws.max_row)
    wb.save(args.target)

    # Kiem chung: anh cu phai o nguyen dong cu, anh moi phai dung dong vua chen
    wb2 = openpyxl.load_workbook(args.target)
    ws2 = wb2[SHEET]
    rows_after = sorted(im.anchor._from.row + 1 for im in ws2._images)
    moved = [r for r in imgs_before if r not in rows_after]
    print('\nĐã ghi: %s' % args.target)
    print('  %d dòng mới ở %d–%d · STT %d–%d' % (len(items), at, at + len(items) - 1,
                                                 args.stt_start, args.stt_start + len(items) - 1))
    print('  ảnh nhúng: %d trước -> %d sau' % (len(imgs_before), len(rows_after)))
    print('  ảnh cũ bị xê dịch dòng: %s' % (moved if moved else 'không'))


if __name__ == '__main__':
    main()
