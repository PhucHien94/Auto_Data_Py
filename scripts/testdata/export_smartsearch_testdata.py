"""Export a Smart Search autocomplete/search-result test dataset (the main
2,000-scenario set, or any single batch file) into a dev-ready deliverable:

  1. A denormalized JSON (`..._v1.0_<date>.json`, or `..._v1.0_<range>_<date>.json`
     for a batch) — same shape as the source, but every search_result is
     joined against the real VI catalog so it carries name/price/category
     inline, not just SKU. Meant for programmatic import into a test
     framework. Written to SmartSearch/test_data/json/for_dev/ — kept
     in its own folder, separate from the raw batches/_source files, so
     QA/dev only ever needs to look in one place for a ready-to-use file.
  2. An Excel workbook (`..._v1.0_<date>.xlsx`, `--with-excel` only) — one row
     per scenario, AutoFilter enabled on every column so QA can filter by
     dimension or route in Excel directly, plus Cover and Summary sheets
     matching the house style used by generate_testcase_datasets.py.

**Standing rule:** every time a new batch is generated in
SmartSearch/test_data/json/batches/, immediately run this script with
`--source <that batch's filename>` so a dev-ready file exists for it too —
this is not an optional follow-up.

Source data: SmartSearch/test_data/json/_source/{dataset_2000.json,
queries_2000.json, search_engine.js} (the original 2,000-scenario set) and
.../batches/NSG_ExpectedData_<range>_<date>.json (incremental batches) —
copied from the session that built the "NSG Expected data" Artifact. Re-run
that Artifact's pipeline to refresh dataset_2000.json before re-running this
script, if the engine/glossaries ever change.

Usage:
    python scripts/testdata/export_smartsearch_testdata.py
    python scripts/testdata/export_smartsearch_testdata.py --source NSG_ExpectedData_2000-3000_20260821.json
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "SmartSearch" / "test_data" / "json" / "_source"
BATCHES_DIR = ROOT / "SmartSearch" / "test_data" / "json" / "batches"
OUT_DIR_DEV = ROOT / "SmartSearch" / "test_data" / "json" / "for_dev"
OUT_DIR_XLSX = ROOT / "SmartSearch" / "test_data" / "excel"
PRODUCT_NDJSON = ROOT / "data" / "ProductInfo" / "mart_vi_nsg_product.ndjson"

TODAY = date.today().strftime("%Y%m%d")

DIM_LABELS = {
    "typo": "Sai chính tả",
    "no_diacritics": "Không dấu",
    "intent": "Mục đích/ngữ nghĩa",
    "regional": "Từ địa phương",
    "synonym": "Đồng nghĩa",
    "category": "Cùng danh mục",
    "multilang": "Đa ngôn ngữ",
}
ROUTE_LABELS = {
    "keyword": "Chỉ từ khoá",
    "keyword_ai": "Từ khoá + AI",
}


def fmt_price(v) -> str:
    if not v:
        return ""
    return f"{v:,.0f}".replace(",", ".") + "đ"


def load_catalog() -> dict[str, dict]:
    out: dict[str, dict] = {}
    with open(PRODUCT_NDJSON, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)["_source"]
            sku = d.get("sku")
            if not sku:
                continue
            cat_path = d.get("category_full_path") or [""]
            out[sku] = {
                "name": (d.get("name") or "").strip(),
                "price": d.get("price_default") or 0,
                "category": cat_path[1] if len(cat_path) > 1 else (cat_path[0] if cat_path else ""),
            }
    return out


def denormalize(dataset: list[dict], catalog: dict[str, dict]) -> list[dict]:
    out = []
    missing = 0
    for scenario in dataset:
        results = []
        for r in scenario["search_results"]:
            p = catalog.get(r["sku"])
            if p is None:
                missing += 1
                results.append({**r, "name": "", "price": "", "category": ""})
            else:
                results.append({**r, "name": p["name"], "price": p["price"], "category": p["category"]})
        out.append({**scenario, "search_results": results})
    if missing:
        print(f"warning: {missing} search_result SKUs not found in catalog (stale reference)")
    return out


# ---------------------------------------------------------------------
# Excel workbook
# ---------------------------------------------------------------------

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True)
ROW_FILL_A = PatternFill("solid", fgColor="F2F2F2")
ROW_FILL_B = PatternFill("solid", fgColor="FFFFFF")
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")

COLUMNS = [
    ("Test ID", 16),
    ("Nhóm hành vi", 16),
    ("Nhánh dự kiến", 14),
    ("Độ chắc chắn", 11),
    ("Query (input)", 26),
    ("Ghi chú / kỳ vọng", 34),
    ("Autocomplete — Loại 1 (theo từ khoá, top 10)", 46),
    ("Số gợi ý (đã xác thực)", 10),
    ("Search results (top 10: SKU — Tên — Giá — tier)", 60),
    ("Số kết quả hiển thị / tổng thật", 14),
]


def autocomplete_cell(scenario: dict) -> str:
    items = scenario["autocomplete_suggestions"][:10]
    if not items:
        return "(không có gợi ý nào có sản phẩm thật khớp)"
    return "; ".join(f'{a["keyword"]} ({a["verified_product_count"]} SP)' for a in items)


def results_cell(scenario: dict) -> str:
    items = scenario["search_results"][:10]
    if not items:
        return "(không có sản phẩm nào khớp)"
    lines = []
    for r in items:
        name = r.get("name") or "(SKU không tra được tên — dữ liệu catalog có thể đã đổi)"
        price = fmt_price(r.get("price"))
        lines.append(f'{r["sku"]} — {name} — {price} — {r["tier"]}')
    return "\n".join(lines)


def write_cover(wb, generated_date: str, total: int):
    ws = wb.create_sheet("Cover", 0)
    ws.column_dimensions["A"].width = 100
    lines = [
        ("MART Smart Search – Autocomplete & Search Result Test Data (2.000 kịch bản)", 16, True),
        (f"Ngày tạo: {generated_date}    |    Nguồn: NSG Search Test Data Artifact (toàn bộ 16.340 SKU store nsg)", 11, False),
        ("", 11, False),
        ("Cách đọc file:", 12, True),
        ("- Sheet 'Scenarios': 1 dòng = 1 kịch bản tìm kiếm thực tế (sai chính tả, không dấu, theo mục đích "
         "sử dụng, từ địa phương, đồng nghĩa, cùng danh mục, đa ngôn ngữ). Đã bật AutoFilter — lọc theo cột "
         "'Nhóm hành vi' hoặc 'Nhánh dự kiến' ngay trong Excel.", 11, False),
        ("- Cột 'Nhánh dự kiến': mô phỏng theo luồng Adaptive Search thật (OVERVIEW-FLOW-VI_Phase1.pdf, Phần 2) — "
         "'Chỉ từ khoá' nghĩa là độ chắc chắn của kết quả từ khoá đã ≥50%, hệ thống thật sẽ dừng lại không cần "
         "gọi AI; 'Từ khoá + AI' nghĩa là <50%, hệ thống thật sẽ gọi thêm nhánh AI/ngữ nghĩa rồi trộn kết quả.", 11, False),
        ("- Cột Autocomplete/Search results chỉ hiển thị Top 10 để file gọn; dữ liệu ĐẦY ĐỦ (top 30 gợi ý, "
         "toàn bộ kết quả tìm kiếm đã tính) nằm trong file JSON đi kèm cùng thư mục, cùng tên, đuôi .json — "
         "import trực tiếp file đó nếu cần automation/so khớp chương trình.", 11, False),
        ("- Mọi từ khoá autocomplete đều đã được xác thực: search lại và chỉ giữ nếu có ít nhất 1 sản phẩm "
         "thật khớp trong catalog — không có gợi ý '0 kết quả' trong dữ liệu này.", 11, False),
        ("", 11, False),
        (f"Tổng số kịch bản: {total}", 12, True),
        ("Nguồn engine/glossary dùng để sinh dữ liệu này (để tái tạo hoặc mở rộng sau này) nằm ở "
         "SmartSearch/test_data/json/_source/ (search_engine.js, queries_2000.json, dataset_2000.json).", 11, False),
    ]
    for text, size, bold in lines:
        ws.append([text])
        ws.cell(ws.max_row, 1).font = Font(size=size, bold=bold)
        ws.cell(ws.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")


def write_summary(wb, dataset: list[dict]):
    ws = wb.create_sheet("Summary")
    by_dim: dict[str, dict[str, int]] = {}
    for s in dataset:
        d = by_dim.setdefault(s["dimension"], {"keyword": 0, "keyword_ai": 0, "total": 0})
        d[s["route"]] += 1
        d["total"] += 1
    ws.append(["Nhóm hành vi", "Tổng số kịch bản", "Chỉ từ khoá", "Từ khoá + AI"])
    for c in ws[1]:
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
    for dim, counts in sorted(by_dim.items(), key=lambda kv: -kv[1]["total"]):
        ws.append([DIM_LABELS.get(dim, dim), counts["total"], counts["keyword"], counts["keyword_ai"]])
    total = len(dataset)
    kw_total = sum(1 for s in dataset if s["route"] == "keyword")
    ws.append(["TỔNG", total, kw_total, total - kw_total])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    widths = [22, 18, 16, 16]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"


def write_scenarios(wb, dataset: list[dict]):
    ws = wb.create_sheet("Scenarios")
    ws.append([c[0] for c in COLUMNS])
    for c in ws[1]:
        c.fill = HEADER_FILL
        c.font = HEADER_FONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    for i, (_, width) in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    for row_i, s in enumerate(dataset, 2):
        vals = [
            s["test_id"],
            DIM_LABELS.get(s["dimension"], s["dimension"]),
            ROUTE_LABELS.get(s["route"], s["route"]),
            f'{round(s["confidence"])}%',
            s["query"],
            s.get("note", ""),
            autocomplete_cell(s),
            len(s["autocomplete_suggestions"]),
            results_cell(s),
            f'{len(s["search_results"])} / {s["search_results_total_before_cap"]}',
        ]
        ws.append(vals)
        fill = ROW_FILL_A if row_i % 2 else ROW_FILL_B
        for c in ws[row_i]:
            c.fill = fill
            c.border = BORDER
            c.alignment = WRAP

    last_row = ws.max_row
    last_col = get_column_letter(len(COLUMNS))
    table = Table(displayName="ScenariosTable", ref=f"A1:{last_col}{last_row}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=False)
    ws.add_table(table)


def resolve_source(name: str) -> Path:
    """A bare filename is searched in _source/ first (dataset_2000.json lives
    there, as a plain array), then batches/ (NSG_ExpectedData_*.json, wrapped
    as {scenarios:[...]}). An explicit path (contains a separator) is used
    as-is, relative to ROOT."""
    if "/" in name or "\\" in name:
        return ROOT / name
    for candidate in (SRC_DIR / name, BATCHES_DIR / name):
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"'{name}' not found in _source/ or batches/")


def load_source_dataset(path: Path) -> tuple[list[dict], str | None]:
    """Returns (scenarios, batch_range). Handles both dataset_2000.json's
    bare-array shape and a batch file's {scenarios:[...], batchRange} shape."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw, None
    return raw["scenarios"], raw.get("batchRange")


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="dataset_2000.json",
                     help="filename to export — searched in test_data/json/_source/ then "
                          "test_data/json/batches/ (default: dataset_2000.json). Accepts a "
                          "batch file (e.g. NSG_ExpectedData_2000-3000_<date>.json) directly.")
    ap.add_argument("--with-excel", action="store_true",
                     help="also build the .xlsx (default: JSON only — the .xlsx is a template, "
                          "regenerate it only when asked)")
    args = ap.parse_args()

    print("loading source dataset...")
    source_path = resolve_source(args.source)
    dataset, batch_range = load_source_dataset(source_path)
    print(f"  {len(dataset)} scenarios (from {source_path.relative_to(ROOT)})")

    print("loading catalog for denormalization...")
    catalog = load_catalog()
    print(f"  {len(catalog)} SKUs")

    print("denormalizing search_results (sku -> name/price/category)...")
    dataset = denormalize(dataset, catalog)

    base_name = (f"MART_SmartSearch_AutocompleteSearch_TestData_v1.0_{batch_range}_{TODAY}"
                 if batch_range else f"MART_SmartSearch_AutocompleteSearch_TestData_v1.0_{TODAY}")

    OUT_DIR_DEV.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR_DEV / f"{base_name}.json"
    payload = {
        "generatedDate": date.today().isoformat(),
        "store": "nsg",
        "totalScenarios": len(dataset),
        "scenarios": dataset,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {json_path} ({json_path.stat().st_size / 1024 / 1024:.2f} MB)")

    if not args.with_excel:
        print("skipping .xlsx (pass --with-excel to also build it)")
        return

    print("building Excel workbook...")
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    write_cover(wb, date.today().isoformat(), len(dataset))
    write_summary(wb, dataset)
    write_scenarios(wb, dataset)
    OUT_DIR_XLSX.mkdir(parents=True, exist_ok=True)
    xlsx_path = OUT_DIR_XLSX / f"{base_name}.xlsx"
    wb.save(xlsx_path)
    print(f"wrote {xlsx_path} ({xlsx_path.stat().st_size / 1024 / 1024:.2f} MB)")


if __name__ == "__main__":
    main()
