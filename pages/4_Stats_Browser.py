import streamlit as st
import pandas as pd
import json
import os
from utils.style import inject_custom_css, render_nav_back
from config import DEFAULT_SEASON, AVAILABLE_SEASONS

from utils.data_loader import load_batting_stats, load_pitching_stats

BOOKMARK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sb_bookmarks.json")

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

st.markdown("## 📋 Stats Browser")

with st.sidebar:
    st.markdown("### ⚙️ Browser Settings")
    season = st.selectbox("Season", AVAILABLE_SEASONS, index=AVAILABLE_SEASONS.index(DEFAULT_SEASON), key="sb_season")
    stat_type = st.radio("Stat Type", ["Batting", "Pitching"])
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
    df = load_batting_stats(season)
    qual_col = "PA"
else:
    df = load_pitching_stats(season)
    qual_col = "IP"

# Normalize team column name (BRef uses "Tm")
if "Tm" in df.columns and "Team" not in df.columns:
    df = df.rename(columns={"Tm": "Team"})

if not df.empty:
    if qual_col in df.columns:
        df = df[df[qual_col] >= min_pa]

    search = st.text_input("🔍 Search player name", "")
    if search:
        df = df[df["Name"].str.contains(search, case=False, na=False)]

    with st.sidebar:
        if "Team" in df.columns:
            teams = sorted(df["Team"].dropna().unique().tolist())
            bm_data = st.session_state.get("sb_bm_data", {})
            default_teams = [t for t in bm_data.get("teams", []) if t in teams]
            selected_teams = st.multiselect("Filter by Team", teams, default=default_teams, key="sb_teams")
            if selected_teams:
                df = df[df["Team"].isin(selected_teams)]

        sortable = [c for c in df.columns if df[c].dtype in ["float64", "int64", "float32", "int32"]]
        sort_col = st.selectbox("Sort by", sortable, index=0)
        sort_asc = st.checkbox("Ascending", value=False)

    df_sorted = df.sort_values(sort_col, ascending=sort_asc)

    st.markdown(f"**{len(df_sorted)} players** | Season {season} | Min {qual_col}: {min_pa}")
    st.dataframe(df_sorted.reset_index(drop=True), use_container_width=True, height=700,
                 column_config={"Name": st.column_config.TextColumn(pinned=True)})

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