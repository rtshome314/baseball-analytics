import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.lines import Line2D
import os

from utils.style import inject_custom_css, render_nav_back
from config import DEFAULT_SEASON, AVAILABLE_SEASONS
from utils.data_loader import load_statcast_local, PITCH_TYPE_MAP, ZONE_MAP

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

st.set_page_config(page_title="Statcast Viewer", page_icon="⚾", layout="wide")
inject_custom_css()
render_nav_back()

st.markdown("## 📊 Pitches Statcast Data Viewer")
st.markdown("Browse your locally stored Statcast pitch data.")

# ── Pitch type color palette (matches Baseball Savant conventions) ──────────
PITCH_COLORS = {
    "4-Seam Fastball": "#D62728",
    "Sinker":          "#E377C2",
    "Cutter":          "#FF7F0E",
    "Slider":          "#BCBD22",
    "Sweeper":         "#17BECF",
    "Curveball":       "#1F77B4",
    "Knuckle Curve":   "#AEC7E8",
    "Slow Curve":      "#9467BD",
    "Changeup":        "#2CA02C",
    "Splitter":        "#8C564B",
    "Slurve":          "#FFBB78",
    "Knuckleball":     "#7F7F7F",
    "Fastball":        "#D62728",
    "Screwball":       "#C5B0D5",
    "Eephus":          "#C49C94",
    "Pitchout":        "#DBDB8D",
    "Intentional Ball":"#9EDAE5",
    "Auto Ball":       "#F7B6D2",
}

# ── Load batter lookup ───────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_batter_lookup(season):
    filepath = os.path.join(DATA_DIR, f"batter_lookup_{season}.parquet")
    if os.path.exists(filepath):
        return pd.read_parquet(filepath)
    return pd.DataFrame()

# ── Season selector ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Statcast Filters")
    season = st.selectbox(
        "Season", AVAILABLE_SEASONS,
        index=AVAILABLE_SEASONS.index(DEFAULT_SEASON),
        key="sc_season",
    )

df_raw = load_statcast_local(season)
batter_lookup = load_batter_lookup(season)

if not df_raw.empty:
    df = df_raw.copy()

    # ── Derived columns ──────────────────────────────────────────────────────
    if "pitch_type" in df.columns:
        df["pitch_desc"] = df["pitch_type"].map(PITCH_TYPE_MAP).fillna(df["pitch_type"])
    if "zone" in df.columns:
        df["zone_desc"] = df["zone"].map(ZONE_MAP).fillna(df["zone"].astype(str))

    # Merge batter names
    if not batter_lookup.empty and "batter" in df.columns:
        df["batter"] = df["batter"].astype(int)
        batter_lookup["batter"] = batter_lookup["batter"].astype(int)
        df = df.merge(batter_lookup, on="batter", how="left")

    # Derive pitcher team and batter team from home/away context
    if "home_team" in df.columns and "away_team" in df.columns and "inning_topbot" in df.columns:
        df["pitcher_team"] = np.where(df["inning_topbot"] == "Bot", df["away_team"], df["home_team"])
        df["batter_team"]  = np.where(df["inning_topbot"] == "Bot", df["home_team"], df["away_team"])

    # ── Sidebar filters ──────────────────────────────────────────────────────
    with st.sidebar:
        if "game_date" in df.columns:
            df["game_date"] = pd.to_datetime(df["game_date"])
            min_date = df["game_date"].min().date()
            max_date = df["game_date"].max().date()
            date_range = st.date_input(
                "Date Range", value=(min_date, max_date),
                min_value=min_date, max_value=max_date,
            )
            if len(date_range) == 2:
                df = df[
                    (df["game_date"].dt.date >= date_range[0]) &
                    (df["game_date"].dt.date <= date_range[1])
                ]

        st.markdown("---")
        st.markdown("**Pitcher**")

        if "player_name" in df.columns:
            pitchers = sorted(df["player_name"].dropna().unique().tolist())
            selected_pitchers = st.multiselect("Pitcher Name", pitchers)
            if selected_pitchers:
                df = df[df["player_name"].isin(selected_pitchers)]

        if "pitcher_team" in df.columns:
            pitcher_teams = sorted(df["pitcher_team"].dropna().unique().tolist())
            selected_pitcher_teams = st.multiselect("Pitcher Team", pitcher_teams)
            if selected_pitcher_teams:
                df = df[df["pitcher_team"].isin(selected_pitcher_teams)]

        if "p_throws" in df.columns:
            throw_options = sorted(df["p_throws"].dropna().unique().tolist())
            selected_throws = st.multiselect("Pitcher Hand", throw_options)
            if selected_throws:
                df = df[df["p_throws"].isin(selected_throws)]

        st.markdown("---")
        st.markdown("**Batter**")

        if "batter_name" in df.columns:
            hitters = sorted(df["batter_name"].dropna().unique().tolist())
            selected_hitters = st.multiselect("Hitter Name", hitters)
            if selected_hitters:
                df = df[df["batter_name"].isin(selected_hitters)]
        elif "batter" in df.columns:
            st.caption("Batter name lookup not available — download batter lookup in Data Manager.")

        if "batter_team" in df.columns:
            batter_teams = sorted(df["batter_team"].dropna().unique().tolist())
            selected_batter_teams = st.multiselect("Hitter Team", batter_teams)
            if selected_batter_teams:
                df = df[df["batter_team"].isin(selected_batter_teams)]

        if "stand" in df.columns:
            stand_options = sorted(df["stand"].dropna().unique().tolist())
            selected_stand = st.multiselect("Batter Hand", stand_options)
            if selected_stand:
                df = df[df["stand"].isin(selected_stand)]

        st.markdown("---")
        st.markdown("**Pitch**")

        if "pitch_desc" in df.columns:
            pitch_types = sorted(df["pitch_desc"].dropna().unique().tolist())
            selected_pitches = st.multiselect("Pitch Type", pitch_types)
            if selected_pitches:
                df = df[df["pitch_desc"].isin(selected_pitches)]

        if "release_speed" in df.columns:
            speed_min, speed_max = st.slider(
                "Pitch Speed (mph)", min_value=40, max_value=105,
                value=(40, 105), key="speed_range",
            )
            df = df[(df["release_speed"] >= speed_min) & (df["release_speed"] <= speed_max)]

        if "events" in df.columns:
            events = sorted(df["events"].dropna().unique().tolist())
            selected_events = st.multiselect("Event Outcome", events)
            if selected_events:
                df = df[df["events"].isin(selected_events)]

        if "description" in df.columns:
            descriptions = sorted(df["description"].dropna().unique().tolist())
            selected_desc = st.multiselect("Pitch Result (ball, strike, etc.)", descriptions)
            if selected_desc:
                df = df[df["description"].isin(selected_desc)]

        if "balls" in df.columns and "strikes" in df.columns:
            st.markdown("**Count Filter**")
            balls_filter   = st.multiselect("Balls",   [0, 1, 2, 3], key="balls_f")
            strikes_filter = st.multiselect("Strikes", [0, 1, 2],    key="strikes_f")
            if balls_filter:
                df = df[df["balls"].isin(balls_filter)]
            if strikes_filter:
                df = df[df["strikes"].isin(strikes_filter)]

        if "zone_desc" in df.columns:
            zones = sorted(df["zone_desc"].dropna().unique().tolist())
            selected_zones = st.multiselect("Strike Zone", zones)
            if selected_zones:
                df = df[df["zone_desc"].isin(selected_zones)]

        if "launch_speed" in df.columns:
            min_ev = st.slider("Min Exit Velocity", 0, 120, 0)
            df = df[(df["launch_speed"] >= min_ev) | df["launch_speed"].isna()]

    # ── Main area ────────────────────────────────────────────────────────────
    st.success(f"**{len(df):,}** pitches loaded from local data.")
    st.markdown(f"**Showing {len(df):,} pitches** after filters")

    # ── Chart section ────────────────────────────────────────────────────────
    st.markdown("### 🎯 Pitch Visualization")

    chart_view = st.radio(
        "View",
        ["Pitch Location (Strike Zone)", "Movement Profile"],
        horizontal=True,
        key="chart_view",
    )

    color_by = st.selectbox(
        "Color by",
        ["Pitch Type", "Pitch Result", "Event Outcome"],
        key="color_by",
    )

    has_location = "plate_x" in df.columns and "plate_z" in df.columns
    has_movement = "pfx_x" in df.columns and "pfx_z" in df.columns

    MAX_PLOT_POINTS = 2000  # cap scatter for performance

    def get_color_map(df, color_by):
        """Return (series, color_dict) for the chosen color dimension."""
        if color_by == "Pitch Type" and "pitch_desc" in df.columns:
            series = df["pitch_desc"].fillna("Unknown")
            cats   = series.unique().tolist()
            cmap   = {c: PITCH_COLORS.get(c, "#999999") for c in cats}
        elif color_by == "Pitch Result" and "description" in df.columns:
            series = df["description"].fillna("Unknown")
            cats   = series.unique().tolist()
            palette = plt.cm.get_cmap("tab20", len(cats))
            cmap   = {c: palette(i) for i, c in enumerate(cats)}
        elif color_by == "Event Outcome" and "events" in df.columns:
            series = df["events"].fillna("—")
            cats   = series.unique().tolist()
            palette = plt.cm.get_cmap("tab20", len(cats))
            cmap   = {c: palette(i) for i, c in enumerate(cats)}
        else:
            series = pd.Series(["All"] * len(df), index=df.index)
            cmap   = {"All": "#1f77b4"}
        return series, cmap

    # ── Strike zone helper ───────────────────────────────────────────────────
    def draw_strike_zone(ax):
        """Draw standard strike zone rectangle and inner grid."""
        sz_left, sz_right = -0.83, 0.83   # ft from centre of plate
        sz_bot,  sz_top   =  1.50, 3.60   # approximate average sz_bot/top

        # Outer box
        zone = patches.Rectangle(
            (sz_left, sz_bot),
            sz_right - sz_left,
            sz_top - sz_bot,
            linewidth=2, edgecolor="#CCCCCC", facecolor="none", zorder=2,
        )
        ax.add_patch(zone)

        # Inner 3×3 grid lines
        third_w = (sz_right - sz_left) / 3
        third_h = (sz_top   - sz_bot)  / 3
        for i in (1, 2):
            x = sz_left + i * third_w
            ax.plot([x, x], [sz_bot, sz_top], color="#AAAAAA", linewidth=0.7, zorder=2)
            y = sz_bot + i * third_h
            ax.plot([sz_left, sz_right], [y, y], color="#AAAAAA", linewidth=0.7, zorder=2)

        # Home plate (trapezoid outline)
        plate_x = [-0.708, 0.708, 0.708, 0.0, -0.708, -0.708]
        plate_y = [0.0,    0.0,   0.25,  0.5,  0.25,   0.0  ]
        ax.plot(plate_x, plate_y, color="#AAAAAA", linewidth=1.2, zorder=2)

    # ─────────────────────────────────────────────────────────────────────────
    if chart_view == "Pitch Location (Strike Zone)":
        if not has_location:
            st.warning("No `plate_x` / `plate_z` columns found in dataset.")
        else:
            plot_df = df.dropna(subset=["plate_x", "plate_z"])
            if len(plot_df) > MAX_PLOT_POINTS:
                plot_df = plot_df.sample(MAX_PLOT_POINTS, random_state=42)
                st.caption(f"Displaying a random sample of {MAX_PLOT_POINTS:,} pitches for performance.")

            color_series, cmap = get_color_map(plot_df, color_by)

            fig, ax = plt.subplots(figsize=(6, 7))
            fig.patch.set_facecolor("#111111")
            ax.set_facecolor("#111111")

            for cat, color in cmap.items():
                mask = color_series == cat
                ax.scatter(
                    plot_df.loc[mask, "plate_x"],
                    plot_df.loc[mask, "plate_z"],
                    c=[color], label=cat,
                    s=18, alpha=0.55, linewidths=0,
                    zorder=3,
                )

            ax.set_xlim(-2.5, 2.5)
            ax.set_ylim(0.5, 5.0)

            draw_strike_zone(ax)

            ax.set_xlabel("Horizontal Position (ft)", color="#CCCCCC")
            ax.set_ylabel("Height (ft)", color="#CCCCCC")
            ax.tick_params(colors="#CCCCCC")
            for spine in ax.spines.values():
                spine.set_edgecolor("#333333")

            ax.text(0, 4.75, "Catcher's perspective",
                    ha="center", va="top", color="#888888", fontsize=8)

            legend = ax.legend(
                fontsize=7, loc="upper right", framealpha=0.3,
                labelcolor="#CCCCCC", facecolor="#222222", edgecolor="#444444",
            )
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

    # ─────────────────────────────────────────────────────────────────────────
    else:  # Movement Profile
        if not has_movement:
            st.warning("No `pfx_x` / `pfx_z` columns found in dataset.")
        else:
            plot_df = df.dropna(subset=["pfx_x", "pfx_z", "pitch_desc"])

            # Convert to inches (Statcast pfx is in feet)
            plot_df = plot_df.copy()
            plot_df["pfx_x_in"] = plot_df["pfx_x"] * 12
            plot_df["pfx_z_in"] = plot_df["pfx_z"] * 12

            if len(plot_df) > MAX_PLOT_POINTS:
                plot_df = plot_df.sample(MAX_PLOT_POINTS, random_state=42)
                st.caption(f"Displaying a random sample of {MAX_PLOT_POINTS:,} pitches for performance.")

            color_series, cmap = get_color_map(plot_df, color_by)

            # Season-average reference circles per pitch type
            avg_movement = (
                df.dropna(subset=["pfx_x", "pfx_z", "pitch_desc"])
                .groupby("pitch_desc")
                .agg(avg_x=("pfx_x", "mean"), avg_z=("pfx_z", "mean"), n=("pfx_x", "count"))
                .reset_index()
            )
            avg_movement["avg_x_in"] = avg_movement["avg_x"] * 12
            avg_movement["avg_z_in"] = avg_movement["avg_z"] * 12

            show_refs = st.checkbox("Show season-average reference markers", value=True)

            fig, ax = plt.subplots(figsize=(7, 7))
            fig.patch.set_facecolor("#111111")
            ax.set_facecolor("#111111")

            # Reference lines
            ax.axhline(0, color="#444444", linewidth=0.8, zorder=1)
            ax.axvline(0, color="#444444", linewidth=0.8, zorder=1)

            # Scatter individual pitches
            for cat, color in cmap.items():
                mask = color_series == cat
                ax.scatter(
                    plot_df.loc[mask, "pfx_x_in"],
                    plot_df.loc[mask, "pfx_z_in"],
                    c=[color], label=cat,
                    s=16, alpha=0.45, linewidths=0,
                    zorder=3,
                )

            # Season-average reference markers
            if show_refs:
                for _, row in avg_movement.iterrows():
                    pt = row["pitch_desc"]
                    color = PITCH_COLORS.get(pt, "#999999")
                    circle = plt.Circle(
                        (row["avg_x_in"], row["avg_z_in"]),
                        radius=1.2,
                        color=color, fill=False,
                        linewidth=2.0, zorder=5,
                    )
                    ax.add_patch(circle)
                    ax.annotate(
                        pt,
                        xy=(row["avg_x_in"], row["avg_z_in"]),
                        xytext=(row["avg_x_in"], row["avg_z_in"] + 1.8),
                        color=color, fontsize=6.5, ha="center", va="bottom",
                        zorder=6,
                    )

            ax.set_xlabel("Horizontal Break (in) — positive = arm side", color="#CCCCCC")
            ax.set_ylabel("Vertical Break (in) — induced", color="#CCCCCC")
            ax.tick_params(colors="#CCCCCC")
            for spine in ax.spines.values():
                spine.set_edgecolor("#333333")

            ax.set_xlim(-25, 25)
            ax.set_ylim(-25, 25)

            legend = ax.legend(
                fontsize=7, loc="upper right", framealpha=0.3,
                labelcolor="#CCCCCC", facecolor="#222222", edgecolor="#444444",
            )
            ax.set_title(
                f"Movement Profile — {season} Season  (pitcher POV)",
                color="#CCCCCC", fontsize=10,
            )

            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

    st.markdown("---")

    # ── Data table ───────────────────────────────────────────────────────────
    key_cols = [
        "game_date", "player_name", "pitcher_team",
        "batter_name", "batter_team",
        "pitch_desc", "release_speed",
        "release_spin_rate", "pfx_x", "pfx_z",
        "plate_x", "plate_z",
        "launch_speed", "launch_angle",
        "hit_distance_3d", "events", "description", "zone_desc",
        "stand", "p_throws", "balls", "strikes",
    ]
    display_cols = [c for c in key_cols if c in df.columns]

    page_size   = st.selectbox("Rows per page", [100, 250, 500, 1000], index=1)
    total_pages = max(1, len(df) // page_size + (1 if len(df) % page_size else 0))
    page        = st.number_input("Page", min_value=1, max_value=total_pages, value=1)

    start_idx = (page - 1) * page_size
    end_idx   = start_idx + page_size

    st.dataframe(
        df[display_cols].iloc[start_idx:end_idx].reset_index(drop=True),
        use_container_width=True, height=600,
    )
    st.caption(f"Page {page} of {total_pages} ({len(df):,} total pitches)")

    # ── Quick summary ────────────────────────────────────────────────────────
    st.markdown("### Quick Summary")
    m1, m2, m3, m4 = st.columns(4)
    if "release_speed" in df.columns:
        m1.metric("Avg Velocity",  f"{df['release_speed'].mean():.1f} mph")
        m2.metric("Max Velocity",  f"{df['release_speed'].max():.1f} mph")
    if "launch_speed" in df.columns:
        m3.metric("Avg Exit Velo", f"{df['launch_speed'].dropna().mean():.1f} mph")
    if "launch_angle" in df.columns:
        m4.metric("Avg Launch Angle", f"{df['launch_angle'].dropna().mean():.1f}°")

    st.markdown("---")
    csv = df[display_cols].to_csv(index=False)
    st.download_button(
        "📥 Download filtered data as CSV", csv,
        file_name=f"statcast_filtered_{season}.csv", mime="text/csv",
    )

else:
    st.warning(f"No Statcast data found for {season}. Head to **Data Manager** to download.")
