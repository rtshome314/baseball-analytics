import streamlit as st
import pandas as pd
import os
from datetime import datetime
from utils.style import inject_custom_css, render_nav_back
from config import DEFAULT_SEASON, AVAILABLE_SEASONS

from utils.data_loader import (
    get_data_status, data_is_fresh, refresh_all_data,
    _load_metadata, DATA_DIR,
    save_weekly_player_stats, load_weekly_player_stats,
    save_yahoo_data, load_yahoo_data,
    save_fantasy_scoring, load_fantasy_scoring,
    load_batting_stats, load_pitching_stats,
    load_batting_stats_post, load_pitching_stats_post,
)

st.set_page_config(page_title="Data Manager", page_icon="⚾", layout="wide")
inject_custom_css()
render_nav_back()

st.markdown("## 💾 Data Manager")
st.markdown("Download, refresh, and monitor your local baseball data.")

season = st.selectbox("Season", AVAILABLE_SEASONS, index=AVAILABLE_SEASONS.index(DEFAULT_SEASON))

st.markdown("### 📦 Data Status")

status = get_data_status(season)
meta = _load_metadata()

dataset_labels = {
    "statcast": "Statcast Pitch Data",
    "batting_stats": "Batting Stats - Regular Season (Baseball Reference)",
    "batting_stats_post": "Batting Stats - Postseason (Baseball Reference)",
    "pitching_stats": "Pitching Stats - Regular Season (Baseball Reference)",
    "pitching_stats_post": "Pitching Stats - Postseason (Baseball Reference)",
    "statcast_batting_agg": "Statcast Batting Aggregates",
    "statcast_pitching_agg": "Statcast Pitching Aggregates",
    "statcast_batter_pcts": "Statcast Batter Percentiles (Savant)",
    "statcast_pitcher_pcts": "Statcast Pitcher Percentiles (Savant)",
    "team_batting": "Team Batting Stats",
    "team_pitching": "Team Pitching Stats",
    "batter_lookup": "Batter Name Lookup",
    "split_summary": "Split Summary (Pre-calculated)",
}

for key, label in dataset_labels.items():
    s = status[key]
    col1, col2, col3, col4 = st.columns([3, 2, 2, 1])

    with col1:
        st.markdown(f"**{label}**")
    with col2:
        if s["exists"]:
            rows_key = f"{key}_{season}_rows"
            rows = meta.get(rows_key, "?")
            st.markdown(f"✅ {rows:,} rows" if isinstance(rows, int) else f"✅ {rows} rows")
        else:
            st.markdown("❌ Not downloaded")
    with col3:
        if s["last_refresh"]:
            ago = datetime.now() - s["last_refresh"]
            hours = ago.total_seconds() / 3600
            if hours < 1:
                st.markdown(f"🕐 {int(ago.total_seconds() / 60)} min ago")
            elif hours < 24:
                st.markdown(f"🕐 {hours:.1f} hours ago")
            else:
                st.markdown(f"⚠️ {hours / 24:.1f} days ago")
        else:
            st.markdown("—")
    with col4:
        if s["stale"] or not s["exists"]:
            st.markdown("🔄 Needs refresh")
        else:
            st.markdown("✅ Fresh")

# Yahoo Fantasy Data Status
st.markdown("### 🏆 Yahoo Fantasy Data")
meta = _load_metadata()
yahoo_file = os.path.join(DATA_DIR, "yahoo_weekly_player_stats.parquet")
yahoo_exists = os.path.exists(yahoo_file)
col_y1, col_y2, col_y3, col_y4 = st.columns([3, 2, 2, 1])
with col_y1:
    st.markdown("**Weekly Player Stats (Yahoo)**")
with col_y2:
    if yahoo_exists:
        rows = meta.get("yahoo_weekly_player_stats_rows", "?")
        st.markdown(f"✅ {rows:,} rows" if isinstance(rows, int) else f"✅ {rows} rows")
    else:
        st.markdown("❌ Not downloaded")
with col_y3:
    last_ref = meta.get("yahoo_weekly_player_stats_last_refresh")
    if last_ref:
        ago = datetime.now() - datetime.fromisoformat(last_ref)
        hours = ago.total_seconds() / 3600
        if hours < 1:
            st.markdown(f"🕐 {int(ago.total_seconds() / 60)} min ago")
        elif hours < 24:
            st.markdown(f"🕐 {hours:.1f} hours ago")
        else:
            st.markdown(f"⚠️ {hours / 24:.1f} days ago")
    else:
        st.markdown("—")
with col_y4:
    if not yahoo_exists:
        st.markdown("🔄 Needs refresh")
    else:
        st.markdown("✅ Fresh")

st.markdown("### 💿 Storage")
total_size = 0
if os.path.exists(DATA_DIR):
    for f in os.listdir(DATA_DIR):
        fp = os.path.join(DATA_DIR, f)
        if os.path.isfile(fp):
            total_size += os.path.getsize(fp)
st.markdown(f"**Total local data:** {total_size / (1024*1024):.1f} MB")

st.markdown("---")
st.markdown("### 🔄 Refresh Data")

col1, col2 = st.columns(2)

with col1:
    if st.button("🔄 Smart Refresh (incremental)", type="primary", use_container_width=True):
        results = refresh_all_data(season, full_statcast=False)

        # Also refresh Yahoo fantasy data if authenticated
        try:
            from utils.yahoo_auth import get_valid_token
            from utils.yahoo_data import (
                get_league_info, get_teams, get_league_standings,
                get_all_rosters, get_weekly_player_stats,
                build_player_scoring_table, build_team_standings_with_splits,
            )
            from config import YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, YAHOO_LEAGUE_ID
            from utils.data_loader import load_batting_stats, load_pitching_stats

            token = get_valid_token(YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET)
            if token:
                with st.spinner("Refreshing Yahoo fantasy data..."):
                    league_info = get_league_info(token, YAHOO_LEAGUE_ID)
                    teams = get_teams(token, YAHOO_LEAGUE_ID)
                    standings = get_league_standings(token, YAHOO_LEAGUE_ID)
                    rosters = get_all_rosters(token, teams)
                    save_yahoo_data(league_info, teams, rosters, standings)

                    start_week = league_info.get("start_week", "1")
                    current_week = league_info.get("current_week", "1")
                    weekly_df = get_weekly_player_stats(token, YAHOO_LEAGUE_ID, teams, start_week, current_week)
                    save_weekly_player_stats(weekly_df)

                    # Recalculate scoring tables
                    batting_df = load_batting_stats(season)
                    pitching_df = load_pitching_stats(season)
                    batter_scoring, pitcher_scoring = build_player_scoring_table(batting_df, pitching_df, rosters)

                    # Build standings with accurate hitter/pitcher split from weekly data
                    if not weekly_df.empty:
                        import pandas as pd
                        active_wdf = weekly_df[weekly_df["is_active"]] if "is_active" in weekly_df.columns else weekly_df
                        team_hitter = active_wdf[~active_wdf["is_pitcher"]].groupby("team")["fan_pts"].sum().to_dict()
                        team_pitcher = active_wdf[active_wdf["is_pitcher"]].groupby("team")["fan_pts"].sum().to_dict()
                        for s in standings:
                            s["Hitter Pts"] = round(team_hitter.get(s["Team"], 0), 1)
                            s["Pitcher Pts"] = round(team_pitcher.get(s["Team"], 0), 1)
                    else:
                        standings = build_team_standings_with_splits(standings, batter_scoring, pitcher_scoring)

                    save_fantasy_scoring(batter_scoring, pitcher_scoring, standings)
                    yahoo_refreshed = True
            else:
                yahoo_refreshed = False
        except Exception as e:
            yahoo_refreshed = False
            st.warning(f"Yahoo refresh skipped: {e}")

        st.success(f"""
        ✅ Refresh complete!
        - Batting stats (regular season): {results['batting']:,} players
        - Batting stats (postseason): {results['batting_post']:,} players
        - Pitching stats (regular season): {results['pitching']:,} players
        - Pitching stats (postseason): {results['pitching_post']:,} players
        - Statcast batting agg: {results['sc_batting']:,} players
        - Statcast pitching agg: {results['sc_pitching']:,} players
        - Statcast pitches: {results['statcast']:,} total rows
        {"- Yahoo fantasy data: ✅ updated" if yahoo_refreshed else "- Yahoo fantasy data: ⚠️ not updated (open Fantasy page first)"}
        """)
        st.rerun()

with col2:
    confirm = st.checkbox("I understand this will replace all data (may take 5-10 minutes)")
    if st.button("🗑️ Full Re-download (replace all)", use_container_width=True):
        if confirm:
            results = refresh_all_data(season, full_statcast=True)
            st.success(f"✅ Full download complete! {results['statcast']:,} Statcast pitches.")
            st.rerun()
        else:
            st.warning("Please check the confirmation box before proceeding.")

st.markdown("---")
st.caption(
    "💡 The app automatically checks data freshness on startup. "
    "If data is older than 24 hours, you'll see a banner on the home page."
)