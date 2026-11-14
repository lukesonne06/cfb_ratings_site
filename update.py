"""
Rebuild the ratings and the website from the JSON already stored on disk.

This does NOT call the API. To download fresh data first, run
cfbd_gather.py separately.

Steps, in order:
    1. build_plays.py       combine play files, flag garbage time
    2. raw_ratings.py       raw offense/defense PPA per play
    3. adjusted_ratings.py  opponent-adjusted ratings
    4. build_site.py        write site/index.html

Run (from the folder containing these scripts and the data/ folder):
    python update.py
"""

import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

STEPS = [
    "build_plays.py",
    "raw_ratings.py",
    "adjusted_ratings.py",
    "build_site.py",
]


def main():
    start = time.time()

    for i, script in enumerate(STEPS, start=1):
        print(f"\n{'=' * 60}\n[{i}/{len(STEPS)}] {script}\n{'=' * 60}")

        if not (HERE / script).exists():
            sys.exit(f"Could not find {script} in {HERE}")

        result = subprocess.run([sys.executable, script], cwd=HERE)
        if result.returncode != 0:
            sys.exit(f"\nStopped: {script} failed (exit code {result.returncode}).")

    print(f"\nAll steps finished in {time.time() - start:.0f}s.")
    print(f"Open {HERE / 'site' / 'index.html'} to view the updated site.")


if __name__ == "__main__":
    main()