"""Count basic complexity metrics for a Python file.

Usage: count_complexity.py --path <file>
"""

import argparse
import ast
import sys


def count_metrics(filepath: str) -> dict:
    try:
        source = open(filepath, encoding="utf-8").read()
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True, help="Python file to analyse")
    args = parser.parse_args()

    metrics = count_metrics(args.path)
    for key, value in metrics.items():
        print(f"{key}: {value}")
