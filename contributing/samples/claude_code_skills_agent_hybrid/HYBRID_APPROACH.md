# Hybrid Approach For Production Skill Agents

This sample shows a middle path between the original script-based sample and the
full native rewrite.

## The problem

Script-backed skills are easy to author, but `run_skill_script` requires a code
executor. In many corporate environments that introduces platform review,
sandboxing, IAM, and operational overhead. A full native rewrite removes that
burden, but it can feel heavy when the original scripts mostly contain a few
lines of business logic surrounded by argument parsing and path handling.

## The hybrid approach

The hybrid sample keeps the production boundary from the native sample:

- no code executor
- no `run_skill_script` exposed to the model
- centralized file and git security checks in `agent.py`

It then reuses trusted, read-only Python script logic by importing it as a
module instead of executing it through ADK's script runner.

## What stays untouched

`skills/code-review/scripts/count_complexity.py` is copied unchanged and loaded
as a module. The agent wraps its `count_metrics()` function with:

- project-root validation
- blocked-path checks
- file-size limits
- structured ADK tool output

## What gets rewritten

Only the bash behavior is rewritten as thin Python tools:

- `lint_check.sh` -> `lint_project_file`
- `backup.sh` -> `backup_project_file`

This keeps the rewrite cost low while removing shell execution from the model's
capability set.

## Security layer

All tools, including the imported-script wrapper, go through the same security
helpers in `agent.py`:

- `_resolve_project_path()` restricts access to a configured project root
- `_ensure_safe_project_path()` blocks `.env`, credentials, tokens, and key material
- `_read_text_file()` enforces a file size cap
- `_run_git()` bounds subprocess execution with a timeout

## Why this is safer than `run_skill_script`

The model can only call explicit reviewed tools. It cannot choose an arbitrary
script path, pass free-form shell arguments, or rely on a general code executor.
That narrows the trust boundary substantially while preserving useful skill
behavior.

## Migration path

1. Start with the hybrid approach when you already have useful Python helper
   scripts and want to avoid a full rewrite.
2. Move more helpers into native tools over time as requirements stabilize.
3. Introduce sandboxed execution later only for capabilities that truly need
   dynamic code execution.

## Comparison

| Approach | Security posture | Maintenance cost | Executor required |
|----------|------------------|------------------|-------------------|
| Script-based | Lowest | Lowest initially | Yes |
| Native | Highest | Highest upfront | No |
| Hybrid | High | Moderate | No |

The hybrid model is appropriate when you want production-friendly controls
without paying the full rewrite cost on day one.
