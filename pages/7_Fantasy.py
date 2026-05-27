import streamlit as st
import pandas as pd
import sys
import os
import plotly.express as px

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.style import inject_custom_css, render_header, render_nav_back, render_data_status
from utils.yahoo_auth import render_auth_flow, get_valid_token, logout
from utils.yahoo_data import (
    get_league_info, get_teams, get_my_team_key, get_roster,
    BATTER_SCORING, PITCHER_SCORING,
    get_league_standings, get_all_rosters,
    build_player_scoring_table, build_team_standings_with_splits,
    sync_rosters_to_bookmarks, get_weekly_team_points,
    build_player_scoring_from_statcast,
    get_draft_results, get_current_matchups,
)
from utils.data_loader import load_batting_stats, load_pitching_stats, load_yahoo_data, save_yahoo_data, yahoo_data_is_fresh, save_fantasy_scoring, load_fantasy_scoring, load_statcast_local, load_weekly_player_stats
from utils.charts import CHART_TEMPLATE
from config import YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET, YAHOO_LEAGUE_ID, DEFAULT_SEASON

st.set_page_config(page_title="Fantasy", page_icon="⚾", layout="wide")
inject_custom_css()
render_header()
render_nav_back()
render_data_status(["batting_stats", "pitching_stats"])

st.markdown("## 🏆 Fantasy Baseball")

# --- Auth ---
authenticated = render_auth_flow(YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET)
if not authenticated:
    st.stop()

access_token = get_valid_token(YAHOO_CLIENT_ID, YAHOO_CLIENT_SECRET)

# --- Sidebar ---
with st.sidebar:
    if st.button("Disconnect Yahoo Account"):
        logout()
        st.rerun()

# --- Load league + teams (from local cache or Yahoo API) ---
if "fantasy_league_info" not in st.session_state:
    cached = load_yahoo_data()
    if cached:
        st.session_state["fantasy_league_info"] = cached["league_info"]
        st.session_state["fantasy_teams"] = cached["teams"]
        st.session_state["fantasy_rosters_cached"] = cached.get("rosters", {})
        st.session_state["fantasy_standings_cached"] = cached.get("standings", [])
        # Still need my_team_key from API (it's user-specific)
        with st.spinner("Connecting to Yahoo..."):
            st.session_state["fantasy_my_team_key"] = get_my_team_key(access_token, YAHOO_LEAGUE_ID)
    else:
        with st.spinner("Loading league data from Yahoo..."):
            st.session_state["fantasy_league_info"] = get_league_info(access_token, YAHOO_LEAGUE_ID)
            st.session_state["fantasy_teams"] = get_teams(access_token, YAHOO_LEAGUE_ID)
            st.session_state["fantasy_my_team_key"] = get_my_team_key(access_token, YAHOO_LEAGUE_ID)

league_info = st.session_state["fantasy_league_info"]
teams = st.session_state["fantasy_teams"]
my_team_key = st.session_state["fantasy_my_team_key"]

# Pre-load scoring data from local files if not in session state
if "sd_standings" not in st.session_state:
    batter_df_cached, pitcher_df_cached, standings_cached = load_fantasy_scoring()
    if not batter_df_cached.empty and standings_cached:
        st.session_state["sd_standings"] = standings_cached
        st.session_state["sd_batters"] = batter_df_cached
        st.session_state["sd_pitchers"] = pitcher_df_cached

if league_info:
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.metric("League", league_info.get("name", ""))
    col_b.metric("Season", league_info.get("season", ""))
    col_c.metric("Teams", league_info.get("num_teams", ""))
    col_d.metric("Current Week", league_info.get("current_week", ""))

st.markdown("---")

BOOKMARKS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bookmarks.json")

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📋 My Roster",
    "🏅 All Teams",
    "📊 Scoring System",
    "🏆 Standings & Scoring",
    "📈 Weekly Trends",
    "🎯 Draft Board",
    "⚔️ Matchups",
])

# ================================================================
# TAB 1: MY ROSTER
# ================================================================
with tab1:
    if not my_team_key:
        st.warning("Could not identify your team.")
    else:
        my_team_name = next((t["name"] for t in teams if t["team_key"] == my_team_key), "My Team")
        st.markdown(f"### {my_team_name}")

        with st.spinner("Loading roster..."):
            roster = get_roster(access_token, my_team_key)

        if roster:
            pitchers = [p for p in roster if any(pos in p["positions"] for pos in ["SP", "RP", "P"])]
            batters = [p for p in roster if p not in pitchers]

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 🏏 Batters")
                if batters:
                    bdf = pd.DataFrame(batters)[["name", "positions", "editorial_team", "status"]]
                    bdf["positions"] = bdf["positions"].apply(lambda x: ", ".join(x))
                    bdf.columns = ["Name", "Positions", "Team", "Status"]
                    st.dataframe(bdf, use_container_width=True, hide_index=True)
            with col2:
                st.markdown("#### ⚾ Pitchers")
                if pitchers:
                    pdf = pd.DataFrame(pitchers)[["name", "positions", "editorial_team", "status"]]
                    pdf["positions"] = pdf["positions"].apply(lambda x: ", ".join(x))
                    pdf.columns = ["Name", "Positions", "Team", "Status"]
                    st.dataframe(pdf, use_container_width=True, hide_index=True)

        st.markdown("---")
        col_sync, col_info = st.columns([1, 3])
        with col_sync:
            if st.button("🔄 Sync Rosters to Bookmarks", use_container_width=True):
                with st.spinner("Syncing..."):
                    batting = load_batting_stats(DEFAULT_SEASON)
                    pitching = load_pitching_stats(DEFAULT_SEASON)
                    all_players = []
                    if not batting.empty and "Name" in batting.columns:
                        all_players += batting["Name"].dropna().tolist()
                    if not pitching.empty and "Name" in pitching.columns:
                        all_players += pitching["Name"].dropna().tolist()
                    bookmarks, report = sync_rosters_to_bookmarks(
                        access_token, YAHOO_LEAGUE_ID, list(set(all_players)), BOOKMARKS_FILE
                    )
                if bookmarks:
                    st.success("✅ Rosters synced to Player Comparison bookmarks!")
                    for r in report:
                        unmatched_str = ", ".join(r["unmatched"]) if r["unmatched"] else "None"
                        st.markdown(f"**{r['team']}** — {r['matched']} matched | Unmatched: {unmatched_str}")
        with col_info:
            st.info("Creates bookmarks in Player Comparison for each fantasy team roster.")

# ================================================================
# TAB 2: ALL TEAMS
# ================================================================
with tab2:
    if not teams:
        st.warning("Could not load teams.")
    else:
        team_names = [t["name"] for t in teams]
        selected_team_name = st.selectbox("Select a team:", team_names)
        selected_team = next((t for t in teams if t["name"] == selected_team_name), None)

        if selected_team:
            with st.spinner(f"Loading {selected_team_name} roster..."):
                roster = get_roster(access_token, selected_team["team_key"])
            if roster:
                rdf = pd.DataFrame(roster)[["name", "positions", "editorial_team", "status"]]
                rdf["positions"] = rdf["positions"].apply(lambda x: ", ".join(x))
                rdf.columns = ["Name", "Positions", "MLB Team", "Status"]
                st.dataframe(rdf, use_container_width=True, hide_index=True)

# ================================================================
# TAB 3: SCORING SYSTEM
# ================================================================
with tab3:
    st.markdown("### Your Custom Scoring System")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 🏏 Batters")
        st.dataframe(
            pd.DataFrame([{"Stat": k, "Points": v} for k, v in BATTER_SCORING.items()]),
            use_container_width=True, hide_index=True
        )
    with col2:
        st.markdown("#### ⚾ Pitchers")
        st.dataframe(
            pd.DataFrame([{"Stat": k, "Points": v} for k, v in PITCHER_SCORING.items()]),
            use_container_width=True, hide_index=True
        )
    st.markdown("""
    **Notes:**
    - Pitcher **Outs** = IP × 3
    - **Total Bases Allowed** = H + 2B + (2×3B) + (3×HR) allowed
    - Stats sourced from Baseball Reference via local data
    """)

# ================================================================
# TAB 4: STANDINGS & SCORING DASHBOARD
# ================================================================
with tab4:
    st.markdown("### 🏆 Standings & Player Scoring")

    col_load, col_info2 = st.columns([1, 3])
    with col_load:
        load_btn = st.button("🔄 Load / Refresh Data", type="primary", key="sd_load", use_container_width=True)
    with col_info2:
        st.info("Loads standings from Yahoo + calculates player fantasy points from local stats data.")

    if load_btn:
        with st.spinner("Loading standings from Yahoo..."):
            standings = get_league_standings(access_token, YAHOO_LEAGUE_ID)
            rosters = get_all_rosters(access_token, teams)
            # Save to local cache
            save_yahoo_data(league_info, teams, rosters, standings)
            st.session_state["fantasy_rosters_cached"] = rosters
            st.session_state["fantasy_standings_cached"] = standings

        with st.spinner("Calculating fantasy points from local stats..."):
            batting_df = load_batting_stats(DEFAULT_SEASON)
            pitching_df = load_pitching_stats(DEFAULT_SEASON)
            batter_scoring, pitcher_scoring = build_player_scoring_table(batting_df, pitching_df, rosters)
            standings = build_team_standings_with_splits(standings, batter_scoring, pitcher_scoring)

        st.session_state["sd_standings"] = standings
        st.session_state["sd_batters"] = batter_scoring
        st.session_state["sd_pitchers"] = pitcher_scoring
        # Save locally so data persists across restarts
        save_fantasy_scoring(batter_scoring, pitcher_scoring, standings)

    if "sd_standings" in st.session_state:
        standings = st.session_state["sd_standings"]
        batter_scoring = st.session_state["sd_batters"]
        pitcher_scoring = st.session_state["sd_pitchers"]

        # --- STANDINGS TABLE ---
        st.markdown("#### League Standings")

        # Use weekly player stats for accurate hitter/pitcher split if available
        weekly_player_df = load_weekly_player_stats()
        if not weekly_player_df.empty:
            active_df = weekly_player_df[weekly_player_df.get("is_active", True)] if "is_active" in weekly_player_df.columns else weekly_player_df
            team_hitter = active_df[~active_df["is_pitcher"]].groupby("team")["fan_pts"].sum().to_dict()
            team_pitcher = active_df[active_df["is_pitcher"]].groupby("team")["fan_pts"].sum().to_dict()
            for s in standings:
                s["Hitter Pts"] = round(team_hitter.get(s["Team"], 0), 1)
                s["Pitcher Pts"] = round(team_pitcher.get(s["Team"], 0), 1)
            st.caption("Total Pts, W-L-T, and Hitter/Pitcher split all from Yahoo matchup data.")
        else:
            st.caption("Total Pts and W-L-T from Yahoo. Hitter/Pitcher Pts approximated from current rosters. Run Smart Refresh for accurate splits.")

        standings_df = pd.DataFrame(standings)[[
            "Rank", "Team", "W", "L", "T", "Pct", "Total Pts", "Pts Against", "Hitter Pts", "Pitcher Pts"
        ]]
        st.dataframe(standings_df, use_container_width=True, hide_index=True)

        st.markdown("---")

        # --- PLAYER SCORING TABLE ---
        st.markdown("#### Player Fantasy Scoring")

        player_type = st.radio("Player Type", ["Batters", "Pitchers"], horizontal=True, key="sd_ptype")

        # Date range selector
        from datetime import date, timedelta
        sc_df = load_statcast_local(DEFAULT_SEASON)
        use_date_range = False

        if not sc_df.empty and "game_date" in sc_df.columns:
            import pandas as pd_inner
            sc_df["game_date"] = pd_inner.to_datetime(sc_df["game_date"])
            min_date = sc_df["game_date"].min().date()
            max_date = sc_df["game_date"].max().date()

            col_dr1, col_dr2 = st.columns([2, 1])
            with col_dr1:
                date_range = st.date_input(
                    "Date Range (uses Statcast data)",
                    value=(max_date - timedelta(days=6), max_date),
                    min_value=min_date,
                    max_value=max_date,
                    key="sd_daterange"
                )
            with col_dr2:
                use_date_range = st.checkbox("Apply date filter", value=False, key="sd_use_date")

        if use_date_range and len(date_range) == 2:
            start_d, end_d = date_range
            rosters_for_filter = st.session_state.get("fantasy_rosters_cached", {})
            if not rosters_for_filter:
                cached = load_yahoo_data()
                rosters_for_filter = cached.get("rosters", {}) if cached else {}

            with st.spinner(f"Calculating stats from {start_d} to {end_d}..."):
                # merge batter names into statcast if available
                from utils.data_loader import load_batter_lookup
                lookup = load_batter_lookup(DEFAULT_SEASON)
                if not lookup.empty and "batter" in sc_df.columns:
                    sc_df["batter"] = sc_df["batter"].astype(int)
                    lookup["batter"] = lookup["batter"].astype(int)
                    sc_merged = sc_df.merge(lookup, on="batter", how="left")
                else:
                    sc_merged = sc_df

                batter_dr, pitcher_dr = build_player_scoring_from_statcast(
                    sc_merged, rosters_for_filter, start_date=start_d, end_date=end_d
                )
            df = batter_dr.copy() if player_type == "Batters" else pitcher_dr.copy()
            st.caption(f"📅 Showing stats from **{start_d}** to **{end_d}** (Statcast data)")
        else:
            df = batter_scoring.copy() if player_type == "Batters" else pitcher_scoring.copy()
            st.caption("📅 Showing full season stats")

        # Min PA/IP filter
        qual_col = "PA" if player_type == "Batters" else "IP"
        min_qual = st.number_input(f"Min {qual_col}", min_value=0, value=5 if use_date_range else 20, step=5, key="sd_minqual")
        if qual_col in df.columns:
            df = df[df[qual_col] >= min_qual]

        # Roster status filter
        team_names_list = [t["name"] for t in teams]
        filter_options = ["All Players", "All Rostered", "Free Agents Only"] + team_names_list
        selected_filters = st.multiselect(
            "Show players from:",
            filter_options,
            default=["All Players"],
            key="sd_filter"
        )

        show_all = "All Players" in selected_filters or not selected_filters
        if not show_all:
            show_fa = "Free Agents Only" in selected_filters
            show_rostered = "All Rostered" in selected_filters
            show_teams = [t for t in selected_filters if t in team_names_list]

            mask = pd.Series([False] * len(df), index=df.index)
            if show_fa:
                mask = mask | df["Is FA"]
            if show_rostered:
                mask = mask | ~df["Is FA"]
            if show_teams:
                mask = mask | df["Fantasy Team"].isin(show_teams)
            df = df[mask]

        df = df.sort_values("Fantasy Pts", ascending=False).reset_index(drop=True)

        # Select columns to show
        if player_type == "Batters":
            display_cols = ["Name", "Fantasy Team", "MLB Team", "Fantasy Pts", "Pts/PA",
                           "PA", "AVG", "OBP", "SLG", "OPS", "H", "HR", "2B", "3B", "BB", "SB", "CS", "SO", "HBP", "GIDP"]
        else:
            display_cols = ["Name", "Fantasy Team", "MLB Team", "Fantasy Pts", "Pts/IP",
                           "IP", "ERA", "WHIP", "K%", "SO", "BB", "HBP", "WP", "BLK", "GIDP"]

        display_cols = [c for c in display_cols if c in df.columns]
        st.markdown(f"**{len(df)} players**")
        st.dataframe(df[display_cols], use_container_width=True, height=700, hide_index=True)

        csv = df.to_csv(index=False)
        st.download_button("📥 Download CSV", csv, file_name=f"fantasy_scoring_{DEFAULT_SEASON}.csv", mime="text/csv")

    else:
        st.info("Click **Load / Refresh Data** to get started.")

# ================================================================
# TAB 5: WEEKLY TRENDS
# ================================================================
with tab5:
    st.markdown("### 📈 Weekly Trends")

    trend_view = st.radio(
        "View by:",
        ["Teams", "Hitters", "Pitchers", "Individual Players"],
        horizontal=True,
        key="wt_view"
    )

    if trend_view == "Teams":
        # Load team weekly points from local weekly player stats file
        weekly_player_local = load_weekly_player_stats()
        if not weekly_player_local.empty:
            # Aggregate to team level
            weekly_team = weekly_player_local.groupby(["team", "week"])["fan_pts"].sum().reset_index()
            weekly_team.columns = ["team", "week", "total_pts"]
            st.session_state["wt_data"] = weekly_team.to_dict("records")
        
        if "wt_data" in st.session_state:
            weekly_df = pd.DataFrame(st.session_state["wt_data"])

            if not weekly_df.empty:
                all_team_names = sorted(weekly_df["team"].unique().tolist())
                selected_teams_wt = st.multiselect(
                    "Select teams to show:",
                    all_team_names,
                    default=all_team_names,
                    key="wt_teams"
                )
                filtered = weekly_df[weekly_df["team"].isin(selected_teams_wt)]

                # Hitter/pitcher toggle using weekly player stats
                weekly_player_df = load_weekly_player_stats()
                pts_toggle = st.radio(
                    "Points to show:",
                    ["Total", "Hitters Only", "Pitchers Only"],
                    horizontal=True,
                    key="wt_pts_toggle"
                )

                if pts_toggle != "Total" and not weekly_player_df.empty:
                    is_pitcher_toggle = pts_toggle == "Pitchers Only"
                    active_wdf = weekly_player_df[weekly_player_df["is_active"]] if "is_active" in weekly_player_df.columns else weekly_player_df
                    filtered_players = active_wdf[
                        (active_wdf["is_pitcher"] == is_pitcher_toggle) &
                        (active_wdf["team"].isin(selected_teams_wt))
                    ]
                    team_week_pts = filtered_players.groupby(["team", "week"])["fan_pts"].sum().reset_index()
                    team_week_pts.columns = ["team", "week", "total_pts"]
                    chart_df = team_week_pts
                    pts_label = "Hitter Pts" if not is_pitcher_toggle else "Pitcher Pts"
                else:
                    chart_df = filtered
                    pts_label = "Points"

                st.markdown("#### Points by Week")
                fig = px.line(
                    chart_df.sort_values("week"),
                    x="week", y="total_pts", color="team", markers=True,
                    labels={"week": "Week", "total_pts": pts_label, "team": "Team"},
                )
                fig.update_layout(**CHART_TEMPLATE, height=500)
                st.plotly_chart(fig, use_container_width=True)

                st.markdown("#### Cumulative Points")
                cum_df = chart_df.sort_values("week").copy()
                cum_df["cumulative_pts"] = cum_df.groupby("team")["total_pts"].cumsum()
                fig2 = px.line(
                    cum_df,
                    x="week", y="cumulative_pts", color="team", markers=True,
                    labels={"week": "Week", "cumulative_pts": f"Cumulative {pts_label}", "team": "Team"},
                )
                fig2.update_layout(**CHART_TEMPLATE, height=500)
                st.plotly_chart(fig2, use_container_width=True)

                st.markdown("#### Weekly Results Table")
                pivot = chart_df.pivot_table(
                    index="team", columns="week", values="total_pts", aggfunc="sum"
                ).round(1)
                pivot["Total"] = pivot.sum(axis=1)
                pivot = pivot.sort_values("Total", ascending=False)
                st.dataframe(pivot, use_container_width=True)
            else:
                st.warning("No weekly data found.")
        else:
            st.info("Click **Load Weekly Data** to see trends.")

    else:
        # Player-level trends from Statcast data
        # Define week date ranges for 2026 season
        WEEK_DATES = {
            1:  ("2026-03-27", "2026-04-06"),
            2:  ("2026-04-07", "2026-04-13"),
            3:  ("2026-04-14", "2026-04-20"),
            4:  ("2026-04-21", "2026-04-27"),
            5:  ("2026-04-28", "2026-05-04"),
            6:  ("2026-05-05", "2026-05-11"),
            7:  ("2026-05-12", "2026-05-18"),
            8:  ("2026-05-19", "2026-05-25"),
            9:  ("2026-05-26", "2026-06-01"),
            10: ("2026-06-02", "2026-06-08"),
            11: ("2026-06-09", "2026-06-15"),
            12: ("2026-06-16", "2026-06-22"),
            13: ("2026-06-23", "2026-06-29"),
            14: ("2026-06-30", "2026-07-06"),
            15: ("2026-07-07", "2026-07-13"),
            16: ("2026-07-14", "2026-07-20"),
            17: ("2026-07-21", "2026-07-27"),
            18: ("2026-07-28", "2026-08-03"),
            19: ("2026-08-04", "2026-08-10"),
            20: ("2026-08-11", "2026-08-17"),
            21: ("2026-08-18", "2026-08-24"),
            22: ("2026-08-25", "2026-08-31"),
            23: ("2026-09-01", "2026-09-07"),
            24: ("2026-09-08", "2026-09-14"),
            25: ("2026-09-15", "2026-09-21"),
            26: ("2026-09-22", "2026-09-27"),
        }

        from datetime import date as dt_date
        today = dt_date.today()
        available_weeks = {w: (s, e) for w, (s, e) in WEEK_DATES.items()
                          if dt_date.fromisoformat(s) <= today}

        if not available_weeks:
            st.warning("No completed weeks yet.")
        else:
            sc_df = load_statcast_local(DEFAULT_SEASON)
            if sc_df.empty:
                st.warning("No Statcast data found. Download it in Data Manager first.")
            else:
                sc_df["game_date"] = pd.to_datetime(sc_df["game_date"])

                # Load batter lookup for names
                from utils.data_loader import load_batter_lookup
                lookup = load_batter_lookup(DEFAULT_SEASON)
                if not lookup.empty and "batter" in sc_df.columns:
                    sc_df["batter"] = sc_df["batter"].astype(int)
                    lookup["batter"] = lookup["batter"].astype(int)
                    sc_df = sc_df.merge(lookup, on="batter", how="left")

                # Get rosters
                rosters_for_filter = st.session_state.get("fantasy_rosters_cached", {})
                if not rosters_for_filter:
                    cached = load_yahoo_data()
                    rosters_for_filter = cached.get("rosters", {}) if cached else {}

                is_pitcher_view = trend_view == "Pitchers"
                is_player_view = trend_view == "Individual Players"

                # Week selector
                week_options = list(available_weeks.keys())
                col_ws1, col_ws2 = st.columns(2)
                with col_ws1:
                    start_week_sel = st.selectbox("From Week", week_options, index=0, key="wt_start_week")
                with col_ws2:
                    end_week_sel = st.selectbox("To Week", week_options, index=len(week_options)-1, key="wt_end_week")

                selected_weeks = [w for w in week_options if start_week_sel <= w <= end_week_sel]

                # Roster/team filter
                team_names_wt = [t["name"] for t in teams]
                filter_opts = ["All Players", "All Rostered", "Free Agents Only"] + team_names_wt
                wt_filter = st.multiselect("Filter by:", filter_opts, default=["All Players"], key="wt_roster_filter")

                if is_player_view:
                    # Build full player list for selection
                    all_player_names = sorted(sc_df["batter_name"].dropna().unique().tolist()) if "batter_name" in sc_df.columns else []
                    if is_pitcher_view:
                        all_player_names = sorted(sc_df["player_name"].dropna().unique().tolist()) if "player_name" in sc_df.columns else []
                    selected_individual = st.multiselect("Select players:", all_player_names, key="wt_players")

                if st.button("📊 Calculate Weekly Trends", type="primary", key="wt_calc"):
                    weekly_player_data = []

                    for week_num in selected_weeks:
                        start_str, end_str = available_weeks[week_num]
                        start_d = dt_date.fromisoformat(start_str)
                        end_d = dt_date.fromisoformat(end_str)

                        b_df, p_df = build_player_scoring_from_statcast(
                            sc_df, rosters_for_filter,
                            start_date=start_d, end_date=end_d
                        )

                        use_df = p_df if is_pitcher_view else b_df
                        if not use_df.empty:
                            use_df = use_df.copy()
                            use_df["Week"] = week_num
                            weekly_player_data.append(use_df)

                    if weekly_player_data:
                        wt_player_df = pd.concat(weekly_player_data, ignore_index=True)
                        st.session_state["wt_player_df"] = wt_player_df
                    else:
                        st.warning("No data found for selected weeks.")

                if "wt_player_df" in st.session_state:
                    wt_df = st.session_state["wt_player_df"].copy()

                    # Apply roster filter
                    show_all_wt = "All Players" in wt_filter or not wt_filter
                    if not show_all_wt:
                        mask = pd.Series([False] * len(wt_df), index=wt_df.index)
                        if "Free Agents Only" in wt_filter:
                            mask = mask | wt_df["Is FA"]
                        if "All Rostered" in wt_filter:
                            mask = mask | ~wt_df["Is FA"]
                        team_filters_wt = [t for t in wt_filter if t in team_names_wt]
                        if team_filters_wt:
                            mask = mask | wt_df["Fantasy Team"].isin(team_filters_wt)
                        wt_df = wt_df[mask]

                    # Apply individual player filter
                    if is_player_view and selected_individual:
                        wt_df = wt_df[wt_df["Name"].isin(selected_individual)]

                    if wt_df.empty:
                        st.warning("No players match the selected filters.")
                    else:
                        pts_col = "Fantasy Pts"

                        # Top N selector for non-individual views
                        if not is_player_view:
                            top_n = st.slider("Show top N players by total points", 5, 30, 10, key="wt_topn")
                            top_players = (wt_df.groupby("Name")[pts_col].sum()
                                          .sort_values(ascending=False)
                                          .head(top_n).index.tolist())
                            wt_df = wt_df[wt_df["Name"].isin(top_players)]

                        st.markdown("#### Weekly Fantasy Points by Player")
                        fig = px.line(
                            wt_df.sort_values("Week"),
                            x="Week", y=pts_col, color="Name", markers=True,
                            labels={"Week": "Week", pts_col: "Fantasy Points", "Name": "Player"},
                        )
                        fig.update_layout(**CHART_TEMPLATE, height=500)
                        st.plotly_chart(fig, use_container_width=True)

                        st.markdown("#### Cumulative Fantasy Points")
                        cum_wt = wt_df.sort_values("Week").copy()
                        cum_wt["Cumulative Pts"] = cum_wt.groupby("Name")[pts_col].cumsum()
                        fig2 = px.line(
                            cum_wt,
                            x="Week", y="Cumulative Pts", color="Name", markers=True,
                            labels={"Week": "Week", "Cumulative Pts": "Cumulative Points", "Name": "Player"},
                        )
                        fig2.update_layout(**CHART_TEMPLATE, height=500)
                        st.plotly_chart(fig2, use_container_width=True)

                        st.markdown("#### Weekly Points Table")
                        pivot_p = wt_df.pivot_table(
                            index="Name", columns="Week", values=pts_col, aggfunc="sum"
                        ).round(1)
                        pivot_p["Total"] = pivot_p.sum(axis=1)
                        pivot_p = pivot_p.sort_values("Total", ascending=False)
                        st.dataframe(pivot_p, use_container_width=True)
                else:
                    st.info("Click **Calculate Weekly Trends** to generate charts.")


# ================================================================
# TAB 6: DRAFT BOARD
# ================================================================
with tab6:
    st.markdown("### 🎯 Draft Board")

    col_draft_load, col_draft_info = st.columns([1, 3])
    with col_draft_load:
        draft_load_btn = st.button("🔄 Load Draft Results", type="primary", key="draft_load", use_container_width=True)
    with col_draft_info:
        st.info("Pulls draft order and picks from Yahoo. Player names resolved from current rosters — dropped players will show player key as fallback.")

    if draft_load_btn:
        with st.spinner("Loading draft results from Yahoo..."):
            draft_picks, draft_raw_xml = get_draft_results(access_token, YAHOO_LEAGUE_ID)
        if draft_picks:
            st.session_state["draft_picks"] = draft_picks
            st.session_state.pop("draft_raw_xml", None)
        else:
            st.warning("No draft results found. Showing raw Yahoo API response for debugging:")
            st.session_state["draft_raw_xml"] = draft_raw_xml

    if "draft_raw_xml" in st.session_state:
        st.code(st.session_state["draft_raw_xml"][:3000] if st.session_state["draft_raw_xml"] else "No response", language="xml")

    if "draft_picks" in st.session_state:
        draft_picks = st.session_state["draft_picks"]
        draft_df = pd.DataFrame(draft_picks)

        is_auction = draft_df["is_auction"].iloc[0] if "is_auction" in draft_df.columns and not draft_df.empty else False

        if is_auction:
            st.caption("🏷️ Auction draft — sorted by cost descending.")
        
        draft_view = st.radio(
            "View:",
            ["Full Draft Table", "Team Draft Board"],
            horizontal=True,
            key="draft_view_toggle"
        )

        if draft_view == "Full Draft Table":
            st.markdown("#### All Picks")

            # Filters
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                all_teams_draft = sorted(draft_df["team_name"].unique().tolist())
                filter_teams_draft = st.multiselect(
                    "Filter by team:", all_teams_draft, default=[], key="draft_team_filter",
                    placeholder="All teams"
                )
            with col_f2:
                all_pos_draft = sorted(draft_df["position"].replace("", "Unknown").unique().tolist())
                filter_pos_draft = st.multiselect(
                    "Filter by position:", all_pos_draft, default=[], key="draft_pos_filter",
                    placeholder="All positions"
                )

            display_draft = draft_df.copy()
            if filter_teams_draft:
                display_draft = display_draft[display_draft["team_name"].isin(filter_teams_draft)]
            if filter_pos_draft:
                display_draft = display_draft[display_draft["position"].replace("", "Unknown").isin(filter_pos_draft)]

            if is_auction:
                display_draft_cols = display_draft[["cost", "team_name", "player_name", "position", "mlb_team"]]
                display_draft_cols.columns = ["Cost ($)", "Team", "Player", "Position", "MLB Team"]
            else:
                display_draft_cols = display_draft[["pick", "round", "team_name", "player_name", "position", "mlb_team"]]
                display_draft_cols.columns = ["Pick", "Round", "Team", "Player", "Position", "MLB Team"]

            st.markdown(f"**{len(display_draft_cols)} picks**")
            st.dataframe(display_draft_cols, use_container_width=True, hide_index=True, height=600)

            csv_draft = display_draft_cols.to_csv(index=False)
            st.download_button("📥 Download CSV", csv_draft, file_name="draft_results.csv", mime="text/csv")

        else:
            # Team draft board
            st.markdown("#### Team Draft Board")
            team_first_pick = draft_df.groupby("team_name")["pick"].min().sort_values()
            all_teams_board = team_first_pick.index.tolist()

            if is_auction:
                st.caption("Each column is a team. Players sorted by cost descending. Cost shown in parentheses.")
                board_data = {}
                for team in all_teams_board:
                    team_picks = draft_df[draft_df["team_name"] == team].sort_values("cost", ascending=False)
                    board_data[team] = [
                        f"{row['player_name']} (${row['cost']})"
                        for _, row in team_picks.iterrows()
                    ]
                # Pad to same length
                max_len = max(len(v) for v in board_data.values()) if board_data else 0
                board_rows = []
                for i in range(max_len):
                    row = {"#": i + 1}
                    for team in all_teams_board:
                        picks_list = board_data.get(team, [])
                        row[team] = picks_list[i] if i < len(picks_list) else "—"
                    board_rows.append(row)
                board_df = pd.DataFrame(board_rows).set_index("#")
            else:
                st.caption("Each column is a team. Rows are rounds. Pick number shown in parentheses.")
                all_rounds = sorted(draft_df["round"].dropna().unique().tolist())
                board_data = {}
                for team in all_teams_board:
                    team_picks = draft_df[draft_df["team_name"] == team].sort_values("round")
                    board_data[team] = {
                        row["round"]: f"{row['player_name']} ({row['pick']})"
                        for _, row in team_picks.iterrows()
                    }
                board_rows = []
                for rnd in all_rounds:
                    row = {"Round": rnd}
                    for team in all_teams_board:
                        row[team] = board_data.get(team, {}).get(rnd, "—")
                    board_rows.append(row)
                board_df = pd.DataFrame(board_rows).set_index("Round")

            st.dataframe(board_df, use_container_width=True, height=600)


# ================================================================
# TAB 7: MATCHUPS
# ================================================================
with tab7:
    st.markdown("### ⚔️ Matchups")

    from datetime import date as dt_date2

    # Week selector — reuse the WEEK_DATES map from tab5
    WEEK_DATES_MU = {
        1:  ("2026-03-27", "2026-04-06"),
        2:  ("2026-04-07", "2026-04-13"),
        3:  ("2026-04-14", "2026-04-20"),
        4:  ("2026-04-21", "2026-04-27"),
        5:  ("2026-04-28", "2026-05-04"),
        6:  ("2026-05-05", "2026-05-11"),
        7:  ("2026-05-12", "2026-05-18"),
        8:  ("2026-05-19", "2026-05-25"),
        9:  ("2026-05-26", "2026-06-01"),
        10: ("2026-06-02", "2026-06-08"),
        11: ("2026-06-09", "2026-06-15"),
        12: ("2026-06-16", "2026-06-22"),
        13: ("2026-06-23", "2026-06-29"),
        14: ("2026-06-30", "2026-07-06"),
        15: ("2026-07-07", "2026-07-13"),
        16: ("2026-07-14", "2026-07-20"),
        17: ("2026-07-21", "2026-07-27"),
        18: ("2026-07-28", "2026-08-03"),
        19: ("2026-08-04", "2026-08-10"),
        20: ("2026-08-11", "2026-08-17"),
        21: ("2026-08-18", "2026-08-24"),
        22: ("2026-08-25", "2026-08-31"),
        23: ("2026-09-01", "2026-09-07"),
        24: ("2026-09-08", "2026-09-14"),
        25: ("2026-09-15", "2026-09-21"),
        26: ("2026-09-22", "2026-09-27"),
    }

    today2 = dt_date2.today()
    available_mu_weeks = {
        w: (s, e) for w, (s, e) in WEEK_DATES_MU.items()
        if dt_date2.fromisoformat(s) <= today2
    }
    current_mu_week = max(available_mu_weeks.keys()) if available_mu_weeks else 1

    col_mu_week, col_mu_load = st.columns([2, 1])
    with col_mu_week:
        selected_mu_week = st.selectbox(
            "Week:",
            list(available_mu_weeks.keys()),
            index=len(available_mu_weeks) - 1,
            format_func=lambda w: f"Week {w}  ({WEEK_DATES_MU[w][0]} – {WEEK_DATES_MU[w][1]})",
            key="mu_week_sel"
        )
    with col_mu_load:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        mu_load_btn = st.button("🔄 Load Matchups", type="primary", key="mu_load", use_container_width=True)

    if mu_load_btn:
        with st.spinner("Loading matchups from Yahoo..."):
            matchups_raw = get_current_matchups(access_token, YAHOO_LEAGUE_ID, week=selected_mu_week)
        st.session_state["mu_matchups"] = matchups_raw
        st.session_state["mu_week_loaded"] = selected_mu_week

    if "mu_matchups" in st.session_state and st.session_state.get("mu_week_loaded") == selected_mu_week:
        matchups_raw = st.session_state["mu_matchups"]
        loaded_week = st.session_state["mu_week_loaded"]

        if not matchups_raw:
            st.warning("No matchup data found for this week.")
        else:
            week_start_str, week_end_str = WEEK_DATES_MU.get(loaded_week, ("", ""))

            # Load Statcast + rosters for real stat lookup
            sc_df_mu = load_statcast_local(DEFAULT_SEASON)
            rosters_mu = st.session_state.get("fantasy_rosters_cached", {})
            if not rosters_mu:
                cached_mu = load_yahoo_data()
                rosters_mu = cached_mu.get("rosters", {}) if cached_mu else {}

            has_statcast = not sc_df_mu.empty

            if has_statcast:
                sc_df_mu["game_date"] = pd.to_datetime(sc_df_mu["game_date"])
                from utils.data_loader import load_batter_lookup
                lookup_mu = load_batter_lookup(DEFAULT_SEASON)
                if not lookup_mu.empty and "batter" in sc_df_mu.columns:
                    sc_df_mu["batter"] = sc_df_mu["batter"].astype(int)
                    lookup_mu["batter"] = lookup_mu["batter"].astype(int)
                    sc_df_mu = sc_df_mu.merge(lookup_mu, on="batter", how="left")

                start_d_mu = dt_date2.fromisoformat(week_start_str) if week_start_str else None
                end_d_mu = dt_date2.fromisoformat(week_end_str) if week_end_str else None

                with st.spinner("Calculating player stats for the week..."):
                    batter_mu_df, pitcher_mu_df = build_player_scoring_from_statcast(
                        sc_df_mu, rosters_mu,
                        start_date=start_d_mu, end_date=end_d_mu
                    )

                # Build lookup: player name -> stats row
                batter_stats_lookup = {r["Name"]: r for r in batter_mu_df.to_dict("records")} if not batter_mu_df.empty else {}
                pitcher_stats_lookup = {r["Name"]: r for r in pitcher_mu_df.to_dict("records")} if not pitcher_mu_df.empty else {}
            else:
                batter_stats_lookup = {}
                pitcher_stats_lookup = {}
                st.caption("⚠️ No Statcast data loaded — showing Yahoo points only. Download Statcast data in Data Manager for full stats.")

            # Build name->team map from rosters
            name_to_fantasy_team = {}
            for norm_name, info in rosters_mu.items():
                name_to_fantasy_team[info["yahoo_name"]] = info["fantasy_team"]
                name_to_fantasy_team[norm_name] = info["fantasy_team"]

            # Helper: get all players for a team from rosters
            def get_team_players(team_name):
                return [
                    info for info in rosters_mu.values()
                    if info["fantasy_team"] == team_name
                ]

            # Helper: aggregate team stats across all rostered players
            def aggregate_team_stats(team_name):
                players = get_team_players(team_name)
                b_stats = {"HR": 0, "SB": 0, "BB": 0, "H": 0, "AB": 0, "SO": 0, "Fantasy Pts": 0.0}
                p_stats = {"IP": 0.0, "SO": 0, "BB": 0, "Fantasy Pts": 0.0}
                hits, ab = 0, 0
                for p in players:
                    pname = p["yahoo_name"]
                    is_pitcher = any(pos in p.get("positions", []) for pos in ["SP", "RP", "P"])
                    if is_pitcher:
                        row = pitcher_stats_lookup.get(pname, {})
                        p_stats["IP"] += row.get("IP", 0) or 0
                        p_stats["SO"] += row.get("SO", 0) or 0
                        p_stats["BB"] += row.get("BB", 0) or 0
                        p_stats["Fantasy Pts"] += row.get("Fantasy Pts", 0) or 0
                    else:
                        row = batter_stats_lookup.get(pname, {})
                        b_stats["HR"] += row.get("HR", 0) or 0
                        b_stats["SB"] += row.get("SB", 0) or 0
                        b_stats["BB"] += row.get("BB", 0) or 0
                        b_stats["H"] += row.get("H", 0) or 0
                        b_stats["AB"] += row.get("PA", 0) or 0
                        b_stats["SO"] += row.get("SO", 0) or 0
                        b_stats["Fantasy Pts"] += row.get("Fantasy Pts", 0) or 0
                        hits += row.get("H", 0) or 0
                        ab_val = row.get("PA", 0) or 0
                        ab += ab_val
                b_stats["AVG"] = round(hits / ab, 3) if ab > 0 else 0.0
                return b_stats, p_stats

            # View toggle
            mu_view = st.radio("View:", ["Scoreboard", "Player Cards"], horizontal=True, key="mu_view_toggle")
            st.markdown("---")

            for mu in matchups_raw:
                t1_name = mu["team1_name"]
                t2_name = mu["team2_name"]
                t1_pts = mu["team1_pts"]
                t2_pts = mu["team2_pts"]
                t1_proj = mu["team1_projected"]
                t2_proj = mu["team2_projected"]
                status = mu.get("status", "")
                is_tied = mu.get("is_tied", False)

                t1_leading = t1_pts > t2_pts
                t2_leading = t2_pts > t1_pts

                if mu_view == "Scoreboard":
                    with st.container():
                        st.markdown(
                            f"""
                            <div style="background:var(--color-background-primary);
                                        border:0.5px solid var(--color-border-tertiary);
                                        border-radius:12px; padding:1.25rem; margin-bottom:1rem;">
                              <div style="display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:1rem; margin-bottom:1rem;">
                                <div>
                                  <div style="font-size:15px; font-weight:500; color:var(--color-text-primary);">{t1_name}</div>
                                  <div style="font-size:28px; font-weight:500; color:{'#185FA5' if t1_leading else 'var(--color-text-primary)'};">{t1_pts:.1f}</div>
                                  {'<div style="font-size:12px;color:var(--color-text-tertiary);">proj ' + str(round(t1_proj,1)) + '</div>' if t1_proj else ''}
                                </div>
                                <div style="font-size:13px; color:var(--color-text-secondary); text-align:center;">{'🔴 Live' if status == 'midevent' else ('✅ Final' if status == 'postevent' else 'vs')}</div>
                                <div style="text-align:right;">
                                  <div style="font-size:15px; font-weight:500; color:var(--color-text-primary);">{t2_name}</div>
                                  <div style="font-size:28px; font-weight:500; color:{'#185FA5' if t2_leading else 'var(--color-text-primary)'};">{t2_pts:.1f}</div>
                                  {'<div style="font-size:12px;color:var(--color-text-tertiary);">proj ' + str(round(t2_proj,1)) + '</div>' if t2_proj else ''}
                                </div>
                              </div>
                            """,
                            unsafe_allow_html=True
                        )

                        if has_statcast:
                            t1_b, t1_p = aggregate_team_stats(t1_name)
                            t2_b, t2_p = aggregate_team_stats(t2_name)

                            def hi(v1, v2, fmt=None):
                                """Return (str1, str2) with leading value bolded blue."""
                                s1 = fmt(v1) if fmt else str(v1)
                                s2 = fmt(v2) if fmt else str(v2)
                                c1 = "#185FA5" if v1 > v2 else "var(--color-text-primary)"
                                c2 = "#185FA5" if v2 > v1 else "var(--color-text-primary)"
                                return (
                                    f'<span style="color:{c1};font-weight:{"500" if v1>v2 else "400"}">{s1}</span>',
                                    f'<span style="color:{c2};font-weight:{"500" if v2>v1 else "400"}">{s2}</span>',
                                )

                            def stat_row(label, v1, v2, fmt=None):
                                h1, h2 = hi(v1, v2, fmt)
                                return f"""
                                <div style="display:grid;grid-template-columns:1fr auto 1fr;align-items:center;font-size:13px;margin:4px 0;">
                                  <div>{h1}</div>
                                  <div style="color:var(--color-text-secondary);font-size:12px;padding:0 12px;text-align:center;">{label}</div>
                                  <div style="text-align:right;">{h2}</div>
                                </div>"""

                            batting_html = (
                                '<div style="font-size:11px;font-weight:500;color:var(--color-text-tertiary);'
                                'text-transform:uppercase;letter-spacing:.06em;margin:1rem 0 6px;">Batting</div>'
                                + stat_row("HR", t1_b["HR"], t2_b["HR"])
                                + stat_row("SB", t1_b["SB"], t2_b["SB"])
                                + stat_row("BB", t1_b["BB"], t2_b["BB"])
                                + stat_row("AVG", t1_b["AVG"], t2_b["AVG"], fmt=lambda x: f"{x:.3f}")
                                + stat_row("SO", t1_b["SO"], t2_b["SO"])
                            )
                            pitching_html = (
                                '<div style="font-size:11px;font-weight:500;color:var(--color-text-tertiary);'
                                'text-transform:uppercase;letter-spacing:.06em;margin:1rem 0 6px;">Pitching</div>'
                                + stat_row("IP", t1_p["IP"], t2_p["IP"], fmt=lambda x: f"{x:.1f}")
                                + stat_row("K", t1_p["SO"], t2_p["SO"])
                                + stat_row("BB allowed", t1_p["BB"], t2_p["BB"])
                            )

                            st.markdown(
                                f'<div style="border-top:0.5px solid var(--color-border-tertiary);padding-top:1rem;">'
                                + batting_html + pitching_html +
                                '</div></div>',
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown("</div>", unsafe_allow_html=True)

                else:
                    # Player Cards view
                    st.markdown(
                        f"""<div style="background:var(--color-background-primary);
                                        border:0.5px solid var(--color-border-tertiary);
                                        border-radius:12px; padding:1.25rem; margin-bottom:1rem;">
                          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;">
                            <span style="font-size:15px;font-weight:500;color:var(--color-text-primary);">{t1_name}</span>
                            <span style="font-size:18px;font-weight:500;color:{'#185FA5' if t1_leading else 'var(--color-text-primary)'};">{t1_pts:.1f}</span>
                            <span style="font-size:13px;color:var(--color-text-secondary);">vs</span>
                            <span style="font-size:18px;font-weight:500;color:{'#185FA5' if t2_leading else 'var(--color-text-primary)'};">{t2_pts:.1f}</span>
                            <span style="font-size:15px;font-weight:500;color:var(--color-text-primary);">{t2_name}</span>
                          </div>""",
                        unsafe_allow_html=True
                    )

                    for team_name in [t1_name, t2_name]:
                        players_mu = get_team_players(team_name)
                        batters_mu = [p for p in players_mu if not any(pos in p.get("positions", []) for pos in ["SP", "RP", "P"])]
                        pitchers_mu = [p for p in players_mu if any(pos in p.get("positions", []) for pos in ["SP", "RP", "P"])]

                        st.markdown(f"**{team_name}**")

                        for group_label, group_players, stats_lookup, stat_keys in [
                            ("Batters", batters_mu, batter_stats_lookup,
                             [("HR", "HR"), ("SB", "SB"), ("AVG", "AVG"), ("BB", "BB"), ("SO", "SO")]),
                            ("Pitchers", pitchers_mu, pitcher_stats_lookup,
                             [("IP", "IP"), ("K", "SO"), ("BB", "BB")]),
                        ]:
                            if not group_players:
                                continue
                            st.markdown(
                                f'<div style="font-size:11px;font-weight:500;color:var(--color-text-tertiary);'
                                f'text-transform:uppercase;letter-spacing:.06em;margin:8px 0 6px;">{group_label}</div>',
                                unsafe_allow_html=True
                            )
                            cols_mu = st.columns(3)
                            for idx, player in enumerate(group_players):
                                pname = player["yahoo_name"]
                                row = stats_lookup.get(pname, {})
                                fpts = row.get("Fantasy Pts", 0) or 0
                                positions = ", ".join(player.get("positions", []))
                                mlb_team = player.get("mlb_team", "")

                                stat_bits = []
                                for label, key in stat_keys:
                                    val = row.get(key)
                                    if val is not None and val != 0:
                                        if key == "AVG":
                                            stat_bits.append(f"{label} {val:.3f}")
                                        elif key == "IP":
                                            stat_bits.append(f"{label} {val:.1f}")
                                        else:
                                            stat_bits.append(f"{label} {int(val)}")
                                stats_str = " · ".join(stat_bits) if stat_bits else "No data"

                                pts_color = "#185FA5" if fpts > 0 else ("var(--color-text-danger)" if fpts < 0 else "var(--color-text-secondary)")

                                with cols_mu[idx % 3]:
                                    st.markdown(
                                        f"""<div style="background:var(--color-background-secondary);
                                                        border-radius:8px;padding:10px 12px;margin-bottom:8px;">
                                          <div style="font-size:13px;font-weight:500;color:var(--color-text-primary);margin-bottom:2px;">{pname}</div>
                                          <div style="font-size:11px;color:var(--color-text-secondary);margin-bottom:6px;">{positions} · {mlb_team}</div>
                                          <div style="font-size:12px;color:var(--color-text-secondary);margin-bottom:6px;">{stats_str}</div>
                                          <div style="font-size:11px;color:{pts_color};font-weight:500;">{'+' if fpts > 0 else ''}{fpts:.1f} pts</div>
                                        </div>""",
                                        unsafe_allow_html=True
                                    )

                    st.markdown("</div>", unsafe_allow_html=True)
                    st.markdown("---")
    else:
        st.info("Select a week and click **Load Matchups** to get started.")
