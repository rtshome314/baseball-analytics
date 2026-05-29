import streamlit as st
import pandas as pd
import json
import os
from utils.style import inject_custom_css, render_nav_back, render_data_status
from config import DEFAULT_SEASON, AVAILABLE_SEASONS

from utils.data_loader import load_batting_stats, load_pitching_stats, load_batting_stats_post, load_pitching_stats_post

BOOKMARK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sb_bookmarks.json")

# --- MLB team → division/league mapping ---
TEAM_DIVISIONS = {
    # AL East
    "NYY": "AL East", "BOS": "AL East", "TBR": "AL East", "TOR": "AL East", "BAL": "AL East",
    # AL Central
    "CLE": "AL Central", "MIN": "AL Central", "CHW": "AL Central", "KCR": "AL Central", "DET": "AL Central",
    # AL West
    "HOU": "AL West", "SEA": "AL West", "TEX": "AL West", "LAA": "AL West", "ATH": "AL West",
    # NL East
    "ATL": "NL East", "NYM": "NL East", "PHI": "NL East", "MIA": "NL East", "WSN": "NL East",
    # NL Central
    "MIL": "NL Central", "CHC": "NL Central", "STL": "NL Central", "PIT": "NL Central", "CIN": "NL Central",
    # NL West
    "LAD": "NL West", "SDP": "NL West", "SFG": "NL West", "ARI": "NL West", "COL": "NL West",
}

DIVISIONS = ["AL East", "AL Central", "AL West", "NL East", "NL Central", "NL West"]
LEAGUES = ["AL", "NL"]

def load_bookmarks():
    if os.path.exists(BOOKMARK_FILE):
        with open(BOOKMARK_FILE, "r") as f:
            return json.load(f)
    return {}

def save_bookmarks(bookmarks):
    with open(BOOKMARK_FILE, "w") as f:
        json.dump(bookmarks, f, indent=2)

st.set_page_config(page_title="Stats Browser", page_icon="⚾", layout="wide")
inject_custom_css()
render_nav_back()
render_data_status(["batting_stats", "pitching_stats"])

st.markdown("## 📋 Stats Browser")

if st.session_state.get("mobile_mode"):
    filters = st.expander("⚙️ Browser Settings", expanded=True)
else:
    filters = st.sidebar

with filters:
    st.markdown("### ⚙️ Browser Settings")
    season = st.selectbox("Season", AVAILABLE_SEASONS, index=AVAILABLE_SEASONS.index(DEFAULT_SEASON), key="sb_season")
    stat_type = st.radio("Stat Type", ["Batting", "Pitching"])
    season_type = st.radio("Season Type", ["Regular Season", "Postseason"], horizontal=True, key="sb_season_type")
    min_pa = st.slider("Min PA" if stat_type == "Batting" else "Min IP", 0, 500, 50)

    # --- Bookmarks ---
    st.markdown("### 🔖 Bookmarks")
    bookmarks = load_bookmarks()
    bookmark_names = list(bookmarks.keys())
    
    if bookmark_names:
        selected_bookmark = st.selectbox("Load bookmark", [""] + bookmark_names, key="sb_bm_select")
        if selected_bookmark and st.button("📂 Load", key="sb_bm_load"):
            bm = bookmarks[selected_bookmark]
            st.session_state["sb_bm_data"] = bm
            st.rerun()
        if selected_bookmark and st.button("🗑️ Delete", key="sb_bm_delete"):
            del bookmarks[selected_bookmark]
            save_bookmarks(bookmarks)
            st.rerun()
    
    new_bm_name = st.text_input("Save current view as", key="sb_bm_name")
    if new_bm_name and st.button("💾 Save Bookmark", key="sb_bm_save"):
        bookmarks[new_bm_name] = {
            "stat_type": stat_type,
            "min_pa": min_pa,
            "teams": st.session_state.get("sb_teams", []),
        }
        save_bookmarks(bookmarks)
        st.success(f"Saved '{new_bm_name}'")

if stat_type == "Batting":
    df = load_batting_stats_post(season) if season_type == "Postseason" else load_batting_stats(season)
    qual_col = "PA"
else:
    df = load_pitching_stats_post(season) if season_type == "Postseason" else load_pitching_stats(season)
    qual_col = "IP"

# Normalize team column name (BRef uses "Tm")
if "Tm" in df.columns and "Team" not in df.columns:
    df = df.rename(columns={"Tm": "Team"})

if not df.empty:
    if qual_col in df.columns:
        df = df[df[qual_col] >= min_pa]

    # --- Per-162 calculated columns (batting only) ---
    if stat_type == "Batting":
        if "H" in df.columns and "G" in df.columns:
            df["H/162"] = (df["H"] / (df["G"] / 162)).round(1)
        if "HR" in df.columns and "G" in df.columns:
            df["HR/162"] = (df["HR"] / (df["G"] / 162)).round(1)

    search = st.text_input("🔍 Search player name", "")
    if search:
        df = df[df["Name"].str.contains(search, case=False, na=False)]

    with filters:
        if "Team" in df.columns:
            # --- League filter ---
            selected_leagues = st.multiselect("Filter by League", LEAGUES, key="sb_leagues")
            # --- Division filter ---
            selected_divisions = st.multiselect("Filter by Division", DIVISIONS, key="sb_divisions")

            # Apply league/division filters
            if selected_leagues or selected_divisions:
                def get_division(team):
                    return TEAM_DIVISIONS.get(team, None)
                def get_league(team):
                    div = TEAM_DIVISIONS.get(team, None)
                    return div[:2] if div else None

                if selected_divisions:
                    df = df[df["Team"].apply(get_division).isin(selected_divisions)]
                elif selected_leagues:
                    df = df[df["Team"].apply(get_league).isin(selected_leagues)]

            # --- Team filter (still works independently) ---
            teams = sorted(df["Team"].dropna().unique().tolist())
            bm_data = st.session_state.get("sb_bm_data", {})
            default_teams = [t for t in bm_data.get("teams", []) if t in teams]
            selected_teams = st.multiselect("Filter by Team", teams, default=default_teams, key="sb_teams")
            if selected_teams:
                df = df[df["Team"].isin(selected_teams)]

        if stat_type == "Batting" and "Pos" in df.columns:
            POS_MAP = {
                "C": "2", "1B": "3", "2B": "4", "3B": "5",
                "SS": "6", "LF": "7", "CF": "8", "RF": "9", "DH": "D",
            }
            pos_labels = list(POS_MAP.keys())

            st.markdown("**Filter by Position (appeared at)**")
            sel_pos = st.multiselect("Position", pos_labels, key="sb_pos_appeared", label_visibility="collapsed")
            if sel_pos:
                codes = [POS_MAP[p] for p in sel_pos]
                def appeared_at(pos_str, codes=codes):
                    if not isinstance(pos_str, str):
                        return False
                    # All position codes are single chars; strip asterisk/slash and check membership
                    chars = set(pos_str.replace("*", "").replace("/", ""))
                    return any(c in chars for c in codes)
                df = df[df["Pos"].apply(appeared_at)]

            st.markdown("**Filter by Primary Position**")
            sel_primary = st.multiselect("Primary Position", pos_labels, key="sb_pos_primary", label_visibility="collapsed")
            if sel_primary:
                codes_p = [POS_MAP[p] for p in sel_primary]
                def is_primary(pos_str, codes_p=codes_p):
                    if not isinstance(pos_str, str) or "*" not in pos_str:
                        return False
                    stripped = pos_str.lstrip("*")
                    return any(stripped.startswith(c) for c in codes_p)
                df = df[df["Pos"].apply(is_primary)]

        sortable = [c for c in df.columns if df[c].dtype in ["float64", "int64", "float32", "int32"]]
        sort_col = st.selectbox("Sort by", sortable, index=0)
        sort_asc = st.checkbox("Ascending", value=False)

    df_sorted = df.sort_values(sort_col, ascending=sort_asc)

    st.markdown(f"**{len(df_sorted)} players** | Season {season} | Min {qual_col}: {min_pa}")
    st.dataframe(df_sorted.reset_index(drop=True), use_container_width=True, height=700,
                 column_config={"Name": st.column_config.TextColumn(pinned=True)})

    # --- Aggregation Builder ---
    st.markdown("---")
    st.markdown("### 🧮 Aggregation Builder")
    st.markdown("Group and summarize the stats table — like running a SQL query.")

    agg_tab1, agg_tab2, agg_tab3 = st.tabs(["⚙️ Build Query", "📋 Results", "🏆 Top N per Group"])

    with agg_tab1:
        # Group by options — categorical columns that make sense to group on
        group_candidate_cols = []
        group_col_labels = {}

        for col, label in [
            ("Name", "Player Name"),
            ("Team", "Team"),
            ("Pos", "Position (raw)"),
            ("Age", "Age"),
            ("stand", "Batter Hand"),
            ("p_throws", "Pitcher Hand"),
        ]:
            if col in df_sorted.columns:
                group_candidate_cols.append(col)
                group_col_labels[col] = label

        # Add derived position cols if Pos exists
        if "Pos" in df_sorted.columns:
            df_sorted["Primary_Pos"] = df_sorted["Pos"].apply(
                lambda x: x.lstrip("*").split("/")[0] if isinstance(x, str) else None
            )
            if "Primary_Pos" not in group_candidate_cols:
                group_candidate_cols.insert(1, "Primary_Pos")
                group_col_labels["Primary_Pos"] = "Primary Position"

        selected_agg_groups = st.multiselect(
            "Group by",
            group_candidate_cols,
            default=["Team"] if "Team" in group_candidate_cols else [],
            format_func=lambda x: group_col_labels.get(x, x),
            key="sb_agg_group",
        )

        # Metric options — numeric cols
        sb_numeric_cols = [
            c for c in df_sorted.columns
            if df_sorted[c].dtype in ["float64", "int64", "float32", "int32"]
            and c not in ["Age"]
        ]
        # Friendly labels where we know them
        sb_metric_labels = {
            "PA": "PA", "AB": "AB", "H": "Hits", "HR": "HR", "R": "Runs",
            "RBI": "RBI", "SB": "SB", "BB": "BB", "SO": "SO", "AVG": "AVG",
            "OBP": "OBP", "SLG": "SLG", "OPS": "OPS", "WAR": "WAR",
            "IP": "IP", "W": "W", "L": "L", "SV": "SV", "ERA": "ERA",
            "WHIP": "WHIP", "K/9": "K/9", "BB/9": "BB/9",
            "H/162": "H/162", "HR/162": "HR/162",
            "G": "G", "GS": "GS",
        }

        # Metric + function pairs
        st.markdown("#### 📊 Select Metrics")
        st.caption("Each row is one output column — pick a metric and the function to apply to it.")

        sb_num_metric_rows = st.number_input("Number of metrics", min_value=1, max_value=8, value=2, step=1, key="sb_agg_num_metrics")
        sb_metric_pairs = []
        sb_agg_funcs_available = ["count", "mean", "median", "sum", "max", "min", "std"]
        for i in range(int(sb_num_metric_rows)):
            mc1, mc2 = st.columns([3, 2])
            with mc1:
                sb_m_col = st.selectbox(f"Metric #{i+1}", sb_numeric_cols, format_func=lambda x: sb_metric_labels.get(x, x), key=f"sb_agg_metric_col_{i}")
            with mc2:
                sb_m_func = st.selectbox(f"Function #{i+1}", sb_agg_funcs_available, key=f"sb_agg_metric_func_{i}")
            sb_metric_pairs.append((sb_m_col, sb_m_func))

        # Derive flat lists for HAVING preview compatibility
        selected_agg_metrics = list(dict.fromkeys(m for m, _ in sb_metric_pairs))
        sb_agg_funcs = list(dict.fromkeys(f for _, f in sb_metric_pairs))

        sb_min_count = st.number_input("Minimum count (filter out small groups)", min_value=1, value=1, key="sb_agg_min")

        # WHERE clause — pre-aggregation filter on raw rows
        st.markdown("#### 🔍 WHERE — Filter Rows Before Grouping")
        st.caption("Filter individual player rows before aggregating — e.g. only count players with OPS > 0.800.")

        sb_num_where_pre = st.number_input("Number of conditions", min_value=0, max_value=5, value=0, step=1, key="sb_where_pre_count")

        sb_where_pre_conditions = []
        if sb_num_where_pre > 0:
            for i in range(int(sb_num_where_pre)):
                wc1, wc2, wc3 = st.columns([3, 2, 3])
                with wc1:
                    wpre_col = st.selectbox(f"Column #{i+1}", sb_numeric_cols, format_func=lambda x: sb_metric_labels.get(x, x), key=f"sb_wpre_col_{i}")
                with wc2:
                    wpre_op = st.selectbox(f"Operator #{i+1}", [">", ">=", "<", "<=", "==", "!="], key=f"sb_wpre_op_{i}")
                with wc3:
                    wpre_val = st.text_input(f"Value #{i+1}", value="", key=f"sb_wpre_val_{i}")
                if wpre_col and wpre_op and wpre_val.strip():
                    sb_where_pre_conditions.append((wpre_col, wpre_op, wpre_val.strip()))

        # HAVING clause — post-aggregation filter on group results
        st.markdown("#### 📐 HAVING — Filter Groups After Aggregating")
        st.caption("Filter the aggregated results — e.g. only show teams with count >= 5.")

        sb_num_where = st.number_input("Number of conditions", min_value=0, max_value=5, value=0, step=1, key="sb_where_count")

        sb_where_conditions = []
        if sb_num_where > 0:
            result_col_preview = []
            for g in (selected_agg_groups or []):
                result_col_preview.append(group_col_labels.get(g, g))
            for sb_m_col, sb_m_func in sb_metric_pairs:
                result_col_preview.append(f"{sb_metric_labels.get(sb_m_col, sb_m_col)}_{sb_m_func}")

            if result_col_preview:
                for i in range(int(sb_num_where)):
                    wc1, wc2, wc3 = st.columns([3, 2, 3])
                    with wc1:
                        w_col = st.selectbox(f"Column #{i+1}", result_col_preview, key=f"sb_where_col_{i}")
                    with wc2:
                        w_op = st.selectbox(f"Operator #{i+1}", [">", ">=", "<", "<=", "==", "!="], key=f"sb_where_op_{i}")
                    with wc3:
                        w_val = st.text_input(f"Value #{i+1}", value="", key=f"sb_where_val_{i}")
                    if w_col and w_op and w_val.strip():
                        sb_where_conditions.append((w_col, w_op, w_val.strip()))
            else:
                st.caption("Select groups and metrics above to enable HAVING filters.")

    with agg_tab2:
        if selected_agg_groups and sb_metric_pairs:
            try:
                # Apply WHERE pre-filter on raw player rows
                df_agg = df_sorted.copy()
                for (wpre_col, wpre_op, wpre_val) in sb_where_pre_conditions:
                    try:
                        typed_val = float(wpre_val)
                        if wpre_op == ">":    df_agg = df_agg[df_agg[wpre_col] > typed_val]
                        elif wpre_op == ">=": df_agg = df_agg[df_agg[wpre_col] >= typed_val]
                        elif wpre_op == "<":  df_agg = df_agg[df_agg[wpre_col] < typed_val]
                        elif wpre_op == "<=": df_agg = df_agg[df_agg[wpre_col] <= typed_val]
                        elif wpre_op == "==": df_agg = df_agg[df_agg[wpre_col] == typed_val]
                        elif wpre_op == "!=": df_agg = df_agg[df_agg[wpre_col] != typed_val]
                    except Exception as we:
                        st.warning(f"WHERE condition '{wpre_col} {wpre_op} {wpre_val}': {we}")

                # Build agg dict from pairs — each metric gets only its chosen function
                sb_agg_dict = {}
                for sb_m_col, sb_m_func in sb_metric_pairs:
                    sb_agg_dict.setdefault(sb_m_col, [])
                    if sb_m_func not in sb_agg_dict[sb_m_col]:
                        sb_agg_dict[sb_m_col].append(sb_m_func)

                sb_result = df_agg.groupby(selected_agg_groups).agg(sb_agg_dict)
                sb_result.columns = [f"{sb_metric_labels.get(col, col)}_{func}" for col, func in sb_result.columns]

                # Keep only the exact pairs requested
                sb_keep = list(dict.fromkeys(f"{sb_metric_labels.get(m, m)}_{f}" for m, f in sb_metric_pairs))
                sb_result = sb_result[[c for c in sb_keep if c in sb_result.columns]]
                sb_result = sb_result.reset_index()

                # Rename group columns to friendly labels
                sb_result = sb_result.rename(columns=group_col_labels)

                # Min count filter
                sb_count_cols = [c for c in sb_result.columns if c.endswith("_count")]
                if sb_count_cols and sb_min_count > 1:
                    sb_result = sb_result[sb_result[sb_count_cols[0]] >= sb_min_count]

                # Apply WHERE conditions
                for (wcol, wop, wval) in sb_where_conditions:
                    if wcol not in sb_result.columns:
                        st.warning(f"Column '{wcol}' not found in results.")
                        continue
                    try:
                        typed = float(wval) if sb_result[wcol].dtype in ["float64", "float32", "int64", "int32"] else wval
                        ops = {">": "__gt__", ">=": "__ge__", "<": "__lt__", "<=": "__le__", "==": "__eq__", "!=": "__ne__"}
                        sb_result = sb_result[getattr(sb_result[wcol], ops[wop])(typed)]
                    except Exception as we:
                        st.warning(f"Condition '{wcol} {wop} {wval}': {we}")

                # Round floats
                for col in sb_result.columns:
                    if sb_result[col].dtype in ["float64", "float32"]:
                        sb_result[col] = sb_result[col].round(3)

                # Sort by first count col descending
                if sb_count_cols:
                    sb_result = sb_result.sort_values(sb_count_cols[0], ascending=False)

                st.markdown(f"**{len(sb_result):,} groups**")
                st.dataframe(sb_result.reset_index(drop=True), use_container_width=True, height=500)

                sb_agg_csv = sb_result.to_csv(index=False)
                st.download_button("📥 Download aggregated data", sb_agg_csv,
                                   file_name=f"stats_agg_{season}.csv", mime="text/csv", key="sb_agg_download")

            except Exception as e:
                st.error(f"Aggregation error: {e}")
        else:
            st.info("Configure your query in the **Build Query** tab, then come back here to see results.")

    with agg_tab3:
        st.markdown("Return the top N players within each group — e.g. the top 3 OPS by team.")

        topn_col1, topn_col2 = st.columns(2)
        with topn_col1:
            # Group by — categorical only (no Name)
            topn_group_opts = [c for c in group_candidate_cols if c != "Name"]
            topn_group = st.selectbox(
                "Group by",
                topn_group_opts,
                format_func=lambda x: group_col_labels.get(x, x),
                key="sb_topn_group",
            )
        with topn_col2:
            topn_rank_col = st.selectbox(
                "Rank by",
                sb_numeric_cols,
                format_func=lambda x: sb_metric_labels.get(x, x),
                key="sb_topn_rank",
            )

        topn_col3, topn_col4 = st.columns(2)
        with topn_col3:
            topn_n = st.number_input("Top N per group", min_value=1, max_value=25, value=3, step=1, key="sb_topn_n")
        with topn_col4:
            topn_asc = st.checkbox("Ascending (bottom N instead)", value=False, key="sb_topn_asc")

        # Which columns to show in result
        topn_display_candidates = ["Name", "Team", "Primary_Pos", "Pos", "Age"] + sb_numeric_cols
        topn_display_cols = st.multiselect(
            "Columns to show",
            [c for c in topn_display_candidates if c in df_sorted.columns],
            default=[c for c in ["Name", "Team", topn_rank_col] if c in df_sorted.columns],
            key="sb_topn_cols",
        )

        if topn_group and topn_rank_col:
            try:
                topn_df = df_sorted.copy()
                # Auto-exclude multi-team rows (2TM, 3TM, etc.)
                if topn_group == "Team" and "Team" in topn_df.columns:
                    topn_df = topn_df[~topn_df["Team"].str.match(r"^\d+TM$", na=False)]

                topn_result = (
                    topn_df
                    .dropna(subset=[topn_rank_col])
                    .sort_values(topn_rank_col, ascending=topn_asc)
                    .groupby(topn_group, group_keys=False)
                    .head(int(topn_n))
                    .sort_values([topn_group, topn_rank_col], ascending=[True, topn_asc])
                )
                show_cols = [topn_group] + [c for c in topn_display_cols if c != topn_group]
                show_cols = [c for c in show_cols if c in topn_result.columns]
                topn_result = topn_result[show_cols].reset_index(drop=True)

                # Round floats
                for col in topn_result.columns:
                    if topn_result[col].dtype in ["float64", "float32"]:
                        topn_result[col] = topn_result[col].round(3)

                st.markdown(f"**{len(topn_result):,} rows** — top {int(topn_n)} per {group_col_labels.get(topn_group, topn_group)}")
                st.dataframe(topn_result, use_container_width=True, height=500)

                topn_csv = topn_result.to_csv(index=False)
                st.download_button("📥 Download", topn_csv,
                                   file_name=f"topn_{season}.csv", mime="text/csv", key="sb_topn_download")
            except Exception as e:
                st.error(f"Top N error: {e}")

    # --- Custom Charts ---
    st.markdown("---")
    st.markdown("### 📈 Custom Charts")

    import plotly.express as px
    from utils.charts import CHART_TEMPLATE

    numeric_cols = [c for c in df_sorted.columns if df_sorted[c].dtype in ["float64", "int64", "float32", "int32"]]

    chart_type = st.radio("Chart Type", ["Scatter Plot", "Line Chart"], horizontal=True, key="sb_chart_type")

    col1, col2 = st.columns(2)
    with col1:
        x_axis = st.selectbox("X-Axis", numeric_cols, index=0, key="sb_x")
    with col2:
        y_idx = min(1, len(numeric_cols) - 1)
        y_axis = st.selectbox("Y-Axis", numeric_cols, index=y_idx, key="sb_y")

    team_col_options = ["Team"] if "Team" in df_sorted.columns else []
    color_by = st.selectbox("Color by (optional)", ["None"] + team_col_options + numeric_cols, key="sb_color")
    if color_by == "None":
        color_by = None

    if chart_type == "Scatter Plot":
        fig = px.scatter(
            df_sorted, x=x_axis, y=y_axis,
            color=color_by,
            hover_name="Name" if "Name" in df_sorted.columns else None,
            trendline="ols",
        )
    else:
        sorted_for_line = df_sorted.sort_values(x_axis)
        fig = px.line(
            sorted_for_line, x=x_axis, y=y_axis,
            hover_name="Name" if "Name" in sorted_for_line.columns else None,
            markers=True,
        )

    fig.update_layout(**CHART_TEMPLATE, height=500, margin=dict(l=60, r=30, t=40, b=50))
    fig.update_traces(marker=dict(size=8, opacity=0.7))
    st.plotly_chart(fig, use_container_width=True)

    # Show correlation for scatter
    if chart_type == "Scatter Plot":
        valid = df_sorted[[x_axis, y_axis]].dropna()
        if len(valid) > 2:
            corr = valid[x_axis].corr(valid[y_axis])
            st.caption(f"Correlation: **r = {corr:.3f}** | R² = {corr**2:.3f} | n = {len(valid)}")


    csv = df_sorted.to_csv(index=False)
    st.download_button("📥 Download as CSV", csv,
                       file_name=f"{stat_type.lower()}_stats_{season}.csv", mime="text/csv")
else:
    st.warning("No stats loaded. Head to **Data Manager** to download data first.")