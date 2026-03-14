"""List bounded GCS object metadata for an investigation workflow."""

from __future__ import annotations

import argparse
from typing import Any


def list_objects(
    project_id: str,
    bucket_name: str,
    prefix: str = '',
    max_results: int = 25,
) -> dict[str, Any]:
    try:
        from google.api_core import exceptions as api_exceptions
        from google.cloud import storage
    except ImportError as exc:
        return {'error': f'google-cloud-storage is not installed: {exc}'}

    try:
        client = storage.Client(project=project_id or None)
        blobs_iter = client.list_blobs(
            bucket_name,
            prefix=prefix,
            max_results=max_results,
        )
        blobs = []
        for blob in blobs_iter:
            blobs.append(
                {
                    'name': blob.name,
                    'size': blob.size,
                    'content_type': blob.content_type,
                    'updated': blob.updated.isoformat() if blob.updated else None,
                    'generation': blob.generation,
                    'md5_hash': blob.md5_hash,
                    'metadata_keys': sorted((blob.metadata or {}).keys()),
                }
            )
        return {
            'project_id': project_id,
            'bucket_name': bucket_name,
            'prefix': prefix,
            'object_count': len(blobs),
            'objects': blobs,
        }
    except api_exceptions.GoogleAPIError as exc:
        return {'error': f'GCS API error: {exc}'}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {'error': f'Unexpected GCS inventory error: {exc}'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project_id', required=True)
    parser.add_argument('--bucket_name', required=True)
    parser.add_argument('--prefix', default='')
    parser.add_argument('--max_results', type=int, default=25)
    args = parser.parse_args()
    print(
        list_objects(
            project_id=args.project_id,
            bucket_name=args.bucket_name,
            prefix=args.prefix,
            max_results=args.max_results,
        )
    )
