# Production Guidance For Native Skill Agents

This sample demonstrates a production-oriented pattern for ADK skills:
skills remain instruction bundles, while the application exposes a small,
reviewed set of native tools for file inspection, linting, git context,
and controlled edits.

## Why this sample excludes `run_skill_script`

`run_skill_script` lets the model trigger executable Python or shell code
stored under a skill. That flexibility is useful for local experiments,
but it broadens the trust boundary significantly in production.

In this sample, the agent removes `run_skill_script` from the skill
toolset entirely and does not configure any code executor. Skills can only
call native tools that are explicitly registered by the application.

## Security risks of script-backed skills in production

1. Arbitrary code execution
A model-directed script runner can execute logic that reads files,
launches processes, or invokes additional tools. Even when the script
source is stored locally, the model still decides when and how to run it.

2. Secret exposure and credential misuse
Script execution often inherits ambient credentials, repository access,
network egress, and local filesystem visibility. That can expose `.env`
files, service account material, or other sensitive runtime state.

3. Command execution and shell expansion risk
Bash support is especially risky because shell behavior brings quoting,
pipelines, environment-variable expansion, and external binary
dependencies into the trust boundary.

4. Weak auditability
Reviewing a narrow native tool is much easier than reasoning about the
effective behavior of arbitrary scripts plus the execution environment
they run inside.

5. Higher platform burden
Dynamic script execution usually requires a sandbox or a hardened compute
boundary, plus additional IAM, network, quota, logging, and approval
work from platform teams.

## Why native tools are the recommended baseline

Native tools give the model a constrained API instead of a general code
runner. That has several practical benefits:

- Bounded capabilities: each tool does one reviewed operation.
- Better least privilege: file tools can enforce a single project root.
- Safer mutation flow: writes and git mutations can require approval.
- Easier testing: tools can be unit-tested like normal Python code.
- Easier maintenance: you update application code, not embedded scripts.
- Better observability: tool names and arguments are easier to log and review.

## Converting script-backed skills to native tools

The previous `code-review` sample used:

- a bash script for simple lint checks
- a Python script for basic complexity metrics

In this native sample, those become application tools:

- `lint_project_file`
- `count_python_complexity`

This is the preferred migration path for most production skills.

## Bash support in production

Do not treat bash as a first-class production skill primitive.

If a bash script only wraps deterministic logic such as line counting,
grep-like checks, or file copying, port that behavior into a Python tool.
If a bash script exists mainly to orchestrate external systems, replace it
with a dedicated application tool or backend service API.

## Notes on git-native tools

This sample includes native git tools for parity with the original
`commit` skill. They are still privileged operations and should normally
be limited to trusted internal users, approval-gated flows, or separate
administrative deployments.

For many production agents, it is better to back git mutations with an
internal service rather than allow direct repository writes from the agent.

## Future option: Agent Engine sandbox

Agent Engine sandbox execution may become a good fit for workloads that
truly require dynamic code execution, such as data-science workflows,
notebook-style analysis, or isolated transformation jobs.

Even then, it should be introduced deliberately:

- define which use cases actually need dynamic execution
- narrow network and identity permissions
- keep file access and data ingress explicit
- add observability, quota, and approval controls

The recommendation today is:

1. Start with native tools for production skills.
2. Add sandboxed execution later only for the specific capabilities that
   cannot be expressed cleanly as reviewed tools or services.
