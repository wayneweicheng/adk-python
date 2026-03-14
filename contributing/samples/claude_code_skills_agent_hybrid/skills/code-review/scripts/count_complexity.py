"""Count basic complexity metrics for a Python file.

Usage: count_complexity.py --path <file>
"""

import argparse
import ast
import os
from pathlib import Path


def count_metrics(filepath: str) -> dict:
    resolved_path = resolve_target_path(filepath)
    try:
        with resolved_path.open(encoding="utf-8") as source_file:
            source = source_file.read()
    except OSError as e:
        return {"error": str(e)}

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"error": f"SyntaxError: {e}"}

    functions = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

    long_functions = [
        f.name
        for f in functions
        if (f.end_lineno or 0) - f.lineno > 50
    ]

    return {
        "function_count": len(functions),
        "class_count": len(classes),
        "long_functions": long_functions,
        "total_lines": source.count("\n") + 1,
    }


def resolve_target_path(path_arg: str) -> Path:
    """Resolve paths relative to the configured project root."""
    candidate = Path(path_arg).expanduser()
    project_root = os.environ.get("ADK_SKILLS_PROJECT_ROOT")
    if candidate.is_absolute():
        resolved = candidate.resolve()
    elif project_root:
        resolved = (Path(project_root).expanduser() / candidate).resolve()
    else:
        resolved = candidate.resolve()

    if project_root:
        root_path = Path(project_root).expanduser().resolve()
        try:
            resolved.relative_to(root_path)
        except ValueError as exc:
            raise ValueError(
                f"path '{resolved}' is outside project root '{root_path}'"
            ) from exc

    return resolved


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True, help="Python file to analyse")
    args = parser.parse_args()

    metrics = count_metrics(args.path)
    for key, value in metrics.items():
        print(f"{key}: {value}")
