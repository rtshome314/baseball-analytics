import streamlit as st
import pandas as pd
import numpy as np
from utils.style import inject_custom_css
from utils.data_loader import load_statcast_local, load_batter_lookup, PITCH_TYPE_MAP, ZONE_MAP
from utils.charts import CHART_TEMPLATE
import plotly.express as px

st.set_page_config(page_title="Hitter Statcast", page_icon="⚾", layout="wide")
inject_custom_css()

st.markdown("## 🔥 Hitter Statcast Viewer")
st.markdown("Explore batted ball data from the hitter's perspective.")

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    season = st.selectbox("Season", [2026, 2025, 2024, 2023], index=1, key="hs_season")

df = load_statcast_local(season)

if not df.empty:
    # Filter to batted ball events only
    if "type" in df.columns:
        df = df[df["type"] == "X"]
    elif "description" in df.columns:
        batted = df["description"].str.contains("hit_into_play", case=False, na=False)
        df = df[batted]

    if "game_date" in df.columns:
        df["game_date"] = pd.to_datetime(df["game_date"])

    st.success(f"**{len(df):,}** batted ball events loaded.")
    
    if "pitch_type" in df.columns:
        df["pitch_desc"] = df["pitch_type"].map(PITCH_TYPE_MAP).fillna(df["pitch_type"])
    if "zone" in df.columns:
        df["zone_desc"] = df["zone"].map(ZONE_MAP).fillna(df["zone"].astype(str))

    # --- Merge batter names ---
    lookup = load_batter_lookup(season)
    if not lookup.empty and "batter" in df.columns:
        df["batter"] = df["batter"].astype(int)
        lookup["batter"] = lookup["batter"].astype(int)
        df = df.merge(lookup, on="batter", how="left")
        hitter_name_col = "batter_name"
    else:
        hitter_name_col = "batter"

    with st.sidebar:
        st.markdown("---")
        st.markdown("### 🎯 Filters")

        # Date range
        if "game_date" in df.columns:
            min_date = df["game_date"].min().date()
            max_date = df["game_date"].max().date()
            date_range = st.date_input("Date Range", value=(min_date, max_date),
                                        min_value=min_date, max_value=max_date, key="hs_dates")
            if len(date_range) == 2:
                df = df[(df["game_date"].dt.date >= date_range[0]) &
                        (df["game_date"].dt.date <= date_range[1])]

        # Batter filter
        if hitter_name_col in df.columns:
            batters = sorted(df[hitter_name_col].dropna().unique().tolist())
            selected_batters = st.multiselect("Filter by Batter", batters, key="hs_batters")
            if selected_batters:
                df = df[df[hitter_name_col].isin(selected_batters)]

        # Pitcher filter
        if "player_name" in df.columns:
            pitchers = sorted(df["player_name"].dropna().unique().tolist())
            selected_pitchers = st.multiselect("Filter by Pitcher", pitchers, key="hs_pitchers")
            if selected_pitchers:
                df = df[df["player_name"].isin(selected_pitchers)]

        # Event outcome
        if "events" in df.columns:
            events = sorted(df["events"].dropna().unique().tolist())
            selected_events = st.multiselect("Event Outcome", events, key="hs_events")
            if selected_events:
                df = df[df["events"].isin(selected_events)]

        # Pitch type
        if "pitch_desc" in df.columns:
            pitch_types = sorted(df["pitch_desc"].dropna().unique().tolist())
            selected_pitches = st.multiselect("Pitch Type", pitch_types, key="hs_pitch_type")
            if selected_pitches:
                df = df[df["pitch_desc"].isin(selected_pitches)]

        st.markdown("---")
        st.markdown("### 📏 Numeric Filters")

        # Exit velocity
        if "launch_speed" in df.columns:
            ev_min, ev_max = st.slider("Exit Velocity (mph)",
                                        min_value=0, max_value=125,
                                        value=(0, 125), key="hs_ev")
            df = df[(df["launch_speed"] >= ev_min) & (df["launch_speed"] <= ev_max) | df["launch_speed"].isna()]

        # Launch angle
        if "launch_angle" in df.columns:
            la_min, la_max = st.slider("Launch Angle (°)",
                                        min_value=-90, max_value=90,
                                        value=(-90, 90), key="hs_la")
            df = df[(df["launch_angle"] >= la_min) & (df["launch_angle"] <= la_max) | df["launch_angle"].isna()]

        # Hit distance
        if "hit_distance_3d" in df.columns:
            dist_min, dist_max = st.slider("Hit Distance (ft)",
                                            min_value=0, max_value=500,
                                            value=(0, 500), key="hs_dist")
            df = df[(df["hit_distance_3d"] >= dist_min) & (df["hit_distance_3d"] <= dist_max) | df["hit_distance_3d"].isna()]

        # Pitch speed
        if "release_speed" in df.columns:
            ps_min, ps_max = st.slider("Pitch Speed (mph)",
                                        min_value=40, max_value=105,
                                        value=(40, 105), key="hs_ps")
            df = df[(df["release_speed"] >= ps_min) & (df["release_speed"] <= ps_max) | df["release_speed"].isna()]

        # Batter handedness
        if "stand" in df.columns:
            stand_opts = sorted(df["stand"].dropna().unique().tolist())
            selected_stand = st.multiselect("Batter Hand", stand_opts, key="hs_stand")
            if selected_stand:
                df = df[df["stand"].isin(selected_stand)]

        # Pitcher handedness
        if "p_throws" in df.columns:
            throw_opts = sorted(df["p_throws"].dropna().unique().tolist())
            selected_throws = st.multiselect("Pitcher Hand", throw_opts, key="hs_throws")
            if selected_throws:
                df = df[df["p_throws"].isin(selected_throws)]

    st.markdown(f"**Showing {len(df):,} batted balls** after filters")

    # --- Display columns ---
    key_cols = [
        "game_date", hitter_name_col, "player_name", "events", "pitch_desc",
        "launch_speed", "launch_angle", "hit_distance_3d", "release_speed",
        "release_spin_rate", "stand", "p_throws", "balls", "strikes", "zone_desc",
    ]
    display_cols = [c for c in key_cols if c in df.columns]

    # Pagination
    page_size = st.selectbox("Rows per page", [100, 250, 500, 1000], index=1, key="hs_page_size")
    total_pages = max(1, len(df) // page_size + (1 if len(df) % page_size else 0))
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, key="hs_page")

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    display_df = df[display_cols].iloc[start_idx:end_idx].reset_index(drop=True)
    if "batter_name" in display_df.columns:
        display_df = display_df.rename(columns={"batter_name": "Batter"})
    if "player_name" in display_df.columns:
        display_df = display_df.rename(columns={"player_name": "Pitcher"})
    st.dataframe(display_df, use_container_width=True, height=500)

    st.caption(f"Page {page} of {total_pages} ({len(df):,} total batted balls)")

    # --- Summary Metrics ---
    st.markdown("### Quick Summary")
    m0, m1, m2, m3, m4 = st.columns(5)
    m0.metric("Count", f"{len(df):,}")

    if "launch_speed" in df.columns:
        m1.metric("Avg Exit Velo", f"{df['launch_speed'].dropna().mean():.1f} mph")
        m2.metric("Max Exit Velo", f"{df['launch_speed'].dropna().max():.1f} mph")
    if "launch_angle" in df.columns:
        m3.metric("Avg Launch Angle", f"{df['launch_angle'].dropna().mean():.1f}°")
    if "hit_distance_3d" in df.columns:
        m4.metric("Avg Distance", f"{df['hit_distance_3d'].dropna().mean():.0f} ft")

    # --- Charts ---
    st.markdown("---")
    st.markdown("### 📊 Visualizations")

    chart_tab1, chart_tab2, chart_tab3 = st.tabs(["Exit Velo vs Launch Angle", "HR by Pitch Type", "Distribution"])

    with chart_tab1:
        if "launch_speed" in df.columns and "launch_angle" in df.columns:
            color_col = "events" if "events" in df.columns else None
            fig = px.scatter(
                df.dropna(subset=["launch_speed", "launch_angle"]),
                x="launch_speed", y="launch_angle",
                color=color_col,
                hover_name=hitter_name_col if hitter_name_col in df.columns else None,
                labels={"launch_speed": "Exit Velocity (mph)", "launch_angle": "Launch Angle (°)"},
                title="Exit Velocity vs Launch Angle",
            )
            fig.update_layout(**CHART_TEMPLATE, height=500)
            fig.update_traces(marker=dict(size=5, opacity=0.6))
            st.plotly_chart(fig, use_container_width=True)

    with chart_tab2:
        if "events" in df.columns and "pitch_type" in df.columns:
            hr_df = df[df["events"] == "home_run"]
            if not hr_df.empty:
                hr_by_pitch = hr_df["pitch_type"].value_counts().reset_index()
                hr_by_pitch.columns = ["Pitch Type", "Home Runs"]
                fig = px.bar(
                    hr_by_pitch, x="Pitch Type", y="Home Runs",
                    title="Home Runs by Pitch Type",
                    color="Home Runs",
                    color_continuous_scale=["#2171B5", "#E87A2C", "#C6011F"],
                )
                fig.update_layout(**CHART_TEMPLATE, height=400)
                st.plotly_chart(fig, use_container_width=True)

                # Also show table
                st.dataframe(hr_by_pitch.reset_index(drop=True), use_container_width=True)
            else:
                st.info("No home runs in current filter selection.")

    with chart_tab3:
        dist_col = st.selectbox("Select stat to visualize",
                                ["launch_speed", "launch_angle", "hit_distance_3d", "release_speed"],
                                format_func=lambda x: {"launch_speed": "Exit Velocity", "launch_angle": "Launch Angle",
                                                        "hit_distance_3d": "Hit Distance", "release_speed": "Pitch Speed"}.get(x, x),
                                key="hs_dist_col")
        if dist_col in df.columns:
            fig = px.histogram(
                df.dropna(subset=[dist_col]), x=dist_col, nbins=40,
                title=f"Distribution of {dist_col}",
                color_discrete_sequence=["#E87A2C"],
            )
            fig.update_layout(**CHART_TEMPLATE, height=400, bargap=0.05)
            st.plotly_chart(fig, use_container_width=True)

# --- Aggregation Builder ---
    st.markdown("---")
    st.markdown("### 🧮 Aggregation Builder")
    st.markdown("Group and summarize batted ball data — like running a SQL query.")

    agg_tab1, agg_tab2 = st.tabs(["⚙️ Build Query", "📋 Results"])

    with agg_tab1:
        # Group by options
        group_options = []
        if hitter_name_col in df.columns:
            group_options.append(hitter_name_col)
        for col in ["events", "pitch_type", "stand", "p_throws", "player_name"]:
            if col in df.columns:
                group_options.append(col)

        group_labels = {
            "batter_name": "Batter",
            "batter": "Batter ID",
            "events": "Event Outcome",
            "pitch_type": "Pitch Type",
            "stand": "Batter Hand",
            "p_throws": "Pitcher Hand",
            "player_name": "Pitcher",
        }

        selected_groups = st.multiselect(
            "Group by",
            group_options,
            default=[hitter_name_col] if hitter_name_col in group_options else [],
            format_func=lambda x: group_labels.get(x, x),
            key="agg_group",
        )

        # Metric options
        metric_options = []
        metric_labels = {}
        for col, label in [
            ("launch_speed", "Exit Velocity"),
            ("launch_angle", "Launch Angle"),
            ("hit_distance_3d", "Hit Distance"),
            ("release_speed", "Pitch Speed"),
            ("release_spin_rate", "Spin Rate"),
        ]:
            if col in df.columns:
                metric_options.append(col)
                metric_labels[col] = label

        selected_metrics = st.multiselect(
            "Metrics to aggregate",
            metric_options,
            default=metric_options[:3] if len(metric_options) >= 3 else metric_options,
            format_func=lambda x: metric_labels.get(x, x),
            key="agg_metrics",
        )

        # Aggregation functions
        agg_funcs = st.multiselect(
            "Aggregation functions",
            ["count", "mean", "median", "max", "min", "std"],
            default=["count", "mean", "max"],
            key="agg_funcs",
        )

        # Min count filter
        min_count = st.number_input("Minimum count (filter out small groups)", min_value=1, value=1, key="agg_min")

    with agg_tab2:
        if selected_groups and selected_metrics and agg_funcs:
            # Build aggregation
            agg_dict = {}
            for metric in selected_metrics:
                agg_dict[metric] = agg_funcs

            try:
                result = df.groupby(selected_groups).agg(agg_dict)

                # Flatten column names
                result.columns = [f"{metric_labels.get(col, col)}_{func}" for col, func in result.columns]
                result = result.reset_index()

                # Rename group columns
                result = result.rename(columns=group_labels)

                # Find the count column to filter on
                count_cols = [c for c in result.columns if c.endswith("_count")]
                if count_cols and min_count > 1:
                    result = result[result[count_cols[0]] >= min_count]

                # Round numeric columns
                for col in result.columns:
                    if result[col].dtype in ["float64", "float32"]:
                        result[col] = result[col].round(2)

                # Sort by first count column descending
                if count_cols:
                    result = result.sort_values(count_cols[0], ascending=False)

                st.markdown(f"**{len(result):,} groups**")
                st.dataframe(result.reset_index(drop=True), use_container_width=True, height=500)

                # Download aggregated data
                agg_csv = result.to_csv(index=False)
                st.download_button("📥 Download aggregated data", agg_csv,
                                   file_name=f"hitter_agg_{season}.csv", mime="text/csv", key="agg_download")

            except Exception as e:
                st.error(f"Aggregation error: {e}")
        else:
            st.info("Configure your query in the **Build Query** tab, then come back here to see results.")

    # --- Download ---
    st.markdown("---")
    csv = df[display_cols].to_csv(index=False)
    st.download_button("📥 Download filtered data as CSV", csv,
                       file_name=f"hitter_statcast_{season}.csv", mime="text/csv")

else:
    st.warning(f"No Statcast data found for {season}. Head to **Data Manager** to download.")