import streamlit as st
import pandas as pd
from utils.style import inject_custom_css
from utils.data_loader import load_statcast_local, PITCH_TYPE_MAP, ZONE_MAP

st.set_page_config(page_title="Statcast Viewer", page_icon="⚾", layout="wide")
inject_custom_css()

st.markdown("## 📊 Pitches Statcast Data Viewer")
st.markdown("Browse your locally stored Statcast pitch data.")

with st.sidebar:
    st.markdown("### ⚙️ Statcast Filters")
    season = st.selectbox("Season", [2026, 2025, 2024, 2023], index=1, key="sc_season")

df = load_statcast_local(season)

if not df.empty:
    st.success(f"**{len(df):,}** pitches loaded from local data.")
    
    # Map pitch types and zones to descriptions
    if "pitch_type" in df.columns:
        df["pitch_desc"] = df["pitch_type"].map(PITCH_TYPE_MAP).fillna(df["pitch_type"])
    if "zone" in df.columns:
        df["zone_desc"] = df["zone"].map(ZONE_MAP).fillna(df["zone"].astype(str))

    with st.sidebar:
        if "game_date" in df.columns:
            df["game_date"] = pd.to_datetime(df["game_date"])
            min_date = df["game_date"].min().date()
            max_date = df["game_date"].max().date()
            date_range = st.date_input("Date Range", value=(min_date, max_date),
                                        min_value=min_date, max_value=max_date)
            if len(date_range) == 2:
                df = df[(df["game_date"].dt.date >= date_range[0]) &
                        (df["game_date"].dt.date <= date_range[1])]

        st.markdown("---")

        if "player_name" in df.columns:
            pitchers = sorted(df["player_name"].dropna().unique().tolist())
            selected_pitchers = st.multiselect("Filter by Pitcher", pitchers)
            if selected_pitchers:
                df = df[df["player_name"].isin(selected_pitchers)]

        if "pitch_desc" in df.columns:
            pitch_types = sorted(df["pitch_desc"].dropna().unique().tolist())
            selected_pitches = st.multiselect("Pitch Type", pitch_types)
            if selected_pitches:
                df = df[df["pitch_desc"].isin(selected_pitches)]

        if "events" in df.columns:
            events = sorted(df["events"].dropna().unique().tolist())
            selected_events = st.multiselect("Event Outcome", events)
            if selected_events:
                df = df[df["events"].isin(selected_events)]
        # Ball/Strike filter
        if "description" in df.columns:
            descriptions = sorted(df["description"].dropna().unique().tolist())
            selected_desc = st.multiselect("Pitch Result (ball, strike, etc.)", descriptions)
            if selected_desc:
                df = df[df["description"].isin(selected_desc)]

        # Count filter
        if "balls" in df.columns and "strikes" in df.columns:
            st.markdown("**Count Filter**")
            balls_filter = st.multiselect("Balls", [0, 1, 2, 3], key="balls_f")
            strikes_filter = st.multiselect("Strikes", [0, 1, 2], key="strikes_f")
            if balls_filter:
                df = df[df["balls"].isin(balls_filter)]
            if strikes_filter:
                df = df[df["strikes"].isin(strikes_filter)]

        # Pitch speed range
        if "release_speed" in df.columns:
            speed_min, speed_max = st.slider(
                "Pitch Speed (mph)",
                min_value=40, max_value=105,
                value=(40, 105),
                key="speed_range"
            )
            df = df[(df["release_speed"] >= speed_min) & (df["release_speed"] <= speed_max)]

        # Zone filter
        if "zone_desc" in df.columns:
            zones = sorted(df["zone_desc"].dropna().unique().tolist())
            selected_zones = st.multiselect("Strike Zone", zones)
            if selected_zones:
                df = df[df["zone_desc"].isin(selected_zones)]
                
        # Batter handedness
        if "stand" in df.columns:
            stand_options = sorted(df["stand"].dropna().unique().tolist())
            selected_stand = st.multiselect("Batter Hand", stand_options)
            if selected_stand:
                df = df[df["stand"].isin(selected_stand)]

        # Pitcher handedness
        if "p_throws" in df.columns:
            throw_options = sorted(df["p_throws"].dropna().unique().tolist())
            selected_throws = st.multiselect("Pitcher Hand", throw_options)
            if selected_throws:
                df = df[df["p_throws"].isin(selected_throws)]
                
        if "launch_speed" in df.columns:
            min_ev = st.slider("Min Exit Velocity", 0, 120, 0)
            df = df[(df["launch_speed"] >= min_ev) | df["launch_speed"].isna()]

    st.markdown(f"**Showing {len(df):,} pitches** after filters")

    key_cols = [
        "game_date", "player_name", "pitch_desc", "release_speed",
        "release_spin_rate", "launch_speed", "launch_angle",
        "hit_distance_3d", "events", "description", "zone_desc",
        "stand", "p_throws", "balls", "strikes",
    ]
    display_cols = [c for c in key_cols if c in df.columns]

    page_size = st.selectbox("Rows per page", [100, 250, 500, 1000], index=1)
    total_pages = max(1, len(df) // page_size + (1 if len(df) % page_size else 0))
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1)

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    st.dataframe(
        df[display_cols].iloc[start_idx:end_idx].reset_index(drop=True),
        use_container_width=True, height=600,
    )
    st.caption(f"Page {page} of {total_pages} ({len(df):,} total pitches)")

    st.markdown("### Quick Summary")
    m1, m2, m3, m4 = st.columns(4)
    if "release_speed" in df.columns:
        m1.metric("Avg Velocity", f"{df['release_speed'].mean():.1f} mph")
        m2.metric("Max Velocity", f"{df['release_speed'].max():.1f} mph")
    if "launch_speed" in df.columns:
        m3.metric("Avg Exit Velo", f"{df['launch_speed'].dropna().mean():.1f} mph")
    if "launch_angle" in df.columns:
        m4.metric("Avg Launch Angle", f"{df['launch_angle'].dropna().mean():.1f}°")

    st.markdown("---")
    csv = df[display_cols].to_csv(index=False)
    st.download_button("📥 Download filtered data as CSV", csv,
                       file_name=f"statcast_filtered_{season}.csv", mime="text/csv")
else:
    st.warning(f"No Statcast data found for {season}. Head to **Data Manager** to download.")