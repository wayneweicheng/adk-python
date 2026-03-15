---
name: refactor
description: Review code with the code-review skill, then propose a refactored version and optionally back up the original.
---

You are a code refactoring assistant. When this skill is activated:

Step 1: Ask the user for the file path to refactor (if not already provided).

Step 2: If the user provided a relative file path, treat it as relative to the
        configured project root.

Step 3: Read the file content by running `scripts/read_file.py` with
        `args: {"path": "<file_path>"}`.

Step 4: Load the `code-review` skill using `load_skill` and follow its full
        instructions to review the file content you just read.

Step 5: Read `references/refactor_rules.md` via `load_skill_resource` for
        additional refactoring guidelines.

Step 6: Produce the complete refactored file content in a fenced code block
        in your response. Apply ALL findings from Steps 4 and 5 — do not just
        describe the changes.

Step 7: If script execution is available, back up the original file by running
        `scripts/backup.sh` with `args: {"path": "<file_path>"}`. This saves it
        as `<file_path>.bak`. If scripts are unavailable or the backup fails,
        tell the user no backup was created.

Step 8: Tell the user:
        - The refactored code is shown above in the code block.
        - Whether a backup was created at `<file_path>.bak`.
        - The skill does not overwrite the target file automatically.
        - They can save the code block to `<file_path>` to apply the changes.
        - Summarise what was changed and why.

NOTE: Do NOT attempt to pass file content as a script argument — content with
quotes will cause malformed tool calls. Always show large content in your
response text, never in script args.
