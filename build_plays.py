"""
Combine the cached weekly play-by-play files into one table, remove
extreme-PPA plays, kickoffs, and fourth-down plays, flag garbage-time
plays, and save the result for the rating model.

Reads:   data/raw/plays_<year>_<type>_wkNN.json
Writes:  data/processed/plays.parquet       (remaining plays, with an is_garbage flag)
         data/processed/plays_all.parquet   (every play, unfiltered, with an is_garbage flag;
                                             used by drive-based stats)

Setup:
    pip install pandas pyarrow

Run:
    python build_plays.py
"""

import glob
import json
import re
from pathlib import Path

import pandas as pd

RAW = Path("data/raw")
PROCESSED = Path("data/processed")

# A play is garbage time when the score margin at that moment is LARGER
# than the threshold for its quarter. Overtime is never garbage time.
# These are tunable: later we can backtest different values and keep
# whichever makes the ratings predict games best.
GARBAGE_MARGIN_BY_QUARTER = {1: 43, 2: 37, 3: 27, 4: 21}

# Plays removed outright, before the garbage-time flag is computed.
# PPA outside [PPA_MIN, PPA_MAX] is dropped (plays with no PPA are kept here;
# raw_ratings.py drops those later). Matching on play type is case-insensitive.
PPA_MAX = 5
PPA_MIN = -3
DROP_PLAY_TYPE_PATTERN = r"kickoff"
DROP_DOWNS = [4]

KEEP_COLUMNS = [
    "season", "season_type", "week",
    "game_id", "id", "drive_id", "drive_number", "play_number",
    "offense", "defense", "home", "away",
    "period", "clock",
    "offense_score", "defense_score",
    "down", "distance", "yards_to_goal", "yards_gained",
    "play_type", "scoring", "ppa",
]


def to_snake(name: str) -> str:
    """homeTeam -> home_team, so camelCase and snake_case files both work."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def load_plays() -> pd.DataFrame:
    pattern = re.compile(r"plays_(\d{4})_(regular|postseason)_wk(\d+)\.json")
    frames = []

    for path in sorted(glob.glob(str(RAW / "plays_*.json"))):
        m = pattern.search(Path(path).name)
        if not m:
            continue
        with open(path) as f:
            rows = json.load(f)
        if not rows:
            continue

        df = pd.DataFrame(rows)
        df.columns = [to_snake(c) for c in df.columns]
        df["season"] = int(m.group(1))
        df["season_type"] = m.group(2)
        df["week"] = int(m.group(3))
        frames.append(df)

    if not frames:
        raise SystemExit("No play files found in data/raw/. Run cfbd_gather.py first.")

    plays = pd.concat(frames, ignore_index=True)
    cols = [c for c in KEEP_COLUMNS if c in plays.columns]
    return plays[cols]


def flag_garbage(plays: pd.DataFrame) -> pd.DataFrame:
    plays = plays.copy()
    plays["margin"] = (plays["offense_score"] - plays["defense_score"]).abs()
    threshold = plays["period"].map(GARBAGE_MARGIN_BY_QUARTER)  # NaN for OT
    plays["is_garbage"] = (plays["margin"] > threshold).fillna(False)
    return plays


def filter_plays(plays: pd.DataFrame) -> pd.DataFrame:
    """Drop extreme-PPA plays, kickoffs, and fourth-down plays."""
    plays = plays.copy()
    plays["ppa"] = pd.to_numeric(plays["ppa"], errors="coerce")

    too_high = plays["ppa"] > PPA_MAX
    too_low = plays["ppa"] < PPA_MIN
    kickoff = plays["play_type"].str.contains(DROP_PLAY_TYPE_PATTERN, case=False, na=False)
    fourth = plays["down"].isin(DROP_DOWNS)
    drop = too_high | too_low | kickoff | fourth

    print(f"Plays before filtering:   {len(plays):,}")
    print(f"  PPA above {PPA_MAX}:           {int(too_high.sum()):,}")
    print(f"  PPA below {PPA_MIN}:          {int(too_low.sum()):,}")
    print(f"  Kickoffs:               {int(kickoff.sum()):,}")
    print(f"  Fourth down:            {int(fourth.sum()):,}")
    print(f"Removed (some overlap):   {int(drop.sum()):,}")
    print(f"Plays remaining:          {int((~drop).sum()):,}")
    return plays[~drop].copy()


def summarize(plays: pd.DataFrame) -> None:
    total = len(plays)
    garbage = int(plays["is_garbage"].sum())
    print(f"\nTotal plays:   {total:,}")
    print(f"Garbage time:  {garbage:,} ({garbage / total:.1%})")

    print("\nShare of plays flagged, by season:")
    print(plays.groupby("season")["is_garbage"].mean().map("{:.1%}".format).to_string())

    print("\nShare flagged, by quarter:")
    print(plays.groupby("period")["is_garbage"].mean().map("{:.1%}".format).to_string())

    # Sanity check: garbage-time plays are usually less efficient for the
    # winning side and noisier overall, so the averages should differ.
    if "ppa" in plays.columns:
        plays["ppa"] = pd.to_numeric(plays["ppa"], errors="coerce")
        print("\nAverage PPA per play:")
        print(plays.groupby("is_garbage")["ppa"].agg(["mean", "count"]).to_string())

    games = (
        plays.groupby("game_id")["is_garbage"]
        .agg(["mean", "size"])
        .query("size > 50")
        .sort_values("mean", ascending=False)
        .head(5)
    )
    print("\nGames with the highest garbage-time share (game_id, share, plays):")
    print(games.to_string())


def main():
    plays = load_plays()
    plays["ppa"] = pd.to_numeric(plays["ppa"], errors="coerce")
    plays = flag_garbage(plays)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    plays.to_parquet(PROCESSED / "plays_all.parquet", index=False)  # every play, unfiltered

    plays = filter_plays(plays)
    out = PROCESSED / "plays.parquet"
    plays.to_parquet(out, index=False)

    summarize(plays)
    print(f"\nSaved {out.resolve()}")
    print("Filter for modeling with:  plays[~plays['is_garbage']]")


if __name__ == "__main__":
    main()