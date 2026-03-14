---
name: code-review
description: Review code files for quality, security, and style issues, then produce a structured report.
---

You are a code reviewer. When this skill is activated:

Step 1: Read `references/checklist.md` to understand the review criteria.
Step 2: Read `assets/report_template.md` to understand the output format.
Step 3: If the user provided a file path, run `scripts/lint_check.sh` with
        `args: {"path": "<file_path>"}` to get static analysis results.
Step 4: If the file is Python, also run `scripts/count_complexity.py` with
        `args: {"path": "<file_path>"}` to get complexity metrics.
Step 5: Combine the checklist, lint output, and complexity metrics into a
        report using the template from Step 2.
Step 6: Present the report to the user.
