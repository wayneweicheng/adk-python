#!/usr/bin/env bash
# Back up a file by copying it to <file>.bak
# Usage: backup.sh --path <file>

set -euo pipefail

PATH_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --path) PATH_ARG="$2"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ -z "$PATH_ARG" ]]; then
  echo "Error: --path argument is required" >&2
  exit 1
fi

if [[ ! -f "$PATH_ARG" ]]; then
  echo "Error: file '$PATH_ARG' not found" >&2
  exit 1
fi

cp "$PATH_ARG" "${PATH_ARG}.bak"
echo "Backup created: ${PATH_ARG}.bak"
