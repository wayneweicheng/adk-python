# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Hybrid version of the Claude Code skills sample.

This sample keeps the production-oriented native tool boundary while avoiding a
full rewrite of every read-only Python script. It imports trusted Python script
logic as a module, rewrites trivial bash behavior as thin Python tools, and does
not configure any code executor.

Runtime configuration:
  - `ADK_HYBRID_SKILLS_PROJECT_ROOT` limits file tools to a single repo.
  - `ADK_HYBRID_SKILLS_MAX_TEXT_BYTES` caps file and diff payload size.
  - `ADK_HYBRID_SKILLS_GIT_TIMEOUT_SECONDS` bounds git subprocess calls.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any

import yaml

from google.adk import Agent
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.skill_toolset import SkillToolset

logger = logging.getLogger(__name__)

_AGENT_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _AGENT_DIR / 'skills'
_TOOLS_DIR = _AGENT_DIR / 'tools'
_PROJECT_ROOT_ENV = 'ADK_HYBRID_SKILLS_PROJECT_ROOT'
_MAX_TEXT_BYTES_ENV = 'ADK_HYBRID_SKILLS_MAX_TEXT_BYTES'
_GIT_TIMEOUT_ENV = 'ADK_HYBRID_SKILLS_GIT_TIMEOUT_SECONDS'
_BLOCKED_FILE_NAMES = {
    '.netrc',
    '.npmrc',
    '.pgpass',
    '.pypirc',
    'application_default_credentials.json',
    'credentials.json',
    'id_dsa',
    'id_ecdsa',
    'id_ed25519',
    'id_rsa',
    'token.json',
}
_BLOCKED_NAME_FRAGMENTS = ('credential', 'secret', 'token')
_BLOCKED_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.crt', '.cer', '.der'}


def _get_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        logger.warning(
            'Invalid %s value %r. Falling back to %d.',
            name,
            raw_value,
            default,
        )
        return default


def _find_project_root(start_dir: Path) -> Path:
    for candidate in (start_dir, *start_dir.parents):
        if (candidate / '.git').exists() or (candidate / 'pyproject.toml').exists():
            return candidate
    return start_dir


_PROJECT_ROOT = Path(
    os.getenv(_PROJECT_ROOT_ENV) or _find_project_root(_AGENT_DIR)
).expanduser().resolve()
os.environ.setdefault(_PROJECT_ROOT_ENV, str(_PROJECT_ROOT))
_MAX_TEXT_BYTES = _get_int_env(_MAX_TEXT_BYTES_ENV, 120_000)
_GIT_TIMEOUT_SECONDS = _get_int_env(_GIT_TIMEOUT_ENV, 10)


class NativeOnlySkillToolset(SkillToolset):
    """Skill toolset that maps tools via `tools/<skill>/tools.yaml` files."""

    def __init__(self, *args, tools_dir: Path = _TOOLS_DIR, **kwargs):
        self._skill_instruction_mappings = self._load_instruction_mappings(tools_dir)
        self._skill_tool_configs = self._load_skill_tool_configs(tools_dir)
        self._skill_tool_names = {
            skill_name: tuple(config['name'] for config in configs)
            for skill_name, configs in self._skill_tool_configs.items()
        }
        super().__init__(*args, **kwargs)

    @staticmethod
    def _load_instruction_mappings(
        tools_dir: Path,
    ) -> dict[str, tuple[dict[str, Any], ...]]:
        instruction_mappings = {}
        if not tools_dir.is_dir():
            return instruction_mappings

        for skill_dir in sorted(tools_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            tools_file = skill_dir / 'tools.yaml'
            if not tools_file.exists():
                continue

            parsed = yaml.safe_load(tools_file.read_text(encoding='utf-8')) or {}
            if not isinstance(parsed, dict):
                continue

            raw_mappings = parsed.get('mappings', [])
            if not isinstance(raw_mappings, list):
                raw_mappings = []

            ordered_mappings = []
            for entry in raw_mappings:
                if not isinstance(entry, dict):
                    continue
                raw_from = entry.get('from', '')
                if not isinstance(raw_from, str):
                    continue
                source_name = raw_from.strip()
                if not source_name:
                    continue

                raw_to = entry.get('to', [])
                if isinstance(raw_to, str):
                    target_names = [raw_to.strip()]
                elif isinstance(raw_to, list):
                    target_names = [
                        value.strip()
                        for value in raw_to
                        if isinstance(value, str) and value.strip()
                    ]
                else:
                    target_names = []
                if target_names:
                    ordered_mappings.append({
                        'from': source_name,
                        'to': tuple(target_names),
                    })

            instruction_mappings[skill_dir.name] = tuple(ordered_mappings)

        return instruction_mappings

    @staticmethod
    def _load_skill_tool_configs(
        tools_dir: Path,
    ) -> dict[str, tuple[dict[str, Any], ...]]:
        skill_tool_configs = {}
        if not tools_dir.is_dir():
            return skill_tool_configs

        for skill_dir in sorted(tools_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            tools_file = skill_dir / 'tools.yaml'
            if not tools_file.exists():
                continue

            ordered_configs = []
            seen_names = set()
            parsed = yaml.safe_load(tools_file.read_text(encoding='utf-8')) or {}
            if not isinstance(parsed, dict):
                logger.warning(
                    'Ignoring invalid tool mapping in %s: expected a mapping.',
                    tools_file,
                )
                continue

            raw_tools = parsed.get('tools', [])
            if not isinstance(raw_tools, list):
                logger.warning(
                    'Ignoring invalid tool mapping in %s: "tools" must be a list.',
                    tools_file,
                )
                continue

            mappings_by_name = {}
            raw_mappings = parsed.get('mappings', [])
            if not isinstance(raw_mappings, list):
                logger.warning(
                    'Ignoring invalid tool mappings in %s: "mappings" must be a list.',
                    tools_file,
                )
                raw_mappings = []

            for entry in raw_mappings:
                if not isinstance(entry, dict):
                    continue
                raw_from = entry.get('from', '')
                if not isinstance(raw_from, str):
                    continue
                source_name = raw_from.strip()
                if not source_name:
                    continue

                raw_to = entry.get('to', [])
                if isinstance(raw_to, str):
                    target_names = [raw_to.strip()]
                elif isinstance(raw_to, list):
                    target_names = [
                        value.strip()
                        for value in raw_to
                        if isinstance(value, str) and value.strip()
                    ]
                else:
                    target_names = []

                for target_name in target_names:
                    mappings_by_name.setdefault(target_name, []).append(source_name)

            for entry in raw_tools:
                if isinstance(entry, str):
                    tool_name = entry.strip()
                elif isinstance(entry, dict):
                    raw_name = entry.get('name', '')
                    tool_name = raw_name.strip() if isinstance(raw_name, str) else ''
                else:
                    tool_name = ''

                if not tool_name or tool_name in seen_names:
                    continue
                ordered_configs.append({
                    'name': tool_name,
                    'maps_from': tuple(mappings_by_name.get(tool_name, ())),
                })
                seen_names.add(tool_name)

            skill_tool_configs[skill_dir.name] = tuple(ordered_configs)

        return skill_tool_configs

    async def get_tools(self, readonly_context=None):
        tools = await super().get_tools(readonly_context)
        return [tool for tool in tools if tool.name != 'run_skill_script']

    async def _resolve_additional_tools_from_state(self, readonly_context):
        if not readonly_context:
            return []

        state_key = f'_adk_activated_skill_{readonly_context.agent_name}'
        activated_skills = readonly_context.state.get(state_key, [])
        if not activated_skills:
            return []

        ordered_tool_names = []
        seen_tool_names = set()
        for skill_name in activated_skills:
            for tool_name in self._skill_tool_names.get(skill_name, ()):
                if tool_name not in seen_tool_names:
                    ordered_tool_names.append(tool_name)
                    seen_tool_names.add(tool_name)

        if not ordered_tool_names:
            return []

        candidate_tools = self._provided_tools_by_name.copy()
        if self._provided_toolsets:
            toolset_results = await asyncio.gather(*(
                toolset.get_tools_with_prefix(readonly_context)
                for toolset in self._provided_toolsets
            ))
            for toolset_tools in toolset_results:
                for tool in toolset_tools:
                    candidate_tools[tool.name] = tool

        resolved_tools = []
        existing_tool_names = {tool.name for tool in self._tools}
        for tool_name in ordered_tool_names:
            tool = candidate_tools.get(tool_name)
            if tool is None:
                logger.warning(
                    'Skill tool mapping referenced unknown tool %r.',
                    tool_name,
                )
                continue
            if tool.name in existing_tool_names:
                logger.error(
                    "Tool name collision: tool '%s' already exists.",
                    tool.name,
                )
                continue
            resolved_tools.append(tool)
            existing_tool_names.add(tool.name)

        return resolved_tools


def _format_mapping_lines(
    skill_toolset: NativeOnlySkillToolset,
    *,
    arrow: str,
    width: int,
) -> str:
    lines = []
    seen_sources = set()
    for mappings in skill_toolset._skill_instruction_mappings.values():
        for mapping in mappings:
            source_name = mapping['from']
            if source_name in seen_sources:
                continue
            target_label = ', '.join(mapping['to'])
            lines.append(f'  {source_name:<{width}} {arrow} {target_label}')
            seen_sources.add(source_name)
    return '\n'.join(lines)


def _load_skill_from_dir(skill_dir: Path):
    try:
        from google.adk.skills import load_skill_from_dir
    except ImportError as exc:
        raise RuntimeError(
            'google-adk does not expose load_skill_from_dir. '
            'Use the repo virtualenv or install the local adk-python checkout.'
        ) from exc
    return load_skill_from_dir(skill_dir)


def _load_all_skills():
    if not _SKILLS_DIR.exists():
        logger.warning('Skills directory does not exist: %s', _SKILLS_DIR)
        return []

    skills = []
    for skill_dir in sorted(_SKILLS_DIR.iterdir()):
        if skill_dir.is_dir() and (skill_dir / 'SKILL.md').exists():
            try:
                skills.append(_load_skill_from_dir(skill_dir))
            except Exception:
                logger.exception('Skipping invalid skill directory: %s', skill_dir)
    if not skills:
        logger.warning('No skills were loaded from %s', _SKILLS_DIR)
    return skills


def _relative_display(path: Path) -> str:
    return str(path.relative_to(_PROJECT_ROOT))


def _ensure_safe_project_path(path: Path) -> None:
    name = path.name.lower()
    if name == '.env' or (name.startswith('.env.') and name != '.env.example'):
        raise PermissionError(f'access to {path.name!r} is blocked')
    if name in _BLOCKED_FILE_NAMES:
        raise PermissionError(f'access to {path.name!r} is blocked')
    if any(fragment in name for fragment in _BLOCKED_NAME_FRAGMENTS):
        raise PermissionError(f'access to {path.name!r} is blocked')
    if path.suffix.lower() in _BLOCKED_SUFFIXES:
        raise PermissionError(f'access to {path.name!r} is blocked')


def _resolve_project_path(path: str, *, must_exist: bool = True) -> Path:
    if not isinstance(path, str):
        raise TypeError(f'path must be a string, got {type(path).__name__}')
    if not path:
        raise ValueError('path is required')
    candidate = Path(path).expanduser()
    resolved = (
        candidate.resolve()
        if candidate.is_absolute()
        else (_PROJECT_ROOT / candidate).resolve()
    )
    try:
        resolved.relative_to(_PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(
            f'path {resolved!r} is outside project root {_PROJECT_ROOT!s}'
        ) from exc

    _ensure_safe_project_path(resolved)
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f'file {path!r} was not found')
    return resolved


def _read_text_file(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f'file {path!s} was not found')
    if path.stat().st_size > _MAX_TEXT_BYTES:
        raise ValueError(
            f'file {_relative_display(path)!r} exceeds {_MAX_TEXT_BYTES} bytes'
        )
    return path.read_text(encoding='utf-8')


def _run_git(args: list[str]) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ['git', *args],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return {'error': 'git executable was not found', 'returncode': -1}
    except subprocess.TimeoutExpired:
        return {
            'error': f'git command timed out after {_GIT_TIMEOUT_SECONDS}s',
            'returncode': -1,
        }

    return {
        'stdout': completed.stdout,
        'stderr': completed.stderr,
        'returncode': completed.returncode,
    }


_COMPLEXITY_SCRIPT_PATH = _SKILLS_DIR / 'code-review' / 'scripts' / 'count_complexity.py'
_COMPLEXITY_SPEC = importlib.util.spec_from_file_location(
    'claude_code_skills_hybrid_count_complexity',
    _COMPLEXITY_SCRIPT_PATH,
)
if _COMPLEXITY_SPEC is None or _COMPLEXITY_SPEC.loader is None:
    raise RuntimeError(f'Unable to load complexity helper from {_COMPLEXITY_SCRIPT_PATH}')
_COMPLEXITY_MODULE = importlib.util.module_from_spec(_COMPLEXITY_SPEC)
_COMPLEXITY_SPEC.loader.exec_module(_COMPLEXITY_MODULE)
_script_count_metrics = _COMPLEXITY_MODULE.count_metrics


def count_python_complexity(path: str) -> dict[str, Any]:
    """Return basic Python structure metrics by importing the existing helper."""
    try:
        target = _resolve_project_path(path)
        metrics = _script_count_metrics(str(target))
        return {'path': _relative_display(target), **metrics}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {'error': str(exc)}


def read_project_file(path: str) -> dict[str, Any]:
    """Read a UTF-8 text file under the configured project root."""
    try:
        target = _resolve_project_path(path)
        text = _read_text_file(target)
        return {
            'path': _relative_display(target),
            'line_count': len(text.splitlines()),
            'content': text,
        }
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {'error': str(exc)}


def lint_project_file(path: str) -> dict[str, Any]:
    """Return simple lint metrics for a project file without shell execution."""
    try:
        target = _resolve_project_path(path)
        text = _read_text_file(target)
        lines = text.splitlines()
        return {
            'path': _relative_display(target),
            'todo_count': sum(line.count('TODO') + line.count('FIXME') for line in lines),
            'line_count': len(lines),
            'trailing_whitespace_lines': sum(1 for line in lines if line.endswith(' ')),
        }
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {'error': str(exc)}


def backup_project_file(path: str) -> dict[str, Any]:
    """Create a `.bak` copy of an existing project file before an edit."""
    try:
        target = _resolve_project_path(path)
        backup_path = target.with_suffix(target.suffix + '.bak')
        shutil.copy2(target, backup_path)
        return {
            'path': _relative_display(target),
            'backup_path': _relative_display(backup_path),
        }
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {'error': str(exc)}


def write_project_file(path: str, content: str) -> dict[str, Any]:
    """Overwrite an existing project file with reviewed text content."""
    try:
        target = _resolve_project_path(path)
        encoded = content.encode('utf-8')
        if len(encoded) > _MAX_TEXT_BYTES:
            raise ValueError(
                f'content exceeds {_MAX_TEXT_BYTES} bytes; prefer smaller targeted edits'
            )
        target.write_text(content, encoding='utf-8')
        return {
            'path': _relative_display(target),
            'bytes_written': len(encoded),
        }
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {'error': str(exc)}


def replace_text_in_project_file(
    path: str,
    old_text: str,
    new_text: str,
    replace_all: bool = False,
) -> dict[str, Any]:
    """Apply a bounded text replacement within an existing project file."""
    try:
        if not old_text:
            raise ValueError('old_text must not be empty')
        target = _resolve_project_path(path)
        content = _read_text_file(target)
        occurrences = content.count(old_text)
        if occurrences == 0:
            raise ValueError('old_text was not found in the target file')
        if occurrences > 1 and not replace_all:
            raise ValueError(
                'old_text matched multiple times; refine the text or set replace_all=true'
            )
        updated = (
            content.replace(old_text, new_text)
            if replace_all
            else content.replace(old_text, new_text, 1)
        )
        target.write_text(updated, encoding='utf-8')
        return {
            'path': _relative_display(target),
            'replacements': occurrences if replace_all else 1,
        }
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {'error': str(exc)}


def git_status_summary() -> dict[str, Any]:
    """Return `git status --short --branch` for the configured project root."""
    result = _run_git(['status', '--short', '--branch'])
    if result.get('returncode') != 0:
        return {'error': result.get('stderr') or result.get('error') or 'git status failed'}
    return {
        'project_root': str(_PROJECT_ROOT),
        'status': result['stdout'].strip() or 'working tree clean',
    }


def list_changed_files() -> dict[str, Any]:
    """List changed files from `git status --porcelain` for the project root."""
    result = _run_git(['status', '--porcelain'])
    if result.get('returncode') != 0:
        return {'error': result.get('stderr') or result.get('error') or 'git status failed'}

    changed_files = []
    for line in result['stdout'].splitlines():
        if len(line) < 4:
            continue
        changed_files.append(
            {
                'index_status': line[0],
                'worktree_status': line[1],
                'path': line[3:].split(' -> ', 1)[-1],
                'raw': line,
            }
        )
    return {'changed_files': changed_files}


def read_git_diff(staged: bool = False, path: str = '') -> dict[str, Any]:
    """Return git diff text, optionally scoped to one project file."""
    args = ['diff', '--unified=3']
    if staged:
        args.append('--staged')

    relative_path = ''
    if path:
        target = _resolve_project_path(path, must_exist=False)
        relative_path = _relative_display(target)
        args.extend(['--', relative_path])

    result = _run_git(args)
    if result.get('returncode') != 0:
        return {'error': result.get('stderr') or result.get('error') or 'git diff failed'}

    diff_text = result['stdout']
    truncated = False
    if len(diff_text.encode('utf-8')) > _MAX_TEXT_BYTES:
        diff_text = diff_text.encode('utf-8')[:_MAX_TEXT_BYTES].decode('utf-8', errors='ignore')
        truncated = True

    return {
        'staged': staged,
        'path': relative_path,
        'diff': diff_text,
        'truncated': truncated,
    }


def stage_project_files(paths: list[str]) -> dict[str, Any]:
    """Stage specific project files with `git add`, excluding blocked secret-like paths."""
    if not paths:
        return {'error': 'paths must contain at least one file'}

    try:
        relative_paths = [
            _relative_display(_resolve_project_path(path, must_exist=False))
            for path in paths
        ]
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {'error': str(exc)}

    result = _run_git(['add', '--', *relative_paths])
    if result.get('returncode') != 0:
        return {'error': result.get('stderr') or result.get('error') or 'git add failed'}
    return {'staged_paths': relative_paths}


def create_git_commit(message: str) -> dict[str, Any]:
    """Create a git commit from the current staged diff using a reviewed message."""
    message = message.strip()
    if not message:
        return {'error': 'message must not be empty'}

    parts = [part.strip() for part in message.split('\n\n') if part.strip()]
    subject = parts[0]
    if not subject:
        return {'error': 'message subject must not be empty'}

    args = ['commit', '-m', subject]
    if len(parts) > 1:
        args.extend(['-m', '\n\n'.join(parts[1:])])

    result = _run_git(args)
    if result.get('returncode') != 0:
        return {
            'error': result.get('stderr') or result.get('error') or 'git commit failed'
        }
    return {'result': result['stdout'].strip() or 'commit created'}


skills = _load_all_skills()
skill_toolset = NativeOnlySkillToolset(
    skills=skills,
    additional_tools=[
        read_project_file,
        lint_project_file,
        count_python_complexity,
        git_status_summary,
        list_changed_files,
        read_git_diff,
        FunctionTool(backup_project_file, require_confirmation=True),
        FunctionTool(write_project_file, require_confirmation=True),
        FunctionTool(replace_text_in_project_file, require_confirmation=True),
        FunctionTool(stage_project_files, require_confirmation=True),
        FunctionTool(create_git_commit, require_confirmation=True),
    ],
)

_TOOL_MAPPING_INSTRUCTION = """\
This agent uses native Python tools instead of shell scripts or a code executor.
When a skill's instructions reference scripts, raw git commands, or generic file
operations, translate them to the equivalent native tool:

{mapping_lines}

`run_skill_script` is not available. Always use the equivalent native tool above.
""".format(
    mapping_lines=_format_mapping_lines(
        skill_toolset,
        arrow='→',
        width=34,
    )
)

root_agent = Agent(
    model='gemini-2.5-flash',
    name='claude_code_skills_agent_hybrid',
    description=(
        'Agent that wraps existing Python skill helpers as native modules and '
        'replaces bash behavior with thin Python tools, without a code executor.'
    ),
    instruction=_TOOL_MAPPING_INSTRUCTION,
    tools=[skill_toolset],
)
