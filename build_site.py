"""
Build a static ratings page from the cached CFBD data.

Reads:   data/raw/teams_fbs.json, data/raw/games_<year>_*.json,
         data/processed/team_adjusted_ratings.csv
Writes:  site/index.html  (self-contained: open it in a browser)

Run:
    python build_site.py
"""

import csv
import glob
import json
from pathlib import Path

RAW = Path("data/raw")
PROCESSED = Path("data/processed")
OUT = Path("site")

CURRENT_SEASON = 2026


def pick(d: dict, *keys):
    """Return the first key present, so camelCase/snake_case both work."""
    for k in keys:
        if k in d:
            return d[k]
    return None


def load_teams() -> dict:
    with open(RAW / "teams_fbs.json") as f:
        return {t["school"]: t for t in json.load(f)}


def load_games(season: int) -> list:
    games = []
    for path in sorted(glob.glob(str(RAW / f"games_{season}_*.json"))):
        with open(path) as f:
            games.extend(json.load(f))
    return games


def load_ratings() -> dict:
    """{(season, team): {...}} from the adjusted ratings CSV, scaled to per 100 plays."""
    path = PROCESSED / "team_adjusted_ratings.csv"
    if not path.exists():
        raise SystemExit("Missing team_adjusted_ratings.csv. Run adjusted_ratings.py first.")

    def num(v, scale=1.0, ndigits=1):
        return round(float(v) * scale, ndigits) if v not in ("", None) else None

    def rank(v):
        return int(float(v)) if v not in ("", None) else None

    ratings = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            ratings[(int(r["season"]), r["team"])] = {
                "off": num(r["adj_off"], 100),
                "def": num(r["adj_def"], 100),
                "net": num(r["adj_net"], 100),
                "sos": num(r["sos"], 100),
                "offRank": rank(r["adj_off_rank"]),
                "defRank": rank(r["adj_def_rank"]),
                "netRank": rank(r["adj_net_rank"]),
            }
    return ratings


def blank(team: dict) -> dict:
    logos = team.get("logos") or []
    return {
        "team": team["school"],
        "conf": team.get("conference") or "",
        "logo": logos[0] if logos else "",
        "w": 0, "l": 0, "t": 0,
        "cw": 0, "cl": 0, "ct": 0,
        "pf": 0, "pa": 0,
        "off": None, "def": None, "net": None, "sos": None,
        "offRank": None, "defRank": None, "netRank": None,
    }


def build_records(teams: dict, games: list) -> dict:
    rows = {name: blank(t) for name, t in teams.items()}

    for g in games:
        home = pick(g, "homeTeam", "home_team")
        away = pick(g, "awayTeam", "away_team")
        hp = pick(g, "homePoints", "home_points")
        ap = pick(g, "awayPoints", "away_points")
        done = pick(g, "completed")
        is_conf = bool(pick(g, "conferenceGame", "conference_game"))

        if not done or hp is None or ap is None:
            continue

        for team, pts_for, pts_against in ((home, hp, ap), (away, ap, hp)):
            row = rows.get(team)
            if row is None:  # opponent is not FBS
                continue
            row["pf"] += pts_for
            row["pa"] += pts_against
            if pts_for > pts_against:
                row["w"] += 1
                if is_conf:
                    row["cw"] += 1
            elif pts_for < pts_against:
                row["l"] += 1
                if is_conf:
                    row["cl"] += 1
            else:
                row["t"] += 1
                if is_conf:
                    row["ct"] += 1
    return rows


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>College Football Ratings</title>
<style>
  :root {
    --bg: #ffffff; --fg: #1a1a1a; --muted: #6b6b6b;
    --line: #e2e2e2; --head: #f3f3f3; --hover: #f8f8f8; --accent: #0b5cd5;
    --good: #2e8b57; --bad: #c23b3b;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #141414; --fg: #eaeaea; --muted: #9a9a9a;
      --line: #2c2c2c; --head: #1d1d1d; --hover: #1a1a1a; --accent: #6aa3ff;
      --good: #4caf7d; --bad: #e06666;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 24px 16px 48px; background: var(--bg); color: var(--fg);
    font: 15px/1.4 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }
  .wrap { max-width: 1040px; margin: 0 auto; }
  h1 { font-size: 24px; margin: 0 0 4px; }
  .sub { color: var(--muted); margin: 0 0 16px; }
  .note { color: var(--muted); font-size: 13px; margin: 0 0 12px; }
  .controls { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
  input, select {
    padding: 8px 10px; border: 1px solid var(--line); border-radius: 6px;
    background: var(--bg); color: var(--fg); font: inherit;
  }
  .scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
  table { border-collapse: collapse; width: 100%; min-width: 760px; }
  th, td { padding: 8px 10px; text-align: right; white-space: nowrap; }
  th:nth-child(-n+3), td:nth-child(-n+3) { text-align: left; }
  th { background: var(--head); cursor: pointer; user-select: none; font-weight: 600; }
  th.active { color: var(--accent); }
  tr + tr td { border-top: 1px solid var(--line); }
  tbody tr:hover { background: var(--hover); }
  .team { display: flex; align-items: center; gap: 8px; }
  .team img { width: 22px; height: 22px; object-fit: contain; }
  .rank { color: var(--muted); width: 40px; }
  .r { color: var(--muted); font-size: 11px; margin-left: 4px; }
  .pos { color: var(--good); } .neg { color: var(--bad); }
  .foot { color: var(--muted); font-size: 13px; margin-top: 16px; }
</style>
</head>
<body>
<div class="wrap">
  <h1>College Football Ratings</h1>
  <p class="sub" id="sub"></p>
  <p class="note" id="note"></p>
  <div class="controls">
    <select id="season"></select>
    <input id="search" type="search" placeholder="Search teams">
    <select id="conf"><option value="">All conferences</option></select>
  </div>
  <div class="scroll">
    <table>
      <thead><tr id="head"></tr></thead>
      <tbody id="body"></tbody>
    </table>
  </div>
  <p class="foot">
    Ratings are opponent-adjusted PPA (predicted points added) per 100 plays, excluding
    garbage time. Off: points above average per 100 plays against an average defense.
    Def: points allowed per 100 plays against an average offense (lower is better).
    Net = Off - Def. SOS is the average net rating of opponents faced. Small numbers
    next to a value are its national rank.
  </p>
</div>
<script>
const DATA = __DATA__;
const SEASONS = __SEASONS__;
const CURRENT_SEASON = __CURRENT__;

const COLS = [
  { key: "rank", label: "#", first: 1 },
  { key: "team", label: "Team", first: 1 },
  { key: "conf", label: "Conf", first: 1 },
  { key: "pct", label: "Record", first: -1 },
  { key: "cpct", label: "Conf Rec", first: -1 },
  { key: "net", label: "Net", first: -1 },
  { key: "off", label: "Off", first: -1 },
  { key: "def", label: "Def", first: 1 },
  { key: "sos", label: "SOS", first: -1 },
  { key: "diff", label: "Pt Diff", first: -1 },
];

const fmtRec = (w, l, t) => t ? `${w}-${l}-${t}` : `${w}-${l}`;
const pct = (w, l, t) => (w + l + t) ? (w + t / 2) / (w + l + t) : 0;
const num = v => v === null || v === undefined ? "\u2013" : (v > 0 ? "+" : "") + v.toFixed(1);
const withRank = (v, r) => v === null ? "\u2013" : `${num(v)}<span class="r">${r}</span>`;

Object.values(DATA).forEach(rows => rows.forEach(r => {
  r.pct = pct(r.w, r.l, r.t);
  r.cpct = pct(r.cw, r.cl, r.ct);
  r.diff = r.pf - r.pa;
  r.rank = r.netRank;
}));

let season = SEASONS[0];
let sortKey = "net", sortDir = -1;

function compare(a, b) {
  const x = a[sortKey], y = b[sortKey];
  if (x === null && y === null) return a.team.localeCompare(b.team);
  if (x === null) return 1;
  if (y === null) return -1;
  if (typeof x === "string") return sortDir * x.localeCompare(y);
  if (x !== y) return sortDir * (x - y);
  return a.team.localeCompare(b.team);
}

function render() {
  const q = document.getElementById("search").value.toLowerCase();
  const conf = document.getElementById("conf").value;
  const rows = DATA[season]
    .filter(r => (!conf || r.conf === conf) && r.team.toLowerCase().includes(q))
    .sort(compare);

  document.getElementById("sub").textContent =
    `${season} season, FBS teams. Click a column header to re-sort.`;
  document.getElementById("note").textContent = season === CURRENT_SEASON
    ? "This season is in progress: ratings rest on a small number of games and are pulled toward average."
    : "";

  document.getElementById("head").innerHTML = COLS.map(c =>
    `<th data-key="${c.key}" class="${c.key === sortKey ? "active" : ""}">${c.label}${c.key === sortKey ? (sortDir < 0 ? " \u25BC" : " \u25B2") : ""}</th>`
  ).join("");

  document.getElementById("body").innerHTML = rows.map(r => `
    <tr>
      <td class="rank">${r.rank === null ? "\u2013" : r.rank}</td>
      <td><div class="team">${r.logo ? `<img src="${r.logo}" alt="" onerror="this.style.display='none'">` : ""}${r.team}</div></td>
      <td>${r.conf}</td>
      <td>${fmtRec(r.w, r.l, r.t)}</td>
      <td>${fmtRec(r.cw, r.cl, r.ct)}</td>
      <td class="${r.net > 0 ? "pos" : r.net < 0 ? "neg" : ""}">${withRank(r.net, r.netRank)}</td>
      <td class="${r.off > 0 ? "pos" : r.off < 0 ? "neg" : ""}">${withRank(r.off, r.offRank)}</td>
      <td class="${r.def < 0 ? "pos" : r.def > 0 ? "neg" : ""}">${withRank(r.def, r.defRank)}</td>
      <td>${num(r.sos)}</td>
      <td class="${r.diff > 0 ? "pos" : r.diff < 0 ? "neg" : ""}">${r.diff > 0 ? "+" : ""}${r.diff}</td>
    </tr>`).join("");

  document.querySelectorAll("th").forEach(th => th.onclick = () => {
    const col = COLS.find(c => c.key === th.dataset.key);
    if (col.key === sortKey) sortDir *= -1;
    else { sortKey = col.key; sortDir = col.first; }
    render();
  });
}

const seasonSelect = document.getElementById("season");
SEASONS.forEach(s => {
  const o = document.createElement("option");
  o.value = o.textContent = s;
  seasonSelect.appendChild(o);
});
seasonSelect.onchange = () => { season = +seasonSelect.value; render(); };

const confSelect = document.getElementById("conf");
[...new Set(Object.values(DATA).flat().map(r => r.conf).filter(Boolean))].sort().forEach(c => {
  const o = document.createElement("option");
  o.value = o.textContent = c;
  confSelect.appendChild(o);
});
confSelect.onchange = render;
document.getElementById("search").oninput = render;
render();
</script>
</body>
</html>
"""


def main():
    teams = load_teams()
    ratings = load_ratings()
    seasons = sorted({s for s, _ in ratings}, reverse=True)

    data = {}
    for season in seasons:
        rows = build_records(teams, load_games(season))
        for name, row in rows.items():
            row.update(ratings.get((season, name), {}))
        data[season] = list(rows.values())

    payload = json.dumps(data).replace("</", "<\\/")
    html = (
        PAGE.replace("__DATA__", payload)
        .replace("__SEASONS__", json.dumps(seasons))
        .replace("__CURRENT__", str(CURRENT_SEASON))
    )

    OUT.mkdir(exist_ok=True)
    out_path = OUT / "index.html"
    out_path.write_text(html, encoding="utf-8")

    for season in seasons:
        rated = sum(1 for r in data[season] if r["net"] is not None)
        print(f"{season}: {len(data[season])} teams, {rated} with ratings")
    print(f"Wrote {out_path.resolve()}")


if __name__ == "__main__":
    main()