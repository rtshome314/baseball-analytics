import os

import duckdb
import pandas as pd
import streamlit as st

from utils.style import inject_custom_css, render_nav_back, render_data_status
from config import DEFAULT_SEASON, AVAILABLE_SEASONS
from utils.data_loader import load_team_batting, load_team_pitching, DATA_DIR

st.set_page_config(page_title="Team Comparison", page_icon="⚾", layout="wide")
inject_custom_css()
render_nav_back()

DIVISIONS = ["AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West"]

filters = st.expander("⚙️ Settings", expanded=True) if st.session_state.get("mobile_mode") else st.sidebar
with filters:
    st.markdown("### ⚙️ Settings")
    season = st.selectbox("Season", AVAILABLE_SEASONS, index=AVAILABLE_SEASONS.index(DEFAULT_SEASON), key="tc_season")
    league_filter = st.radio("League", ["All", "AL", "NL"], horizontal=True, key="tc_league")
    available_divs = [d for d in DIVISIONS if league_filter == "All" or d.startswith(league_filter)]
    selected_divs = st.multiselect("Divisions", available_divs, default=available_divs, key=f"tc_divs_{league_filter}")

render_data_status(["team_batting", "team_pitching", "statcast"], season=season)

st.markdown("## 🏟️ Team Comparison")
st.markdown("Compare teams side by side: standings, team batting and pitching (Baseball Reference), and Statcast quality of contact.")

team_batting = load_team_batting(season)
team_pitching = load_team_pitching(season)

if team_batting.empty or team_pitching.empty:
    st.warning("No team stats for this season. Head to **Data Manager** and run Smart Refresh to download them.")
    st.stop()


@st.cache_data(show_spinner="Crunching Statcast by team…")
def team_statcast(season, mtime):
    """Team-level Statcast for offense (batting team) and pitching (contact allowed). mtime busts the cache after refresh."""
    path = os.path.join(DATA_DIR, f"statcast_{season}.parquet").replace("\\", "/")
    if not os.path.exists(path):
        return pd.DataFrame(), pd.DataFrame()
    swing = "('swinging_strike','swinging_strike_blocked','foul','foul_tip','foul_bunt','hit_into_play','missed_bunt')"
    whiff = "('swinging_strike','swinging_strike_blocked','missed_bunt')"
    metrics = f"""
        ROUND(AVG(launch_speed) FILTER (WHERE bbe), 1) AS "Avg EV",
        MAX(launch_speed) FILTER (WHERE bbe) AS "Max EV",
        ROUND(100.0 * COUNT(*) FILTER (WHERE bbe AND launch_speed >= 95) / COUNT(*) FILTER (WHERE bbe), 1) AS "Hard Hit %",
        ROUND(100.0 * COUNT(*) FILTER (WHERE bbe AND launch_speed_angle = 6) / COUNT(*) FILTER (WHERE bbe), 1) AS "Barrel %",
        ROUND(AVG(launch_angle) FILTER (WHERE bbe), 1) AS "Launch Angle",
        ROUND(SUM(CASE WHEN bbe AND estimated_woba_using_speedangle IS NOT NULL THEN estimated_woba_using_speedangle
                       ELSE woba_value END) FILTER (WHERE woba_denom > 0)
              / SUM(woba_denom) FILTER (WHERE woba_denom > 0), 3) AS "xwOBA",
        ROUND(100.0 * COUNT(*) FILTER (WHERE description IN {whiff}) / COUNT(*) FILTER (WHERE description IN {swing}), 1) AS "Whiff %",
        ROUND(100.0 * COUNT(*) FILTER (WHERE zone > 9 AND description IN {swing}) / COUNT(*) FILTER (WHERE zone > 9), 1) AS "Chase %"
    """
    base = f"""
        SELECT *, (type = 'X' AND launch_speed IS NOT NULL) AS bbe,
               CASE WHEN inning_topbot = 'Top' THEN away_team ELSE home_team END AS bat_team,
               CASE WHEN inning_topbot = 'Top' THEN home_team ELSE away_team END AS pit_team
        FROM read_parquet('{path}')
    """
    con = duckdb.connect()
    off = con.execute(f"SELECT bat_team AS sc_team, {metrics} FROM ({base}) GROUP BY 1").df()
    pit = con.execute(f"SELECT pit_team AS sc_team, {metrics} FROM ({base}) GROUP BY 1").df()
    con.close()
    return off, pit


def rank_table(df, cols, lower_is_better=()):
    """Rank every team 1-30 on each column (#1 = best)."""
    ranks = df[["Team"]].copy()
    for c in cols:
        ranks[c] = df[c].rank(ascending=c in lower_is_better, method="min").astype("Int64")
    return ranks


def show_stats_and_ranks(df, cols, sort_col, lower_is_better=(), fmt=None, key=""):
    sel = df[df["Team"].isin(selected_teams)]
    sort_asc = sort_col in lower_is_better
    st.dataframe(
        sel[["Team"] + cols].sort_values(sort_col, ascending=sort_asc).reset_index(drop=True),
        use_container_width=True, hide_index=True,
        column_config={c: st.column_config.NumberColumn(format=f) for c, f in (fmt or {}).items()},
    )
    st.caption("Rank out of 30 teams (#1 = best).")
    ranks = rank_table(df, cols, lower_is_better)
    ranks = ranks[ranks["Team"].isin(selected_teams)]
    st.dataframe(ranks.sort_values(sort_col).reset_index(drop=True), use_container_width=True, hide_index=True)


# Team selection
info = team_batting[["Team", "Tm", "sc_team", "Lg", "Div"]]
div_teams = info.loc[info["Div"].isin(selected_divs), "Team"].tolist()
all_teams = sorted(info["Team"].tolist())
selected_teams = st.multiselect("Select teams to compare", all_teams, default=sorted(div_teams), key=f"tc_teams_{season}_{league_filter}_{'-'.join(selected_divs)}")

if not selected_teams:
    st.info("👆 Select teams above to compare.")
    st.stop()

tab0, tab1, tab2, tab3 = st.tabs(["🏆 Standings", "🏏 Team Batting", "⚾ Team Pitching", "📊 Team Statcast"])

# ========================
# STANDINGS
# ========================
with tab0:
    standings = info.merge(team_pitching[["Team", "W", "L", "W-L%", "R"]].rename(columns={"R": "RA"}), on="Team")
    standings = standings.merge(team_batting[["Team", "R"]].rename(columns={"R": "RS"}), on="Team")
    standings["Run Diff"] = standings["RS"] - standings["RA"]
    standings = standings[standings["Team"].isin(selected_teams)]
    st.caption("Win-loss records and runs from Baseball Reference team totals. GB = games behind the division leader among all teams.")
    full = info.merge(team_pitching[["Team", "W", "L"]], on="Team")
    for div in DIVISIONS:
        d = standings[standings["Div"] == div]
        if d.empty:
            continue
        lead = full[full["Div"] == div]
        lead = lead.loc[(lead["W"] - lead["L"]).idxmax()]
        d = d.assign(GB=((lead["W"] - d["W"]) + (d["L"] - lead["L"])) / 2)
        d["GB"] = d["GB"].map(lambda g: "—" if g == 0 else f"{g:g}")
        st.markdown(f"#### {div}")
        st.dataframe(
            d.sort_values("W-L%", ascending=False)[["Team", "W", "L", "W-L%", "GB", "RS", "RA", "Run Diff"]],
            use_container_width=True, hide_index=True,
            column_config={"W-L%": st.column_config.NumberColumn(format="%.3f")},
        )

# ========================
# TEAM BATTING
# ========================
with tab1:
    bat_cols = [c for c in ["R/G", "BA", "OBP", "SLG", "OPS", "OPS+", "R", "HR", "RBI", "SB", "BB", "SO", "BatAge"] if c in team_batting.columns]
    st.markdown("### Team Batting")
    show_stats_and_ranks(
        team_batting, bat_cols, "OPS", lower_is_better=("SO",),
        fmt={"BA": "%.3f", "OBP": "%.3f", "SLG": "%.3f", "OPS": "%.3f", "R/G": "%.2f"},
    )
    st.caption("BatAge is ranked youngest first.")

# ========================
# TEAM PITCHING
# ========================
with tab2:
    pit_cols = [c for c in ["RA/G", "ERA", "ERA+", "FIP", "WHIP", "SO9", "BB9", "HR9", "SO/W", "SV", "IP", "PAge"] if c in team_pitching.columns]
    st.markdown("### Team Pitching")
    show_stats_and_ranks(
        team_pitching, pit_cols, "ERA",
        lower_is_better=("RA/G", "ERA", "FIP", "WHIP", "BB9", "HR9", "PAge"),
        fmt={"ERA": "%.2f", "FIP": "%.2f", "WHIP": "%.3f", "RA/G": "%.2f"},
    )

# ========================
# TEAM STATCAST
# ========================
with tab3:
    sc_path = os.path.join(DATA_DIR, f"statcast_{season}.parquet")
    off, pit = team_statcast(season, os.path.getmtime(sc_path) if os.path.exists(sc_path) else 0)
    if off.empty:
        st.warning("No Statcast data for this season. Head to **Data Manager** to download it.")
    else:
        sc_cols = ["Avg EV", "Max EV", "Hard Hit %", "Barrel %", "Launch Angle", "xwOBA", "Whiff %", "Chase %"]
        names = info[["Team", "sc_team"]]
        st.markdown("### Offense: quality of contact")
        st.caption("Computed from every pitch in Statcast. Whiff % and Chase % are the hitters' rates.")
        show_stats_and_ranks(
            names.merge(off, on="sc_team"), sc_cols, "xwOBA",
            lower_is_better=("Whiff %", "Chase %"), fmt={"xwOBA": "%.3f"},
        )
        st.markdown("### Pitching: contact allowed")
        st.caption("Same stats for batters facing this team's pitchers. Lower contact quality is better; higher Whiff % and Chase % are better.")
        show_stats_and_ranks(
            names.merge(pit, on="sc_team"), sc_cols, "xwOBA",
            lower_is_better=("Avg EV", "Max EV", "Hard Hit %", "Barrel %", "xwOBA"), fmt={"xwOBA": "%.3f"},
        )
        st.caption("Launch Angle is ranked highest first and is neither good nor bad on its own.")
