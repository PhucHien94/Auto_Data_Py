---
description: Bóc tách logic và sinh Test Cases Matrix
model: gemini-3-flash
---
Đọc file REQ và file `QnA_Requirement.md` (nếu có). Hãy Viết bộ Test Cases đầy đủ bao gồm: Luồng chuẩn (Happy path), Luồng lỗi (Negative path) và Điều kiện biên (Edge cases).

Test Case Generator (from Requirement + Template)
What this skill does

Takes inputs:

Requirement file — Word/Excel/PowerPoint describing what to build: SRS, BRD, user stories, feature descriptions, or even a loosely-structured "AI Search requirement QnA" doc. Format and structure vary per project — read whatever is actually there rather than assuming a fixed layout.
Test-case template (.xlsx) — the project's existing test-case/scenario workbook shape. Three shapes have been seen so far (see references/template-shapes.md), but always read the actual sheet names and header rows of the supplied template first — don't assume it matches one of the three known shapes; a project may have a fourth, slightly different one.

...and produces a new .xlsx populated with test cases/scenarios derived from the requirement content, following the template's exact structure, plus a live aggregate report (Total/Pass/Fail/... via formulas) regardless of which template shape is used.

Step 0 — Confirm inputs, and which template

If either file is missing, ask the user to upload it. If the user has multiple known templates (this project has three: a "standard" multi-system one, a GEMS-style Requirements/Test-Cases/Traceability one, and a scenario-register one), ask which one applies for this run rather than guessing — different modules/projects use different ones. Also confirm which module/project/scope the requirement covers, since test cases are authored per project.

Step 1 — Read the requirement file per its actual format
.docx → use the docx skill's read approach (extract-text) to get headings, bullet lists, tables of requirements.
.xlsx → use the xlsx skill's read approach; look for columns like Requirement/Description/Priority/Acceptance Criteria, or a feature-list shape like the one used in testplan-from-featurelist.
.pptx → use the pptx skill's read approach (extract-text); requirements are often one-per-slide or in slide bullet points — read all slides, don't stop at the first few.

Extract, at minimum: a distinct list of requirements/features/capabilities, each with (if present) a source reference, priority, and any explicit acceptance criteria or business rules — these map directly to template columns like Requirement Source, Priority, Acceptance Criteria, Business Rationale. If the requirement doc doesn't state priority or acceptance criteria explicitly, derive a reasonable one from the described behavior and flag it as inferred (e.g. "Priority: High — inferred from 'must' language in requirement") rather than presenting a guess as given fact.

Step 2 — Detect the template shape

Open the template with openpyxl (data_only=False, so you can see and reuse existing formulas) and read:

wb.sheetnames
the header row of each non-Cover/Summary sheet

Compare against references/template-shapes.md. Match to the closest known shape, but populate based on the actual columns found, not the reference names verbatim — templates get customized per project (extra columns, renamed columns, merged Module tabs, etc.).

Step 3 — Author test cases from the requirements

For each requirement/feature extracted in Step 1, write one or more test case rows covering multiple angles — don't stop at one "happy path" case per requirement:

Functional — the main positive flow described by the requirement
Validation — mandatory-field / format / business-rule checks if the requirement implies input
Negative — disallowed actions, invalid input, permission-denied paths
Boundary — limits explicitly mentioned in the requirement (size caps, counts, time windows) — only author boundary cases where the requirement actually states a limit; don't invent numeric limits that aren't in the source
Exception/Error — dependency/interface failure, timeout, unavailability, if the requirement involves an integration
Security/RBAC — permission enforcement, if the requirement involves access control
Integration — cross-system contract behavior, if the requirement crosses a system boundary
Performance — only if the requirement states a measurable target (response time, concurrency) — don't fabricate a target that isn't in the source

Not every requirement needs every category — pick the ones that are actually implied by that requirement's content. Write concrete Test Steps and Expected Result text (not vague placeholders); use realistic sample data drawn from the requirement's own examples where given.

Test Case IDs should follow the template's existing ID convention (check an existing populated template, or references/template-shapes.md, for the pattern — e.g. TC-<MODULE>-NNN, <AreaCode>-NN) — don't invent a new scheme.

Default execution-tracking fields (Actual Result, Pass/Fail Status, Tester, Test Date, Comments) to blank / the template's own default value (usually Not Run) — never pre-fill these as if already executed.

Step 4 — Always include a live aggregate report

Whatever the template shape, the workbook must show Total/Pass/Fail/etc. counts that recalculate automatically as testers fill in the status column — not numbers you compute once and hardcode. Use COUNTIF formulas referencing the actual status column and range, e.g.:

=COUNTIF($T$13:$T$73, R4)     ' counts rows in the Test Status column matching the label in R4 (e.g. "Pass")
=SUM(S4:S8)                    ' Total of TC = sum of the individual status counts above

See references/template-shapes.md for the exact aggregate-block layout seen in each known template shape, and reuse that layout/formula pattern for consistency. If the chosen template has no aggregate block at all, add one (a small block at the top of the main sheet, or a dedicated Summary sheet) using the same COUNTIF pattern, keyed off whatever status vocabulary the template's own Test Result/Status column actually uses (e.g. Pass/Fail/Blocked/Not Run vs Pass/Fail/Open/Ready for QC/N/A) — don't invent new status values not supported by the template's data-validation list (check the column's data validation dropdown if present).

If the template groups content across multiple sheets (one per system/module, as in the "standard" shape), give each sheet its own aggregate block, matching the pattern already used by that template's other sheets.

Step 5 — Generate, verify, present

Save the output .xlsx, then open it back up and check the formulas evaluate correctly (e.g. via libreoffice --headless --convert-to xlsx --calculate or by recalculating with a tool that supports formula evaluation) rather than just trusting the formula text is syntactically plausible — a wrong range reference silently produces 0 for every status, which is easy to miss without checking. Present the file with present_files and briefly summarize: how many test cases were authored, how many per requirement/category, and which aggregate block was added/reused.

Step 6 — Iterate

Ask the user what to adjust (more edge cases, different ID convention, different category mix, additional modules). Re-run Steps 3-4 with corrections.

Notes
If the requirement file references a feature list workbook (like the one used by testplan-from-featurelist), consider cross-referencing it for Feature IDs / Priority rather than re-deriving those from scratch — ask the user if such a file is available when the requirement doc is thin on structure.
If the user wants test cases for multiple modules/projects in one run, confirm whether they want one output file per module or a combined one — don't silently pick one.
Don't fabricate specific numeric limits, SLAs, or performance targets that aren't stated in the requirement — mark those as TBD — confirm target with BA instead.


