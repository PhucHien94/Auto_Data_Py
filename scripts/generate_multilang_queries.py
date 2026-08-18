#!/usr/bin/env python3
import json
import unicodedata
from pathlib import Path
from itertools import islice
import argparse
import pandas as pd


SYNONYMS_VI = {
    'lợn': ['heo'],
    'heo': ['lợn'],
    'rau mùi': ['rau húng', 'ngò'],
    'rau húng': ['rau mùi', 'ngò'],
}


def strip_diacritics(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


def stream_ndjson(path):
    with open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def unwrap_source(obj):
    if isinstance(obj, dict) and '_source' in obj and isinstance(obj['_source'], dict):
        return obj['_source']
    return obj


def find_title(obj):
    if not isinstance(obj, dict):
        return None
    for key in ('title', 'name', 'product_name', 'name_en', 'name_vi', 'name_kr'):
        if key in obj and obj[key]:
            return str(obj[key])
    # try nested custom_attribute
    ca = obj.get('custom_attribute') or {}
    if isinstance(ca, dict):
        for k in ('name', 'title'):
            if ca.get(k):
                return str(ca.get(k))
    # fallback to 'name' in top
    if 'name' in obj:
        return str(obj['name'])
    return None


def find_sku(obj):
    if not isinstance(obj, dict):
        return None
    for key in ('sku', 'sku_code', 'id', 'product_id'):
        if key in obj and obj[key]:
            return str(obj[key])
    ca = obj.get('custom_attribute') or {}
    if isinstance(ca, dict) and ca.get('sku'):
        return str(ca.get('sku'))
    return None


def generate_short_keywords(title):
    # produce 1-5 char tokens: initials, prefixes, substrings from words
    out = set()
    words = [w for w in title.split() if w]
    if not words:
        return []
    # initials
    initials = ''.join(w[0] for w in words)[:5]
    if initials:
        out.add(initials)
    # prefixes of first word
    first = words[0]
    for L in range(1, min(6, len(first)+1)):
        out.add(first[:L])
    # small substrings from words
    for w in words:
        for i in range(len(w)):
            for L in range(1, 6):
                sub = w[i:i+L]
                if len(sub) >= 1:
                    out.add(sub)
    # limit to reasonable count
    res = [s for s in out if 1 <= len(s) <= 5]
    # sort by length then lexicographically
    res = sorted(set(res), key=lambda x: (len(x), x))
    return res[:20]


def apply_synonyms_vi(title):
    # return list of variants replacing known synonym phrases
    variants = set([title])
    lower = title.lower()
    for phrase, alts in SYNONYMS_VI.items():
        if phrase in lower:
            for alt in alts:
                variants.add(lower.replace(phrase, alt))
    return list(variants)


def make_variants_for_title(title, lang):
    variants = []
    title = title.strip()
    if not title:
        return variants
    # exact
    variants.append(('exact', title))
    # lowercase
    variants.append(('lowercase', title.lower()))
    # partial: first 2-4 words
    words = title.split()
    if len(words) > 1:
        take = min(4, max(2, len(words)//2))
        variants.append(('partial', ' '.join(words[:take])))
    # short keywords
    short_keys = generate_short_keywords(title)
    for sk in short_keys[:5]:
        variants.append(('short', sk))
    # language specific
    if lang == 'vi':
        variants.append(('no_diacritics', strip_diacritics(title)))
        # synonyms
        for v in apply_synonyms_vi(title):
            if v != title:
                variants.append(('synonym', v))
    # include typo-light variant: swap two chars
    if len(title) >= 4:
        s = list(title)
        i = min(len(s)-2, max(1, len(s)//4))
        s[i], s[i+1] = s[i+1], s[i]
        variants.append(('typo', ''.join(s)))

    # dedupe preserving order
    seen = set()
    out = []
    for t, q in variants:
        key = q.lower()
        if key not in seen:
            out.append((t, q))
            seen.add(key)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--v1', required=True, help='Path to v1 folder')
    p.add_argument('--out', default='output/text_testdata/multilang_queries.xlsx')
    p.add_argument('--max-per-file', type=int, default=500)
    args = p.parse_args()

    v1 = Path(args.v1)
    files = list(v1.glob('*.ndjson'))
    # group by language code in filename: _en_, _vi_, _kr_
    lang_files = {'en': [], 'vi': [], 'kr': []}
    for f in files:
        name = f.name.lower()
        if '_en_' in name:
            lang_files['en'].append(f)
        if '_vi_' in name:
            lang_files['vi'].append(f)
        if '_kr_' in name:
            lang_files['kr'].append(f)

    # map sku -> {lang: title}
    products = {}

    for lang, flist in lang_files.items():
        for f in flist:
            count = 0
            for obj in islice(stream_ndjson(f), args.max_per_file):
                count += 1
                src = unwrap_source(obj)
                sku = find_sku(src)
                title = find_title(src)
                if not sku or not title:
                    continue
                if sku not in products:
                    products[sku] = {'sku': sku, 'titles': {}}
                products[sku]['titles'][lang] = title

    rows = []
    tid = 0
    for sku, info in products.items():
        titles = info.get('titles', {})
        # for each language available, generate queries
        for lang, title in titles.items():
            variants = make_variants_for_title(title, lang)
            for vtype, query in variants:
                tid += 1
                # search order: origin lang first, then the other two
                order = [lang] + [l for l in ('en', 'vi', 'kr') if l != lang]
                rows.append({
                    'test_id': f'MQ-{tid:06d}', 'sku': sku, 'origin_lang': lang,
                    'title': title, 'variant_type': vtype, 'query': query,
                    'search_order': ','.join(order), 'priority': 'normal', 'notes': ''
                })

    df = pd.DataFrame(rows)
    outp = Path(args.out)
    try:
        with pd.ExcelWriter(outp, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='queries', index=False)
        print(f'Wrote {len(df)} queries to {outp}')
    except Exception as e:
        print('Failed to write Excel:', e)


if __name__ == '__main__':
    main()
