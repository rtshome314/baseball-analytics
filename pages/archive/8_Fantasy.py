import streamlit as st
import pandas as pd
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.style import inject_custom_css, render_header
from utils.yahoo_auth import render_auth_flow, get_valid_token, logout
from utils.yahoo_data import (
    get_league_info, get_teams, get_my_team_key,
    get_roster, BATTER_SCORING, PITCHER_SCORING
)
from config import YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, YAHOO_LEAGUE_ID

st.set_page_config(page_title="Fantasy", page_icon="⚾", layout="wide")
inject_custom_css()
render_header()

st.markdown("## 🏆 Fantasy Baseball")

# --- Auth ---
authenticated = render_auth_flow(YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET)
if not authenticated:
    st.stop()

access_token = get_valid_token(YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET)

# --- Sidebar logout ---
with st.sidebar:
    if st.button("Disconnect Yahoo Account"):
        logout()
        st.rerun()

# --- Load league + teams ---
with st.spinner("Loading league data..."):
    league_info = get_league_info(access_token, YAHOO_LEAGUE_ID)
    teams = get_teams(access_token, YAHOO_LEAGUE_ID)
    my_team_key = get_my_team_key(access_token, YAHOO_LEAGUE_ID)

if league_info:
    st.markdown(f"**League:** {league_info.get('name', '')} &nbsp;|&nbsp; **Season:** {league_info.get('season', '')} &nbsp;|&nbsp; **Teams:** {league_info.get('num_teams', '')}")

st.markdown("---")

# --- Sync rosters to bookmarks ---
from utils.yahoo_data import sync_rosters_to_bookmarks
from utils.data_loader import load_batting_stats, load_pitching_stats

BOOKMARKS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bookmarks.json")

col_sync, col_info = st.columns([1, 3])
with col_sync:
    if st.button("🔄 Sync Rosters to Bookmarks", use_container_width=True):
        with st.spinner("Fetching rosters and matching players..."):
            # Load all available player names from both batting and pitching
            batting = load_batting_stats(2026)
            pitching = load_pitching_stats(2026)
            all_players = []
            if not batting.empty and "Name" in batting.columns:
                all_players += batting["Name"].dropna().tolist()
            if not pitching.empty and "Name" in pitching.columns:
                all_players += pitching["Name"].dropna().tolist()
            all_players = list(set(all_players))

            bookmarks, report = sync_rosters_to_bookmarks(
                access_token, YAHOO_LEAGUE_ID, all_players, BOOKMARKS_FILE
            )

        if bookmarks:
            st.success("✅ Rosters synced! Fantasy team bookmarks are now available in Player Comparison.")
            for r in report:
                unmatched_str = ", ".join(r["unmatched"]) if r["unmatched"] else "None"
                st.markdown(f"**{r['team']}** — {r['matched']} matched | Unmatched: {unmatched_str}")
        else:
            st.error("Failed to sync rosters.")
with col_info:
    st.info("Sync your Yahoo rosters to create bookmarks in Player Comparison. Run this whenever rosters change.")

# --- Team selector ---
tab1, tab2, tab3 = st.tabs(["📋 My Roster", "🏅 All Teams", "📊 Scoring System"])

# ================================================================
# TAB 1: MY ROSTER
# ================================================================
with tab1:
    if not my_team_key:
        st.warning("Could not identify your team. Make sure you're logged in with the account that owns a team in this league.")
    else:
        my_team_name = next((t["name"] for t in teams if t["team_key"] == my_team_key), "My Team")
        st.markdown(f"### {my_team_name}")

        with st.spinner("Loading roster..."):
            roster = get_roster(access_token, my_team_key)

        if roster:
            # Separate batters and pitchers
            pitchers = [p for p in roster if "P" in p["positions"] and p["positions"] != ["P"] or p["positions"] == ["P"] or "SP" in p["positions"] or "RP" in p["positions"]]
            batters = [p for p in roster if p not in pitchers]

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### 🏏 Batters")
                if batters:
                    batter_df = pd.DataFrame(batters)[["name", "positions", "editorial_team", "status"]]
                    batter_df["positions"] = batter_df["positions"].apply(lambda x: ", ".join(x))
                    batter_df.columns = ["Name", "Positions", "Team", "Status"]
                    st.dataframe(batter_df, use_container_width=True, hide_index=True)

            with col2:
                st.markdown("#### ⚾ Pitchers")
                if pitchers:
                    pitcher_df = pd.DataFrame(pitchers)[["name", "positions", "editorial_team", "status"]]
                    pitcher_df["positions"] = pitcher_df["positions"].apply(lambda x: ", ".join(x))
                    pitcher_df.columns = ["Name", "Positions", "Team", "Status"]
                    st.dataframe(pitcher_df, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.info("💡 **Tip:** Use the 'My Team' filter in Player Comparison and Stats Browser to quickly view your roster's stats.")
        else:
            st.warning("No roster data found.")

# ================================================================
# TAB 2: ALL TEAMS
# ================================================================
with tab2:
    if not teams:
        st.warning("Could not load teams.")
    else:
        st.markdown(f"### All {len(teams)} Teams")

        team_names = [t["name"] for t in teams]
        selected_team_name = st.selectbox("Select a team to view roster:", team_names)
        selected_team = next((t for t in teams if t["name"] == selected_team_name), None)

        if selected_team:
            with st.spinner(f"Loading {selected_team_name} roster..."):
                roster = get_roster(access_token, selected_team["team_key"])

            if roster:
                roster_df = pd.DataFrame(roster)[["name", "positions", "editorial_team", "status"]]
                roster_df["positions"] = roster_df["positions"].apply(lambda x: ", ".join(x))
                roster_df.columns = ["Name", "Positions", "MLB Team", "Status"]
                st.dataframe(roster_df, use_container_width=True, hide_index=True)
            else:
                st.warning("No roster data found for this team.")

# ================================================================
# TAB 3: SCORING SYSTEM
# ================================================================
with tab3:
    st.markdown("### Your Custom Scoring System")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 🏏 Batters")
        batter_rows = [{"Stat": stat, "Points": val} for stat, val in BATTER_SCORING.items()]
        batter_score_df = pd.DataFrame(batter_rows)
        st.dataframe(batter_score_df, use_container_width=True, hide_index=True)

    with col2:
        st.markdown("#### ⚾ Pitchers")
        pitcher_rows = [{"Stat": stat, "Points": val} for stat, val in PITCHER_SCORING.items()]
        pitcher_score_df = pd.DataFrame(pitcher_rows)
        st.dataframe(pitcher_score_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("""
    **Notes on scoring:**
    - Pitcher **Outs** = IP × 3
    - **Total Bases Allowed** = (1B × 1) + (2B × 2) + (3B × 3) + (HR × 4) allowed by pitcher
    - Fantasy score calculation is built in — a scoring dashboard with date range filtering is coming next
    """)
