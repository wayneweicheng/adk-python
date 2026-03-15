# Implementation Plan: Directory-based tool mapping

## Goal

Eliminate the `metadata.adk_additional_tools:` block from every `skills/*/SKILL.md`
so those files become **byte-for-byte identical** to the originals in
`contributing/samples/claude_code_skills_agent/`.

The mapping from skill → tools moves into a new `tools/<skill-name>/tools.txt`
convention handled entirely inside `NativeOnlySkillToolset` in `agent.py`.

---

## Background

`SkillToolset._resolve_additional_tools_from_state` (in
`src/google/adk/tools/skill_toolset.py`, around line 732) reads
`skill.frontmatter.metadata.get("adk_additional_tools")` to decide which
`additional_tools` to expose after a skill is activated.

Because `get_tools` calls `self._resolve_additional_tools_from_state(...)`, Python
dynamic dispatch lets us override this one method in `NativeOnlySkillToolset` to swap
in the directory-based lookup — **no changes to ADK core**.

---

## Step 1 — Create `tools/<skill-name>/tools.txt` files

Create the following files (one tool name per line; blank lines and lines starting
with `#` are ignored):

### `tools/code-review/tools.txt`
```
read_project_file
lint_project_file
count_python_complexity
git_status_summary
list_changed_files
read_git_diff
```

### `tools/commit/tools.txt`
```
git_status_summary
list_changed_files
read_git_diff
stage_project_files
create_git_commit
```

### `tools/refactor/tools.txt`
```
read_project_file
backup_project_file
replace_text_in_project_file
write_project_file
```

### `tools/simplify/tools.txt`
```
read_project_file
backup_project_file
replace_text_in_project_file
write_project_file
list_changed_files
read_git_diff
```

---

## Step 2 — Update `NativeOnlySkillToolset` in `agent.py`

Replace the existing `NativeOnlySkillToolset` class and add a `_TOOLS_DIR` constant.

### Add constant (after the `_SKILLS_DIR` line):
```python
_TOOLS_DIR = _AGENT_DIR / 'tools'
```

### Replace the class:
```python
class NativeOnlySkillToolset(SkillToolset):
    """Skill toolset that maps tools to skills via tools/<skill>/tools.txt files.

    This replaces the metadata.adk_additional_tools: convention in SKILL.md so
    those files remain identical to the originals in claude_code_skills_agent/.
    """

    def __init__(self, *args, tools_dir: Path = _TOOLS_DIR, **kwargs):
        # Build skill-name → set[tool_name] from tools/<skill-name>/tools.txt
        self._skill_tool_names: dict[str, set[str]] = {}
        if tools_dir.is_dir():
            for skill_dir in sorted(tools_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                tools_file = skill_dir / 'tools.txt'
                if tools_file.exists():
                    names = {
                        line.strip()
                        for line in tools_file.read_text(encoding='utf-8').splitlines()
                        if line.strip() and not line.strip().startswith('#')
                    }
                    self._skill_tool_names[skill_dir.name] = names
        super().__init__(*args, **kwargs)

    async def get_tools(self, readonly_context=None):
        tools = await super().get_tools(readonly_context)
        return [t for t in tools if t.name != 'run_skill_script']

    async def _resolve_additional_tools_from_state(self, readonly_context):
        if not readonly_context:
            return []
        agent_name = readonly_context.agent_name
        activated = readonly_context.state.get(
            f'_adk_activated_skill_{agent_name}', []
        )
        if not activated:
            return []

        wanted: set[str] = set()
        for skill_name in activated:
            wanted.update(self._skill_tool_names.get(skill_name, set()))

        existing = {t.name for t in self._tools}
        result = []
        for name in wanted:
            tool = self._provided_tools_by_name.get(name)
            if tool and tool.name not in existing:
                result.append(tool)
                existing.add(tool.name)
        return result
```

---

## Step 3 — Strip `metadata:` block from each SKILL.md

Remove only the `metadata:` section from each file's YAML frontmatter. The body
instructions must not change.

**Before** (example from `skills/code-review/SKILL.md`):
```yaml
---
name: code-review
description: Review code files for quality, security, and style issues, then produce a structured report.
metadata:
  adk_additional_tools:
    - read_project_file
    - lint_project_file
    - count_python_complexity
    - git_status_summary
    - list_changed_files
    - read_git_diff
---
```

**After**:
```yaml
---
name: code-review
description: Review code files for quality, security, and style issues, then produce a structured report.
---
```

Apply the same strip to:
- `skills/commit/SKILL.md`
- `skills/refactor/SKILL.md`
- `skills/simplify/SKILL.md`

---

## Verification

```bash
# Start the agent
cd contributing/samples/claude_code_skills_agent_hybrid
adk web

# In the chat, test each skill:
# 1. "review agent.py"
#    → load_skill("code-review") fires
#    → read_project_file, lint_project_file, count_python_complexity become available

# 2. "commit my changes"
#    → load_skill("commit") fires
#    → git_status_summary, stage_project_files, create_git_commit become available

# Confirm SKILL.md bodies are identical to originals:
diff skills/code-review/SKILL.md ../claude_code_skills_agent/skills/code-review/SKILL.md
diff skills/commit/SKILL.md      ../claude_code_skills_agent/skills/commit/SKILL.md
diff skills/refactor/SKILL.md    ../claude_code_skills_agent/skills/refactor/SKILL.md
diff skills/simplify/SKILL.md    ../claude_code_skills_agent/skills/simplify/SKILL.md
# All diffs should show only the removed metadata: block (i.e., no body changes)
```
