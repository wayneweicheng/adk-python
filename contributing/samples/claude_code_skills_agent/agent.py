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

Runtime configuration:
  - Set ADK_SKILLS_CODE_EXECUTOR=unsafe-local for local-only development.
  - Set ADK_SKILLS_CODE_EXECUTOR=container and ADK_SKILLS_CONTAINER_IMAGE (or
    ADK_SKILLS_CONTAINER_DOCKER_PATH) to run scripts inside a container.
  - Set ADK_SKILLS_CODE_EXECUTOR=gke to execute scripts in a GKE sandboxed Job.
  - Set ADK_SKILLS_CODE_EXECUTOR=agent-engine-sandbox to execute scripts in an
    Agent Engine sandbox.
  - Leave ADK_SKILLS_CODE_EXECUTOR unset or set it to disabled to turn off
    skill script execution entirely.
"""

import logging
import os
import pathlib

from google.adk import Agent
from google.adk.tools.skill_toolset import SkillToolset

logger = logging.getLogger(__name__)

_AGENT_DIR = pathlib.Path(__file__).resolve().parent
_SKILLS_DIR = _AGENT_DIR / "skills"
_PROJECT_ROOT_ENV = "ADK_SKILLS_PROJECT_ROOT"
_EXECUTOR_MODE_ENV = "ADK_SKILLS_CODE_EXECUTOR"
_SCRIPT_TIMEOUT_ENV = "ADK_SKILLS_SCRIPT_TIMEOUT"
_CONTAINER_IMAGE_ENV = "ADK_SKILLS_CONTAINER_IMAGE"
_CONTAINER_DOCKER_PATH_ENV = "ADK_SKILLS_CONTAINER_DOCKER_PATH"
_CONTAINER_BASE_URL_ENV = "ADK_SKILLS_CONTAINER_BASE_URL"
_GKE_NAMESPACE_ENV = "ADK_SKILLS_GKE_NAMESPACE"
_GKE_IMAGE_ENV = "ADK_SKILLS_GKE_IMAGE"
_GKE_TIMEOUT_ENV = "ADK_SKILLS_GKE_TIMEOUT_SECONDS"
_GKE_EXECUTOR_TYPE_ENV = "ADK_SKILLS_GKE_EXECUTOR_TYPE"
_GKE_KUBECONFIG_PATH_ENV = "ADK_SKILLS_GKE_KUBECONFIG_PATH"
_GKE_KUBECONFIG_CONTEXT_ENV = "ADK_SKILLS_GKE_KUBECONFIG_CONTEXT"
_AGENT_ENGINE_RESOURCE_ENV = "ADK_SKILLS_AGENT_ENGINE_RESOURCE_NAME"
_SANDBOX_RESOURCE_ENV = "ADK_SKILLS_SANDBOX_RESOURCE_NAME"


def _find_project_root(start_dir: pathlib.Path) -> pathlib.Path:
    """Find the repository root used to resolve relative file paths."""
    for candidate in (start_dir, *start_dir.parents):
        if (candidate / ".git").exists() or (candidate / "pyproject.toml").exists():
            return candidate
    return start_dir


def _load_skill_from_dir(skill_dir: pathlib.Path):
    """Load a skill lazily so import errors don't break module import."""
    try:
        from google.adk.skills import load_skill_from_dir
    except ImportError as exc:
        raise RuntimeError(
            "google-adk does not expose load_skill_from_dir. "
            "Use the repo's virtualenv or install the local adk-python checkout."
        ) from exc
    return load_skill_from_dir(skill_dir)


def _load_all_skills():
    """Load every sub-directory inside skills/ as an ADK Skill."""
    if not _SKILLS_DIR.exists():
        logger.warning("Skills directory does not exist: %s", _SKILLS_DIR)
        return []

    skills = []
    for skill_dir in sorted(_SKILLS_DIR.iterdir()):
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            try:
                skills.append(_load_skill_from_dir(skill_dir))
            except Exception:
                logger.exception("Skipping invalid skill directory: %s", skill_dir)
    if not skills:
        logger.warning("No skills were loaded from %s", _SKILLS_DIR)
    return skills


def _get_script_timeout() -> int:
    raw_timeout = os.getenv(_SCRIPT_TIMEOUT_ENV, "60")
    try:
        return int(raw_timeout)
    except ValueError:
        logger.warning(
            "Invalid %s value %r. Falling back to 60 seconds.",
            _SCRIPT_TIMEOUT_ENV,
            raw_timeout,
        )
        return 60


def _build_code_executor():
    """Create the configured code executor for skill scripts."""
    executor_mode = os.getenv(_EXECUTOR_MODE_ENV, "disabled").strip().lower()

    if executor_mode in {"", "disabled", "none"}:
        logger.info(
            "Skill script execution is disabled. Set %s=unsafe-local for local "
            "development or %s=container for a containerized executor.",
            _EXECUTOR_MODE_ENV,
            _EXECUTOR_MODE_ENV,
        )
        return None

    if executor_mode == "unsafe-local":
        from google.adk.code_executors.unsafe_local_code_executor import (
            UnsafeLocalCodeExecutor,
        )

        logger.warning(
            "Using UnsafeLocalCodeExecutor. This is only appropriate for trusted "
            "local development."
        )
        return UnsafeLocalCodeExecutor()

    if executor_mode == "container":
        from google.adk.code_executors.container_code_executor import (
            ContainerCodeExecutor,
        )

        image = os.getenv(_CONTAINER_IMAGE_ENV)
        docker_path = os.getenv(_CONTAINER_DOCKER_PATH_ENV)
        if not image and not docker_path:
            logger.error(
                "Container executor requested but neither %s nor %s is set. "
                "Script execution will remain disabled.",
                _CONTAINER_IMAGE_ENV,
                _CONTAINER_DOCKER_PATH_ENV,
            )
            return None

        try:
            return ContainerCodeExecutor(
                base_url=os.getenv(_CONTAINER_BASE_URL_ENV),
                image=image,
                docker_path=docker_path,
            )
        except Exception:
            logger.exception("Failed to initialize ContainerCodeExecutor.")
            return None

    if executor_mode == "gke":
        from google.adk.code_executors.gke_code_executor import GkeCodeExecutor

        try:
            return GkeCodeExecutor(
                namespace=os.getenv(_GKE_NAMESPACE_ENV, "default"),
                image=os.getenv(_GKE_IMAGE_ENV, "python:3.11-slim"),
                timeout_seconds=_get_int_env(_GKE_TIMEOUT_ENV, 300),
                executor_type=os.getenv(_GKE_EXECUTOR_TYPE_ENV, "job"),
                kubeconfig_path=os.getenv(_GKE_KUBECONFIG_PATH_ENV),
                kubeconfig_context=os.getenv(_GKE_KUBECONFIG_CONTEXT_ENV),
            )
        except Exception:
            logger.exception("Failed to initialize GkeCodeExecutor.")
            return None

    if executor_mode == "agent-engine-sandbox":
        from google.adk.code_executors.agent_engine_sandbox_code_executor import (
            AgentEngineSandboxCodeExecutor,
        )

        sandbox_resource_name = os.getenv(_SANDBOX_RESOURCE_ENV)
        agent_engine_resource_name = os.getenv(_AGENT_ENGINE_RESOURCE_ENV)
        if not sandbox_resource_name and not agent_engine_resource_name:
            logger.error(
                "Agent Engine sandbox executor requested but neither %s nor %s "
                "is set. Script execution will remain disabled.",
                _SANDBOX_RESOURCE_ENV,
                _AGENT_ENGINE_RESOURCE_ENV,
            )
            return None

        try:
            return AgentEngineSandboxCodeExecutor(
                sandbox_resource_name=sandbox_resource_name,
                agent_engine_resource_name=agent_engine_resource_name,
            )
        except Exception:
            logger.exception("Failed to initialize AgentEngineSandboxCodeExecutor.")
            return None

    logger.error(
        "Unsupported %s value %r. Script execution will remain disabled.",
        _EXECUTOR_MODE_ENV,
        executor_mode,
    )
    return None


def _get_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except ValueError:
        logger.warning("Invalid %s value %r. Falling back to %d.", name, raw_value, default)
        return default


os.environ.setdefault(_PROJECT_ROOT_ENV, str(_find_project_root(_AGENT_DIR)))

skills = _load_all_skills()
skill_toolset = SkillToolset(
    skills=skills,
    code_executor=_build_code_executor(),
    script_timeout=_get_script_timeout(),
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
