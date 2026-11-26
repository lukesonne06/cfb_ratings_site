"""
Build a static ratings page with week-by-week rankings.

Reads:   data/raw/teams_fbs.json, data/raw/games_<year>_*.json,
         data/processed/team_weekly_yard_pct.csv
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
POSTSEASON_WEEK = 16  # must match weekly_yard_pct.py


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


def game_week(g: dict) -> int:
    """Week index of a game; all postseason games share one final week."""
    if pick(g, "seasonType", "season_type") == "postseason":
        return POSTSEASON_WEEK
    week = pick(g, "week")
    return int(week) if week is not None else POSTSEASON_WEEK


def load_weekly():
    """Ratings by (season, week, team), plus the list of weeks per season."""
    path = PROCESSED / "team_weekly_yard_pct.csv"
    if not path.exists():
        raise SystemExit("Missing team_weekly_yard_pct.csv. Run weekly_yard_pct.py first.")

    def num(v, ndigits=1):
        return round(float(v), ndigits) if v not in ("", None) else None

    def rank(v):
        return int(float(v)) if v not in ("", None) else None

    ratings, weeks = {}, {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            season, week = int(r["season"]), int(r["week"])
            weeks.setdefault(season, set()).add(week)

            opp_off, opp_def = r["opp_off_faced"], r["opp_def_faced"]
            sos = (round(float(opp_off) - float(opp_def), 1)
                   if opp_off not in ("", None) and opp_def not in ("", None) else None)

            ratings[(season, week, r["team"])] = {
                "off": num(r["adj_off_pct"]),
                "def": num(r["adj_def_pct"]),
                "net": num(r["adj_net_pct"]),
                "sos": sos,
                "offRank": rank(r["adj_off_pct_rank"]),
                "defRank": rank(r["adj_def_pct_rank"]),
                "netRank": rank(r["adj_net_pct_rank"]),
                "gp": int(float(r["games"])),
                "wt": round(float(r["weight"]) * 100),
            }
    return ratings, {s: sorted(w) for s, w in weeks.items()}


def blank(team: dict) -> dict:
    return {
        "team": team["school"],
        "w": 0, "l": 0, "t": 0,
        "cw": 0, "cl": 0, "ct": 0,
        "pf": 0, "pa": 0,
        "off": None, "def": None, "net": None, "sos": None,
        "offRank": None, "defRank": None, "netRank": None,
        "gp": None, "wt": None,
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
  .wrap { max-width: 1120px; margin: 0 auto; }
  h1 { font-size: 24px; margin: 0 0 4px; }
  .sub { color: var(--muted); margin: 0 0 16px; }
  .note { color: var(--muted); font-size: 13px; margin: 0 0 12px; }
  .controls { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
  input, select {
    padding: 8px 10px; border: 1px solid var(--line); border-radius: 6px;
    background: var(--bg); color: var(--fg); font: inherit;
  }
  .scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
  table { border-collapse: collapse; width: 100%; min-width: 820px; }
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
  .dim { color: var(--muted); }
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
    <select id="week"></select>
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
    Ratings are built from drives. At the start of each possession, the offense has some
    number of yards to the goal line available; the rating is the share of those available
    yards the offense gained, adjusted for the quality of the opponents faced. Off: the share
    of available yards an offense gains (higher is better). Def: the share a defense allows
    (lower is better). Net = Off minus Def, in percentage points. SOS is the average opposing
    offense faced minus the average opposing defense faced, so positive means a tougher
    schedule. Garbage time is excluded, and only games between FBS teams count toward the
    ratings. Yardage is adjusted for home field: a home team's yards are scaled down 10% and
    a road team's scaled up 10%, with neutral-site games left alone. Small numbers next to a value are its national rank. Records and point
    differential are as of the selected week.
    Through a team's first 8 games, its rating is a blend of its final rating from last season and
    its rating from this season so far: with g games played, this season counts for g/8 and last
    season for the rest. The This Yr column shows that share. The Preseason view is last season's
    final ratings.
  </p>
</div>
<script>
const DATA = __DATA__;       // DATA[season][week] -> list of team rows
const TEAMS = __TEAMS__;     // team -> { conf, logo }
const SEASONS = __SEASONS__;
const NAT = __NAT__;         // NAT[season][week] -> average Off % that snapshot
const CURRENT_SEASON = __CURRENT__;
const POST_WEEK = __POSTWEEK__;

const COLS = [
  { key: "rank", label: "#", first: 1 },
  { key: "team", label: "Team", first: 1 },
  { key: "conf", label: "Conf", first: 1 },
  { key: "pct", label: "Record", first: -1 },
  { key: "cpct", label: "Conf Rec", first: -1 },
  { key: "net", label: "Net", first: -1 },
  { key: "off", label: "Off %", first: -1 },
  { key: "def", label: "Def %", first: 1 },
  { key: "sos", label: "SOS", first: -1 },
  { key: "wt", label: "This Yr", first: -1 },
  { key: "diff", label: "Pt Diff", first: -1 },
];

const dash = "\\u2013";
const fmtRec = (w, l, t) => t ? `${w}-${l}-${t}` : `${w}-${l}`;
const pct = (w, l, t) => (w + l + t) ? (w + t / 2) / (w + l + t) : 0;
const signed = v => v === null || v === undefined ? dash : (v > 0 ? "+" : "") + v.toFixed(1);
const level = v => v === null || v === undefined ? dash : v.toFixed(1) + "%";
const withRank = (v, r, fmt) => v === null ? dash : `${fmt(v)}<span class="r">${r}</span>`;
// dir = 1: above the national average is good. dir = -1: below is good.
const cls = (v, nat, dir) => v === null ? "" : (dir * (v - nat) > 0 ? "pos" : dir * (v - nat) < 0 ? "neg" : "");

const weekLabel = w => w === 0 ? "Preseason" : w === POST_WEEK ? "Final (after bowls)" : `After week ${w}`;
const weeksOf = s => Object.keys(DATA[s]).map(Number).sort((a, b) => a - b);

Object.values(DATA).forEach(byWeek => Object.values(byWeek).forEach(rows => rows.forEach(r => {
  const t = TEAMS[r.team] || {};
  r.conf = t.conf || "";
  r.logo = t.logo || "";
  r.pct = pct(r.w, r.l, r.t);
  r.cpct = pct(r.cw, r.cl, r.ct);
  r.diff = r.pf - r.pa;
  r.rank = r.netRank;
})));

let season = SEASONS[0];
let week = weeksOf(season).slice(-1)[0];
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
  const all = DATA[season][week];
  const nat = NAT[season][week];
  const rows = all
    .filter(r => (!conf || r.conf === conf) && r.team.toLowerCase().includes(q))
    .sort(compare);

  document.getElementById("sub").textContent =
    `${season} season, ${weekLabel(week)}. National average: ${nat.toFixed(1)}% of available yards gained per drive. Click a column header to re-sort.`;

  const notes = [];
  if (all.some(r => r.wt !== null && r.wt < 100)) {
    notes.push("Teams with fewer than 8 rated games have ratings that blend last season's final rating with this season so far. The This Yr column shows the share coming from this season.");
  }
  if (season === CURRENT_SEASON && week === weeksOf(season).slice(-1)[0]) {
    notes.push("This season is in progress.");
  }
  document.getElementById("note").textContent = notes.join(" ");

  document.getElementById("head").innerHTML = COLS.map(c =>
    `<th data-key="${c.key}" class="${c.key === sortKey ? "active" : ""}">${c.label}${c.key === sortKey ? (sortDir < 0 ? " \\u25BC" : " \\u25B2") : ""}</th>`
  ).join("");

  document.getElementById("body").innerHTML = rows.map(r => `
    <tr>
      <td class="rank">${r.rank === null ? dash : r.rank}</td>
      <td><div class="team">${r.logo ? `<img src="${r.logo}" alt="" onerror="this.style.display='none'">` : ""}${r.team}</div></td>
      <td>${r.conf}</td>
      <td>${fmtRec(r.w, r.l, r.t)}</td>
      <td>${fmtRec(r.cw, r.cl, r.ct)}</td>
      <td class="${r.net > 0 ? "pos" : r.net < 0 ? "neg" : ""}">${withRank(r.net, r.netRank, signed)}</td>
      <td class="${cls(r.off, nat, 1)}">${withRank(r.off, r.offRank, level)}</td>
      <td class="${cls(r.def, nat, -1)}">${withRank(r.def, r.defRank, level)}</td>
      <td>${signed(r.sos)}</td>
      <td class="dim">${r.wt === null ? dash : r.wt + "%"}</td>
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
const weekSelect = document.getElementById("week");

function fillWeeks() {
  weekSelect.innerHTML = "";
  weeksOf(season).forEach(w => {
    const o = document.createElement("option");
    o.value = w;
    o.textContent = weekLabel(w);
    weekSelect.appendChild(o);
  });
  weekSelect.value = week;
}

SEASONS.forEach(s => {
  const o = document.createElement("option");
  o.value = o.textContent = s;
  seasonSelect.appendChild(o);
});
seasonSelect.onchange = () => {
  season = +seasonSelect.value;
  week = weeksOf(season).slice(-1)[0];   // jump to the latest week of that season
  fillWeeks();
  render();
};
weekSelect.onchange = () => { week = +weekSelect.value; render(); };

const confSelect = document.getElementById("conf");
[...new Set(Object.values(TEAMS).map(t => t.conf).filter(Boolean))].sort().forEach(c => {
  const o = document.createElement("option");
  o.value = o.textContent = c;
  confSelect.appendChild(o);
});
confSelect.onchange = render;
document.getElementById("search").oninput = render;

seasonSelect.value = season;
fillWeeks();
render();
</script>
</body>
</html>
"""


def main():
    teams = load_teams()
    ratings, week_map = load_weekly()
    seasons = sorted(week_map, reverse=True)

    team_info = {
        name: {"conf": t.get("conference") or "", "logo": (t.get("logos") or [""])[0]}
        for name, t in teams.items()
    }

    data, nat = {}, {}
    for season in seasons:
        games = load_games(season)
        data[season], nat[season] = {}, {}

        for week in week_map[season]:
            through = [g for g in games if game_week(g) <= week]
            rows = build_records(teams, through)
            for name, row in rows.items():
                row.update(ratings.get((season, week, name), {}))
            data[season][week] = list(rows.values())

            offs = [r["off"] for r in data[season][week] if r["off"] is not None]
            nat[season][week] = round(sum(offs) / len(offs), 2) if offs else 0.0

    def dump(obj):
        return json.dumps(obj, separators=(",", ":")).replace("</", "<\\/")

    html = (
        PAGE.replace("__DATA__", dump(data))
        .replace("__TEAMS__", dump(team_info))
        .replace("__SEASONS__", json.dumps(seasons))
        .replace("__NAT__", dump(nat))
        .replace("__CURRENT__", str(CURRENT_SEASON))
        .replace("__POSTWEEK__", str(POSTSEASON_WEEK))
    )

    OUT.mkdir(exist_ok=True)
    out_path = OUT / "index.html"
    out_path.write_text(html, encoding="utf-8")

    for season in seasons:
        print(f"{season}: {len(week_map[season])} week snapshots "
              f"({week_map[season][0]} to {week_map[season][-1]})")
    print(f"Wrote {out_path.resolve()} ({out_path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()