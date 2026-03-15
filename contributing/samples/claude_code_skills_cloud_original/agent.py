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

"""Cloud-skills sample that runs the original script-backed skills as-is.

This sample wires the unmodified cloud skills to `UnsafeLocalCodeExecutor` for
trusted local development only. It is intentionally not suitable for production
because skill scripts execute directly on the local machine.
"""

from __future__ import annotations

import logging
from pathlib import Path

from google.adk import Agent
from google.adk.code_executors.unsafe_local_code_executor import (
    UnsafeLocalCodeExecutor,
)
from google.adk.tools.skill_toolset import SkillToolset

logger = logging.getLogger(__name__)

_AGENT_DIR = Path(__file__).resolve().parent
_SKILLS_DIR = _AGENT_DIR / 'skills'


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


skills = _load_all_skills()
skill_toolset = SkillToolset(
    skills=skills,
    code_executor=UnsafeLocalCodeExecutor(),
)

root_agent = Agent(
    model='gemini-2.5-flash',
    name='claude_code_skills_cloud_original',
    description=(
        'Agent that runs the original cloud Claude Code skills with an '
        'UnsafeLocalCodeExecutor.'
    ),
    tools=[skill_toolset],
)
