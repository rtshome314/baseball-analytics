"""
yahoo_data.py
Fetches roster, standings, and matchup data from Yahoo Fantasy Sports API.
Stats and fantasy points are calculated from local data sources.
"""

import requests
import streamlit as st
from xml.etree import ElementTree as ET
import unicodedata
import re


YAHOO_API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"

# Your custom scoring system
BATTER_SCORING = {
    "1B": 1,
    "2B": 2,
    "3B": 3,
    "HR": 4,
    "SB": 1,
    "CS": -1,
    "BB": 1,
    "IBB": 1,
    "HBP": 1,
    "SO": -0.5,
    "GIDP": -1,
}

PITCHER_SCORING = {
    "OUT": 1,       # Outs recorded (IP * 3)
    "BB": -1,
    "IBB": -0.5,
    "HBP": -1,
    "SO": 0.5,
    "WP": -1,
    "BLK": -1,      # Balks
    "GIDP": 1,      # Batters grounded into DP (induced)
    "TB": -1,       # Total bases allowed
}


# ===========================================================
# INTERNAL HELPERS
# ===========================================================

def _api_get(access_token, endpoint, params=None):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"{YAHOO_API_BASE}/{endpoint}"
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code == 200:
        return resp.text
    else:
        st.error(f"Yahoo API error {resp.status_code}: {resp.text[:300]}")
        return None


def _parse_xml(xml_text):
    if not xml_text:
        return None
    try:
        return ET.fromstring(xml_text)
    except ET.ParseError as e:
        st.error(f"XML parse error: {e}")
        return None


def _find_text(element, tag, ns):
    if element is None:
        return ""
    el = element.find(tag, ns)
    return el.text if el is not None and el.text else ""


def _normalize_name(s):
    """Normalize a player name for fuzzy matching."""
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = s.replace("'", "").replace("-", " ")
    s = re.sub(r"\s*\(.*?\)\s*$", "", s)  # remove Yahoo's (Batter)/(Pitcher) suffixes
    return s


# ===========================================================
# LEAGUE / TEAM INFO
# ===========================================================

def get_league_info(access_token, league_id):
    """Get basic league info."""
    xml = _api_get(access_token, f"league/mlb.l.{league_id}")
    root = _parse_xml(xml)
    if root is None:
        return None

    ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
    league = root.find(".//y:league", ns)
    if league is None:
        return None

    return {
        "name": _find_text(league, "y:name", ns),
        "season": _find_text(league, "y:season", ns),
        "num_teams": _find_text(league, "y:num_teams", ns),
        "league_key": _find_text(league, "y:league_key", ns),
        "current_week": _find_text(league, "y:current_week", ns),
        "start_week": _find_text(league, "y:start_week", ns),
    }


def get_teams(access_token, league_id):
    """Get all teams in the league."""
    xml = _api_get(access_token, f"league/mlb.l.{league_id}/teams")
    root = _parse_xml(xml)
    if root is None:
        return []

    ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
    teams = []
    for team in root.findall(".//y:team", ns):
        team_key = _find_text(team, "y:team_key", ns)
        team_name = _find_text(team, "y:name", ns)
        manager_el = team.find(".//y:manager", ns)
        manager = _find_text(manager_el, "y:nickname", ns) if manager_el is not None else ""
        teams.append({
            "team_key": team_key,
            "name": team_name,
            "manager": manager,
        })
    return teams


def get_my_team_key(access_token, league_id):
    """Find the team key for the authenticated user."""
    xml = _api_get(access_token, f"league/mlb.l.{league_id}/teams")
    root = _parse_xml(xml)
    if root is None:
        return None

    ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
    for team in root.findall(".//y:team", ns):
        is_owned = team.find("y:is_owned_by_current_login", ns)
        if is_owned is not None and is_owned.text == "1":
            return _find_text(team, "y:team_key", ns)
    return None


def get_roster(access_token, team_key):
    """Get current roster for a team."""
    xml = _api_get(access_token, f"team/{team_key}/roster/players")
    root = _parse_xml(xml)
    if root is None:
        return []

    ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
    players = []
    for player in root.findall(".//y:player", ns):
        name_el = player.find("y:name", ns)
        full_name = _find_text(name_el, "y:full", ns) if name_el else ""
        pos_el = player.find("y:eligible_positions", ns)
        positions = [p.text for p in pos_el.findall("y:position", ns)] if pos_el else []
        players.append({
            "name": full_name,
            "player_key": _find_text(player, "y:player_key", ns),
            "positions": positions,
            "editorial_team": _find_text(player, "y:editorial_team_abbr", ns),
            "status": _find_text(player, "y:status", ns) or "Active",
        })
    return players


def get_roster_player_names(access_token, team_key):
    """Returns just a list of player names for filtering other views."""
    roster = get_roster(access_token, team_key)
    return [p["name"] for p in roster]


# ===========================================================
# STANDINGS
# ===========================================================

def get_league_standings(access_token, league_id):
    """
    Fetch official standings from Yahoo.
    Returns list of dicts with W, L, T, Pct, total points, points against.
    """
    xml = _api_get(access_token, f"league/mlb.l.{league_id}/standings")
    root = _parse_xml(xml)
    if root is None:
        return []

    ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
    standings = []
    for team in root.findall(".//y:team", ns):
        name = _find_text(team, "y:name", ns)
        team_key = _find_text(team, "y:team_key", ns)

        ts = team.find(".//y:team_standings", ns)
        outcomes = ts.find("y:outcome_totals", ns) if ts is not None else None
        wins = int(_find_text(outcomes, "y:wins", ns) or 0)
        losses = int(_find_text(outcomes, "y:losses", ns) or 0)
        ties = int(_find_text(outcomes, "y:ties", ns) or 0)
        pct = float(_find_text(outcomes, "y:percentage", ns) or 0)

        pts_for_el = ts.find("y:points_for", ns) if ts is not None else None
        pts_against_el = ts.find("y:points_against", ns) if ts is not None else None
        total_pts = float(pts_for_el.text) if pts_for_el is not None and pts_for_el.text else 0.0
        pts_against = float(pts_against_el.text) if pts_against_el is not None and pts_against_el.text else 0.0

        rank_el = ts.find("y:rank", ns) if ts is not None else None
        rank = int(rank_el.text) if rank_el is not None and rank_el.text else 0

        standings.append({
            "Rank": rank,
            "Team": name,
            "team_key": team_key,
            "W": wins,
            "L": losses,
            "T": ties,
            "Pct": pct,
            "Total Pts": total_pts,
            "Pts Against": pts_against,
        })

    return sorted(standings, key=lambda x: x["Rank"])


# ===========================================================
# WEEKLY MATCHUP DATA (for hitter/pitcher split)
# ===========================================================


def get_weekly_player_stats(access_token, league_id, teams, start_week, current_week):
    """
    Fetch per-player fantasy points for each team for each week.
    Excludes bench (BN) and IL slots so totals match Yahoo's official scoring.
    Returns a DataFrame with columns: team, week, player, position, lineup_slot, is_pitcher, is_active, fan_pts
    """
    import pandas as pd
    ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
    rows = []

    PITCHER_POSITIONS = {"SP", "RP", "P"}
    INACTIVE_SLOTS = {"BN", "IL", "IL+", "NA"}

    for week in range(int(start_week), int(current_week) + 1):
        for team in teams:
            team_key = team["team_key"]
            team_name = team["name"]

            xml = _api_get(
                access_token,
                f"team/{team_key}/roster;week={week}/players/stats;type=week;week={week}"
            )
            root = _parse_xml(xml)
            if root is None:
                continue

            for player in root.findall(".//y:player", ns):
                name_el = player.find("y:name", ns)
                name = _find_text(name_el, "y:full", ns) if name_el else ""
                display_pos = _find_text(player, "y:display_position", ns)

                # Get the lineup slot (the position they were slotted into that week)
                selected_pos_el = player.find(".//y:selected_position/y:position", ns)
                lineup_slot = selected_pos_el.text if selected_pos_el is not None and selected_pos_el.text else ""

                # Skip bench and IL
                is_active = lineup_slot not in INACTIVE_SLOTS

                # Get fantasy points
                pts_el = player.find(".//y:player_points/y:total", ns)
                fan_pts = float(pts_el.text) if pts_el is not None and pts_el.text else 0.0

                is_pitcher = any(p in display_pos.split(",") for p in PITCHER_POSITIONS)

                rows.append({
                    "team": team_name,
                    "week": week,
                    "player": name,
                    "position": display_pos,
                    "lineup_slot": lineup_slot,
                    "is_pitcher": is_pitcher,
                    "is_active": is_active,
                    "fan_pts": fan_pts,
                })

    return pd.DataFrame(rows)

def get_weekly_team_points(access_token, league_id, teams, start_week, current_week):
    """
    Pull week-by-week points for each team broken down by hitter/pitcher.
    Returns a list of dicts: {team, week, hitter_pts, pitcher_pts, total_pts, opponent, win}
    """
    ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
    weekly_data = []

    weeks = list(range(int(start_week), int(current_week) + 1))

    for team in teams:
        team_key = team["team_key"]
        team_name = team["name"]

        for week in weeks:
            # Get matchup for this week
            xml = _api_get(access_token, f"team/{team_key}/matchups;weeks={week}")
            root = _parse_xml(xml)
            if root is None:
                continue

            for matchup in root.findall(".//y:matchup", ns):
                week_num = _find_text(matchup, "y:week", ns)
                status = _find_text(matchup, "y:status", ns)
                is_tied = _find_text(matchup, "y:is_tied", ns)

                # Find this team's stats in the matchup
                for team_el in matchup.findall(".//y:team", ns):
                    t_key = _find_text(team_el, "y:team_key", ns)
                    if t_key != team_key:
                        continue

                    # Points for this team this week
                    pts_el = team_el.find(".//y:team_points/y:total", ns)
                    total_pts = float(pts_el.text) if pts_el is not None and pts_el.text else 0.0

                    # Win/loss
                    win_el = team_el.find(".//y:team_standings/y:outcome_totals/y:wins", ns)
                    loss_el = team_el.find(".//y:team_standings/y:outcome_totals/y:losses", ns)
                    week_wins = int(win_el.text) if win_el is not None and win_el.text else 0
                    week_losses = int(loss_el.text) if loss_el is not None and loss_el.text else 0
                    result = "W" if week_wins > 0 else ("L" if week_losses > 0 else "T")

                    weekly_data.append({
                        "team": team_name,
                        "team_key": team_key,
                        "week": int(week_num) if week_num else week,
                        "total_pts": total_pts,
                        "result": result,
                        "status": status,
                    })
                    break

    return weekly_data


# ===========================================================
# ROSTER ASSIGNMENTS (for local data join)
# ===========================================================

def get_all_rosters(access_token, teams):
    """
    Get all rostered player names across all teams.
    Returns dict: normalized_name -> {fantasy_team, positions, mlb_team, status}
    """
    from collections import defaultdict
    rosters = {}

    for team in teams:
        roster = get_roster(access_token, team["team_key"])
        for player in roster:
            norm = _normalize_name(player["name"])
            rosters[norm] = {
                "yahoo_name": player["name"],
                "fantasy_team": team["name"],
                "team_key": team["team_key"],
                "positions": player["positions"],
                "mlb_team": player["editorial_team"],
                "status": player["status"],
            }

    return rosters



def build_player_scoring_from_statcast(statcast_df, rosters, start_date=None, end_date=None):
    """
    Calculate fantasy points for batters from Statcast pitch-level data filtered by date range.
    For pitchers, calculates approximate points (missing WP, BLK, GIDP induced).
    Returns (batter_df, pitcher_df)
    """
    import pandas as pd
    from datetime import date

    if statcast_df.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = statcast_df.copy()
    df["game_date"] = pd.to_datetime(df["game_date"])

    if start_date:
        df = df[df["game_date"].dt.date >= start_date]
    if end_date:
        df = df[df["game_date"].dt.date <= end_date]

    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    def get_fantasy_info(name):
        norm = _normalize_name(str(name))
        if norm in rosters:
            return rosters[norm]["fantasy_team"], False
        return "Free Agent", True

    # ---- BATTERS ----
    ab_events = ["single", "double", "triple", "home_run", "strikeout",
                 "field_out", "grounded_into_double_play", "force_out",
                 "fielders_choice", "fielders_choice_out", "double_play",
                 "field_error", "strikeout_double_play", "triple_play"]
    hits = ["single", "double", "triple", "home_run"]

    batter_df = df[df["events"].notna()].copy()
    batter_df["is_1b"] = (batter_df["events"] == "single").astype(int)
    batter_df["is_2b"] = (batter_df["events"] == "double").astype(int)
    batter_df["is_3b"] = (batter_df["events"] == "triple").astype(int)
    batter_df["is_hr"] = (batter_df["events"] == "home_run").astype(int)
    batter_df["is_bb"] = batter_df["events"].isin(["walk"]).astype(int)
    batter_df["is_ibb"] = batter_df["events"].isin(["intent_walk"]).astype(int)
    batter_df["is_hbp"] = (batter_df["events"] == "hit_by_pitch").astype(int)
    batter_df["is_so"] = batter_df["events"].str.contains("strikeout", na=False).astype(int)
    batter_df["is_sb"] = (batter_df["events"] == "stolen_base_2b").astype(int)  # approximation
    batter_df["is_cs"] = (batter_df["events"] == "caught_stealing_2b").astype(int)
    batter_df["is_gidp"] = (batter_df["events"] == "grounded_into_double_play").astype(int)
    batter_df["is_ab"] = batter_df["events"].isin(ab_events).astype(int)
    batter_df["is_hit"] = batter_df["events"].isin(hits).astype(int)
    batter_df["is_sf"] = (batter_df["events"] == "sac_fly").astype(int)

    # Need batter names - use batter_lookup if available
    has_name = "batter_name" in batter_df.columns

    if has_name:
        group_col = "batter_name"
    else:
        group_col = "batter"

    batter_agg = batter_df.groupby(group_col).agg(
        singles=("is_1b", "sum"),
        doubles=("is_2b", "sum"),
        triples=("is_3b", "sum"),
        hr=("is_hr", "sum"),
        bb=("is_bb", "sum"),
        ibb=("is_ibb", "sum"),
        hbp=("is_hbp", "sum"),
        so=("is_so", "sum"),
        sb=("is_sb", "sum"),
        cs=("is_cs", "sum"),
        gidp=("is_gidp", "sum"),
        ab=("is_ab", "sum"),
        h=("is_hit", "sum"),
        sf=("is_sf", "sum"),
    ).reset_index()

    batter_rows = []
    for _, row in batter_agg.iterrows():
        name = str(row[group_col])
        fantasy_team, is_fa = get_fantasy_info(name)
        stats = {
            "1B": row["singles"], "2B": row["doubles"], "3B": row["triples"],
            "HR": row["hr"], "BB": row["bb"], "IBB": row["ibb"],
            "HBP": row["hbp"], "SO": row["so"], "SB": row["sb"],
            "CS": row["cs"], "GIDP": row["gidp"],
        }
        fpts = calculate_batter_score(stats)
        pa = row["ab"] + row["bb"] + row["ibb"] + row["hbp"] + row["sf"]
        avg = round(row["h"] / row["ab"], 3) if row["ab"] > 0 else 0
        obp_denom = row["ab"] + row["bb"] + row["ibb"] + row["hbp"] + row["sf"]
        obp = round((row["h"] + row["bb"] + row["ibb"] + row["hbp"]) / obp_denom, 3) if obp_denom > 0 else 0
        slg_num = row["singles"] + 2*row["doubles"] + 3*row["triples"] + 4*row["hr"]
        slg = round(slg_num / row["ab"], 3) if row["ab"] > 0 else 0

        batter_rows.append({
            "Name": name,
            "Fantasy Team": fantasy_team,
            "Is FA": is_fa,
            "Fantasy Pts": fpts,
            "Pts/PA": round(fpts / pa, 3) if pa > 0 else 0,
            "PA": int(pa),
            "AVG": avg,
            "OBP": obp,
            "SLG": slg,
            "OPS": round(obp + slg, 3),
            "H": int(row["h"]),
            "1B": int(row["singles"]),
            "2B": int(row["doubles"]),
            "3B": int(row["triples"]),
            "HR": int(row["hr"]),
            "BB": int(row["bb"]),
            "SB": int(row["sb"]),
            "CS": int(row["cs"]),
            "SO": int(row["so"]),
            "HBP": int(row["hbp"]),
            "GIDP": int(row["gidp"]),
        })

    # ---- PITCHERS (approximate) ----
    pitcher_df_raw = df.copy()
    pitcher_agg = pitcher_df_raw.groupby("player_name").agg(
        outs=("type", lambda x: (x == "X").sum() + (x == "S").sum()),  # approximate
        so=("events", lambda x: x.str.contains("strikeout", na=False).sum()),
        bb=("events", lambda x: x.isin(["walk"]).sum()),
        ibb=("events", lambda x: x.isin(["intent_walk"]).sum()),
        hbp=("events", lambda x: x.isin(["hit_by_pitch"]).sum()),
        h_allowed=("events", lambda x: x.isin(["single","double","triple","home_run"]).sum()),
        doubles_allowed=("events", lambda x: x.isin(["double"]).sum()),
        triples_allowed=("events", lambda x: x.isin(["triple"]).sum()),
        hr_allowed=("events", lambda x: x.isin(["home_run"]).sum()),
    ).reset_index()

    # Better out estimate: use outs_when_up delta
    if "outs_when_up" in df.columns and "events" in df.columns:
        end_events = df[df["events"].notna()].copy()
        out_counts = end_events.groupby("player_name").apply(
            lambda g: (g["events"].isin(["strikeout","field_out","grounded_into_double_play",
                                          "force_out","fielders_choice_out","double_play",
                                          "strikeout_double_play","triple_play"])).sum() +
                      g["events"].isin(["grounded_into_double_play","double_play","triple_play"]).sum()
        ).reset_index()
        out_counts.columns = ["player_name", "estimated_outs"]
        pitcher_agg = pitcher_agg.merge(out_counts, on="player_name", how="left")
        pitcher_agg["outs"] = pitcher_agg["estimated_outs"].fillna(pitcher_agg["outs"])

    pitcher_rows = []
    for _, row in pitcher_agg.iterrows():
        name = str(row["player_name"])
        fantasy_team, is_fa = get_fantasy_info(name)
        outs = row.get("estimated_outs", row["outs"])
        ip = round(outs / 3, 1)
        tb_allowed = (row["h_allowed"] - row["doubles_allowed"] - row["triples_allowed"] - row["hr_allowed"] +
                      2*row["doubles_allowed"] + 3*row["triples_allowed"] + 4*row["hr_allowed"])

        stats = {
            "OUT": outs, "IP": ip,
            "SO": row["so"], "BB": row["bb"], "IBB": row["ibb"],
            "HBP": row["hbp"], "TB": tb_allowed,
            "WP": 0, "BLK": 0, "GIDP": 0,  # not available in Statcast
        }
        fpts = calculate_pitcher_score(stats)

        pitcher_rows.append({
            "Name": name,
            "Fantasy Team": fantasy_team,
            "Is FA": is_fa,
            "Fantasy Pts": fpts,
            "Pts/IP": round(fpts / ip, 3) if ip > 0 else 0,
            "IP": ip,
            "SO": int(row["so"]),
            "BB": int(row["bb"]),
            "HBP": int(row["hbp"]),
            "H Allowed": int(row["h_allowed"]),
            "HR Allowed": int(row["hr_allowed"]),
        })

    return pd.DataFrame(batter_rows), pd.DataFrame(pitcher_rows)

# ===========================================================
# SCORING CALCULATIONS (from local stats)
# ===========================================================

def calculate_batter_score(stats: dict) -> float:
    """Calculate fantasy points for a batter from a stats dict."""
    stats = dict(stats)
    if "1B" not in stats:
        h = stats.get("H", 0)
        doubles = stats.get("2B", 0)
        triples = stats.get("3B", 0)
        hrs = stats.get("HR", 0)
        stats["1B"] = max(0, h - doubles - triples - hrs)

    score = 0.0
    for stat, multiplier in BATTER_SCORING.items():
        score += stats.get(stat, 0) * multiplier
    return round(score, 2)


def calculate_pitcher_score(stats: dict) -> float:
    """Calculate fantasy points for a pitcher from a stats dict."""
    stats = dict(stats)
    if "IP" in stats and "OUT" not in stats:
        stats["OUT"] = round(stats["IP"] * 3)
    score = 0.0
    for stat, multiplier in PITCHER_SCORING.items():
        score += stats.get(stat, 0) * multiplier
    return round(score, 2)


def build_player_scoring_table(batting_df, pitching_df, rosters):
    """
    Build a combined player scoring table from local stats data.
    Joins roster assignments, calculates fantasy points.
    batting_df: from load_batting_stats()
    pitching_df: from load_pitching_stats()
    rosters: from get_all_rosters()
    Returns two DataFrames: batter_df, pitcher_df
    """
    import pandas as pd

    def get_fantasy_info(name):
        norm = _normalize_name(str(name))
        if norm in rosters:
            r = rosters[norm]
            return r["fantasy_team"], False
        return "Free Agent", True

    # --- BATTERS ---
    batter_rows = []
    if not batting_df.empty and "Name" in batting_df.columns:
        for _, row in batting_df.iterrows():
            name = row.get("Name", "")
            fantasy_team, is_fa = get_fantasy_info(name)

            stats = {
                "H": row.get("H", 0) or 0,
                "2B": row.get("2B", 0) or 0,
                "3B": row.get("3B", 0) or 0,
                "HR": row.get("HR", 0) or 0,
                "BB": row.get("BB", 0) or 0,
                "IBB": row.get("IBB", 0) or 0,
                "SB": row.get("SB", 0) or 0,
                "CS": row.get("CS", 0) or 0,
                "SO": row.get("SO", 0) or 0,
                "HBP": row.get("HBP", 0) or 0,
                "GIDP": row.get("GIDP", 0) or row.get("GDP", 0) or 0,
                "SF": row.get("SF", 0) or 0,
                "AB": row.get("AB", 0) or 0,
            }
            fpts = calculate_batter_score(stats)
            pa = row.get("PA", stats["AB"] + stats["BB"] + stats["HBP"] + stats["SF"]) or 0
            pts_per_pa = round(fpts / pa, 3) if pa > 0 else 0

            batter_rows.append({
                "Name": name,
                "Fantasy Team": fantasy_team,
                "Is FA": is_fa,
                "MLB Team": row.get("Team", ""),
                "Fantasy Pts": fpts,
                "Pts/PA": pts_per_pa,
                "PA": pa,
                "AVG": row.get("AVG", 0) or 0,
                "OBP": row.get("OBP", 0) or 0,
                "SLG": row.get("SLG", 0) or 0,
                "OPS": row.get("OPS", 0) or 0,
                "H": stats["H"],
                "1B": stats.get("1B", 0),
                "2B": stats["2B"],
                "3B": stats["3B"],
                "HR": stats["HR"],
                "BB": stats["BB"],
                "SB": stats["SB"],
                "CS": stats["CS"],
                "SO": stats["SO"],
                "HBP": stats["HBP"],
                "GIDP": stats["GIDP"],
            })

    # --- PITCHERS ---
    pitcher_rows = []
    if not pitching_df.empty and "Name" in pitching_df.columns:
        for _, row in pitching_df.iterrows():
            name = row.get("Name", "")
            fantasy_team, is_fa = get_fantasy_info(name)

            import math
            def _safe(v): return 0 if (v is None or (isinstance(v, float) and math.isnan(v))) else v

            ip = _safe(row.get("IP", 0))
            so = _safe(row.get("SO", 0))
            bb = _safe(row.get("BB", 0))
            ibb = _safe(row.get("IBB", 0))
            hbp = _safe(row.get("HBP", 0))
            wp = _safe(row.get("WP", 0))
            blk = _safe(row.get("BK", 0)) or _safe(row.get("BLK", 0))
            gdp = _safe(row.get("GDP", 0)) or _safe(row.get("GIDP", 0))
            h_allowed = _safe(row.get("H", 0))
            hr_allowed = _safe(row.get("HR", 0))
            doubles_allowed = _safe(row.get("2B", 0))
            triples_allowed = _safe(row.get("3B", 0))

            tb_allowed = h_allowed + doubles_allowed + 2 * triples_allowed + 3 * hr_allowed

            stats = {
                "IP": ip,
                "OUT": round(ip * 3),
                "SO": so,
                "BB": bb,
                "IBB": ibb,
                "HBP": hbp,
                "WP": wp,
                "BLK": blk,
                "GIDP": gdp,
                "TB": tb_allowed,
            }
            fpts = calculate_pitcher_score(stats)
            pts_per_ip = round(fpts / ip, 3) if ip > 0 else 0

            era = row.get("ERA", 0) or 0
            whip = row.get("WHIP", 0) or 0
            # K% = SO / BF (batters faced); approximate from BF if available
            bf = row.get("BF", 0) or 0
            k_pct = round(so / bf * 100, 1) if bf > 0 else 0

            pitcher_rows.append({
                "Name": name,
                "Fantasy Team": fantasy_team,
                "Is FA": is_fa,
                "MLB Team": row.get("Tm", row.get("Team", "")),
                "Fantasy Pts": fpts,
                "Pts/IP": pts_per_ip,
                "IP": ip,
                "ERA": era,
                "WHIP": whip,
                "K%": k_pct,
                "SO": so,
                "BB": bb,
                "HBP": hbp,
                "WP": wp,
                "BLK": blk,
                "GIDP": gdp,
            })

    return pd.DataFrame(batter_rows), pd.DataFrame(pitcher_rows)


def build_team_standings_with_splits(standings, batter_df, pitcher_df):
    """
    Enrich the Yahoo standings with hitter/pitcher point splits from local data.
    Uses current rosters as approximation (doesn't account for mid-season adds/drops).
    Weekly matchup data handles that more accurately when available.
    """
    import pandas as pd

    team_hitter_pts = batter_df[~batter_df["Is FA"]].groupby("Fantasy Team")["Fantasy Pts"].sum().to_dict()
    team_pitcher_pts = pitcher_df[~pitcher_df["Is FA"]].groupby("Fantasy Team")["Fantasy Pts"].sum().to_dict()

    for s in standings:
        team = s["Team"]
        s["Hitter Pts"] = round(team_hitter_pts.get(team, 0), 1)
        s["Pitcher Pts"] = round(team_pitcher_pts.get(team, 0), 1)

    return standings


# ===========================================================
# DRAFT RESULTS
# ===========================================================

def get_draft_results(access_token, league_id):
    """
    Fetch full draft results for the league.
    Handles both snake drafts (<draft_pick>) and auction drafts (<auction_draft_pick>).
    Returns list of dicts: {pick, round, cost, team_key, team_name, player_key, player_name, position, mlb_team}
    Player names resolved by cross-referencing all team rosters.
    Players dropped since the draft will fall back to player_key as their name.
    """
    xml = _api_get(access_token, f"league/mlb.l.{league_id}/draftresults")
    root = _parse_xml(xml)
    if root is None:
        return [], xml

    ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}

    # Build team_key -> team_name map
    teams_xml = _api_get(access_token, f"league/mlb.l.{league_id}/teams")
    teams_root = _parse_xml(teams_xml)
    team_map = {}
    if teams_root is not None:
        for team in teams_root.findall(".//y:team", ns):
            tk = _find_text(team, "y:team_key", ns)
            tn = _find_text(team, "y:name", ns)
            if tk:
                team_map[tk] = tn

    # Build player_key -> player info map from all rosters
    player_map = {}
    if teams_root is not None:
        for team in teams_root.findall(".//y:team", ns):
            tk = _find_text(team, "y:team_key", ns)
            if not tk:
                continue
            roster_xml = _api_get(access_token, f"team/{tk}/roster/players")
            roster_root = _parse_xml(roster_xml)
            if roster_root is None:
                continue
            for player in roster_root.findall(".//y:player", ns):
                pk = _find_text(player, "y:player_key", ns)
                name_el = player.find("y:name", ns)
                pname = _find_text(name_el, "y:full", ns) if name_el else ""
                display_pos = _find_text(player, "y:display_position", ns)
                mlb_team = _find_text(player, "y:editorial_team_abbr", ns)
                if pk:
                    player_map[pk] = {
                        "name": pname,
                        "position": display_pos,
                        "mlb_team": mlb_team,
                    }

    picks = []
    num_teams = len(team_map) or 1
    is_auction = False

    # Yahoo uses <draft_result> for both auction and snake drafts.
    # Auction drafts include a <cost> field; snake drafts do not.
    all_picks = root.findall(".//y:draft_result", ns)

    for pick_el in all_picks:
        pick_num = int(_find_text(pick_el, "y:pick", ns) or 0)
        round_num = int(_find_text(pick_el, "y:round", ns) or 0)
        team_key = _find_text(pick_el, "y:team_key", ns)
        player_key = _find_text(pick_el, "y:player_key", ns)
        cost_str = _find_text(pick_el, "y:cost", ns)
        cost = int(cost_str) if cost_str and cost_str.isdigit() else None

        if cost is not None:
            is_auction = True

        if round_num == 0 and pick_num > 0 and not is_auction:
            round_num = ((pick_num - 1) // num_teams) + 1

        player_info = player_map.get(player_key, {})
        player_name = player_info.get("name") or player_key
        position = player_info.get("position", "")
        mlb_team = player_info.get("mlb_team", "")

        picks.append({
            "pick": pick_num,
            "round": round_num if not is_auction else None,
            "cost": cost,
            "team_key": team_key,
            "team_name": team_map.get(team_key, team_key),
            "player_key": player_key,
            "player_name": player_name,
            "position": position,
            "mlb_team": mlb_team,
            "is_auction": is_auction,
        })

    return sorted(picks, key=lambda x: x["cost"] if is_auction else x["pick"], reverse=is_auction), xml


# ===========================================================
# CURRENT / ACTIVE MATCHUPS
# ===========================================================

def get_current_matchups(access_token, league_id, week=None):
    """
    Fetch the current (or specified) week's matchup pairings and scores from Yahoo.
    Returns list of dicts, each representing one matchup:
    {
        week, matchup_index,
        team1_key, team1_name, team1_pts,
        team2_key, team2_name, team2_pts,
        status, is_tied, winner_team_key
    }
    """
    endpoint = f"league/mlb.l.{league_id}/scoreboard"
    if week:
        endpoint += f";week={week}"

    xml = _api_get(access_token, endpoint)
    root = _parse_xml(xml)
    if root is None:
        return []

    ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
    matchups = []

    for i, matchup_el in enumerate(root.findall(".//y:matchup", ns)):
        week_num = _find_text(matchup_el, "y:week", ns)
        status = _find_text(matchup_el, "y:status", ns)
        is_tied = _find_text(matchup_el, "y:is_tied", ns)
        winner_key = _find_text(matchup_el, "y:winner_team_key", ns)

        teams_el = matchup_el.findall(".//y:team", ns)
        if len(teams_el) < 2:
            continue

        def extract_team(team_el):
            tk = _find_text(team_el, "y:team_key", ns)
            tn = _find_text(team_el, "y:name", ns)
            pts_el = team_el.find(".//y:team_points/y:total", ns)
            pts = float(pts_el.text) if pts_el is not None and pts_el.text else 0.0
            proj_el = team_el.find(".//y:team_projected_points/y:total", ns)
            proj = float(proj_el.text) if proj_el is not None and proj_el.text else 0.0
            return {"key": tk, "name": tn, "pts": pts, "projected": proj}

        t1 = extract_team(teams_el[0])
        t2 = extract_team(teams_el[1])

        matchups.append({
            "week": int(week_num) if week_num else None,
            "matchup_index": i,
            "team1_key": t1["key"],
            "team1_name": t1["name"],
            "team1_pts": t1["pts"],
            "team1_projected": t1["projected"],
            "team2_key": t2["key"],
            "team2_name": t2["name"],
            "team2_pts": t2["pts"],
            "team2_projected": t2["projected"],
            "status": status,
            "is_tied": is_tied == "1",
            "winner_team_key": winner_key,
        })

    return matchups


# ===========================================================
# BOOKMARK SYNC
# ===========================================================

def sync_rosters_to_bookmarks(access_token, league_id, available_players, bookmarks_file):
    """
    Fetches all team rosters from Yahoo and saves them as bookmarks.
    Returns (updated_bookmarks, match_report).
    """
    import json, os, glob
    from collections import defaultdict

    normalized_available = {_normalize_name(p): p for p in available_players}

    last_name_lookup = defaultdict(list)
    for norm_name, real_name in normalized_available.items():
        parts = norm_name.split()
        if parts:
            last_name_lookup[parts[-1]].append(real_name)

    # Also load batter_lookup for more complete early-season coverage
    data_dir = os.path.dirname(bookmarks_file)
    for lookup_file in glob.glob(os.path.join(data_dir, "batter_lookup_*.parquet")):
        try:
            import pandas as pd
            lookup_df = pd.read_parquet(lookup_file)
            if "batter_name" in lookup_df.columns:
                for name in lookup_df["batter_name"].dropna().unique():
                    norm = _normalize_name(str(name))
                    if norm not in normalized_available:
                        normalized_available[norm] = str(name)
                        parts = norm.split()
                        if parts:
                            last_name_lookup[parts[-1]].append(str(name))
        except Exception:
            pass

    def fuzzy_match(yahoo_name):
        n = _normalize_name(yahoo_name)
        if n in normalized_available:
            return normalized_available[n]
        parts = n.split()
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            for candidate in last_name_lookup.get(last, []):
                if _normalize_name(candidate).startswith(first):
                    return candidate
        if len(parts) >= 1:
            candidates = last_name_lookup.get(parts[-1], [])
            if len(candidates) == 1:
                return candidates[0]
        return None

    teams = get_teams(access_token, league_id)
    if not teams:
        return None, "Could not load teams from Yahoo."

    bookmarks = {}
    if os.path.exists(bookmarks_file):
        with open(bookmarks_file, "r") as f:
            bookmarks = json.load(f)

    match_report = []
    for team in teams:
        roster = get_roster(access_token, team["team_key"])
        matched, unmatched = [], []
        for player in roster:
            match = fuzzy_match(player["name"])
            if match:
                matched.append(match)
            else:
                unmatched.append(player["name"])
        bookmarks[f"Fantasy: {team['name']}"] = matched
        match_report.append({"team": team["name"], "matched": len(matched), "unmatched": unmatched})

    os.makedirs(os.path.dirname(bookmarks_file), exist_ok=True)
    with open(bookmarks_file, "w") as f:
        json.dump(bookmarks, f, indent=2)

    return bookmarks, match_report
