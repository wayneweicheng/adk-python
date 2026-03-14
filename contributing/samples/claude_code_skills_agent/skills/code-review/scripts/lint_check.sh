#!/usr/bin/env bash
# Usage: lint_check.sh --path <file>
# Runs basic lint checks on the given file and prints findings.

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

echo "=== Lint check: $PATH_ARG ==="

# Check for TODO / FIXME comments
todo_count=$(grep -c "TODO\|FIXME" "$PATH_ARG" 2>/dev/null || true)
echo "TODOs/FIXMEs found: $todo_count"

# Check line count
line_count=$(wc -l < "$PATH_ARG")
echo "Total lines: $line_count"

# Check for trailing whitespace
trailing=$(grep -c " $" "$PATH_ARG" 2>/dev/null || true)
echo "Lines with trailing whitespace: $trailing"

echo "=== Done ==="
