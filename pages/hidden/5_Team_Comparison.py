import streamlit as st
import pandas as pd
import numpy as np
from utils.style import inject_custom_css
from config import DEFAULT_SEASON, AVAILABLE_SEASONS

from utils.data_loader import (
    load_team_batting,
    load_team_pitching,
    load_statcast_batting_agg,
    load_batting_stats,
)

st.set_page_config(page_title="Team Comparison", page_icon="⚾", layout="wide")
inject_custom_css()

st.markdown("## 🏟️ Team Comparison")
st.markdown("Compare teams side-by-side with official team stats and rankings.")

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    season = st.selectbox("Season", AVAILABLE_SEASONS, index=AVAILABLE_SEASONS.index(DEFAULT_SEASON), key="tc_season")

team_batting = load_team_batting(season)
team_pitching = load_team_pitching(season)

if not team_batting.empty:

    # Division/League mapping
    divisions = {
        "AL East": ["NYY", "BOS", "TBR", "TOR", "BAL"],
        "AL Central": ["CLE", "MIN", "DET", "CHW", "KCR"],
        "AL West": ["HOU", "SEA", "TEX", "LAA", "OAK", "ATH"],
        "NL East": ["ATL", "NYM", "PHI", "MIA", "WSN", "WSH"],
        "NL Central": ["MIL", "CHC", "STL", "PIT", "CIN"],
        "NL West": ["LAD", "SDP", "SFG", "ARI", "COL"],
    }

    with st.sidebar:
        st.markdown("### 🏟️ Quick Filters")

        league_filter = st.radio("League", ["All", "AL", "NL"], horizontal=True, key="tc_league")

        if league_filter == "AL":
            available_divs = ["AL East", "AL Central", "AL West"]
        elif league_filter == "NL":
            available_divs = ["NL East", "NL Central", "NL West"]
        else:
            available_divs = list(divisions.keys())

        selected_divs = st.multiselect("Divisions", available_divs, default=available_divs, key="tc_divs")

        div_teams = []
        for div in selected_divs:
            div_teams.extend(divisions[div])

    all_teams = sorted(team_batting["Team"].dropna().unique().tolist())
    default_teams = [t for t in all_teams if t in div_teams]
    selected_teams = st.multiselect("Select teams to compare", all_teams, default=default_teams)

    if selected_teams:
        tab1, tab2, tab3 = st.tabs(["🏏 Team Batting", "⚾ Team Pitching", "📊 Team Statcast"])

        # ========================
        # TEAM BATTING
        # ========================
        with tab1:
            bat_stats = ["AVG", "OBP", "SLG", "OPS", "HR", "R", "RBI", "SB", "BB", "SO", "wOBA", "wRC+"]
            bat_cols = [c for c in bat_stats if c in team_batting.columns]

            display_bat = team_batting[team_batting["Team"].isin(selected_teams)][["Team"] + bat_cols].copy()

            # Add rankings based on all 30 teams
            for c in bat_cols:
                ascending = c == "SO"
                team_batting[f"{c}_rank"] = team_batting[c].rank(ascending=ascending, method="min").astype(int)

            st.markdown("### Team Batting Stats")
            st.dataframe(
                display_bat.sort_values("OPS", ascending=False).reset_index(drop=True),
                use_container_width=True,
            )

            st.markdown("### Team Batting Rankings")
            st.caption("Rank out of 30 teams. #1 = best.")
            rank_cols = ["Team"] + [f"{c}_rank" for c in bat_cols if f"{c}_rank" in team_batting.columns]
            rank_display = team_batting[team_batting["Team"].isin(selected_teams)][rank_cols].copy()
            rank_display.columns = ["Team"] + [c for c in bat_cols if f"{c}_rank" in team_batting.columns]
            st.dataframe(
                rank_display.sort_values("OPS").reset_index(drop=True),
                use_container_width=True,
            )

        # ========================
        # TEAM PITCHING
        # ========================
        with tab2:
            if not team_pitching.empty:
                pitch_stats = ["ERA", "FIP", "WHIP", "K/9", "BB/9", "SV"]
                pitch_cols = [c for c in pitch_stats if c in team_pitching.columns]

                display_pitch = team_pitching[team_pitching["Team"].isin(selected_teams)][["Team"] + pitch_cols].copy()

                for c in pitch_cols:
                    ascending = c not in ["K/9", "SV"]
                    team_pitching[f"{c}_rank"] = team_pitching[c].rank(ascending=ascending, method="min").astype(int)

                st.markdown("### Team Pitching Stats")
                st.dataframe(
                    display_pitch.sort_values("ERA").reset_index(drop=True),
                    use_container_width=True,
                )

                st.markdown("### Team Pitching Rankings")
                st.caption("Rank out of 30 teams. #1 = best.")
                rank_cols = ["Team"] + [f"{c}_rank" for c in pitch_cols if f"{c}_rank" in team_pitching.columns]
                rank_display = team_pitching[team_pitching["Team"].isin(selected_teams)][rank_cols].copy()
                rank_display.columns = ["Team"] + [c for c in pitch_cols if f"{c}_rank" in team_pitching.columns]
                st.dataframe(
                    rank_display.sort_values("ERA").reset_index(drop=True),
                    use_container_width=True,
                )
            else:
                st.warning("No pitching data loaded.")

        # ========================
        # TEAM STATCAST
        # ========================
        with tab3:
            sc_stats = ["EV", "Barrel%", "HardHit%", "maxEV", "LA", "xBA", "xSLG", "xwOBA"]
            sc_cols = [c for c in sc_stats if c in team_batting.columns]

            if sc_cols:
                display_sc = team_batting[team_batting["Team"].isin(selected_teams)][["Team"] + sc_cols].copy()

                sc_labels = {
                    "EV": "Avg Exit Velo",
                    "Barrel%": "Barrel %",
                    "HardHit%": "Hard Hit %",
                    "maxEV": "Max Exit Velo",
                    "LA": "Launch Angle",
                    "xBA": "xBA",
                    "xSLG": "xSLG",
                    "xwOBA": "xwOBA",
                }

                for c in sc_cols:
                    team_batting[f"{c}_rank"] = team_batting[c].rank(ascending=False, method="min").astype(int)

                st.markdown("### Team Statcast Stats")
                display_renamed = display_sc.rename(columns=sc_labels)
                st.dataframe(
                    display_renamed.sort_values(sc_labels.get("EV", "EV") if "EV" in sc_cols else display_renamed.columns[1], ascending=False).reset_index(drop=True),
                    use_container_width=True,
                )

                st.markdown("### Team Statcast Rankings")
                st.caption("Rank out of 30 teams. #1 = best.")
                rank_cols = ["Team"] + [f"{c}_rank" for c in sc_cols if f"{c}_rank" in team_batting.columns]
                rank_display = team_batting[team_batting["Team"].isin(selected_teams)][rank_cols].copy()
                rank_display.columns = ["Team"] + [sc_labels.get(c, c) for c in sc_cols if f"{c}_rank" in team_batting.columns]
                st.dataframe(
                    rank_display.reset_index(drop=True),
                    use_container_width=True,
                )
            else:
                st.warning("No Statcast columns found in team batting data.")
    else:
        st.info("👆 Select teams above to compare.")
else:
    st.warning("No team batting data loaded. Head to **Data Manager** to download data first.")