"""Inspect schema, partitioning, clustering, and labels for a BigQuery table."""

from __future__ import annotations

import argparse
from typing import Any


def _schema_summary(schema_fields: list[Any]) -> list[dict[str, Any]]:
    summary = []
    for field in schema_fields:
        summary.append(
            {
                'name': field.name,
                'field_type': field.field_type,
                'mode': field.mode,
                'description': field.description,
                'subfields': _schema_summary(field.fields) if field.fields else [],
            }
        )
    return summary


def inspect_table(
    project_id: str,
    dataset_id: str,
    table_id: str,
) -> dict[str, Any]:
    try:
        from google.api_core import exceptions as api_exceptions
        from google.cloud import bigquery
    except ImportError as exc:
        return {'error': f'google-cloud-bigquery is not installed: {exc}'}

    try:
        client = bigquery.Client(project=project_id or None)
        table_ref = bigquery.DatasetReference(project_id, dataset_id).table(table_id)
        table = client.get_table(table_ref)
        return {
            'project_id': project_id,
            'dataset_id': dataset_id,
            'table_id': table.table_id,
            'full_table_id': table.full_table_id,
            'num_rows': table.num_rows,
            'num_bytes': table.num_bytes,
            'table_type': table.table_type,
            'location': table.location,
            'partition_field': (
                table.time_partitioning.field
                if table.time_partitioning and table.time_partitioning.field
                else None
            ),
            'partition_type': (
                str(table.time_partitioning.type_)
                if table.time_partitioning and table.time_partitioning.type_
                else None
            ),
            'clustering_fields': list(table.clustering_fields or []),
            'labels': table.labels or {},
            'schema': _schema_summary(list(table.schema)),
        }
    except api_exceptions.GoogleAPIError as exc:
        return {'error': f'BigQuery API error: {exc}'}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {'error': f'Unexpected BigQuery table inspection error: {exc}'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project_id', required=True)
    parser.add_argument('--dataset_id', required=True)
    parser.add_argument('--table_id', required=True)
    args = parser.parse_args()
    print(
        inspect_table(
            project_id=args.project_id,
            dataset_id=args.dataset_id,
            table_id=args.table_id,
        )
    )
