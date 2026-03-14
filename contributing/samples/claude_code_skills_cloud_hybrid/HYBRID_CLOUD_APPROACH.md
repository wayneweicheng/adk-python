# Hybrid Cloud Skills Approach

This sample demonstrates the hybrid pattern on more realistic cloud
workflows than the earlier toy skill examples.

The design goal is to keep the production advantages of native tools while
reducing rewrite cost when you already have trustworthy Python helpers.

## What makes this sample more realistic

The skills work with real cloud resource concepts:

- GCS buckets, prefixes, object metadata, and text previews
- BigQuery datasets, table listings, schemas, labels, and partitioning
- cross-resource triage for ingestion pipeline debugging

## Why the hybrid pattern still works here

The cloud-facing Python helpers are read-only and structured. They already
expose callable functions with meaningful inputs and outputs. That makes
them good candidates to import as modules instead of executing them via
`run_skill_script`.

The bash helpers in the original skills mostly parse resource references.
Those are better expressed as native Python utilities in the agent.

## Production boundary

The runnable agent:

- does not configure a code executor
- hides `run_skill_script`
- exposes only reviewed native tool entry points
- uses lazy `google.cloud` imports so import-time verification remains cheap
- centralizes path and secret guardrails in one place

## When the hybrid model is a good fit

Use it when:

- you already have useful read-only Python helper scripts
- the helpers have stable callable functions
- you want to avoid a full native rewrite immediately
- you still need a strong production posture

## When full native or service-backed tools are better

Prefer a full native tool or service boundary when:

- the helper performs mutations
- the helper shells out to other tools
- the helper has broad filesystem or network side effects
- you need strict auditability, policy enforcement, or per-call approval

## Future path

Agent Engine sandbox could still make sense later for cases where dynamic
code execution is genuinely needed, but this sample shows that a large
class of cloud investigation skills can stay out of that category.
