# Auto_Data_Py

QA test-automation workspace for MART. Structured as one **shared infrastructure layer** (this root) plus one folder per feature module.

```
Auto_Data_Py/
├── scripts/        shared tooling (testcase, testdata, automation, performance) — see module READMEs for usage
├── data/            shared source data (product catalogs, glossary CSVs)
├── config/          shared environment config (API endpoints)
├── docs/            shared supplementary docs
├── requirements.txt
├── SmartSearch/     feature module: Smart Search & Autocomplete — see SmartSearch/README.md
├── SimplifyCheckout/ feature module: Simplify Checkout user flow
└── Recommendation/  feature module: product Recommendation — see Recommendation/README.md
```

## Modules

- **[SmartSearch/](SmartSearch/README.md)** — Smart Search & Autocomplete: REQ, test cases, QnA log, golden test data, run reports, manual-QC assets. Start there for anything related to this feature; see [SmartSearch/AI_CONTEXT.md](SmartSearch/AI_CONTEXT.md) for the full context/decisions log.
- **[SimplifyCheckout/](SimplifyCheckout/)** — Simplify Checkout user flow: SRS/Figma source docs, test-case workbook (VI + EN), QnA log.
- **[Recommendation/](Recommendation/README.md)** — product Recommendation: REQ, Figma, test cases, QnA log, test data, run/client reports. Scaffold created 2026-09-22; see [Recommendation/AI_CONTEXT.md](Recommendation/AI_CONTEXT.md).

Future feature modules should follow the same pattern: a top-level folder (its own REQ/testcases/test_data/README/AI_CONTEXT), reusing the shared `scripts/`, `data/`, and `config/` at the repo root rather than duplicating them.

## Setup (shared)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
