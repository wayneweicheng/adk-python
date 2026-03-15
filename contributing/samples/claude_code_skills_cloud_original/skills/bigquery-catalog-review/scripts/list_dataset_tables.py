"""List dataset tables and key metadata from BigQuery."""

from __future__ import annotations

import argparse
from typing import Any


def list_dataset_tables(
    project_id: str,
    dataset_id: str,
    include_views: bool = True,
    max_results: int = 50,
) -> dict[str, Any]:
    try:
        from google.api_core import exceptions as api_exceptions
        from google.cloud import bigquery
    except ImportError as exc:
        return {'error': f'google-cloud-bigquery is not installed: {exc}'}

    try:
        client = bigquery.Client(project=project_id or None)
        dataset_ref = bigquery.DatasetReference(project_id, dataset_id)
        tables_iter = client.list_tables(dataset_ref, max_results=max_results)
        tables = []
        for item in tables_iter:
            table_type = item.table_type or 'TABLE'
            if not include_views and table_type.upper() == 'VIEW':
                continue
            tables.append(
                {
                    'table_id': item.table_id,
                    'full_table_id': item.full_table_id,
                    'table_type': table_type,
                    'friendly_name': item.friendly_name,
                    'labels': item.labels or {},
                }
            )
        return {
            'project_id': project_id,
            'dataset_id': dataset_id,
            'table_count': len(tables),
            'tables': tables,
        }
    except api_exceptions.GoogleAPIError as exc:
        return {'error': f'BigQuery API error: {exc}'}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {'error': f'Unexpected BigQuery dataset listing error: {exc}'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project_id', required=True)
    parser.add_argument('--dataset_id', required=True)
    parser.add_argument('--include_views', default='true')
    parser.add_argument('--max_results', type=int, default=50)
    args = parser.parse_args()
    print(
        list_dataset_tables(
            project_id=args.project_id,
            dataset_id=args.dataset_id,
            include_views=args.include_views.lower() == 'true',
            max_results=args.max_results,
        )
    )
