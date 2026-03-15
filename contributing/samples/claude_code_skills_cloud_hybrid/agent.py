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

"""Hybrid cloud-skills agent using imported Python helpers and native tools.

This sample keeps the original skill text and bundled scripts intact, but maps
skill activation to reviewed native tools instead of exposing a code executor.
Python helper scripts are imported directly as modules, while simple bash
behavior is rewritten as thin Python tools.

Runtime configuration:
  - `ADK_CLOUD_HYBRID_SKILLS_MAX_TEXT_BYTES` caps bounded object previews.
  - `CLOUD_HYBRID_DEFAULT_PROJECT` sets the default GCP project.
  - `CLOUD_HYBRID_DEFAULT_DATASET` sets the default BigQuery dataset.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
from pathlib import Path
import re
from typing import Any

import yaml

from google.adk import Agent
from google.adk.planners import PlanReActPlanner
from google.adk.tools.skill_toolset import SkillToolset

logger = logging.getLogger(__name__)

_AGENT_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _AGENT_DIR / 'skills'
_TOOLS_DIR = _AGENT_DIR / 'tools'
_MAX_TEXT_BYTES_ENV = 'ADK_CLOUD_HYBRID_SKILLS_MAX_TEXT_BYTES'
_DEFAULT_PROJECT_ENV = 'CLOUD_HYBRID_DEFAULT_PROJECT'
_DEFAULT_DATASET_ENV = 'CLOUD_HYBRID_DEFAULT_DATASET'
_TABLE_REF_RE = re.compile(
    r'^(?:(?P<project>[a-z0-9-]+)\.)?'
    r'(?P<dataset>[A-Za-z0-9_]+)\.(?P<table>[A-Za-z0-9_]+)$'
)


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


_MAX_TEXT_BYTES = _get_int_env(_MAX_TEXT_BYTES_ENV, 120_000)
_DEFAULT_PROJECT = os.getenv(_DEFAULT_PROJECT_ENV, '').strip()
_DEFAULT_DATASET = os.getenv(_DEFAULT_DATASET_ENV, '').strip()


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


def _load_helper_module(relative_path: str, module_name: str):
    helper_path = _SKILLS_DIR / relative_path
    spec = importlib.util.spec_from_file_location(module_name, helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load helper module from {helper_path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_gcs_inventory = _load_helper_module(
    'gcs-investigator/scripts/gcs_inventory.py',
    'cloud_hybrid_gcs_inventory',
)
_gcs_preview = _load_helper_module(
    'gcs-investigator/scripts/object_preview.py',
    'cloud_hybrid_gcs_preview',
)
_bq_dataset_tables = _load_helper_module(
    'bigquery-catalog-review/scripts/list_dataset_tables.py',
    'cloud_hybrid_bq_list_dataset_tables',
)
_bq_table_profile = _load_helper_module(
    'bigquery-catalog-review/scripts/table_profile.py',
    'cloud_hybrid_bq_table_profile',
)


def parse_gcs_resource(resource: str) -> dict[str, Any]:
    """Parse a GCS bucket or `gs://` URI into bucket and prefix parts."""
    if not isinstance(resource, str):
        return {'error': f'resource must be a string, got {type(resource).__name__}'}
    resource = resource.strip()
    if not resource:
        return {'error': 'resource must not be empty'}
    if resource.startswith('gs://'):
        trimmed = resource[5:]
        bucket_name, _, prefix = trimmed.partition('/')
    else:
        bucket_name, _, prefix = resource.partition('/')
    if not bucket_name:
        return {'error': 'bucket name could not be determined'}
    return {
        'resource': resource,
        'bucket_name': bucket_name,
        'prefix': prefix,
        'normalized_uri': (
            f'gs://{bucket_name}/{prefix}'
            if prefix
            else f'gs://{bucket_name}'
        ),
    }


def list_gcs_objects(
    bucket_name: str,
    prefix: str = '',
    project_id: str = '',
    max_results: int = 25,
) -> dict[str, Any]:
    """List bounded GCS objects using the imported helper module."""
    if not isinstance(bucket_name, str) or not bucket_name.strip():
        return {'error': 'bucket_name must be a non-empty string'}
    if not isinstance(prefix, str):
        return {'error': f'prefix must be a string, got {type(prefix).__name__}'}
    if max_results <= 0:
        return {'error': 'max_results must be greater than zero'}
    project = project_id.strip() if isinstance(project_id, str) else ''
    project = project or _DEFAULT_PROJECT
    return _gcs_inventory.list_objects(
        project_id=project,
        bucket_name=bucket_name.strip(),
        prefix=prefix.strip(),
        max_results=max_results,
    )


def preview_gcs_text_object(
    bucket_name: str,
    object_name: str,
    project_id: str = '',
    max_bytes: int = 4096,
) -> dict[str, Any]:
    """Preview a bounded text object using the imported helper module."""
    if not isinstance(bucket_name, str) or not bucket_name.strip():
        return {'error': 'bucket_name must be a non-empty string'}
    if not isinstance(object_name, str) or not object_name.strip():
        return {'error': 'object_name must be a non-empty string'}
    if max_bytes <= 0 or max_bytes > _MAX_TEXT_BYTES:
        return {'error': f'max_bytes must be between 1 and {_MAX_TEXT_BYTES}'}
    project = project_id.strip() if isinstance(project_id, str) else ''
    project = project or _DEFAULT_PROJECT
    return _gcs_preview.preview_text_object(
        project_id=project,
        bucket_name=bucket_name.strip(),
        object_name=object_name.strip(),
        max_bytes=max_bytes,
    )


def parse_bigquery_resource(
    resource: str,
    default_project: str = '',
    default_dataset: str = '',
) -> dict[str, Any]:
    """Parse dataset.table or project.dataset.table into structured parts."""
    if not isinstance(resource, str):
        return {'error': f'resource must be a string, got {type(resource).__name__}'}
    resource = resource.strip().replace(':', '.')
    if not resource:
        return {'error': 'resource must not be empty'}
    match = _TABLE_REF_RE.match(resource)
    if not match:
        if resource.count('.') == 1:
            dataset_id, table_id = resource.split('.', 1)
            project_id = default_project or _DEFAULT_PROJECT
            if not project_id:
                return {
                    'error': (
                        'default project is required for dataset.table references'
                    )
                }
            return {
                'project_id': project_id,
                'dataset_id': dataset_id,
                'table_id': table_id,
                'normalized': f'{project_id}.{dataset_id}.{table_id}',
            }
        return {'error': 'resource must be dataset.table or project.dataset.table'}
    project_id = match.group('project') or default_project or _DEFAULT_PROJECT
    dataset_id = match.group('dataset')
    table_id = match.group('table')
    if not project_id:
        return {'error': 'project_id could not be determined'}
    return {
        'project_id': project_id,
        'dataset_id': dataset_id,
        'table_id': table_id,
        'normalized': f'{project_id}.{dataset_id}.{table_id}',
    }


def list_bigquery_tables(
    dataset_id: str,
    project_id: str = '',
    include_views: bool = True,
    max_results: int = 50,
) -> dict[str, Any]:
    """List tables for a dataset using the imported helper module."""
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        return {'error': 'dataset_id must be a non-empty string'}
    if max_results <= 0:
        return {'error': 'max_results must be greater than zero'}
    project = project_id.strip() if isinstance(project_id, str) else ''
    project = project or _DEFAULT_PROJECT
    if not project:
        return {'error': 'project_id is required'}
    return _bq_dataset_tables.list_dataset_tables(
        project_id=project,
        dataset_id=dataset_id.strip(),
        include_views=include_views,
        max_results=max_results,
    )


def inspect_bigquery_table(
    table_id: str,
    dataset_id: str = '',
    project_id: str = '',
    table_ref: str = '',
) -> dict[str, Any]:
    """Inspect a BigQuery table using the imported helper module."""
    if table_ref:
        parsed = parse_bigquery_resource(
            table_ref,
            default_project=project_id,
            default_dataset=dataset_id,
        )
        if 'error' in parsed:
            return parsed
        project = parsed['project_id']
        dataset = parsed['dataset_id']
        table = parsed['table_id']
    else:
        if not isinstance(table_id, str) or not table_id.strip():
            return {'error': 'table_id must be a non-empty string'}
        project = project_id.strip() if isinstance(project_id, str) else ''
        dataset = dataset_id.strip() if isinstance(dataset_id, str) else ''
        project = project or _DEFAULT_PROJECT
        dataset = dataset or _DEFAULT_DATASET
        if not project or not dataset:
            return {
                'error': (
                    'project_id and dataset_id are required when table_ref is '
                    'not provided'
                )
            }
        table = table_id.strip()
    return _bq_table_profile.inspect_table(
        project_id=project,
        dataset_id=dataset,
        table_id=table,
    )


def summarize_pipeline_alignment(
    object_names: list[str],
    table_names: list[str],
    prefix: str = '',
) -> dict[str, Any]:
    """Compare GCS object-name patterns with BigQuery table names."""
    if not isinstance(object_names, list) or not all(
        isinstance(value, str) for value in object_names
    ):
        return {'error': 'object_names must be a list of strings'}
    if not isinstance(table_names, list) or not all(
        isinstance(value, str) for value in table_names
    ):
        return {'error': 'table_names must be a list of strings'}

    normalized_tables = {name.lower() for name in table_names}
    inferred_targets = {}
    for object_name in object_names:
        stem = Path(object_name).stem.lower()
        stem = re.sub(r'[^a-z0-9_]+', '_', stem)
        candidates = [part for part in stem.split('_') if part]
        matched = sorted({
            table_name
            for table_name in normalized_tables
            if any(part in table_name for part in candidates)
        })
        inferred_targets[object_name] = matched[:5]

    covered_tables = {
        match
        for matches in inferred_targets.values()
        for match in matches
    }
    return {
        'prefix': prefix,
        'object_count': len(object_names),
        'table_count': len(table_names),
        'missing_table_matches': sorted(normalized_tables - covered_tables),
        'objects_without_matches': [
            name
            for name, matches in inferred_targets.items()
            if not matches
        ],
        'inferred_targets': inferred_targets,
    }


skills = _load_all_skills()
skill_toolset = NativeOnlySkillToolset(
    skills=skills,
    additional_tools=[
        parse_gcs_resource,
        list_gcs_objects,
        preview_gcs_text_object,
        parse_bigquery_resource,
        list_bigquery_tables,
        inspect_bigquery_table,
        summarize_pipeline_alignment,
    ],
)

_TOOL_MAPPING_INSTRUCTION = """\
This agent uses native Python tools instead of shell scripts or a code executor.
When a skill's instructions reference scripts or comparison work, translate
them to the equivalent native tool:

{mapping_lines}

When `data-pipeline-triage` tells you to inspect GCS or BigQuery with subskills,
call `load_skill` for those subskills first, then use their mapped tools.
`run_skill_script` is not available.
""".format(
    mapping_lines=_format_mapping_lines(
        skill_toolset,
        arrow='->',
        width=34,
    )
)

root_agent = Agent(
    model='gemini-2.5-flash',
    name='claude_code_skills_cloud_hybrid',
    description=(
        'Agent that preserves original cloud skill text while replacing script '
        'execution with reviewed native tools.'
    ),
    instruction=_TOOL_MAPPING_INSTRUCTION,
    tools=[skill_toolset],
    planner=PlanReActPlanner(),
)
