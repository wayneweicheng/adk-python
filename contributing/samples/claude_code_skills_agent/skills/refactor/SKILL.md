---
name: refactor
description: Review code with the code-review skill, then produce a refactored version and back up the original.
---

You are a code refactoring assistant. When this skill is activated:

Step 1: Ask the user for the file path to refactor (if not already provided).

Step 2: Read the file content by running `scripts/read_file.py` with
        `args: {"path": "<file_path>"}`.

Step 3: Load the `code-review` skill using `load_skill` and follow its full
        instructions to review the file content you just read.

Step 4: Read `references/refactor_rules.md` via `load_skill_resource` for
        additional refactoring guidelines.

Step 5: Produce the complete refactored file content in a fenced code block
        in your response. Apply ALL findings from Steps 3 and 4 — do not just
        describe the changes.

Step 6: Back up the original file by running `scripts/backup.sh` with
        `args: {"path": "<file_path>"}`. This saves it as `<file_path>.bak`.

Step 7: Tell the user:
        - The refactored code is shown above in the code block.
        - The original is backed up at `<file_path>.bak`.
        - They can save the code block to `<file_path>` to apply the changes.
        - Summarise what was changed and why.

NOTE: Do NOT attempt to pass file content as a script argument — content with
quotes will cause malformed tool calls. Always show large content in your
response text, never in script args.
