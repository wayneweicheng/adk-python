        #!/usr/bin/env bash
        # Usage: parse_table_ref.sh --resource project.dataset.table

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

        IFS='.' read -r A B C <<< "$RESOURCE"
        if [[ -z "${C:-}" ]]; then
          echo "Error: expected project.dataset.table" >&2
          exit 1
        fi

        printf 'project_id=%s
dataset_id=%s
table_id=%s
' "$A" "$B" "$C"
