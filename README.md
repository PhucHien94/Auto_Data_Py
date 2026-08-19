# Auto_Data_Py

This workspace contains scripts and test data for generating and running text-search, image-search, and golden-set relevance tests for the MART Smart Search project.

## Layout

```
Auto_Data_Py/
├── scripts/
│   ├── testcase/              testcase authoring/review: combine REQ+testcases, preview, keyword search, translate
│   ├── testdata/               test-data generators: golden testset, text/image testdata, multilang queries, sampling
│   ├── automation/             execute automation test: run_autoscript (+ lib_scoring/lib_search_client), runner_text_search
│   └── performance/            execute performance test (k6): export_manual_qc_assets, k6_search_test.js + k6_queries.json
├── data/
│   ├── ProductInfo/          source NDJSON product datasets (EN/VI/KR per store)
│   └── glossary/              synonyms/regional/related-term CSVs for keyword-variant generation
├── config/
│   └── environments.yaml     search/autocomplete API endpoints per environment
├── output/
│   ├── golden_testsets/      per-store datasets from generate_master_testset.py
│   ├── runs/                  run_autoscript.py results (report.xlsx + raw NDJSON)
│   ├── manual_qc/             exported Postman collections per dataset
│   ├── text_testdata/        generated inputs, expected outputs, samples, and workbooks
│   ├── REQ/                   BRD/storyboard source documents
│   └── test_cases/            delivered test-case and QnA-log workbooks
├── docs/                      additional docs (e.g. image test data usage)
└── requirements.txt
```

## Quick start

1. Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Golden-set relevance testing (search + autocomplete)

Full strategy and rationale (4-tier pass model, keyword-variant taxonomy, manual-QC guide) is written up as a shared strategy doc; ask if you need the link again. Short version:

1. Generate a golden dataset for one store (or all 20):

```powershell
python scripts\testdata\generate_master_testset.py --store nsg --out-dir output\golden_testsets\nsg
python scripts\testdata\generate_master_testset.py --all-stores --out-dir output\golden_testsets
```

Writes `search_result_expected.ndjson`, `autocomplete_expected.ndjson`, and a `manifest.json` documenting sample size and assumptions (popularity proxy, glossary coverage). Keyword-variant coverage (`data/glossary/*.csv`) ships with placeholder rows only for the `regional` and `related` dimensions — curate those with QA/BA before relying on them in a real cycle.

2. Run it against a live API and get a scored report:

```powershell
python scripts\automation\run_autoscript.py `
  --dataset-dir output\golden_testsets\nsg `
  --search-api https://staging-search.internal/api/v1/search `
  --autocomplete-api https://staging-search.internal/api/v1/suggest `
  --header "Authorization: Bearer <TOKEN>"

# or with a saved environment
python scripts\automation\run_autoscript.py --dataset-dir output\golden_testsets\nsg --env staging
```

Writes `output/runs/<dataset>_<timestamp>/report.xlsx` (Summary + tier-colored Detail + a Tier4_NeedsReview sheet) plus raw NDJSON results, and prints a console summary. Scoring logic (`scripts/lib_scoring.py`) applies a 4-tier model — exact Top-1, present in Top-N, recall against an `acceptable_set`, or flagged for manual review — since a single expected SKU isn't a valid pass criterion for every query dimension (synonym/related-term queries can have several legitimately correct results).

3. Manual QC tooling (Postman / k6), generated from the same dataset:

```powershell
python scripts\performance\export_manual_qc_assets.py --dataset-dir output\golden_testsets\nsg --out-dir output\manual_qc\nsg
```

Writes a Postman collection + environment + data CSV, and `scripts/performance/k6_search_test.js` + `k6_queries.json`. Run the load test itself with the k6 extension (or CLI): `k6 run scripts/performance/k6_search_test.js`.

## Legacy / ad-hoc test data generation

```powershell
python scripts\testdata\generate_text_testdata.py --ndjson data\ProductInfo\mart_en_nsg_product.ndjson --out-dir output\text_testdata
python scripts\testdata\generate_multilang_queries.py --v1 data\ProductInfo --out output\text_testdata\multilang_queries.xlsx --max-per-file 200
python scripts\testdata\sample_queries.py --in output\text_testdata\multilang_queries.xlsx --out output\text_testdata\sample_queries.xlsx --size 1000
python scripts\automation\runner_text_search.py --excel output\text_testdata\text_testdata.xlsx --inputs output\text_testdata\sample_inputs.ndjson --api-url "https://api.example.com/search" --method GET --param q --topn 5 --header "Authorization: Bearer <TOKEN>"
```

## Files of interest

- `scripts/testdata/generate_master_testset.py` — golden dataset generator (Part 1 of the strategy)
- `scripts/automation/run_autoscript.py` + `lib_scoring.py` + `lib_search_client.py` — run + score + report against a live API (Part 2/3)
- `scripts/performance/export_manual_qc_assets.py` + `k6_search_test.js` + `k6_queries.json` — Postman/k6 asset export and the k6 load-test script itself (Part 4)
- `scripts/testdata/generate_text_testdata.py`, `generate_multilang_queries.py`, `generate_image_testdata.py`, `sample_queries.py` — earlier ad-hoc test-data generators, still usable standalone
- `scripts/automation/runner_text_search.py` — earlier ad-hoc runner, still usable standalone
- `scripts/testcase/add_results_template.py`, `preview_testcase.py`, `translate_excel.py`, `combine_req_testcases.py`, `search_testcases_keywords.py`, `extract_ss_scr_002*.py` — test-case workbook tooling (combine REQ+testcases, preview, translate, keyword/ID search)
- `data/ProductInfo/` — source NDJSON product datasets (EN/VI/KR per store)
- `data/glossary/` — synonym/regional/related-term CSVs (see file headers for schema)
- `output/test_cases/` — delivered MART SmartSearch test-case and QnA-log workbooks
- `docs/` — additional documentation
