import streamlit as st
import pandas as pd
import os
from datetime import datetime
from utils.style import inject_custom_css
from config import DEFAULT_SEASON, AVAILABLE_SEASONS

from utils.data_loader import (
    get_data_status, data_is_fresh, refresh_all_data,
    _load_metadata, DATA_DIR,
)

st.set_page_config(page_title="Data Manager", page_icon="⚾", layout="wide")
inject_custom_css()

st.markdown("## 💾 Data Manager")
st.markdown("Download, refresh, and monitor your local baseball data.")

season = st.selectbox("Season", AVAILABLE_SEASONS, index=AVAILABLE_SEASONS.index(DEFAULT_SEASON))

st.markdown("### 📦 Data Status")

status = get_data_status(season)
meta = _load_metadata()

dataset_labels = {
    "statcast": "Statcast Pitch Data",
    "batting_stats": "Batting Stats (FanGraphs)",
    "pitching_stats": "Pitching Stats (FanGraphs)",
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
        st.success(f"""
        ✅ Refresh complete!
        - Batting stats: {results['batting']:,} players
        - Pitching stats: {results['pitching']:,} players
        - Statcast batting agg: {results['sc_batting']:,} players
        - Statcast pitching agg: {results['sc_pitching']:,} players
        - Statcast pitches: {results['statcast']:,} total rows
        """)
        st.rerun()

with col2:
    if st.button("🗑️ Full Re-download (replace all)", use_container_width=True):
        st.warning("This will re-download the entire season. May take 5-10 minutes.")
        confirm = st.checkbox("I understand, proceed with full download")
        if confirm:
            results = refresh_all_data(season, full_statcast=True)
            st.success(f"✅ Full download complete! {results['statcast']:,} Statcast pitches.")
            st.rerun()

st.markdown("---")
st.caption(
    "💡 The app automatically checks data freshness on startup. "
    "If data is older than 24 hours, you'll see a banner on the home page."
)