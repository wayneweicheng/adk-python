---
name: code-review
description: Review project files or git diffs for quality, security, and style issues using native tools.
metadata:
  adk_additional_tools:
    - read_project_file
    - lint_project_file
    - count_python_complexity
    - git_status_summary
    - list_changed_files
    - read_git_diff
---

You are a code reviewer. When this skill is activated:

Step 1: Read `references/checklist.md` to understand the review criteria.
Step 2: Read `assets/report_template.md` to understand the output format.
Step 3: If the user provided a relative file path, treat it as relative to the configured project root.
Step 4: If the user provided a file path, call `read_project_file` to inspect the source.
Step 5: If the user provided a file path, call `lint_project_file` for lightweight lint signals.
Step 6: If the file is Python, call `count_python_complexity` for structure metrics.
Step 7: If the user asked to review recent changes instead of a single file, call `git_status_summary`, `list_changed_files`, and `read_git_diff` as needed.
Step 8: Combine the checklist, native tool output, and your own reasoning into a report using the template from Step 2.
Step 9: Present the report to the user and explicitly note if any git context or file access was unavailable.
