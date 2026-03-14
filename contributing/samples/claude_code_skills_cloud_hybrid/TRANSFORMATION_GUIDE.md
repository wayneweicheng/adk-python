# Transformation Guide: Original vs Hybrid Cloud Skills

This sample keeps both forms side by side:

- `original_skills/` shows how the skills would look when driven by
  `run_skill_script`
- `skills/` contains the transformed hybrid skills used by the runnable
  agent

## Skill 1: GCS Investigator

Original skill:

- `scripts/gcs_inventory.py`
- `scripts/object_preview.py`
- `scripts/normalize_gcs_uri.sh`

Hybrid transformation:

- `gcs_inventory.py` is imported as a module
- `object_preview.py` is imported as a module
- `normalize_gcs_uri.sh` becomes native tool `parse_gcs_resource`

Result:

- no shell execution
- no ADK code executor
- same logical capabilities through reviewed tool entry points

## Skill 2: BigQuery Catalog Review

Original skill:

- `scripts/list_dataset_tables.py`
- `scripts/table_profile.py`
- `scripts/parse_table_ref.sh`

Hybrid transformation:

- `list_dataset_tables.py` is imported as a module
- `table_profile.py` is imported as a module
- `parse_table_ref.sh` becomes native tool `parse_bigquery_resource`

Result:

- the substantial BigQuery inspection logic is reused
- parsing and normalization moves into the agent boundary

## Skill 3: Data Pipeline Triage

Original skill:

- instruction-driven orchestration over the script-backed GCS and BigQuery skills
- optional shell formatting helpers

Hybrid transformation:

- the skill now orchestrates native/hybrid tools only
- cross-resource comparison uses native tool `summarize_pipeline_alignment`

## Agent changes

Original conceptual model:

- skill instructions + `run_skill_script`
- cloud helper scripts executed by a code executor

Hybrid model:

- skill instructions + native reviewed tools
- selected Python helpers imported with `importlib`
- no code executor
- centralized validation for resource refs and local file access

## Why this is a stronger production shape

The model never chooses a script path to execute. It only calls approved
tool functions with typed inputs. That gives you a much tighter audit and
policy boundary while preserving most of the original helper logic.
