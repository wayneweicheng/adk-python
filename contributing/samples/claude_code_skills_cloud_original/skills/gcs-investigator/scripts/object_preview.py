"""Preview a bounded text object from GCS."""

from __future__ import annotations

import argparse
from typing import Any

_TEXT_TYPES = (
    'application/json',
    'application/x-ndjson',
    'text/',
)


def preview_text_object(
    project_id: str,
    bucket_name: str,
    object_name: str,
    max_bytes: int = 4096,
) -> dict[str, Any]:
    try:
        from google.api_core import exceptions as api_exceptions
        from google.cloud import storage
    except ImportError as exc:
        return {'error': f'google-cloud-storage is not installed: {exc}'}

    try:
        client = storage.Client(project=project_id or None)
        blob = client.bucket(bucket_name).blob(object_name)
        blob.reload()
        content_type = blob.content_type or ''
        if not any(
            content_type == allowed or content_type.startswith(allowed)
            for allowed in _TEXT_TYPES
        ):
            return {
                'error': (
                    f'Object {object_name!r} has unsupported content type '
                    f'{content_type!r} for text preview'
                )
            }
        content = blob.download_as_bytes(start=0, end=max_bytes - 1)
        return {
            'project_id': project_id,
            'bucket_name': bucket_name,
            'object_name': object_name,
            'content_type': content_type,
            'size': blob.size,
            'preview': content.decode('utf-8', errors='replace'),
            'truncated': bool(blob.size and blob.size > max_bytes),
        }
    except api_exceptions.GoogleAPIError as exc:
        return {'error': f'GCS API error: {exc}'}
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return {'error': f'Unexpected GCS preview error: {exc}'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--project_id', required=True)
    parser.add_argument('--bucket_name', required=True)
    parser.add_argument('--object_name', required=True)
    parser.add_argument('--max_bytes', type=int, default=4096)
    args = parser.parse_args()
    print(
        preview_text_object(
            project_id=args.project_id,
            bucket_name=args.bucket_name,
            object_name=args.object_name,
            max_bytes=args.max_bytes,
        )
    )
