# -*- coding: utf-8 -*-
"""Trich anh nhung trong sheet Top100_Keywords ra file de upload len API.

    python scripts/extract_excel_images.py [--xlsx <file>]

Anh nam trong cot J cua tung dong keyword. Moi anh -> images/excel_keywords/
va mot dong trong manifest.json (image_id, dong Excel, keyword, duong dan).
Chay lai bat ky luc nao: anh moi them vao Excel se duoc trich bo sung.
"""
import argparse, glob, hashlib, json, os, re, unicodedata, zipfile
import xml.etree.ElementTree as ET
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'images', 'excel_keywords')
NS = {'xdr': 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
R_EMBED = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed'


ID_MAP = os.path.join(OUT_DIR, 'id_map.json')


def load_id_map():
    """sha256 cua anh -> image_id. Ben qua moi thao tac tren sheet.

    Truoc day image_id = 'kw%03d' % STT, tuc buoc dinh danh vao MOT COT MA USER
    SUA — danh lai so thu tu la doi id ca bo, moi ket qua da chay thanh mo coi
    va phai chay lai tu dau. Neo vao noi dung anh thi doi so bao nhieu lan cung
    khong anh huong. Lan dau chay, map duoc gieo tu manifest cu de giu nguyen
    id da cap (kw001, kw101...).
    """
    if os.path.exists(ID_MAP):
        return json.load(open(ID_MAP, encoding='utf-8'))
    seed, old = {}, os.path.join(OUT_DIR, 'manifest.json')
    if os.path.exists(old):
        for r in json.load(open(old, encoding='utf-8')):
            f = os.path.join(os.path.dirname(OUT_DIR), r['file'])
            if os.path.exists(f):
                seed[hashlib.sha256(open(f, 'rb').read()).hexdigest()] = r['image_id']
        print('Gieo id_map tu manifest cu: %d anh giu nguyen image_id' % len(seed))
    return seed


def save_id_map(m):
    with open(ID_MAP, 'w', encoding='utf-8') as fh:
        json.dump(m, fh, indent=2)


def next_free_id(used):
    n = 1
    while ('kw%03d' % n) in used:
        n += 1
    return 'kw%03d' % n


def slug(s):
    s = unicodedata.normalize('NFD', str(s)).replace('đ', 'd').replace('Đ', 'D')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--xlsx', default=os.path.join(ROOT, 'ImageSearch_TopKeywords_100_20260921.xlsx'))
    ap.add_argument('--sheet', default='Top100_Keywords')
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    z = zipfile.ZipFile(args.xlsx)
    ws = openpyxl.load_workbook(args.xlsx)[args.sheet]

    # Target trong rels luc la '../media/x.png', luc la '/xl/media/x.png'
    # (openpyxl ghi kieu tuyet doi) -> quy ve duong dan trong zip.
    def zip_path(target):
        return target.replace('../', 'xl/').lstrip('/')

    # sheet nao -> drawing nao: doc qua rels cua chinh sheet do
    sheet_idx = openpyxl.load_workbook(args.xlsx).sheetnames.index(args.sheet) + 1
    rels_path = 'xl/worksheets/_rels/sheet%d.xml.rels' % sheet_idx
    drawing = None
    for rel in ET.fromstring(z.read(rels_path)):
        if rel.get('Type').endswith('/drawing'):
            drawing = zip_path(rel.get('Target'))
    if not drawing:
        raise SystemExit('Sheet %s khong co drawing (khong co anh nhung).' % args.sheet)

    dir_, base_ = os.path.split(drawing)
    drels = {r.get('Id'): zip_path(r.get('Target'))
             for r in ET.fromstring(z.read('%s/_rels/%s.rels' % (dir_, base_)))}

    id_map = load_id_map()          # sha256 anh -> image_id, ben qua moi lan sua sheet
    used = set(id_map.values())
    taken_this_run = set()

    rows, new, minted = [], 0, []
    for anchor in ET.fromstring(z.read(drawing)):
        frm = anchor.find('xdr:from', NS)
        if frm is None:
            continue
        xl_row = int(frm.find('xdr:row', NS).text) + 1
        blip = anchor.find('.//a:blip', NS)
        if blip is None:
            continue
        src = drels[blip.get(R_EMBED)]
        stt, lang, kw = (ws.cell(xl_row, i).value for i in (1, 2, 3))
        data = z.read(src)
        sha = hashlib.sha256(data).hexdigest()

        # image_id neo vao NOI DUNG ANH, khong phai so thu tu: cot No doi so
        # (them/xoa/danh lai) thi id van nguyen, ket qua da chay van dung chu.
        # Cung mot anh dan o hai dong -> dong thu hai duoc cap id rieng.
        image_id = id_map.get(sha)
        if image_id is None or image_id in taken_this_run:
            image_id = next_free_id(used)
            id_map[sha] = image_id if image_id not in id_map.values() else image_id
            used.add(image_id)
            minted.append((image_id, kw))
        taken_this_run.add(image_id)
        id_map[sha] = image_id

        fname = '%s_%s%s' % (image_id, slug(kw), os.path.splitext(src)[1])
        path = os.path.join(OUT_DIR, fname)
        if not (os.path.exists(path) and open(path, 'rb').read() == data):
            open(path, 'wb').write(data)
            new += 1
        # keyword doi ten -> ten file cu cua chinh id do khong con dung, don di
        for old in glob.glob(os.path.join(OUT_DIR, image_id + '_*')):
            if os.path.basename(old) != fname:
                os.remove(old)
        rows.append(dict(image_id=image_id, excel_row=xl_row, stt=stt, lang=lang,
                         keyword=kw, file='excel_keywords/' + fname, sha256=sha,
                         bytes=len(data), src=src))

    save_id_map(id_map)

    rows.sort(key=lambda r: r['excel_row'])
    with open(os.path.join(OUT_DIR, 'manifest.json'), 'w', encoding='utf-8') as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)

    print('%d anh trong sheet (%d file moi ghi, %d image_id moi cap)' % (len(rows), new, len(minted)))
    for i, k in minted:
        print('   + %s  %s' % (i, k))
    for r in rows:
        print('  %s  dong %-3d %-18s %6.1f KB  %s'
              % (r['image_id'], r['excel_row'], r['keyword'], r['bytes'] / 1024, r['file']))


if __name__ == '__main__':
    main()
