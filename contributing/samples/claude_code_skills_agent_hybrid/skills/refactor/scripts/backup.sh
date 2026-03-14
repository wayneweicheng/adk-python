#!/usr/bin/env bash
# Back up a file by copying it to <file>.bak
# Usage: backup.sh --path <file>

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

cp "$PATH_ARG" "${PATH_ARG}.bak"
echo "Backup created: ${PATH_ARG}.bak"
