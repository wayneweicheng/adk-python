# Code Review: claude_code_skills_agent (Script-Based)

## Summary

This sample demonstrates loading Claude Code skills into an ADK agent with
script execution support. Skills are defined as SKILL.md instruction bundles
with optional Python/Bash scripts that run via a configurable code executor
(local, container, GKE, or Agent Engine sandbox).

The architecture is sound and the skill discovery mechanism is clean. The main
issues are around duplicated security logic across scripts, missing safety
guards that the native sample provides, and a few hygiene items.

---

## Issue 1: Duplicated Path Resolution Across All Scripts

**Severity**: Medium — maintenance risk and inconsistency vector

Every script reimplements the same `resolve_target_path` logic independently:

| Script | Language | Lines |
|--------|----------|-------|
| `scripts/count_complexity.py` | Python | Lines 42–62 |
| `scripts/read_file.py` | Python | Lines 11–31 |
| `scripts/lint_check.sh` | Bash | Lines 7–33 |
| `scripts/backup.sh` | Bash | Lines 7–33 |

All four copies do the same thing:
1. Resolve relative paths against `ADK_SKILLS_PROJECT_ROOT`
2. Canonicalize via `resolve()` / `pwd -P`
3. Check that the result stays within the project root

This means:
- A fix to one copy (e.g., adding blocked-path enforcement) must be
  replicated to all others manually.
- The Bash and Python implementations have subtly different edge-case
  behavior (e.g., Bash uses `cd && pwd -P` for canonicalization, Python
  uses `Path.resolve()`).
- New scripts will copy-paste this boilerplate, compounding the problem.

**Recommendation**: Extract the Python path resolution into a shared module
(e.g., `skills/_shared/path_utils.py`) that scripts can import. For Bash
scripts, either source a shared shell library or have the SkillToolset
pre-resolve and validate paths before passing them to scripts (preferred —
see "Missing Middle Ground" section below).

---

## Issue 2: No Blocked-Path Enforcement

**Severity**: Medium-High — security gap

Scripts validate that paths stay inside the project root, but they do **not**
block access to sensitive files. A model-directed script invocation like:

```
run_skill_script(skill="refactor", script="read_file.py", args={"path": ".env"})
```

will happily read and return the contents of `.env`, which may contain API
keys, database credentials, or cloud project identifiers.

Compare the native sample's `_ensure_safe_project_path()` which explicitly
blocks:
- `.env` and `.env.*` files
- `credentials.json`, `application_default_credentials.json`
- Files with extensions `.pem`, `.key`, `.p12`, `.crt`, `.cer`, `.der`

**Recommendation**: Add a blocklist check to the shared path resolution
utility, or enforce it at the SkillToolset/code-executor layer so that
individual scripts don't need to know about it.

---

## Issue 3: No File-Size Limits

**Severity**: Low-Medium — resource exhaustion risk

Scripts will read arbitrarily large files without complaint. If the model
requests a review of a large generated file or binary that happens to have a
text extension, the script will load the entire file into memory and return
it as tool output, potentially overwhelming the context window or causing
OOM errors.

The native sample caps file reads at 120,000 bytes
(`ADK_NATIVE_SKILLS_MAX_TEXT_BYTES`). Git diffs are also truncated at this
limit.

**Recommendation**: Either add a size check to each script (not ideal — see
Issue 1 about duplication), or have the code executor / SkillToolset enforce
an output size cap on script stdout.

---

## Issue 4: Graceful Degradation Pattern (Positive)

**Strength**: Good resilience design

The `code-review/SKILL.md` Step 6 is a well-designed pattern:

> If scripts are unavailable or fail, continue the review using the file
> content and explicitly note which automated checks were skipped.

This means the skill degrades gracefully when:
- The code executor is set to `disabled`
- A script fails due to a missing dependency
- The container/GKE executor is temporarily unavailable

The native sample drops this pattern (since native tools are always
available), but it's worth preserving as a best practice for script-based
skills in general.

---

## Issue 5: `.env` Should Not Be Committed

**Severity**: Low — credential hygiene

The `.env` file contains `GOOGLE_CLOUD_PROJECT=ark-of-data-2000` and is
present in the working tree. While `.env.example` exists as a template (which
is correct), the actual `.env` file should be:
1. Added to `.gitignore`
2. Removed from version control

Even if the values are not secret, committing `.env` files sets a bad
precedent and risks future secret leakage when someone adds an API key.

---

## Issue 6: `agent.py.bak` Should Not Be Committed

**Severity**: Low — hygiene

There is an `agent.py.bak` file in the directory, likely created during
testing of the backup script. This should be removed and added to
`.gitignore`.

---

## Issue 7: Code Executor Configuration Complexity

**Observation**: Not a bug, but worth noting

The `_build_code_executor()` function (lines 132–228) handles five execution
modes with ~15 environment variables. This is comprehensive but creates a
large configuration surface for a sample. Users trying this for the first
time may find it overwhelming.

The `.env.example` file helps, but consider whether the sample should focus
on just `disabled` + `unsafe-local` modes, with the others documented but
not implemented inline.

---

## The Missing Middle Ground

The current framing across both samples presents a binary choice: either run
scripts with full trust via a code executor, or rewrite everything as native
Python tools. There is a practical middle ground that would let existing
Claude Code skills work safely without script refactoring.

### Approach: Centralized Security at the SkillToolset Layer

Instead of requiring each script to implement its own path validation, the
SkillToolset (or a wrapper around the code executor) could:

1. **Pre-validate all `--path` arguments** before passing them to scripts.
   Apply `resolve_project_path` + `ensure_safe_project_path` logic once, at
   the platform layer.

2. **Inject validated environment variables** that scripts can trust:
   - `ADK_SKILLS_PROJECT_ROOT` (already done)
   - `ADK_SKILLS_MAX_FILE_SIZE` (new)
   - `ADK_SKILLS_VALIDATED_PATH` (pre-resolved absolute path)

3. **Cap output size** — truncate script stdout/stderr to a configurable
   maximum byte limit to prevent context window flooding.

4. **Classify scripts as read-only vs mutating** via SKILL.md metadata:
   ```yaml
   metadata:
     scripts:
       lint_check.sh: {mode: read-only}
       backup.sh: {mode: mutating, require_confirmation: true}
   ```
   Mutating scripts would require user confirmation before execution, similar
   to the native version's `FunctionTool(fn, require_confirmation=True)`.

### What This Preserves

- Skills remain portable between Claude Code and ADK
- Script authors don't need to learn the ADK tool API
- Existing skills work without refactoring
- Security is enforced at the infrastructure boundary, not inside each script

### What Scripts Should NOT Do in This Model

- Write files without going through a gated path
- Execute arbitrary subprocesses beyond their stated purpose
- Access network resources
- Read environment variables beyond the ones explicitly injected

### Where to Implement This

The upstream `_SkillScriptCodeExecutor._build_wrapper_code()` in
`src/google/adk/tools/skill_toolset.py` already materializes scripts into a
temporary directory. This is the natural injection point for:
- Path pre-validation before script arguments are passed through
- File-size limits on script inputs
- Blocked-path checks
- Output truncation on script results

This would make scripts safe by default without requiring script authors to
implement security themselves.

---

## Summary of Recommendations

| Priority | Action |
|----------|--------|
| High | Add blocked-path enforcement (`.env`, credentials, key material) |
| High | Extract duplicated `resolve_target_path` into shared utility or platform layer |
| Medium | Add file-size limits to script file reads |
| Medium | Remove `.env` and `agent.py.bak` from version control |
| Low | Consider reducing code executor modes in the sample to focus on the common cases |
| Strategic | Explore centralized security wrapper at the SkillToolset layer to enable safe script execution without per-script refactoring |
