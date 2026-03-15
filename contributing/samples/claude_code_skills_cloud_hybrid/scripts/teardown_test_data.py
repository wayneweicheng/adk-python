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

"""Remove GCS objects and BigQuery dataset created by setup_test_data.py.

Usage:
    python teardown_test_data.py --project ark-of-data-2000
    python teardown_test_data.py --project ark-of-data-2000 --delete-bucket
"""

from __future__ import annotations

import argparse
import logging
import sys

from google.cloud import bigquery
from google.cloud import storage

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
logger = logging.getLogger(__name__)

GCS_PREFIX = 'sales/2026-03-14/'
DATASET_ID = 'acme_warehouse'


def _default_bucket(project: str) -> str:
    return f'acme-data-lake-{project}'


def teardown_gcs(project: str, bucket_name: str, delete_bucket: bool) -> None:
    """Delete test objects and optionally the bucket."""
    client = storage.Client(project=project)

    try:
        bucket = client.get_bucket(bucket_name)
    except Exception:
        logger.info('Bucket gs://%s does not exist, nothing to clean up.', bucket_name)
        return

    blobs = list(bucket.list_blobs(prefix=GCS_PREFIX))
    if blobs:
        for blob in blobs:
            blob.delete()
            logger.info('Deleted gs://%s/%s', bucket_name, blob.name)
        logger.info('Deleted %d objects from gs://%s/%s', len(blobs), bucket_name, GCS_PREFIX)
    else:
        logger.info('No objects found under gs://%s/%s', bucket_name, GCS_PREFIX)

    if delete_bucket:
        remaining = list(bucket.list_blobs(max_results=1))
        if remaining:
            logger.warning(
                'Bucket gs://%s still has other objects. Skipping bucket deletion.',
                bucket_name,
            )
        else:
            bucket.delete()
            logger.info('Deleted bucket gs://%s.', bucket_name)


def teardown_bigquery(project: str) -> None:
    """Delete the BigQuery dataset and all its tables."""
    client = bigquery.Client(project=project)
    dataset_ref = bigquery.DatasetReference(project, DATASET_ID)

    try:
        client.get_dataset(dataset_ref)
    except Exception:
        logger.info('Dataset %s.%s does not exist, nothing to clean up.', project, DATASET_ID)
        return

    client.delete_dataset(dataset_ref, delete_contents=True, not_found_ok=True)
    logger.info('Deleted dataset %s.%s and all its contents.', project, DATASET_ID)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Tear down GCS and BigQuery test data created by setup_test_data.py.',
    )
    parser.add_argument(
        '--project',
        default='ark-of-data-2000',
        help='GCP project ID (default: ark-of-data-2000)',
    )
    parser.add_argument(
        '--bucket',
        default=None,
        help='GCS bucket name (default: acme-data-lake-<project>)',
    )
    parser.add_argument(
        '--delete-bucket',
        action='store_true',
        help='Also delete the GCS bucket if empty after removing test objects.',
    )
    parser.add_argument(
        '--gcs-only',
        action='store_true',
        help='Only tear down GCS objects, skip BigQuery.',
    )
    parser.add_argument(
        '--bq-only',
        action='store_true',
        help='Only tear down BigQuery dataset, skip GCS.',
    )
    args = parser.parse_args()

    if args.gcs_only and args.bq_only:
        logger.error('Cannot use both --gcs-only and --bq-only.')
        sys.exit(1)

    bucket_name = args.bucket or _default_bucket(args.project)

    if not args.bq_only:
        teardown_gcs(args.project, bucket_name, args.delete_bucket)
    if not args.gcs_only:
        teardown_bigquery(args.project)

    logger.info('Teardown complete.')


if __name__ == '__main__':
    main()
