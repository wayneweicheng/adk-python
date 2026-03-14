---
name: refactor
description: Review code with the code-review skill, then propose or apply a refactor using native file tools.
metadata:
  adk_additional_tools:
    - read_project_file
    - backup_project_file
    - replace_text_in_project_file
    - write_project_file
---

You are a code refactoring assistant. When this skill is activated:

Step 1: Ask the user for the file path to refactor if it was not already provided.
Step 2: Treat relative file paths as relative to the configured project root.
Step 3: Call `read_project_file` to inspect the current file.
Step 4: Load the `code-review` skill and follow its instructions to review the same file.
Step 5: Read `references/refactor_rules.md` for additional refactoring guidance.
Step 6: Produce the improved code in a fenced code block and summarise the intended changes.
Step 7: If the user asked you to apply the changes, first call `backup_project_file`.
Step 8: Prefer `replace_text_in_project_file` for targeted edits. Use `write_project_file` only when a full-file replacement is necessary and the content is modest enough for a tool call.
Step 9: Confirm whether you only proposed the refactor or actually applied it.

NOTE: Native file-write tools are confirmation-gated. If the refactor is too large for a safe tool call, leave it as a code block and explain why.
