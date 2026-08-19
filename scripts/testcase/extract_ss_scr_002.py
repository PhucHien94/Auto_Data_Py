import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TC_DIR = ROOT / 'output' / 'test_cases'

for xlsx in TC_DIR.glob('MART_SmartSearch_Combined_TestCases_v3.0_20260818*.xlsx'):
    if xlsx.name.startswith('~$'):
        continue
    print('---', xlsx.name)
    xls = pd.read_excel(xlsx, sheet_name=None, engine='openpyxl')
    for sheet_name, df in xls.items():
        # convert all to string
        df_str = df.fillna('').astype(str)
        mask = df_str.apply(lambda row: row.str.contains('SS-SCR-002', case=False, na=False)).any(axis=1)
        matches = df[mask]
        if not matches.empty:
            print(f'Sheet: {sheet_name} — {len(matches)} rows')
            for idx, row in matches.iterrows():
                print('Row', idx+1)
                for col in df.columns:
                    print(f'  {col}:', row[col])
                print()

print('Done')
