# Data Pipeline Triage Playbook

- Confirm the landing prefix contains data for the expected incident window
- Check whether object names imply a destination table or entity grouping
- Compare those names with actual BigQuery tables in the target dataset
- If the table exists, inspect partitioning and schema for compatibility clues
- If the table does not exist, call that out explicitly as a possible deployment gap
- End with the next 2-3 highest-signal investigation actions
