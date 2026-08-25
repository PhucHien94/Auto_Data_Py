---
description: Claude Review danh sách Test Cases
model: claude-3-7-sonnet
---
Đọc file TestCases và QnA, và REQ. Hãy:
1. Soi kỹ các testcase xem có bị sót luồng, hổng logic điều kiện biên hoặc thiếu kịch bản tiêu cực (Negative cases) không.
2. Tối ưu lại các bước thực hiện (Steps) và kết quả mong đợi (Expected Results) cho chuẩn hóa.
3. testcase viết dễ hiểu, chi tiết, không dùng từ hàn lâm

Test Case Reviewer (against Requirement)
What this skill does

Takes two inputs:

Populated test case / scenario workbook (.xlsx) — following any of the shapes in testcase-from-requirement's reference (standard multi-system, GEMS Requirements/Test-Cases/Traceability, or scenario-register), or a new/unknown shape — read its actual structure, don't assume.
Requirement source — Word/Excel/PowerPoint, the same kind of file testcase-from-requirement would consume.

...and produces an updated workbook with:

A Review column appended to the end of each test-case table, containing a specific comment per row (not a generic "looks fine").
A new sheet listing, one row per finding: requirements with no test case, ambiguous/underspecified requirement language, missing edge cases, contradictions, and other issues — including issues the BA may not have thought to ask about.
Step 0 — Confirm inputs

If either file is missing, ask the user to upload it. Confirm which module/project this review covers if it isn't obvious from the files.

Step 1 — Read both files
Test case workbook: open with openpyxl (data_only=False so existing formulas are visible and preserved). Identify the shape (see testcase-from-requirement's references/template-shapes.md for the three known ones) by reading actual sheet names and header rows — don't assume. Locate the test-case table(s) — there may be one per sheet (standard shape) or one central sheet (GEMS/scenario shapes).
Requirement file: read per its actual format (.docx → docx skill's extract-text; .xlsx → xlsx skill; .pptx → pptx skill, reading every slide). Extract the full list of stated requirements/features/rules, not just the first section.
Step 2 — Build the requirement ↔ test-case mapping

Match test cases to requirements using whatever link already exists in the workbook (a Requirement Ref / Req ID column, a Traceability sheet, or a Requirement Source column). If no explicit link column exists, match by content similarity (feature/module name, keywords) and note in your findings that the mapping was inferred, not authored.

For each requirement, determine:

Zero test cases → this is a coverage gap.
Test cases exist but only cover the happy path → flag which angles are missing (Validation/Negative/Boundary/Exception/Security/Integration/Performance — see testcase-from-requirement's category list) based on what the requirement's wording actually implies (e.g. a requirement mentioning a size limit but no boundary test case is a real gap; don't invent a category the requirement doesn't support).
Step 3 — Review test-case quality, row by row

For every existing test case row, check for concrete, checkable issues — not stylistic nitpicks:

Vague steps or expected result — e.g. "verify it works correctly" instead of a specific, checkable outcome.
Missing test data where the step implies specific input is needed.
Duplicate or near-duplicate cases covering the same behavior.
Category mismatch — e.g. a case testing a rejection path labeled Functional instead of Negative.
Orphaned reference — a Requirement Ref pointing to a requirement ID that doesn't exist in the requirement source (possible typo or stale reference).
Untestable expected result — expected result that can't actually be verified as written (e.g. no observable signal given).

Write your finding directly into the new Review column for that row: a short, specific comment (e.g. "Expected result doesn't state the actual error message shown — confirm exact wording with BA"), or leave it blank / "OK" if the case is genuinely fine — don't manufacture a comment for every single row just to fill the column.

Step 4 — Proactively surface requirement gaps and ambiguities

This is the part a mechanical traceability check would miss, and the part the user most wants: read the requirement source critically and flag, independent of what test cases currently exist:

Undefined behavior — the requirement describes the happy path but never states what happens on invalid input, timeout, concurrent access, or permission denial.
Missing boundary values — a limit is implied ("large files", "many items") without ever stating the actual number/threshold.
Contradictions — two parts of the requirement (or requirement vs. an existing test case's assumption) that can't both be true as written.
Unstated non-functional expectations — performance, security, localization, accessibility that a similar feature would normally need but this requirement doesn't mention.
Ambiguous ownership/authorization — "the admin can..." without specifying which role, or overlapping permissions that aren't reconciled.
Silent dependencies — the requirement assumes another system/interface behaves a certain way without stating it as an explicit assumption.

For each, write a specific, falsifiable observation tied to the actual requirement text — not a generic "requirements should be clearer." Always phrase these as questions/gaps to confirm with the BA, not as asserted facts about what the system does (you're flagging what's missing, not inventing what should replace it).

Step 5 — Write the outputs
Review column: append one new column (header Review, or match the workbook's existing naming convention if there's a similar column already, e.g. Note/Comments) to the end of every test-case table found, filled per Step 3. Preserve all existing columns, formulas, and formatting — only add the new column, don't restructure the table.
Gaps & Issues sheet: add a new sheet (name it Review - Gaps & Issues or similar, avoiding collision with existing sheet names) with one row per finding from Steps 2 and 4:
Column	Content
Type	No Test Case / Incomplete Coverage / Requirement Ambiguity / Missing Edge Case / Contradiction / Other
Requirement / Area	which requirement or feature this concerns
Finding	the specific observation
Suggested Action	a concrete next step (e.g. "confirm max file size with BA", "add a negative test case for X")
Severity	High / Medium / Low — based on user-facing or data-integrity impact, not just volume
Use conditional formatting or fill color on High severity rows if the workbook's existing style supports it, so they stand out — but don't let formatting substitute for a specific, actionable Finding text.
Save as a new file (e.g. append _reviewed to the original filename) — don't silently overwrite the user's original test case file.
Step 6 — Verify and present

Open the saved workbook back up and spot-check: the Review column exists on every expected sheet, the Gaps & Issues sheet has rows (or if truly no findings, still exists and clearly states "no issues found" rather than being empty and ambiguous about whether the review ran), and no existing formulas or data were disturbed. Present the file with present_files and summarize in chat: how many test cases got a review comment, how many coverage gaps were found, and the top 2-3 requirement-ambiguity findings — don't just say "review complete," give the person something to act on immediately in the chat response itself, in addition to the file.

Notes
If the test case workbook has no requirement-link column at all and the requirement source is large, ask the user whether to prioritize the review (e.g. by module) rather than silently attempting an exhaustive pass that produces low-confidence matches.
Never delete or renumber existing test cases while reviewing — this skill only adds a column and a new sheet, it doesn't rewrite existing content.
If the user's test case file was generated by the testcase-from-requirement skill in this same conversation, reuse the shape/column knowledge already established rather than re-detecting from scratch.
