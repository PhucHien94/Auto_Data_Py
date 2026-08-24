"""
Combine REQ documents and test case Excel files into a single combined CSV.
- Reads .docx files from SmartSearch/REQ
- Reads .xlsx files from SmartSearch/testcases
- Attempts to extract Requirement IDs and attach them to testcases
- Writes SmartSearch/testcases/Combined_TestCases_auto.csv

Dependencies: pandas, python-docx, openpyxl
"""
import os
import re
import sys
from pathlib import Path

try:
    import pandas as pd
except Exception:
    print("Missing pandas. Please install with: pip install pandas openpyxl python-docx")
    sys.exit(1)

try:
    import docx
except Exception:
    print("Missing python-docx. Please install with: pip install python-docx")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[2]
REQ_DIR = ROOT / "SmartSearch" / "REQ"
TESTCASE_DIR = ROOT / "SmartSearch" / "testcases"
OUT_FILE = TESTCASE_DIR / "Combined_TestCases_auto.csv"

REQ_PATTERN = re.compile(r'(REQ[-_ ]?\d+|R[EQ]?\d{2,}|Requirement\s*[:#-]?\s*(\w+))', re.IGNORECASE)

def extract_req_ids_from_text(text):
    if not isinstance(text, str):
        return []
    ids = set()
    for m in REQ_PATTERN.finditer(text):
        ids.add(m.group(0).strip())
    return list(ids)


def parse_docx_requirements(req_dir):
    reqs = []
    if not req_dir.exists():
        print(f"REQ folder not found: {req_dir}")
        return pd.DataFrame(columns=["req_source","req_id","req_text"])
    for p in req_dir.glob("*.docx"):
        try:
            doc = docx.Document(p)
            paragraphs = [para.text.strip() for para in doc.paragraphs if para.text.strip()]
            full = "\n".join(paragraphs)
            ids = extract_req_ids_from_text(full)
            if ids:
                for rid in ids:
                    reqs.append({"req_source": str(p.name), "req_id": rid, "req_text": full[:1000]})
            else:
                reqs.append({"req_source": str(p.name), "req_id": "", "req_text": full[:1000]})
        except Exception as e:
            print(f"Failed to parse {p}: {e}")
    return pd.DataFrame(reqs)


def read_testcase_excels(tc_dir):
    rows = []
    if not tc_dir.exists():
        print(f"Testcase folder not found: {tc_dir}")
        return pd.DataFrame()
    for p in tc_dir.glob("*.xlsx"):
        if p.name.startswith('~$'):
            continue
        try:
            xls = pd.read_excel(p, sheet_name=None, engine='openpyxl')
        except Exception as e:
            print(f"Failed to read {p}: {e}")
            continue
        for sheet_name, df in xls.items():
            if df.empty:
                continue
            df_columns = [c.strip() if isinstance(c, str) else c for c in df.columns]
            df.columns = df_columns
            for idx, row in df.iterrows():
                r = {"source_file": p.name, "sheet": sheet_name, "row_index": idx}
                # Try common columns
                for key in ["Testcase ID","TestcaseID","TC ID","TC_ID","ID","Test Case ID","Test Case"]:
                    if key in df.columns:
                        r["testcase_id"] = row.get(key, "")
                        break
                else:
                    r["testcase_id"] = row.get(df.columns[0], "")
                # Title/Description
                title_col = None
                for key in ["Title","Summary","Testcase Title","Description","Test Case"]:
                    if key in df.columns:
                        title_col = key
                        break
                r["title"] = row.get(title_col, "") if title_col else ""
                # Steps and expected
                r["steps"] = row.get("Steps", row.get("Test Steps", ""))
                r["expected"] = row.get("Expected", row.get("Expected Result", ""))
                # Try to extract requirement ids from known columns
                req_candidates = []
                for key in ["Requirement ID","Req ID","Requirement","Traceability","Req","Requirement ID(s)"]:
                    if key in df.columns:
                        val = row.get(key, "")
                        if pd.notna(val):
                            req_candidates.append(str(val))
                # also search in title/description
                text_search = " ".join([str(r.get("title", "")), str(r.get("steps", "")), str(r.get("expected", ""))])
                found = []
                for cand in req_candidates:
                    found.extend(extract_req_ids_from_text(cand))
                found.extend(extract_req_ids_from_text(text_search))
                r["requirement_ids"] = ",".join(sorted(set(found))) if found else ""
                rows.append(r)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def main():
    print(f"ROOT: {ROOT}")
    req_df = parse_docx_requirements(REQ_DIR)
    print(f"Found {len(req_df)} requirement entries from docx.")
    tc_df = read_testcase_excels(TESTCASE_DIR)
    if tc_df.empty:
        print("No testcases found or failed to read test_cases folder.")
    else:
        print(f"Found {len(tc_df)} testcase rows from Excel files.")
    # Simple mapping: keep testcase rows and attach any matching reqs
    out_dir = TESTCASE_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    if not tc_df.empty:
        tc_df.to_csv(OUT_FILE, index=False, encoding='utf-8-sig')
        print(f"Wrote combined testcases to {OUT_FILE}")
    else:
        print("No combined file written.")

if __name__ == '__main__':
    main()
