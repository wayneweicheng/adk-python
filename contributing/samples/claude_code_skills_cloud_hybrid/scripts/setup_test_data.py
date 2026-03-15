#!/usr/bin/env python3
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

"""Create GCS objects and BigQuery tables for testing the cloud hybrid agent.

This script sets up a realistic "stalled pipeline" scenario:
  - GCS: 5 files landed in gs://acme-data-lake/sales/2026-03-14/
  - BigQuery: tables exist with older data but NO rows for 2026-03-14

Usage:
    python setup_test_data.py --project ark-of-data-2000
    python setup_test_data.py --project ark-of-data-2000 --location US
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys

from google.cloud import bigquery
from google.cloud import storage

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────

# GCS bucket names are globally unique. The default includes the project ID
# to avoid conflicts. Override with --bucket if needed.
def _default_bucket(project: str) -> str:
    return f'acme-data-lake-{project}'

GCS_PREFIX = 'sales/2026-03-14/'
DATASET_ID = 'acme_warehouse'

# ── GCS test data ────────────────────────────────────────────────────────────

TRANSACTIONS_001 = '\n'.join(
    json.dumps(row)
    for row in [
        {
            'transaction_id': 'TXN-20260314-0001',
            'sale_date': '2026-03-14',
            'store_id': 'STORE-042',
            'item_sku': 'SKU-1001',
            'quantity': 2,
            'unit_price': 29.99,
            'currency': 'USD',
        },
        {
            'transaction_id': 'TXN-20260314-0002',
            'sale_date': '2026-03-14',
            'store_id': 'STORE-042',
            'item_sku': 'SKU-2050',
            'quantity': 1,
            'unit_price': 149.00,
            'currency': 'USD',
        },
        {
            'transaction_id': 'TXN-20260314-0003',
            'sale_date': '2026-03-14',
            'store_id': 'STORE-007',
            'item_sku': 'SKU-1001',
            'quantity': 5,
            'unit_price': 29.99,
            'currency': 'USD',
        },
    ]
) + '\n'

TRANSACTIONS_002 = '\n'.join(
    json.dumps(row)
    for row in [
        {
            'transaction_id': 'TXN-20260314-0004',
            'sale_date': '2026-03-14',
            'store_id': 'STORE-118',
            'item_sku': 'SKU-3300',
            'quantity': 1,
            'unit_price': 499.95,
            'currency': 'USD',
        },
        {
            'transaction_id': 'TXN-20260314-0005',
            'sale_date': '2026-03-14',
            'store_id': 'STORE-007',
            'item_sku': 'SKU-2050',
            'quantity': 3,
            'unit_price': 149.00,
            'currency': 'USD',
        },
    ]
) + '\n'

RETURNS_001 = json.dumps(
    {
        'returns': [
            {
                'return_id': 'RET-20260314-001',
                'transaction_id': 'TXN-20260313-0010',
                'return_date': '2026-03-14',
                'store_id': 'STORE-042',
                'item_sku': 'SKU-1001',
                'quantity': 1,
                'reason': 'defective',
            },
            {
                'return_id': 'RET-20260314-002',
                'transaction_id': 'TXN-20260313-0022',
                'return_date': '2026-03-14',
                'store_id': 'STORE-118',
                'item_sku': 'SKU-3300',
                'quantity': 1,
                'reason': 'wrong_size',
            },
        ]
    },
    indent=2,
) + '\n'

CUSTOMERS_UPDATE = (
    'customer_id,name,email,segment,updated_at\n'
    'CUST-5001,Alice Zhang,alice@example.com,enterprise,2026-03-14T02:15:00Z\n'
    'CUST-5002,Bob Martinez,bob@example.com,smb,2026-03-14T02:15:00Z\n'
    'CUST-5003,Carol Osei,carol@example.com,enterprise,2026-03-14T02:15:00Z\n'
)

MANIFEST = json.dumps(
    {
        'pipeline_run_id': 'run-20260314-nightly',
        'expected_files': [
            'transactions_001.ndjson',
            'transactions_002.ndjson',
            'returns_001.json',
            'customers_update.csv',
        ],
        'status': 'delivered',
        'delivered_at': '2026-03-14T03:45:12Z',
    },
    indent=2,
) + '\n'

GCS_OBJECTS: list[tuple[str, str, str]] = [
    ('transactions_001.ndjson', 'application/x-ndjson', TRANSACTIONS_001),
    ('transactions_002.ndjson', 'application/x-ndjson', TRANSACTIONS_002),
    ('returns_001.json', 'application/json', RETURNS_001),
    ('customers_update.csv', 'text/csv', CUSTOMERS_UPDATE),
    ('_manifest.json', 'application/json', MANIFEST),
]

# ── BigQuery schemas ─────────────────────────────────────────────────────────

SALES_RAW_SCHEMA = [
    bigquery.SchemaField('transaction_id', 'STRING', mode='REQUIRED'),
    bigquery.SchemaField('sale_date', 'DATE', mode='REQUIRED'),
    bigquery.SchemaField('store_id', 'STRING'),
    bigquery.SchemaField('item_sku', 'STRING'),
    bigquery.SchemaField('quantity', 'INTEGER'),
    bigquery.SchemaField('unit_price', 'FLOAT'),
    bigquery.SchemaField('currency', 'STRING'),
    bigquery.SchemaField('ingested_at', 'TIMESTAMP'),
]

RETURNS_RAW_SCHEMA = [
    bigquery.SchemaField('return_id', 'STRING', mode='REQUIRED'),
    bigquery.SchemaField('transaction_id', 'STRING'),
    bigquery.SchemaField('return_date', 'DATE', mode='REQUIRED'),
    bigquery.SchemaField('store_id', 'STRING'),
    bigquery.SchemaField('item_sku', 'STRING'),
    bigquery.SchemaField('quantity', 'INTEGER'),
    bigquery.SchemaField('reason', 'STRING'),
    bigquery.SchemaField('ingested_at', 'TIMESTAMP'),
]

CUSTOMERS_SCHEMA = [
    bigquery.SchemaField('customer_id', 'STRING', mode='REQUIRED'),
    bigquery.SchemaField('name', 'STRING'),
    bigquery.SchemaField('email', 'STRING'),
    bigquery.SchemaField('segment', 'STRING'),
    bigquery.SchemaField('updated_at', 'TIMESTAMP'),
]

# Rows for 2026-03-13 only — the agent should notice 2026-03-14 is missing.
SALES_RAW_ROWS = [
    {
        'transaction_id': 'TXN-20260313-0001',
        'sale_date': '2026-03-13',
        'store_id': 'STORE-042',
        'item_sku': 'SKU-1001',
        'quantity': 4,
        'unit_price': 29.99,
        'currency': 'USD',
        'ingested_at': '2026-03-13T04:10:00Z',
    },
    {
        'transaction_id': 'TXN-20260313-0010',
        'sale_date': '2026-03-13',
        'store_id': 'STORE-042',
        'item_sku': 'SKU-2050',
        'quantity': 1,
        'unit_price': 149.00,
        'currency': 'USD',
        'ingested_at': '2026-03-13T04:10:00Z',
    },
    {
        'transaction_id': 'TXN-20260313-0022',
        'sale_date': '2026-03-13',
        'store_id': 'STORE-118',
        'item_sku': 'SKU-3300',
        'quantity': 2,
        'unit_price': 499.95,
        'currency': 'USD',
        'ingested_at': '2026-03-13T04:10:00Z',
    },
]

RETURNS_RAW_ROWS = [
    {
        'return_id': 'RET-20260313-001',
        'transaction_id': 'TXN-20260312-0005',
        'return_date': '2026-03-13',
        'store_id': 'STORE-007',
        'item_sku': 'SKU-1001',
        'quantity': 1,
        'reason': 'changed_mind',
        'ingested_at': '2026-03-13T04:10:00Z',
    },
]

CUSTOMERS_ROWS = [
    {
        'customer_id': 'CUST-5001',
        'name': 'Alice Zhang',
        'email': 'alice@example.com',
        'segment': 'enterprise',
        'updated_at': '2026-03-13T02:00:00Z',
    },
    {
        'customer_id': 'CUST-5002',
        'name': 'Bob Martinez',
        'email': 'bob@example.com',
        'segment': 'smb',
        'updated_at': '2026-03-13T02:00:00Z',
    },
]


# ── Setup functions ──────────────────────────────────────────────────────────


def setup_gcs(project: str, bucket_name: str) -> None:
    """Create the GCS bucket (if needed) and upload test objects."""
    client = storage.Client(project=project)

    try:
        bucket = client.get_bucket(bucket_name)
        logger.info('Bucket gs://%s already exists.', bucket_name)
    except Exception:
        bucket = client.create_bucket(bucket_name, location='US')
        logger.info('Created bucket gs://%s.', bucket_name)

    for name, content_type, content in GCS_OBJECTS:
        object_name = f'{GCS_PREFIX}{name}'
        blob = bucket.blob(object_name)
        blob.upload_from_file(
            io.BytesIO(content.encode('utf-8')),
            content_type=content_type,
        )
        logger.info(
            'Uploaded gs://%s/%s (%d bytes, %s)',
            bucket_name,
            object_name,
            len(content.encode('utf-8')),
            content_type,
        )

    logger.info('GCS setup complete: %d objects uploaded.', len(GCS_OBJECTS))


def setup_bigquery(project: str, location: str) -> None:
    """Create the BigQuery dataset, tables, view, and insert sample rows."""
    client = bigquery.Client(project=project)

    dataset_ref = bigquery.DatasetReference(project, DATASET_ID)
    dataset = bigquery.Dataset(dataset_ref)
    dataset.location = location
    dataset.description = 'Acme warehouse for sales pipeline testing.'
    dataset = client.create_dataset(dataset, exists_ok=True)
    logger.info('Dataset %s.%s ready.', project, DATASET_ID)

    # ── sales_raw ────────────────────────────────────────────────────────
    sales_table_ref = dataset_ref.table('sales_raw')
    sales_table = bigquery.Table(sales_table_ref, schema=SALES_RAW_SCHEMA)
    sales_table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field='sale_date',
    )
    sales_table.clustering_fields = ['store_id']
    sales_table.labels = {'pipeline': 'nightly-ingest', 'env': 'test'}
    sales_table.friendly_name = 'Raw Sales Transactions'
    sales_table.description = (
        'Ingested nightly from gs://acme-data-lake/sales/<date>/transactions_*.ndjson'
    )
    client.create_table(sales_table, exists_ok=True)
    logger.info('Table %s.%s.sales_raw ready.', project, DATASET_ID)

    errors = client.insert_rows_json(
        f'{project}.{DATASET_ID}.sales_raw', SALES_RAW_ROWS
    )
    if errors:
        logger.error('Error inserting sales_raw rows: %s', errors)
    else:
        logger.info('Inserted %d rows into sales_raw.', len(SALES_RAW_ROWS))

    # ── returns_raw ──────────────────────────────────────────────────────
    returns_table_ref = dataset_ref.table('returns_raw')
    returns_table = bigquery.Table(returns_table_ref, schema=RETURNS_RAW_SCHEMA)
    returns_table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field='return_date',
    )
    returns_table.clustering_fields = ['store_id']
    returns_table.labels = {'pipeline': 'nightly-ingest', 'env': 'test'}
    returns_table.friendly_name = 'Raw Returns'
    returns_table.description = (
        'Ingested nightly from gs://acme-data-lake/sales/<date>/returns_*.json'
    )
    client.create_table(returns_table, exists_ok=True)
    logger.info('Table %s.%s.returns_raw ready.', project, DATASET_ID)

    errors = client.insert_rows_json(
        f'{project}.{DATASET_ID}.returns_raw', RETURNS_RAW_ROWS
    )
    if errors:
        logger.error('Error inserting returns_raw rows: %s', errors)
    else:
        logger.info('Inserted %d rows into returns_raw.', len(RETURNS_RAW_ROWS))

    # ── customers ────────────────────────────────────────────────────────
    customers_table_ref = dataset_ref.table('customers')
    customers_table = bigquery.Table(
        customers_table_ref, schema=CUSTOMERS_SCHEMA
    )
    customers_table.labels = {'domain': 'crm', 'env': 'test'}
    customers_table.friendly_name = 'Customer Dimension'
    customers_table.description = 'Customer master data updated from CRM exports.'
    client.create_table(customers_table, exists_ok=True)
    logger.info('Table %s.%s.customers ready.', project, DATASET_ID)

    errors = client.insert_rows_json(
        f'{project}.{DATASET_ID}.customers', CUSTOMERS_ROWS
    )
    if errors:
        logger.error('Error inserting customers rows: %s', errors)
    else:
        logger.info('Inserted %d rows into customers.', len(CUSTOMERS_ROWS))

    # ── daily_summary (view) ─────────────────────────────────────────────
    view_ref = dataset_ref.table('daily_summary')
    view = bigquery.Table(view_ref)
    view.view_query = (
        f'SELECT sale_date, store_id, COUNT(*) AS txn_count, '
        f'SUM(quantity * unit_price) AS gross_revenue '
        f'FROM `{project}.{DATASET_ID}.sales_raw` '
        f'GROUP BY sale_date, store_id'
    )
    view.friendly_name = 'Daily Sales Summary'
    view.description = 'Aggregated daily sales by store.'
    client.create_table(view, exists_ok=True)
    logger.info('View %s.%s.daily_summary ready.', project, DATASET_ID)

    logger.info('BigQuery setup complete.')


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Set up GCS and BigQuery test data for the cloud hybrid agent.',
    )
    parser.add_argument(
        '--project',
        default='ark-of-data-2000',
        help='GCP project ID (default: ark-of-data-2000)',
    )
    parser.add_argument(
        '--bucket',
        default=None,
        help=(
            'GCS bucket name (default: acme-data-lake-<project>). '
            'GCS bucket names are globally unique, so the default includes '
            'your project ID to avoid conflicts.'
        ),
    )
    parser.add_argument(
        '--location',
        default='US',
        help='BigQuery dataset location (default: US)',
    )
    parser.add_argument(
        '--gcs-only',
        action='store_true',
        help='Only set up GCS objects, skip BigQuery.',
    )
    parser.add_argument(
        '--bq-only',
        action='store_true',
        help='Only set up BigQuery tables, skip GCS.',
    )
    args = parser.parse_args()

    if args.gcs_only and args.bq_only:
        logger.error('Cannot use both --gcs-only and --bq-only.')
        sys.exit(1)

    bucket_name = args.bucket or _default_bucket(args.project)

    if not args.bq_only:
        setup_gcs(args.project, bucket_name)
    if not args.gcs_only:
        setup_bigquery(args.project, args.location)

    logger.info('Done. Test data is ready for the cloud hybrid agent.')
    logger.info('')
    logger.info('Recommended agent prompt:')
    logger.info(
        '  "Our nightly ingestion pipeline for gs://%s/sales/2026-03-14/'
        ' into BigQuery dataset acme_warehouse.sales_raw appears to have stalled.'
        ' No new rows showed up this morning. Investigate the GCS landing zone'
        ' and the BigQuery target, figure out what went wrong, and recommend'
        ' next steps."',
        bucket_name,
    )
    logger.info('')
    logger.info('Environment setup:')
    logger.info('  export CLOUD_HYBRID_DEFAULT_PROJECT=%s', args.project)


if __name__ == '__main__':
    main()
