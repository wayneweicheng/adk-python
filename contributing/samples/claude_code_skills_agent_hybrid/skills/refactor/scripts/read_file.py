"""Read a file and print its content.

Usage: read_file.py --path <file>
"""

import argparse
import os
import pathlib


def resolve_target_path(path_arg: str) -> pathlib.Path:
    """Resolve paths relative to the configured project root."""
    candidate = pathlib.Path(path_arg).expanduser()
    project_root = os.environ.get("ADK_SKILLS_PROJECT_ROOT")
    if candidate.is_absolute():
        resolved = candidate.resolve()
    elif project_root:
        resolved = (pathlib.Path(project_root).expanduser() / candidate).resolve()
    else:
        resolved = candidate.resolve()

    if project_root:
        root_path = pathlib.Path(project_root).expanduser().resolve()
        try:
            resolved.relative_to(root_path)
        except ValueError as exc:
            raise ValueError(
                f"path '{resolved}' is outside project root '{root_path}'"
            ) from exc

    return resolved


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    try:
        path = resolve_target_path(args.path)
    except ValueError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1) from exc

    if not path.is_file():
        print(f"Error: file '{args.path}' not found")
        raise SystemExit(1)

    print(path.read_text(encoding="utf-8"))
