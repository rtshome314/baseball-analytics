"""
yahoo_data.py
Fetches roster, matchup, and stat data from Yahoo Fantasy Sports API.
"""

import requests
import streamlit as st
from xml.etree import ElementTree as ET


YAHOO_API_BASE = "https://fantasysports.yahooapis.com/fantasy/v2"

# Your scoring system
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
    "GIDP": 1,      # Batters grounded into DP
    "TB": -1,       # Total bases allowed
}


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


def get_matchups(access_token, league_id, team_key, weeks=None):
    """Get matchup results for the season or specific weeks."""
    if weeks:
        week_param = ",".join(str(w) for w in weeks)
        xml = _api_get(access_token, f"team/{team_key}/matchups;weeks={week_param}")
    else:
        xml = _api_get(access_token, f"team/{team_key}/matchups")
    root = _parse_xml(xml)
    if root is None:
        return []

    ns = {"y": "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"}
    matchups = []
    for matchup in root.findall(".//y:matchup", ns):
        week = _find_text(matchup, "y:week", ns)
        week_start = _find_text(matchup, "y:week_start", ns)
        week_end = _find_text(matchup, "y:week_end", ns)
        status = _find_text(matchup, "y:status", ns)
        matchups.append({
            "week": week,
            "week_start": week_start,
            "week_end": week_end,
            "status": status,
        })
    return matchups


def calculate_batter_score(stats: dict) -> float:
    """
    Calculate fantasy points for a batter given a stats dict.
    Stats dict keys should match BATTER_SCORING keys.
    Singles must be calculated as H - 2B - 3B - HR if not provided directly.
    """
    # Derive singles if not provided
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
    """
    Calculate fantasy points for a pitcher given a stats dict.
    IP should be converted to outs (IP * 3).
    """
    score = 0.0
    # Convert IP to outs if needed
    if "IP" in stats and "OUT" not in stats:
        stats["OUT"] = stats["IP"] * 3
    for stat, multiplier in PITCHER_SCORING.items():
        score += stats.get(stat, 0) * multiplier
    return round(score, 2)


def _find_text(element, tag, ns):
    if element is None:
        return ""
    el = element.find(tag, ns)
    return el.text if el is not None and el.text else ""
