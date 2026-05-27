import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import os

from utils.style import inject_custom_css, render_nav_back, render_data_status
from config import DEFAULT_SEASON, AVAILABLE_SEASONS
from utils.data_loader import load_statcast_local, PITCH_TYPE_MAP, ZONE_MAP

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

st.set_page_config(page_title="Statcast Viewer", page_icon="⚾", layout="wide")
inject_custom_css()
render_nav_back()
render_data_status(["statcast", "batter_lookup"])

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
if st.session_state.get("mobile_mode"):
    filters = st.expander("⚙️ Statcast Filters", expanded=True)
else:
    filters = st.sidebar

with filters:
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

    # ── Date shortcuts (main area — st.columns not allowed in sidebar/expander)
    import datetime
    shortcuts = {
        "Last Day":     1,
        "Last 3 Days":  3,
        "Last 10 Days": 10,
        "This Season":  None,
    }
    if "sc_date_shortcut" not in st.session_state:
        st.session_state["sc_date_shortcut"] = "This Season"

    if "game_date" in df.columns:
        df["game_date"] = pd.to_datetime(df["game_date"])
        min_date = df["game_date"].min().date()
        max_date = df["game_date"].max().date()

        st.markdown("**📅 Date Range**")
        btn_cols = st.columns(4)
        for col, label in zip(btn_cols, shortcuts.keys()):
            if col.button(label, key=f"shortcut_{label}", use_container_width=True):
                st.session_state["sc_date_shortcut"] = label
                days_val = shortcuts[label]
                new_start = min_date if days_val is None else max(min_date, max_date - datetime.timedelta(days=days_val - 1))
                st.session_state["sc_date_range"] = (new_start, max_date)

        active = st.session_state["sc_date_shortcut"]
        days = shortcuts.get(active)
        default_start = min_date if days is None else max(min_date, max_date - datetime.timedelta(days=days - 1))

    # ── Sidebar filters ──────────────────────────────────────────────────────
    # NOTE: All option lists are built from df (pre-filter snapshot) so that
    # changing the date range does NOT reset other multiselect widgets.
    df_options = df.copy()  # stable snapshot for building option lists

    with filters:
        if "game_date" in df.columns:
            date_range = st.date_input(
                "Date Range", value=(default_start, max_date),
                min_value=min_date, max_value=max_date,
                key="sc_date_range",
            )

        st.markdown("---")
        st.markdown("**Pitcher**")

        if "player_name" in df_options.columns:
            pitchers = sorted(df_options["player_name"].dropna().unique().tolist())
            selected_pitchers = st.multiselect("Pitcher Name", pitchers)

        if "pitcher_team" in df_options.columns:
            pitcher_teams = sorted(df_options["pitcher_team"].dropna().unique().tolist())
            selected_pitcher_teams = st.multiselect("Pitcher Team", pitcher_teams)

        if "p_throws" in df_options.columns:
            throw_options = sorted(df_options["p_throws"].dropna().unique().tolist())
            selected_throws = st.multiselect("Pitcher Hand", throw_options)

        st.markdown("---")
        st.markdown("**Batter**")

        if "batter_name" in df_options.columns:
            hitters = sorted(df_options["batter_name"].dropna().unique().tolist())
            selected_hitters = st.multiselect("Hitter Name", hitters)
        elif "batter" in df_options.columns:
            selected_hitters = []
            st.caption("Batter name lookup not available — download batter lookup in Data Manager.")

        if "batter_team" in df_options.columns:
            batter_teams = sorted(df_options["batter_team"].dropna().unique().tolist())
            selected_batter_teams = st.multiselect("Hitter Team", batter_teams)

        if "stand" in df_options.columns:
            stand_options = sorted(df_options["stand"].dropna().unique().tolist())
            selected_stand = st.multiselect("Batter Hand", stand_options)

        st.markdown("---")
        st.markdown("**Pitch**")

        if "pitch_desc" in df_options.columns:
            pitch_types = sorted(df_options["pitch_desc"].dropna().unique().tolist())
            selected_pitches = st.multiselect("Pitch Type", pitch_types)

        if "release_speed" in df_options.columns:
            speed_min, speed_max = st.slider(
                "Pitch Speed (mph)", min_value=40, max_value=105,
                value=(40, 105), key="speed_range",
            )

        if "events" in df_options.columns:
            events = sorted(df_options["events"].dropna().unique().tolist())
            selected_events = st.multiselect("Event Outcome", events)

        if "description" in df_options.columns:
            descriptions = sorted(df_options["description"].dropna().unique().tolist())
            selected_desc = st.multiselect("Pitch Result (ball, strike, etc.)", descriptions)

        if "balls" in df_options.columns and "strikes" in df_options.columns:
            st.markdown("**Count Filter**")
            balls_filter   = st.multiselect("Balls",   [0, 1, 2, 3], key="balls_f")
            strikes_filter = st.multiselect("Strikes", [0, 1, 2],    key="strikes_f")

        if "zone_desc" in df_options.columns:
            zones = sorted(df_options["zone_desc"].dropna().unique().tolist())
            selected_zones = st.multiselect("Strike Zone", zones)

        if "launch_speed" in df_options.columns:
            min_ev = st.slider("Min Exit Velocity", 0, 120, 0)

    # ── Apply all filters after widgets are rendered ─────────────────────────
    if "game_date" in df.columns and len(date_range) == 2:
        df = df[
            (df["game_date"].dt.date >= date_range[0]) &
            (df["game_date"].dt.date <= date_range[1])
        ]
    if "player_name" in df.columns and selected_pitchers:
        df = df[df["player_name"].isin(selected_pitchers)]
    if "pitcher_team" in df.columns and selected_pitcher_teams:
        df = df[df["pitcher_team"].isin(selected_pitcher_teams)]
    if "p_throws" in df.columns and selected_throws:
        df = df[df["p_throws"].isin(selected_throws)]
    if "batter_name" in df.columns and selected_hitters:
        df = df[df["batter_name"].isin(selected_hitters)]
    if "batter_team" in df.columns and selected_batter_teams:
        df = df[df["batter_team"].isin(selected_batter_teams)]
    if "stand" in df.columns and selected_stand:
        df = df[df["stand"].isin(selected_stand)]
    if "pitch_desc" in df.columns and selected_pitches:
        df = df[df["pitch_desc"].isin(selected_pitches)]
    if "release_speed" in df.columns:
        df = df[(df["release_speed"] >= speed_min) & (df["release_speed"] <= speed_max)]
    if "events" in df.columns and selected_events:
        df = df[df["events"].isin(selected_events)]
    if "description" in df.columns and selected_desc:
        df = df[df["description"].isin(selected_desc)]
    if "balls" in df.columns and balls_filter:
        df = df[df["balls"].isin(balls_filter)]
    if "strikes" in df.columns and strikes_filter:
        df = df[df["strikes"].isin(strikes_filter)]
    if "zone_desc" in df.columns and selected_zones:
        df = df[df["zone_desc"].isin(selected_zones)]
    if "launch_speed" in df.columns:
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

    TAB20 = [
        "#1f77b4","#aec7e8","#ff7f0e","#ffbb78","#2ca02c","#98df8a","#d62728","#ff9896",
        "#9467bd","#c5b0d5","#8c564b","#c49c94","#e377c2","#f7b6d2","#7f7f7f","#c7c7c7",
        "#bcbd22","#dbdb8d","#17becf","#9edae5",
    ]

    def get_color_map(df, color_by):
        """Return (series, color_dict) for the chosen color dimension."""
        if color_by == "Pitch Type" and "pitch_desc" in df.columns:
            series = df["pitch_desc"].fillna("Unknown")
            cats   = series.unique().tolist()
            cmap   = {c: PITCH_COLORS.get(c, "#999999") for c in cats}
        elif color_by == "Pitch Result" and "description" in df.columns:
            series = df["description"].fillna("Unknown")
            cats   = series.unique().tolist()
            cmap   = {c: TAB20[i % len(TAB20)] for i, c in enumerate(cats)}
        elif color_by == "Event Outcome" and "events" in df.columns:
            series = df["events"].fillna("—")
            cats   = series.unique().tolist()
            cmap   = {c: TAB20[i % len(TAB20)] for i, c in enumerate(cats)}
        else:
            series = pd.Series(["All"] * len(df), index=df.index)
            cmap   = {"All": "#1f77b4"}
        return series, cmap

    # ── Plotly strike zone shapes helper ────────────────────────────────────
    def strike_zone_shapes():
        """Return a list of Plotly shape dicts for the strike zone overlay."""
        sz_left, sz_right = -0.83, 0.83
        sz_bot,  sz_top   =  1.50, 3.60
        third_w = (sz_right - sz_left) / 3
        third_h = (sz_top   - sz_bot)  / 3
        shapes = [
            # Outer box
            dict(type="rect", x0=sz_left, x1=sz_right, y0=sz_bot, y1=sz_top,
                 line=dict(color="#CCCCCC", width=2), fillcolor="rgba(0,0,0,0)"),
            # Inner vertical grid lines
            dict(type="line", x0=sz_left+third_w, x1=sz_left+third_w, y0=sz_bot, y1=sz_top,
                 line=dict(color="#AAAAAA", width=1)),
            dict(type="line", x0=sz_left+2*third_w, x1=sz_left+2*third_w, y0=sz_bot, y1=sz_top,
                 line=dict(color="#AAAAAA", width=1)),
            # Inner horizontal grid lines
            dict(type="line", x0=sz_left, x1=sz_right, y0=sz_bot+third_h, y1=sz_bot+third_h,
                 line=dict(color="#AAAAAA", width=1)),
            dict(type="line", x0=sz_left, x1=sz_right, y0=sz_bot+2*third_h, y1=sz_bot+2*third_h,
                 line=dict(color="#AAAAAA", width=1)),
            # Home plate trapezoid
            dict(type="path",
                 path="M -0.708 0 L 0.708 0 L 0.708 0.25 L 0 0.5 L -0.708 0.25 Z",
                 line=dict(color="#AAAAAA", width=1.2), fillcolor="rgba(0,0,0,0)"),
        ]
        return shapes

    PLOTLY_DARK = dict(
        paper_bgcolor="#111111",
        plot_bgcolor="#111111",
        font_color="#CCCCCC",
    )

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
            plot_df = plot_df.copy()
            plot_df["_color_cat"] = color_series.values

            fig = go.Figure()
            for cat, color in cmap.items():
                mask = plot_df["_color_cat"] == cat
                sub = plot_df[mask]
                fig.add_trace(go.Scatter(
                    x=sub["plate_x"], y=sub["plate_z"],
                    mode="markers",
                    name=cat,
                    marker=dict(color=color, size=5, opacity=0.55, line=dict(width=0)),
                    hovertemplate=(
                        "<b>%{text}</b><br>x: %{x:.2f} ft<br>z: %{y:.2f} ft<extra></extra>"
                    ),
                    text=sub.get("pitch_desc", pd.Series([""] * len(sub))),
                ))

            fig.update_layout(
                **PLOTLY_DARK,
                shapes=strike_zone_shapes(),
                xaxis=dict(range=[-2.5, 2.5], title="Horizontal Position (ft)",
                           gridcolor="#333333", zerolinecolor="#444444", scaleanchor="y", scaleratio=1),
                yaxis=dict(range=[0.5, 5.0], title="Height (ft)",
                           gridcolor="#333333", zerolinecolor="#444444"),
                legend=dict(bgcolor="#222222", bordercolor="#444444", borderwidth=1, font_size=11),
                annotations=[dict(x=0, y=4.85, text="Catcher's perspective", showarrow=False,
                                  font=dict(color="#888888", size=11), xanchor="center")],
                margin=dict(l=50, r=20, t=30, b=50),
                height=550,
            )
            col_map, _ = st.columns([1, 1])
            with col_map:
                st.plotly_chart(fig, use_container_width=True)

    # ─────────────────────────────────────────────────────────────────────────
    else:  # Movement Profile
        if not has_movement:
            st.warning("No `pfx_x` / `pfx_z` columns found in dataset.")
        else:
            plot_df = df.dropna(subset=["pfx_x", "pfx_z", "pitch_desc"]).copy()
            plot_df["pfx_x_in"] = plot_df["pfx_x"] * 12
            plot_df["pfx_z_in"] = plot_df["pfx_z"] * 12

            if len(plot_df) > MAX_PLOT_POINTS:
                plot_df = plot_df.sample(MAX_PLOT_POINTS, random_state=42)
                st.caption(f"Displaying a random sample of {MAX_PLOT_POINTS:,} pitches for performance.")

            color_series, cmap = get_color_map(plot_df, color_by)
            plot_df["_color_cat"] = color_series.values

            # Season-average reference per pitch type (from full filtered df)
            avg_movement = (
                df.dropna(subset=["pfx_x", "pfx_z", "pitch_desc"])
                .groupby("pitch_desc")
                .agg(avg_x=("pfx_x", "mean"), avg_z=("pfx_z", "mean"), n=("pfx_x", "count"))
                .reset_index()
            )
            avg_movement["avg_x_in"] = avg_movement["avg_x"] * 12
            avg_movement["avg_z_in"] = avg_movement["avg_z"] * 12

            show_refs = st.checkbox("Show season-average reference markers", value=True)

            fig = go.Figure()

            # Reference crosshairs
            fig.add_hline(y=0, line_color="#444444", line_width=1)
            fig.add_vline(x=0, line_color="#444444", line_width=1)

            # Scatter individual pitches
            for cat, color in cmap.items():
                mask = plot_df["_color_cat"] == cat
                sub = plot_df[mask]
                fig.add_trace(go.Scatter(
                    x=sub["pfx_x_in"], y=sub["pfx_z_in"],
                    mode="markers",
                    name=cat,
                    marker=dict(color=color, size=5, opacity=0.45, line=dict(width=0)),
                    hovertemplate="<b>%{text}</b><br>HB: %{x:.1f} in<br>VB: %{y:.1f} in<extra></extra>",
                    text=sub.get("pitch_desc", pd.Series([""] * len(sub))),
                ))

            # Season-average reference circles + labels
            if show_refs:
                for _, row in avg_movement.iterrows():
                    pt = row["pitch_desc"]
                    color = PITCH_COLORS.get(pt, "#999999")
                    fig.add_shape(type="circle",
                        x0=row["avg_x_in"] - 1.2, x1=row["avg_x_in"] + 1.2,
                        y0=row["avg_z_in"] - 1.2, y1=row["avg_z_in"] + 1.2,
                        line=dict(color=color, width=2),
                    )
                    fig.add_annotation(
                        x=row["avg_x_in"], y=row["avg_z_in"] + 2.2,
                        text=pt, showarrow=False,
                        font=dict(color=color, size=9), xanchor="center",
                    )

            fig.update_layout(
                **PLOTLY_DARK,
                title=dict(text=f"Movement Profile — {season} Season  (catcher's perspective)",
                           font=dict(color="#CCCCCC", size=13)),
                xaxis=dict(range=[-25, 25], title="Horizontal Break (in) — ← 3B side       1B side →",
                           gridcolor="#333333", zerolinecolor="#444444", scaleanchor="y", scaleratio=1),
                yaxis=dict(range=[-25, 25], title="Vertical Break (in) — induced",
                           gridcolor="#333333", zerolinecolor="#444444"),
                legend=dict(bgcolor="#222222", bordercolor="#444444", borderwidth=1, font_size=11),
                margin=dict(l=60, r=20, t=50, b=60),
                height=600,
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── Pitch type breakdown ─────────────────────────────────────────────────
    if "pitch_desc" in df.columns:
        st.markdown("### 🔢 Pitch Type Breakdown")
        pitch_counts = df["pitch_desc"].value_counts().reset_index()
        pitch_counts.columns = ["Pitch Type", "Count"]
        pitch_counts["Pct"] = pitch_counts["Count"] / pitch_counts["Count"].sum() * 100
        pitch_counts = pitch_counts.sort_values("Pct", ascending=True)

        colors = [PITCH_COLORS.get(p, "#999999") for p in pitch_counts["Pitch Type"]]
        labels = [
            f"{row['Pct']:.1f}%  ({int(row['Count']):,})"
            for _, row in pitch_counts.iterrows()
        ]

        fig_pt = go.Figure(go.Bar(
            x=pitch_counts["Pct"],
            y=pitch_counts["Pitch Type"],
            orientation="h",
            marker_color=colors,
            text=labels,
            textposition="outside",
            textfont=dict(color="#CCCCCC", size=11),
            hovertemplate="<b>%{y}</b><br>Usage: %{x:.1f}%<extra></extra>",
        ))
        fig_pt.update_layout(
            **PLOTLY_DARK,
            xaxis=dict(title="Usage %", range=[0, pitch_counts["Pct"].max() * 1.4],
                       gridcolor="#333333", zerolinecolor="#444444"),
            yaxis=dict(gridcolor="#333333", zerolinecolor="#444444"),
            margin=dict(l=120, r=80, t=20, b=40),
            height=max(200, len(pitch_counts) * 40 + 60),
            showlegend=False,
        )
        st.plotly_chart(fig_pt, use_container_width=True)

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
