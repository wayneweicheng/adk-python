#!/usr/bin/env bash
# Usage: lint_check.sh --path <file>
# Runs basic lint checks on the given file and prints findings.

set -euo pipefail

resolve_target_path() {
  local path_arg="$1"
  local candidate="$path_arg"
  local project_root="${ADK_SKILLS_PROJECT_ROOT:-}"

  if [[ "$candidate" != /* && -n "$project_root" ]]; then
    candidate="${project_root%/}/$candidate"
  fi

  local parent_dir
  parent_dir=$(cd "$(dirname "$candidate")" 2>/dev/null && pwd -P) || return 1
  candidate="${parent_dir}/$(basename "$candidate")"

  if [[ -n "$project_root" ]]; then
    local resolved_root
    resolved_root=$(cd "$project_root" 2>/dev/null && pwd -P) || return 1
    case "$candidate" in
      "$resolved_root" | "$resolved_root"/*) ;;
      *)
        echo "Error: path '$candidate' is outside project root '$resolved_root'" >&2
        return 1
        ;;
    esac
  fi

  printf '%s\n' "$candidate"
}

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

PATH_ARG="$(resolve_target_path "$PATH_ARG")" || exit 1

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
