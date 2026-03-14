"""Read a file and print its content.

Usage: read_file.py --path <file>
"""

import argparse
import pathlib

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    args = parser.parse_args()

    path = pathlib.Path(args.path)
    if not path.exists():
        print(f"Error: file '{args.path}' not found")
        raise SystemExit(1)

    print(path.read_text(encoding="utf-8"))
