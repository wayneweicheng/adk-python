        #!/usr/bin/env bash
        # Usage: normalize_gcs_uri.sh --resource gs://bucket/prefix

        set -euo pipefail

        RESOURCE=""
        while [[ $# -gt 0 ]]; do
          case "$1" in
            --resource) RESOURCE="$2"; shift 2 ;;
            *) shift ;;
          esac
        done

        if [[ -z "$RESOURCE" ]]; then
          echo "Error: --resource is required" >&2
          exit 1
        fi

        if [[ "$RESOURCE" != gs://* ]]; then
          echo "Error: resource must start with gs://" >&2
          exit 1
        fi

        TRIMMED="${RESOURCE#gs://}"
        BUCKET="${TRIMMED%%/*}"
        PREFIX=""
        if [[ "$TRIMMED" == */* ]]; then
          PREFIX="${TRIMMED#*/}"
        fi

        printf 'bucket=%s
prefix=%s
' "$BUCKET" "$PREFIX"
