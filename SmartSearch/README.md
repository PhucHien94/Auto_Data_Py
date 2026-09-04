# Smart Search — MART

This folder contains everything specific to the **Smart Search & Autocomplete** feature (REQ, test cases, QnA log, golden test data, run reports, manual-QC assets, full-catalog exports, AI context). Shared infrastructure — `scripts/`, `data/` (source product catalogs), `config/environments.yaml`, `.claude/` — stays at the repo root (`Auto_Data_Py/`) so other feature modules can reuse it. All commands below are run **from the repo root**, not from inside this folder.

See [`AI_CONTEXT.md`](AI_CONTEXT.md) for the full architecture/decisions context (written for another AI to onboard quickly). See [`RUNBOOK_data_and_compare.md`](RUNBOOK_data_and_compare.md) (in Vietnamese) for the day-to-day manual runbook covering the Expected/Actual/As-Is data workflow and `compare_results.py` step by step.

## Layout

```
Auto_Data_Py/
├── scripts/                      (shared — see repo-root README.md)
├── data/                          (shared — product catalogs + glossary)
├── config/environments.yaml       (shared — search/autocomplete API endpoints per env)
└── SmartSearch/
    ├── REQ/                       BRD/storyboard/flow-doc source documents
    ├── qna/                       QnA log workbook (VI + EN pair)
    ├── testcases/                 Combined_TestCases workbook (VI + EN) + auto CSV
    ├── test_data/
    │   ├── excel/                 dev/QA-facing Excel deliverables
    │   └── json/
    │       ├── batches/           NSG_ExpectedData_<range>_<date>.json (non-overlapping query batches)
    │       ├── for_dev/            denormalized (name/price/category joined) dev-ready JSON, one per source
    │       └── _source/           dataset_2000.json, queries_2000.json, search_engine.js (raw pipeline snapshot)
    ├── smoke_test/                 10-query smoke test (real engine-computed, run before a full batch)
    ├── golden_testsets/<store>/    output of generate_master_testset.py
    ├── runs/                       run_autoscript.py results (report.xlsx + raw NDJSON)
    ├── manual_qc/<store>/          exported Postman collection/env/CSV + k6 fixture
    ├── text_testdata/              legacy ad-hoc generated inputs/expected/samples/workbooks
    ├── full_store_catalog/         full (unsampled) per-store catalog JSON, for Artifact pages
    ├── full_store_catalog_desc/    same, with desc-keyword field included
    ├── image_test_data_sets.csv    image-search test set (see repo-root docs/README_image_test_data.md)
    ├── README.md                  (this file)
    └── AI_CONTEXT.md               full context/decisions log for AI onboarding
```

## Quick start

1. Create a virtual environment and install dependencies (from repo root):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Golden-set relevance testing (search + autocomplete)

Full strategy and rationale (4-tier pass model, keyword-variant taxonomy, manual-QC guide) is written up as a shared strategy doc; ask if you need the link again. Short version:

1. Generate a golden dataset for one store (or all 20):

```powershell
python scripts\testdata\generate_master_testset.py --store nsg --out-dir SmartSearch\golden_testsets\nsg
python scripts\testdata\generate_master_testset.py --all-stores --out-dir SmartSearch\golden_testsets
```

Writes `search_result_expected.ndjson`, `autocomplete_expected.ndjson`, and a `manifest.json` documenting sample size and assumptions (popularity proxy, glossary coverage). Keyword-variant coverage (`data/glossary/*.csv`) ships with placeholder rows only for the `regional` and `related` dimensions — curate those with QA/BA before relying on them in a real cycle.

2. Run it against a live API and get a scored report:

```powershell
python scripts\automation\run_autoscript.py `
  --dataset-dir SmartSearch\golden_testsets\nsg `
  --search-api https://staging-search.internal/api/v1/search `
  --autocomplete-api https://staging-search.internal/api/v1/suggest `
  --header "Authorization: Bearer <TOKEN>"

# or with a saved environment
python scripts\automation\run_autoscript.py --dataset-dir SmartSearch\golden_testsets\nsg --env staging
```

Writes `SmartSearch/runs/<dataset>_<timestamp>/report.xlsx` (Summary + tier-colored Detail + a Tier4_NeedsReview sheet) plus raw NDJSON results, and prints a console summary. Scoring logic (`scripts/automation/lib_scoring.py`) applies a 4-tier model — exact Top-1, present in Top-N, recall against an `acceptable_set`, or flagged for manual review — since a single expected SKU isn't a valid pass criterion for every query dimension (synonym/related-term queries can have several legitimately correct results).

3. Manual QC tooling (Postman / k6), generated from the same dataset:

```powershell
python scripts\performance\export_manual_qc_assets.py --dataset-dir SmartSearch\golden_testsets\nsg --out-dir SmartSearch\manual_qc\nsg
```

Writes a Postman collection + environment + data CSV, and `scripts/performance/k6_search_test.js` + `k6_queries.json`. Run the load test itself with the k6 extension (or CLI): `k6 run scripts/performance/k6_search_test.js`.

## Batch test runner (NSG precomputed scenarios + response-time/matching dashboard)

Runs one or more of the 1000-row batches under `SmartSearch/test_data/json/batches/` (`NSG_ExpectedData_<start>-<end>_<date>.json`, precomputed by the NSG search-testdata engine — see `AI_CONTEXT.md` §3b) against the real dev API, records response time per call, and compares actual results to each scenario's precomputed `search_results`/`autocomplete_suggestions`.

**Precondition — manual login, every time.** This tool never types a username/password or 2FA code itself. Two ways to get a session:

- **`--headed-login` (recommended)** — opens a real, visible browser at the dev-console; you log in by hand (username/password, then your 2FA authenticator code), and the tool auto-detects completion and captures the cookie for you — including navigating into Playground and setting the search mode to `adaptive` (best-effort; never blocks on this since the cookie is already valid once you're logged in). Needs `pip install playwright` + `playwright install chromium` once.
- **Manual copy** — log in via a normal browser, copy the `Cookie` header value from DevTools → Network → any `products/search` or `/autocomplete` request → Request Headers, then:

```powershell
$env:DEV_SEARCH_COOKIE = "visid_incap_...=...; incap_ses_...=..."
```

Run one batch, or all of them:

```powershell
python scripts\automation\run_batch_test.py --env dev --batch 0-1000
python scripts\automation\run_batch_test.py --env dev --batch all          # combined report across every batch found
python scripts\automation\run_batch_test.py --env dev --batch 2000-3000 --limit 20   # smoke test first
```

Or use the dedicated 10-query smoke-test set (`SmartSearch/smoke_test/`, real engine-computed, see its own README) to sanity-check the whole flow in seconds before committing to a full batch:

```powershell
python scripts\automation\run_batch_test.py --env dev --batches-dir SmartSearch\smoke_test --batch 0-10
```

Before running the full batch it does one preflight request to catch an expired/missing login early. While running, it also watches for a **degraded/throttled session**: if many different queries in a row come back with the exact same (small, generic) result set — a real failure mode seen on this gateway, where the WAF/session quietly falls back to a canned response instead of erroring — it aborts immediately (`--stuck-streak-limit`, default 8) rather than producing a dashboard that looks like "search returns nothing relevant" when the real cause is just a dead session. If that happens, log in again and re-run.

Output, in `SmartSearch/runs/batch_<selection>_<timestamp>/`:
- `report.xlsx` — a **Dashboard** sheet (latency + recall charts by dimension, KPI summary) plus `Search_Detail`/`Autocomplete_Detail` sheets (one row per scenario, tier-colored).
- `dashboard.html` — the same dashboard as a standalone page (open directly in a browser, no server/internet needed).
- `search_raw_results.ndjson` / `autocomplete_raw_results.ndjson` / `stats.json` — raw per-call data for further analysis.

Matching uses a rank-based comparison (same idea as the "Search Result Comparator" Artifact, not the golden-set 4-tier model): every expected item's rank in the actual response is checked (`matched` within `--search-topn`, `outside_top` if found further down, `missing` if absent), and actual's own top results not present anywhere in the expected list are counted as `extras`.

## Legacy / ad-hoc test data generation

```powershell
python scripts\testdata\generate_text_testdata.py --ndjson data\ProductInfo\mart_en_nsg_product.ndjson --out-dir SmartSearch\text_testdata
python scripts\testdata\generate_multilang_queries.py --v1 data\ProductInfo --out SmartSearch\text_testdata\multilang_queries.xlsx --max-per-file 200
python scripts\testdata\sample_queries.py --in SmartSearch\text_testdata\multilang_queries.xlsx --out SmartSearch\text_testdata\sample_queries.xlsx --size 1000
python scripts\automation\runner_text_search.py --excel SmartSearch\text_testdata\text_testdata.xlsx --inputs SmartSearch\text_testdata\sample_inputs.ndjson --api-url "https://api.example.com/search" --method GET --param q --topn 5 --header "Authorization: Bearer <TOKEN>"
```

## Files of interest

- `scripts/testdata/generate_master_testset.py` — golden dataset generator (Part 1 of the strategy)
- `scripts/automation/run_autoscript.py` + `lib_scoring.py` + `lib_search_client.py` — run + score + report against a live API (Part 2/3)
- `scripts/automation/run_batch_test.py` + `lib_dashboard.py` — run the precomputed NSG batch scenarios against a live API and produce a response-time/matching dashboard (see "Batch test runner" above)
- `scripts/performance/export_manual_qc_assets.py` + `k6_search_test.js` + `k6_queries.json` — Postman/k6 asset export and the k6 load-test script itself (Part 4)
- `scripts/testdata/generate_text_testdata.py`, `generate_multilang_queries.py`, `generate_image_testdata.py`, `sample_queries.py` — earlier ad-hoc test-data generators, still usable standalone
- `scripts/automation/runner_text_search.py` — earlier ad-hoc runner, still usable standalone
- `scripts/testcase/add_results_template.py`, `preview_testcase.py`, `translate_excel.py`, `combine_req_testcases.py`, `search_testcases_keywords.py`, `extract_ss_scr_002*.py` — test-case workbook tooling (combine REQ+testcases, preview, translate, keyword/ID search)
- `scripts/testdata/export_full_store_catalog.py`, `export_smartsearch_testdata.py`, `generate_testcase_datasets.py` — full-catalog export and Smart Search test-data/dev-deliverable exporters
- `data/ProductInfo/` — source NDJSON product datasets (EN/VI/KR per store), shared at repo root
- `data/glossary/` — synonym/regional/related-term CSVs (see file headers for schema), shared at repo root
- `SmartSearch/testcases/`, `SmartSearch/qna/` — delivered MART SmartSearch test-case and QnA-log workbooks
- `docs/` (repo root) — additional documentation (e.g. image test data usage)
