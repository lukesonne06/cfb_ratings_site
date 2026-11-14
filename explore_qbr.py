"""
Find and inspect cached QBR JSON files, and load the records into pandas.

Usage (from your project folder):
    python explore_qbr.py                     # searches data/ for files with "qbr" in the name
    python explore_qbr.py data/raw/some.json  # inspect one specific file
"""

import json
import sys
from pathlib import Path

import pandas as pd


def describe(obj, indent=0, depth=0, max_depth=3):
    """Print the shape of a nested JSON object."""
    pad = "  " * indent
    if isinstance(obj, dict):
        print(f"{pad}dict with {len(obj)} keys: {list(obj.keys())[:12]}")
        if depth < max_depth:
            for k, v in list(obj.items())[:6]:
                if isinstance(v, (dict, list)):
                    print(f"{pad}  [{k}]")
                    describe(v, indent + 2, depth + 1, max_depth)
    elif isinstance(obj, list):
        print(f"{pad}list of {len(obj)} items")
        if obj and depth < max_depth:
            describe(obj[0], indent + 1, depth + 1, max_depth)


def find_records(obj, depth=0):
    """Return the first list of dicts found, which is usually the table of players."""
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        return obj
    if isinstance(obj, dict) and depth < 4:
        for v in obj.values():
            found = find_records(v, depth + 1)
            if found:
                return found
    return None


def find_files(arg):
    if arg and Path(arg).is_file():
        return [Path(arg)]
    root = Path(arg) if arg else Path("data")
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and "qbr" in p.name.lower())


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    files = find_files(arg)

    if not files:
        raise SystemExit("No QBR files found. Pass the path to a file or folder.")

    print(f"Found {len(files)} file(s):")
    for p in files[:20]:
        print(f"  {p}  ({p.stat().st_size / 1024:.0f} KB)")

    path = files[0]
    print(f"\nInspecting {path}\n")
    with open(path) as f:
        data = json.load(f)

    describe(data)

    records = find_records(data)
    if records is None:
        print("\nNo list of records found. Paste the structure above and I can help.")
        return

    df = pd.json_normalize(records)
    print(f"\nLoaded {len(df)} records, {len(df.columns)} columns")
    print("\nColumns:")
    print(df.columns.tolist())
    print("\nFirst rows:")
    with pd.option_context("display.max_columns", 12, "display.width", 200):
        print(df.head())


if __name__ == "__main__":
    main()