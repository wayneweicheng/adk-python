# Code Review: claude_code_skills_agent_native (Native Tools)

## Summary

This sample replaces all script execution with purpose-built Python tools
registered directly on the agent. It removes `run_skill_script` entirely via
a `NativeOnlySkillToolset` subclass and provides 11 native tools for file
reading, linting, complexity analysis, git operations, and file mutations.

The security posture is significantly stronger than the script-based version.
The code is well-structured and the `PRODUCTION_GUIDANCE.md` is genuinely
useful. The main concerns are around the high rewrite cost relative to the
actual script logic being replaced, a few correctness edge cases, and a
brittle subclass pattern.

---

## Issue 1: High Rewrite Cost vs Actual Script Logic

**Observation**: Architecture trade-off worth acknowledging

The native `agent.py` is ~440 lines. The combined business logic in all four
scripts it replaces is roughly 10–15 lines:

| Original Script | Core Logic |
|-----------------|-----------|
| `lint_check.sh` | `grep -c "TODO\|FIXME"`, `wc -l`, `grep -c " $"` |
| `count_complexity.py` | `ast.parse` + walk for FunctionDef/ClassDef |
| `read_file.py` | `path.read_text()` |
| `backup.sh` | `cp "$file" "${file}.bak"` |

The remaining ~95% of both the scripts and the native tools is path
resolution, argument parsing, error handling, and security validation. The
native version centralizes this (good), but the total code volume
**increased** from ~200 lines across 4 scripts + agent.py to ~440 lines in
a single agent.py.

This isn't necessarily wrong — centralization and type safety have value —
but it should be acknowledged in the sample's documentation. The message
should be: "You're trading script simplicity for centralized security and
auditability, and the cost is proportional to the number of distinct
operations you need to support."

**Recommendation**: Consider showing a hybrid skill in the sample — one that
uses native tools for mutations (write, backup, git) but keeps a simple
read-only script for analysis (lint, complexity). This would demonstrate
that the two approaches aren't mutually exclusive and that the migration can
be incremental.

---

## Issue 2: `replace_text_in_project_file` — Minor Correctness Note

**Severity**: Low — behavior is correct but code is misleading

In `agent.py` lines 344–371:

```python
occurrences = content.count(old_text)
if occurrences == 0:
    raise ValueError('old_text was not found in the target file')
if occurrences > 1 and not replace_all:
    raise ValueError(
        'old_text matched multiple times; refine the text or set replace_all=true'
    )
replacement_count = occurrences if replace_all else 1
updated = content.replace(old_text, new_text, replacement_count)
```

Two observations:

1. When `replace_all=True`, passing `count=occurrences` to `str.replace()`
   is equivalent to omitting the count argument — both replace all
   occurrences. The explicit count is unnecessary and slightly confusing.

2. When `occurrences == 1`, the guard at line 359 doesn't fire regardless of
   the `replace_all` value, so `replace_all` is effectively ignored for
   single-occurrence matches. This is actually the right behavior (replacing
   1 occurrence is the same whether you asked for "all" or "one"), but the
   variable name `replacement_count` suggests it might matter.

**Recommendation**: Simplify to:
```python
if replace_all:
    updated = content.replace(old_text, new_text)
else:
    updated = content.replace(old_text, new_text, 1)
```

---

## Issue 3: `create_git_commit` Silently Drops Multi-Line Subjects

**Severity**: Medium — data loss potential

In `agent.py` lines 399–413:

```python
parts = [part.strip() for part in message.split('\n\n') if part.strip()]
subject = parts[0].splitlines()[0].strip()
```

If the model generates a commit message like:

```
Fix authentication timeout
when session token expires during refresh

This change adds a retry mechanism...
```

The subject extraction (`splitlines()[0]`) keeps only `Fix authentication
timeout`. The continuation line `when session token expires during refresh`
is silently discarded — it's part of `parts[0]` but not the first line, and
only the first line is passed as `-m` argument.

The second paragraph (`This change adds...`) is preserved via the second
`-m` flag, but the second line of the first paragraph is lost entirely.

**Recommendation**: Either:
- Use the full `parts[0]` as the first `-m` argument (preserving multi-line
  subjects), or
- Validate that the subject is a single line and return an error if not,
  giving the model a chance to reformulate.

---

## Issue 4: `NativeOnlySkillToolset` Is a Brittle Subclass

**Severity**: Medium — future maintenance risk

In `agent.py` lines 86–91:

```python
class NativeOnlySkillToolset(SkillToolset):
    """Skill toolset that removes `run_skill_script` entirely."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tools = [tool for tool in self._tools if tool.name != 'run_skill_script']
```

This pattern has several fragility risks:

1. **Name coupling**: If upstream renames the tool from `run_skill_script` to
   something else, the filter silently stops working and the script tool
   reappears.

2. **Internal attribute access**: `self._tools` is a private attribute. If
   `SkillToolset` changes how tools are stored (e.g., moves to lazy
   evaluation, a registry, or a different attribute name), this breaks.

3. **Init-time filtering**: If `SkillToolset` adds tools after `__init__`
   (e.g., in a `get_tools()` override), the filter won't catch them.

**Recommendation**: The cleanest fix would be upstream — have `SkillToolset`
skip adding `run_skill_script` when `code_executor=None`. Failing that,
override `get_tools()` instead of filtering in `__init__`:

```python
class NativeOnlySkillToolset(SkillToolset):
    def get_tools(self, *args, **kwargs):
        tools = super().get_tools(*args, **kwargs)
        return [t for t in tools if t.name != 'run_skill_script']
```

This is still name-coupled, but at least it's evaluated at call time rather
than frozen at init time.

---

## Issue 5: `PRODUCTION_GUIDANCE.md` Is Well-Written (Positive)

**Strength**: Valuable documentation

This document clearly explains:
- Why native tools are preferred over scripts in production
- The specific security risks of script execution (arbitrary code, secret
  exposure, shell expansion, weak auditability)
- A concrete migration path from scripts to native tools
- When sandbox execution might still be appropriate

The recommendation to "start with native tools, add sandbox only for what
can't be expressed as reviewed tools" is sound production advice.

One nuance worth adding: the document states "do not treat bash as a
first-class production skill primitive." While this is reasonable for
model-directed execution, many production systems (CI/CD, infrastructure
automation, deployment pipelines) rely heavily on bash. The distinction is
about **who controls the invocation** — bash scripts invoked by deterministic
pipelines are different from bash scripts invoked by an LLM that decides
the arguments at runtime.

---

## Issue 6: `_ensure_safe_project_path` Blocklist Gaps

**Severity**: Low — the blocklist is good but could be more comprehensive

The current blocklist covers:

```python
_BLOCKED_FILE_NAMES = {
    'application_default_credentials.json',
    'credentials.json',
}
_BLOCKED_SUFFIXES = {'.pem', '.key', '.p12', '.crt', '.cer', '.der'}
```

Plus `.env` / `.env.*` files checked separately. This covers the common
cases but misses some patterns:

- `.netrc` (contains HTTP auth credentials)
- `.pgpass` (PostgreSQL passwords)
- `id_rsa`, `id_ed25519` (SSH keys without `.pem` extension)
- `*.pfx` (Windows certificate format, similar to `.p12`)
- `token.json` (OAuth tokens from Google client libraries)
- `.npmrc` (can contain registry auth tokens)
- `.pypirc` (PyPI upload credentials)

**Recommendation**: Consider matching against a pattern like
`*credential*`, `*secret*`, `*token*` in addition to the explicit names, or
document that the blocklist is intentionally minimal and operators should
extend it for their environment.

---

## Issue 7: No Input Validation on `path` Parameter Types

**Severity**: Low — defense in depth

Most tool functions accept `path: str` but don't validate that the argument
is actually a string before passing it to `Path()`. If the model sends a
non-string type (integer, list, None), `Path()` will raise a `TypeError`
that gets caught by the broad `except Exception` handler and returned as an
error dict.

This works but produces unhelpful error messages like
`"TypeError: expected str, bytes or os.PathLike object, not int"` instead of
`"path must be a string"`.

**Recommendation**: Add a type check at the top of `_resolve_project_path`:
```python
if not isinstance(path, str):
    raise TypeError(f'path must be a string, got {type(path).__name__}')
```

---

## The Hybrid Approach: A Missing Third Option

Both samples present a binary choice: full script execution vs full native
rewrite. A practical middle ground exists:

### Keep Scripts for Read-Only Operations, Use Native Tools for Mutations

| Operation Type | Approach | Rationale |
|---------------|----------|-----------|
| Lint checking | Script (read-only) | Simple, portable, no security risk |
| Complexity analysis | Script (read-only) | Same — pure analysis |
| File reading | Either | Low risk either way |
| File writing | Native tool (confirmation-gated) | Mutation needs approval |
| File backup | Native tool (confirmation-gated) | Mutation needs approval |
| Git staging | Native tool (confirmation-gated) | Mutation needs approval |
| Git commit | Native tool (confirmation-gated) | Mutation needs approval |

This would:
- Cut the native tool code roughly in half (drop `lint_project_file`,
  `count_python_complexity`, `read_project_file`)
- Let existing Claude Code analysis scripts work unmodified
- Still enforce security on all mutating operations
- Demonstrate that the migration can be incremental

### SKILL.md Metadata for Script Classification

The `metadata.adk_additional_tools` field already provides a mechanism for
skills to declare which native tools they need. A similar pattern could
classify scripts:

```yaml
metadata:
  adk_additional_tools:
    - backup_project_file
    - write_project_file
  scripts:
    lint_check.sh:
      mode: read-only
    count_complexity.py:
      mode: read-only
```

The SkillToolset could then:
- Allow read-only scripts to execute without confirmation
- Require confirmation for mutating scripts
- Block scripts not listed in the metadata

### Centralized Security for Scripts

Rather than requiring each script to implement path validation, the
`_SkillScriptCodeExecutor._build_wrapper_code()` in the upstream
`skill_toolset.py` could inject:

1. Pre-validated path arguments (resolved and checked against blocklist)
2. File-size limits on script inputs
3. Output truncation on script results
4. Environment variable injection with validated values

This makes scripts safe by default without per-script refactoring.

---

## Summary of Recommendations

| Priority | Action |
|----------|--------|
| High | Fix `create_git_commit` to preserve or validate multi-line subjects |
| High | Replace `NativeOnlySkillToolset.__init__` filter with `get_tools()` override or upstream fix |
| Medium | Simplify `replace_text_in_project_file` replace logic |
| Medium | Extend `_ensure_safe_project_path` blocklist or document extension points |
| Low | Add type validation on `path` parameters |
| Low | Add nuance to PRODUCTION_GUIDANCE.md about bash in deterministic vs model-directed contexts |
| Strategic | Consider a hybrid sample showing incremental migration (native for mutations, scripts for analysis) |
