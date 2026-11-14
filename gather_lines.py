"""
Download betting lines from the CFBD API and cache them on disk.

Uses the same caching fetch() as cfbd_gather.py, so completed seasons are
only ever downloaded once. Costs one API call per season on a first run.

Run (from the same folder as cfbd_gather.py):
    python gather_lines.py
"""

import cfbd_gather
from cfbd_gather import SEASONS, fetch


def main():
    for year in SEASONS:
        games = fetch(
            "/lines",
            {"year": year, "seasonType": "regular"},
            f"lines_{year}_regular",
        )
        with_lines = sum(1 for g in games if g.get("lines"))
        print(f"lines {year}: {len(games)} games, {with_lines} with at least one line")

    print(f"\nDone. API calls made this run: {cfbd_gather.api_calls_made}")


if __name__ == "__main__":
    main()