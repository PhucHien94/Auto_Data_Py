import pandas as pd
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TC_DIR = ROOT / 'output' / 'test_cases'
KEYWORDS = [
    'recent', 'recent search', 'recent searches', 'clear all', 'clear history', 'history', 'login', 'device', 'account',
    'placeholder',
    # Vietnamese
    'gần đây', 'tìm gần đây', 'lịch sử', 'xóa tất cả', 'xóa', 'đăng nhập', 'thiết bị', 'tài khoản'
]

pattern = re.compile('|'.join(re.escape(k) for k in KEYWORDS), re.IGNORECASE)

for xlsx in TC_DIR.glob('*.xlsx'):
    if xlsx.name.startswith('~$'):
        continue
    print(f'-- Scanning {xlsx.name}')
    try:
        sheets = pd.read_excel(xlsx, sheet_name=None, engine='openpyxl')
    except Exception as e:
        print('  failed to read:', e)
        continue
    for sheet_name, df in sheets.items():
        # convert all cells to string and search
        found_any = False
        for col in df.columns:
            for i, val in df[col].fillna('').astype(str).items():
                if pattern.search(val):
                    print(f'  Match in {xlsx.name} | Sheet: {sheet_name} | Row: {i+1} | Col: {col} -> {val[:200]}')
                    found_any = True
        if not found_any:
            pass

print('Done')
