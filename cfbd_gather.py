"""
Gather college football data from the CollegeFootballData.com API and
cache the raw JSON on disk. Re-running is safe: anything already
downloaded is read from disk instead of calling the API again.

Setup:
    pip install requests
    export CFBD_API_KEY="your_key_here"      (PowerShell: $env:CFBD_API_KEY="...")

Run:
    python cfbd_gather.py
"""

import json
import os
import time
from pathlib import Path

import requests

API_KEY = os.environ.get("CFBD_API_KEY")
BASE_URL = "https://api.collegefootballdata.com"
DATA_DIR = Path("data/raw")

# Seasons to pull. Completed seasons are fetched once and cached forever.
SEASONS = [2023, 2024, 2025, 2026]
CURRENT_SEASON = 2026          # still in progress, so its files get refreshed
CURRENT_MAX_AGE_HOURS = 12     # re-download current-season files older than this

REGULAR_SEASON_WEEKS = range(1, 16)   # weeks 1-15; empty weeks just return []
POSTSEASON_WEEKS = [1]

PAUSE_SECONDS = 0.3   # small delay between real API calls

api_calls_made = 0


def cache_path(name: str) -> Path:
    return DATA_DIR / f"{name}.json"


def is_stale(path: Path, year: int | None) -> bool:
    """Completed seasons never go stale; the current season does after a while."""
    if not path.exists():
        return True
    if year == CURRENT_SEASON:
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        return age_hours > CURRENT_MAX_AGE_HOURS
    return False


def fetch(endpoint: str, params: dict, name: str):
    """GET an endpoint, using the on-disk cache when possible."""
    global api_calls_made

    path = cache_path(name)
    if not is_stale(path, params.get("year")):
        with open(path) as f:
            return json.load(f)

    if not API_KEY:
        raise SystemExit("CFBD_API_KEY is not set.")

    response = requests.get(
        f"{BASE_URL}{endpoint}",
        headers={"Authorization": f"Bearer {API_KEY}"},
        params=params,
        timeout=60,
    )
    api_calls_made += 1
    response.raise_for_status()
    data = response.json()

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)

    time.sleep(PAUSE_SECONDS)
    return data


def gather_teams():
    teams = fetch("/teams/fbs", {"year": CURRENT_SEASON}, "teams_fbs")
    print(f"teams: {len(teams)} FBS teams")


def gather_games(year: int):
    for season_type in ("regular", "postseason"):
        games = fetch(
            "/games",
            {"year": year, "seasonType": season_type},
            f"games_{year}_{season_type}",
        )
        print(f"games {year} {season_type}: {len(games)} games")


def gather_plays(year: int):
    jobs = [("regular", w) for w in REGULAR_SEASON_WEEKS]
    jobs += [("postseason", w) for w in POSTSEASON_WEEKS]

    for season_type, week in jobs:
        plays = fetch(
            "/plays",
            {
                "year": year,
                "week": week,
                "seasonType": season_type,
                "classification": "fbs",
            },
            f"plays_{year}_{season_type}_wk{week:02d}",
        )
        if plays:
            print(f"plays {year} {season_type} wk{week}: {len(plays)} plays")


def main():
    gather_teams()
    for year in SEASONS:
        gather_games(year)
        gather_plays(year)
    print(f"\nDone. API calls made this run: {api_calls_made}")
    print(f"Raw data saved under: {DATA_DIR.resolve()}")


if __name__ == "__main__":
    main()