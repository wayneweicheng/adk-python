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

"""Agent that loads Claude Code skills from a local directory and exposes them
via SkillToolset.

Directory layout expected under skills/:
    skills/
        <skill-name>/
            SKILL.md              # frontmatter (name, description) + instructions
            references/           # docs / examples the agent can read
            assets/               # templates or text files the agent can read
            scripts/
                my_script.py      # Python script — invoked via runpy
                my_script.sh      # Bash script  — invoked via subprocess bash

SKILL.md format (same as Claude Code skill files):
    ---
    name: my-skill-name       # kebab-case, must match directory name
    description: What it does # required, ≤1024 chars
    ---

    Step 1: ...
    Step 2: ...

Script notes:
  - .py  scripts receive CLI args as --key value (parsed via argparse)
  - .sh / .bash scripts also receive --key value arguments
  - Binary assets (images, etc.) are NOT supported locally — text files only
  - Scripts require a code_executor to be configured (see below)

WARNING: UnsafeLocalCodeExecutor executes code on the local machine without
sandboxing. Do NOT use in production. See ContainerCodeExecutor for a safer
alternative.
"""

import pathlib

from google.adk import Agent
from google.adk.code_executors.unsafe_local_code_executor import (
    UnsafeLocalCodeExecutor,
)
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset

# ── locate the skills/ directory next to this file ──────────────────────────
_SKILLS_DIR = pathlib.Path(__file__).parent / "skills"


def _load_all_skills():
    """Load every sub-directory inside skills/ as an ADK Skill."""
    skills = []
    for skill_dir in sorted(_SKILLS_DIR.iterdir()):
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            skills.append(load_skill_from_dir(skill_dir))
    return skills


skills = _load_all_skills()

# UnsafeLocalCodeExecutor is required for run_skill_script to work.
# It executes .py scripts via runpy and .sh/.bash scripts via subprocess.
skill_toolset = SkillToolset(
    skills=skills,
    code_executor=UnsafeLocalCodeExecutor(),
    script_timeout=60,  # seconds; applies to .sh/.bash scripts only
)

root_agent = Agent(
    model="gemini-2.5-flash",
    name="claude_code_skills_agent",
    description=(
        "An agent that can use Claude Code skills copied to the local"
        " skills/ directory."
    ),
    tools=[skill_toolset],
)
