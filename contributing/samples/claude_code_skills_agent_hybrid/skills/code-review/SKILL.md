---
name: code-review
description: Review code files for quality, security, and style issues, then produce a structured report.
---

You are a code reviewer. When this skill is activated:

Step 1: Read `references/checklist.md` to understand the review criteria.
Step 2: Read `assets/report_template.md` to understand the output format.
Step 3: If the user provided a relative file path, treat it as relative to the
        configured project root.
Step 4: If the user provided a file path and script execution is available, run
        `scripts/lint_check.sh` with
        `args: {"path": "<file_path>"}` to get static analysis results.
Step 5: If the file is Python and script execution is available, also run
        `scripts/count_complexity.py` with
        `args: {"path": "<file_path>"}` to get complexity metrics.
Step 6: If scripts are unavailable or fail, continue the review using the file
        content and explicitly note which automated checks were skipped.
Step 7: Combine the checklist, lint output, and complexity metrics into a
        report using the template from Step 2.
Step 8: Present the report to the user.
