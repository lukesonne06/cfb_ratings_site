"""
Walk-forward backtest of the ratings against Vegas lines.

For every regular-season week N, ratings are fit using ONLY games from
weeks before N (plus last season's games, down-weighted, as a prior), then
used to predict week N's games. Nothing from the future leaks in.

Honest-evaluation setup:
  - TRAIN_SEASONS are used to pick ALPHA and PRIOR_WEIGHT (by error against
    actual margins, never against the Vegas line) and to calibrate the
    rating-to-points conversion.
  - TEST_SEASONS are scored with those frozen settings.

Reads:   data/processed/plays.parquet, data/raw/games_*_regular.json,
         data/raw/lines_*_regular.json
Writes:  data/processed/backtest_predictions.csv

Setup / run (same folder as adjusted_ratings.py and raw_ratings.py):
    python gather_lines.py     # once, calls the API
    python backtest.py
"""

import contextlib
import glob
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

import adjusted_ratings
from adjusted_ratings import fit_season, load_neutral_sites, pick
from raw_ratings import load_scrimmage_plays

RAW = Path("data/raw")
PROCESSED = Path("data/processed")

TRAIN_SEASONS = [2024]
TEST_SEASONS = [2025, 2026]

ALPHAS = [50, 100, 150, 300, 600]
PRIOR_WEIGHTS = [0.0, 0.15, 0.3, 0.5]   # how much last season counts vs. this season

EARLY_WEEKS = 4                          # report weeks 1-4 separately
GAP_THRESHOLDS = [0, 1, 2, 3, 5]         # model-vs-line disagreement, in points


# ---------------------------------------------------------------- data loading

def load_sides() -> pd.DataFrame:
    """One row per team offense per game, with week, for regular-season plays."""
    with contextlib.redirect_stdout(io.StringIO()):
        plays = load_scrimmage_plays()
    plays = plays[plays["season_type"] == "regular"]

    sides = plays.groupby(
        ["season", "week", "game_id", "offense", "defense", "home", "away"], as_index=False
    ).agg(ppa=("ppa", "mean"), n=("ppa", "size"))

    neutral = load_neutral_sites()
    is_neutral = sides["game_id"].map(neutral).fillna(False).astype(bool)
    sides["home_field"] = np.where(
        is_neutral, 0,
        np.where(sides["offense"] == sides["home"], 1,
                 np.where(sides["offense"] == sides["away"], -1, 0)),
    )
    return sides


def load_games(fbs: set) -> pd.DataFrame:
    rows = []
    for path in sorted(glob.glob(str(RAW / "games_*_regular.json"))):
        with open(path) as f:
            games = json.load(f)
        for g in games:
            home = pick(g, "homeTeam", "home_team")
            away = pick(g, "awayTeam", "away_team")
            hp = pick(g, "homePoints", "home_points")
            ap = pick(g, "awayPoints", "away_points")
            if not pick(g, "completed") or hp is None or ap is None:
                continue
            if home not in fbs or away not in fbs:
                continue
            rows.append({
                "season": pick(g, "season"),
                "week": pick(g, "week"),
                "game_id": g["id"],
                "home": home,
                "away": away,
                "neutral": bool(pick(g, "neutralSite", "neutral_site")),
                "margin": hp - ap,   # actual home margin
            })
    return pd.DataFrame(rows)


def load_vegas() -> dict:
    """{game_id: Vegas predicted home margin}, averaged across providers.

    Assumes the spread is from the home team's view (negative = home favored),
    so the predicted home margin is -spread. A sanity check later confirms it.
    """
    out = {}
    for path in sorted(glob.glob(str(RAW / "lines_*_regular.json"))):
        with open(path) as f:
            for g in json.load(f):
                spreads = [l.get("spread") for l in (g.get("lines") or [])
                           if l.get("spread") is not None]
                if spreads:
                    out[g["id"]] = -float(np.mean(spreads))
    return out


# ----------------------------------------------------------- walk-forward fit

def predict_season(sides, games, season, alpha, prior_weight) -> pd.DataFrame:
    """Walk-forward rating difference (home net minus away net) for each game."""
    adjusted_ratings.ALPHA = alpha

    season_games = games[games["season"] == season]
    if season_games.empty:
        return season_games.assign(d=[], home_flag=[])

    cur = sides[sides["season"] == season]
    prev = sides[sides["season"] == season - 1].copy()
    prev["n"] = prev["n"] * prior_weight
    if prior_weight <= 0:
        prev = prev.iloc[0:0]

    parts = []
    for week in sorted(season_games["week"].unique()):
        train = pd.concat([prev, cur[cur["week"] < week]], ignore_index=True)
        if len(train) > 0:
            res, _ = fit_season(train)
            net = dict(zip(res["team"], res["adj_off"] - res["adj_def"]))
        else:
            net = {}  # no information yet: everyone rates as average

        g = season_games[season_games["week"] == week].copy()
        g["d"] = g["home"].map(net).fillna(0.0) - g["away"].map(net).fillna(0.0)
        g["home_flag"] = (~g["neutral"]).astype(int)
        parts.append(g)

    return pd.concat(parts, ignore_index=True)


def calibrate(pred: pd.DataFrame) -> np.ndarray:
    """Fit margin = k * rating_diff + h * home_flag on training predictions."""
    X = np.column_stack([pred["d"], pred["home_flag"]])
    coef, *_ = np.linalg.lstsq(X, pred["margin"].to_numpy(float), rcond=None)
    return coef


def apply_calibration(pred: pd.DataFrame, coef: np.ndarray) -> pd.DataFrame:
    pred = pred.copy()
    pred["model"] = np.column_stack([pred["d"], pred["home_flag"]]) @ coef
    return pred


# ------------------------------------------------------------------ evaluation

def evaluate(df: pd.DataFrame, label: str) -> None:
    df = df.dropna(subset=["vegas"]).copy()
    print(f"\n{'=' * 64}\n{label}: {len(df)} games with lines\n{'=' * 64}")
    if len(df) < 30:
        print("Too few games with lines to evaluate.")
        return

    corr = np.corrcoef(df["vegas"], df["margin"])[0, 1]
    print(f"Sanity check: corr(Vegas predicted margin, actual margin) = {corr:.2f}")
    if corr < 0:
        print("  WARNING: negative. The spread sign convention is probably reversed;")
        print("  flip the sign in load_vegas() before trusting anything below.")

    err_m = df["margin"] - df["model"]
    err_v = df["margin"] - df["vegas"]
    print(f"\n{'':22}{'Model':>9}{'Vegas':>9}")
    print(f"{'MAE (points)':22}{err_m.abs().mean():>9.2f}{err_v.abs().mean():>9.2f}")
    print(f"{'RMSE (points)':22}{np.sqrt((err_m ** 2).mean()):>9.2f}{np.sqrt((err_v ** 2).mean()):>9.2f}")

    early = df["week"] <= EARLY_WEEKS
    for name, mask in ((f"MAE weeks 1-{EARLY_WEEKS}", early), (f"MAE weeks {EARLY_WEEKS + 1}+", ~early)):
        if mask.sum() > 0:
            print(f"{name:22}{err_m[mask].abs().mean():>9.2f}{err_v[mask].abs().mean():>9.2f}   (n={int(mask.sum())})")

    # Against the spread: bet whichever side the model likes more than the line does.
    margin = df["margin"].to_numpy(float)
    vegas = df["vegas"].to_numpy(float)
    model = df["model"].to_numpy(float)
    pick_home = model > vegas
    covered = np.where(pick_home, margin > vegas, margin < vegas)
    push = margin == vegas
    gap = np.abs(model - vegas)

    print("\nAgainst the spread (break-even is about 52.4% at -110 odds)")
    print(f"{'gap >=':>8}{'games':>8}{'cover %':>10}{'95% range':>18}")
    for t in GAP_THRESHOLDS:
        sub = (~push) & (gap >= t)
        n = int(sub.sum())
        if n == 0:
            continue
        p = covered[sub].mean()
        half = 1.96 * np.sqrt(p * (1 - p) / n)
        print(f"{t:>8}{n:>8}{p:>10.1%}{f'{p - half:.1%} to {p + half:.1%}':>18}")

    # Does the model add information beyond the line?
    X = np.column_stack([np.ones(len(df)), vegas, model])
    y = margin
    coef = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ coef
    sigma2 = resid @ resid / (len(y) - 3)
    se = np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X)))
    print("\nRegression: actual margin ~ Vegas + model")
    print(f"  Vegas coefficient: {coef[1]:.2f} (SE {se[1]:.2f})")
    print(f"  Model coefficient: {coef[2]:.2f} (SE {se[2]:.2f})")
    print("  A model coefficient well above 0 (relative to its SE) means the model")
    print("  carries information the line does not.")


# ------------------------------------------------------------------------ main

def main():
    with open(RAW / "teams_fbs.json") as f:
        fbs = {t["school"] for t in json.load(f)}

    sides = load_sides()
    games = load_games(fbs)
    games["vegas"] = games["game_id"].map(load_vegas())

    # 1. Tune on training seasons, scored against ACTUAL margins.
    print("Tuning on seasons:", TRAIN_SEASONS)
    results = []
    for alpha in ALPHAS:
        for pw in PRIOR_WEIGHTS:
            frames = [predict_season(sides, games, s, alpha, pw) for s in TRAIN_SEASONS]
            preds = pd.concat([f for f in frames if len(f)], ignore_index=True)
            if preds.empty:
                raise SystemExit("No training games found. Check TRAIN_SEASONS and your data.")
            coef = calibrate(preds)
            scored = apply_calibration(preds, coef)
            mae = (scored["margin"] - scored["model"]).abs().mean()
            results.append((alpha, pw, mae, coef))

    results.sort(key=lambda r: r[2])
    print(f"\n{'alpha':>7}{'prior wt':>10}{'train MAE':>11}")
    for alpha, pw, mae, _ in results:
        print(f"{alpha:>7}{pw:>10}{mae:>11.3f}")

    best_alpha, best_pw, best_mae, _ = results[0]
    print(f"\nChosen: ALPHA={best_alpha}, PRIOR_WEIGHT={best_pw} (train MAE {best_mae:.3f})")

    # 2. Freeze the calibration from the training seasons.
    train_preds = pd.concat(
        [predict_season(sides, games, s, best_alpha, best_pw) for s in TRAIN_SEASONS],
        ignore_index=True,
    )
    coef = calibrate(train_preds)
    print(f"Calibration: {coef[0]:.2f} points per unit of rating difference, "
          f"home field {coef[1]:.2f} points")

    evaluate(apply_calibration(train_preds, coef),
             f"TRAIN seasons {TRAIN_SEASONS} (in-sample, for reference only)")

    # 3. Score the held-out seasons.
    all_test = []
    for season in TEST_SEASONS:
        pred = predict_season(sides, games, season, best_alpha, best_pw)
        if pred.empty:
            print(f"\nNo completed games found for {season}, skipping.")
            continue
        pred = apply_calibration(pred, coef)
        all_test.append(pred)
        evaluate(pred, f"TEST season {season}")

    if len(all_test) > 1:
        evaluate(pd.concat(all_test, ignore_index=True), f"TEST seasons combined {TEST_SEASONS}")

    if all_test:
        out = PROCESSED / "backtest_predictions.csv"
        pd.concat(all_test, ignore_index=True).to_csv(out, index=False)
        print(f"\nSaved {out.resolve()}")


if __name__ == "__main__":
    main()