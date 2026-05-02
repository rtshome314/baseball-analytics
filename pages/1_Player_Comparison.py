import unicodedata
import streamlit as st
import pandas as pd
import numpy as np
from utils.style import inject_custom_css, render_nav_back
from config import DEFAULT_SEASON, AVAILABLE_SEASONS

from utils.data_loader import (
    load_batting_stats,
    load_pitching_stats,
    load_statcast_batting_agg,
    load_statcast_pitching_agg,
    load_statcast_batter_percentiles,
    load_statcast_pitcher_percentiles,
    get_percentile_color,
    load_statcast_local, 
    load_batter_lookup, 
    calculate_stats_from_statcast,
    load_split_summary,
    combine_split_rows,
)

import json
import os

BOOKMARKS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bookmarks.json")

def load_bookmarks():
    if os.path.exists(BOOKMARKS_FILE):
        with open(BOOKMARKS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_bookmarks(bookmarks):
    os.makedirs(os.path.dirname(BOOKMARKS_FILE), exist_ok=True)
    with open(BOOKMARKS_FILE, "w") as f:
        json.dump(bookmarks, f, indent=2)
from utils.charts import create_percentile_chart, create_comparison_radar

st.set_page_config(page_title="Player Comparison", page_icon="⚾", layout="wide")
inject_custom_css()
render_nav_back()

st.markdown("## ⚾ Player Comparison")

with st.sidebar:
    st.markdown("### ⚙️ Comparison Settings")
    season = st.selectbox("Season", AVAILABLE_SEASONS, index=AVAILABLE_SEASONS.index(DEFAULT_SEASON))
    player_type = st.radio("Player Type", ["Batters", "Pitchers"])
    show_qualified_only = st.checkbox("Show only qualified players", value=False, key="qual_filter")
    st.markdown("### 🔀 Splits")
    split_hand = st.radio("Pitcher Hand", ["All", "vs RHP", "vs LHP", "Both"], horizontal=True, key="split_hand")
    split_venue = st.radio("Venue", ["All", "Home", "Away", "Both"], horizontal=True, key="split_venue")
    month_options = ["All", "March/April", "May", "June", "July", "August", "September/October"]
    split_months = st.multiselect("Months", month_options[1:], key="split_months")
    ev_threshold = st.select_slider("Exit Velo Threshold", options=[0, 90, 95, 100, 105, 110], value=0, key="ev_thresh")
    min_bbe = st.slider("Min PA (for split percentiles)", 0, 200, 50, key="min_bbe")
    split_active = False
    if split_hand != "All" or split_venue != "All" or len(split_months) > 0:
        split_active = True
        st.info("⚠️ Split active — stats calculated from local Statcast data.")
   

BATTER_STATCAST_METRICS = {
    "exit_velocity": "Exit Velocity",
    "max_ev": "Max Exit Velo",
    "brl_percent": "Barrel %",
    "hard_hit_percent": "Hard Hit %",
    "xwoba": "xwOBA",
    "xba": "xBA",
    "xslg": "xSLG",
    "xiso": "xISO",
    "xobp": "xOBP",
    "brl": "Barrels",
    "k_percent": "K%",
    "bb_percent": "BB%",
    "whiff_percent": "Whiff %",
    "chase_percent": "Chase %",
    "sprint_speed": "Sprint Speed",
    "bat_speed": "Bat Speed",
    "squared_up_rate": "Squared Up %",
    "swing_length": "Swing Length",
}
BATTER_TRADITIONAL_METRICS = {
    "AVG": "Batting Avg", "OBP": "On-Base %", "SLG": "Slugging %",
    "OPS": "OPS", "HR": "Home Runs", "wOBA": "wOBA", "WAR": "WAR",
    "wRC+": "wRC+", "ISO": "ISO", "BB%": "Walk %", "K%": "Strikeout %",
}
PITCHER_STATCAST_METRICS = {
    "exit_velocity": "Exit Velo Against",
    "max_ev": "Max Exit Velo Against",
    "brl_percent": "Barrel % Against",
    "hard_hit_percent": "Hard Hit % Against",
    "xwoba": "xwOBA Against",
    "xba": "xBA Against",
    "xslg": "xSLG Against",
    "xera": "xERA",
    "k_percent": "K%",
    "bb_percent": "BB%",
    "whiff_percent": "Whiff %",
    "chase_percent": "Chase %",
    "fb_velocity": "Fastball Velo",
    "fb_spin": "Fastball Spin",
    "curve_spin": "Curveball Spin",
}
PITCHER_TRADITIONAL_METRICS = {
    "ERA": "ERA", "FIP": "FIP", "WHIP": "WHIP", "K/9": "K/9",
    "BB/9": "BB/9", "WAR": "WAR", "K%": "K%", "BB%": "BB%", "HR/9": "HR/9",
}

if player_type == "Batters":
    trad_stats = load_batting_stats(season)
    statcast_agg = load_statcast_batting_agg(season)
    savant_pcts = load_statcast_batter_percentiles(season)
    sc_metrics = BATTER_STATCAST_METRICS
    trad_metrics = BATTER_TRADITIONAL_METRICS
    invert_metrics = ["K%"]
else:
    trad_stats = load_pitching_stats(season)
    statcast_agg = load_statcast_pitching_agg(season)
    savant_pcts = load_statcast_pitcher_percentiles(season)
    sc_metrics = PITCHER_STATCAST_METRICS
    trad_metrics = PITCHER_TRADITIONAL_METRICS
    invert_metrics = ["avg_hit_speed", "brl_percent", "hard_hit_percent",
                      "ERA", "FIP", "WHIP", "BB/9", "BB%", "HR/9"]

name_col_trad = "Name"
name_col_sc = "last_name, first_name"

if not trad_stats.empty:
    # Build qualified lookup — scales with season progress
    # Qualifying rate: 3.1 PA per team game (batters), 1.0 IP per team game (pitchers)
    qualified_players = set()
    if player_type == "Batters" and "PA" in trad_stats.columns and "G" in trad_stats.columns:
        max_games = min(trad_stats["G"].max(), 162)
        qual_threshold = max(1, int(3.1 * max_games))
        qualified_players = set(trad_stats[trad_stats["PA"] >= qual_threshold][name_col_trad].tolist())
        st.caption(f"✅ {len(qualified_players)} qualified players ({qual_threshold}+ {'PA' if player_type == 'Batters' else 'IP'})")
    elif player_type == "Pitchers" and "IP" in trad_stats.columns and "G" in trad_stats.columns:
        max_games = min(trad_stats["G"].max(), 162)
        qual_threshold = max(1, int(1.0 * max_games))
        qualified_players = set(trad_stats[trad_stats["IP"] >= qual_threshold][name_col_trad].tolist())

    all_available_metrics = {**sc_metrics, **trad_metrics}
    with st.sidebar:
        with st.expander("📊 Percentile Stats to Show"):
            default_metrics = ["exit_velocity", "max_ev", "brl_percent", "k_percent", "bb_percent",
                               "sprint_speed", "AVG", "OBP", "SLG", "OPS", "HR", "WAR", "BB%", "K%"]
            select_all = st.checkbox("Select All", value=False, key="select_all_metrics")
            if select_all:
                selected_metrics = list(all_available_metrics.keys())
            else:
                selected_metrics = []
                for key, label in all_available_metrics.items():
                    default_on = key in default_metrics
                    if st.checkbox(label, value=default_on, key=f"metric_{key}"):
                        selected_metrics.append(key)

    available_players = sorted(trad_stats[name_col_trad].dropna().unique().tolist())
    

    # --- Bookmarks ---
    bookmarks = load_bookmarks()
    bookmark_names = list(bookmarks.keys())

    with st.expander("📌 Bookmarks"):
        # Load a bookmark
        if bookmark_names:
            chosen_bookmark = st.selectbox("Load a saved group", [""] + bookmark_names, key="load_bm")
            if st.button("📂 Load Bookmark") and chosen_bookmark:
                valid = [p for p in bookmarks[chosen_bookmark] if p in available_players]
                st.session_state["player_multiselect"] = valid
                st.session_state["bookmarked_players_current"] = valid
                st.rerun()
        else:
            st.caption("No bookmarks saved yet.")

        # Save current selection as bookmark
        new_bookmark_name = st.text_input("Save current selection as", placeholder="e.g. My Team, Top 1B")
        if st.button("💾 Save Bookmark") and new_bookmark_name:
            bookmarks[new_bookmark_name] = st.session_state.get("bookmarked_players_current", st.session_state.get("bookmarked_players", []))
            save_bookmarks(bookmarks)
            st.success(f"Saved '{new_bookmark_name}'!")
            st.rerun()

        # Delete a bookmark
        if bookmark_names:
            delete_choice = st.selectbox("Delete a bookmark", [""] + bookmark_names, key="delete_bm")
            if st.button("🗑️ Delete") and delete_choice:
                del bookmarks[delete_choice]
                save_bookmarks(bookmarks)
                st.success(f"Deleted '{delete_choice}'")
                st.rerun()

    if show_qualified_only:
        player_options = [p for p in available_players if p in qualified_players]
    else:
        player_options = available_players

    # Ensure key exists so multiselect doesn't reset between reruns
    if "player_multiselect" not in st.session_state:
        st.session_state["player_multiselect"] = []

    # Filter out any players no longer in available options
    st.session_state["player_multiselect"] = [
        p for p in st.session_state["player_multiselect"] if p in player_options
    ]

    selected_players = st.multiselect(
        "Select players to compare",
        options=player_options,
        placeholder="Type to search players...",
        key="player_multiselect",
    )

    st.session_state["bookmarked_players_current"] = selected_players

    if selected_players:
        trad_pct_cols = [c for c in trad_metrics.keys() if c in trad_stats.columns]
        trad_pcts = trad_stats[[name_col_trad] + trad_pct_cols].copy()

        for col in trad_pct_cols:
            ascending = col not in invert_metrics
            trad_pcts[f"{col}_pct"] = trad_stats[col].rank(pct=True, ascending=ascending) * 100

        if not statcast_agg.empty and name_col_sc in statcast_agg.columns:
            sc_pct_cols = [c for c in sc_metrics.keys() if c in statcast_agg.columns]
            for col in sc_pct_cols:
                ascending = col in invert_metrics
                statcast_agg[f"{col}_pct"] = statcast_agg[col].rank(pct=True, ascending=ascending) * 100

# --- Split Filters ---
        
        # --- Calculate split stats if active ---
        # --- Calculate split stats if active ---
        split_stats = pd.DataFrame()
        if split_active and player_type == "Batters":
            summary = load_split_summary(season)
            if not summary.empty:
                # Build split combinations
                hand_splits = []
                if split_hand == "Both":
                    hand_splits = [("vs RHP", "R"), ("vs LHP", "L")]
                elif split_hand == "vs RHP":
                    hand_splits = [("vs RHP", "R")]
                elif split_hand == "vs LHP":
                    hand_splits = [("vs LHP", "L")]
                else:
                    hand_splits = [("All", None)]

                venue_splits = []
                if split_venue == "Both":
                    venue_splits = [("Home", "Home"), ("Away", "Away")]
                elif split_venue == "Home":
                    venue_splits = [("Home", "Home")]
                elif split_venue == "Away":
                    venue_splits = [("Away", "Away")]
                else:
                    venue_splits = [("All", None)]

                if len(split_months) > 0:
                    month_splits = [(m, m) for m in split_months]
                else:
                    month_splits = [("All", None)]

                # Generate stats for each combination
                all_splits = []
                for hand_label, hand_val in hand_splits:
                    for venue_label, venue_val in venue_splits:
                        for month_label, month_val in month_splits:
                            filtered = summary.copy()

                            if hand_val is not None:
                                filtered = filtered[filtered["p_throws"] == hand_val]
                            if venue_val is not None:
                                filtered = filtered[filtered["venue"] == venue_val]
                            if month_val is not None:
                                filtered = filtered[filtered["month_label"] == month_val]

                            # Group by batter and combine rows
                            if not filtered.empty:
                                player_stats = []
                                for batter_name, group in filtered.groupby("batter_name"):
                                    combined = combine_split_rows(group)
                                    combined["batter_name"] = batter_name
                                    split_label_parts = []
                                    if hand_label != "All":
                                        split_label_parts.append(hand_label)
                                    if venue_label != "All":
                                        split_label_parts.append(venue_label)
                                    if month_label != "All":
                                        split_label_parts.append(month_label)
                                    combined["Split"] = ", ".join(split_label_parts) if split_label_parts else "All"
                                    player_stats.append(combined)

                                if player_stats:
                                    split_df = pd.DataFrame(player_stats)
                                    all_splits.append(split_df)

                if all_splits:
                    split_stats = pd.concat(all_splits, ignore_index=True)  




        view_mode = st.radio(
            "View Mode",
            ["Grid View", "Detail View", "Radar Comparison", "Stats Table"],
            horizontal=True,
            key="view_mode_radio",
            index=["Grid View", "Detail View", "Radar Comparison", "Stats Table"].index(
                st.session_state.get("last_view_mode", "Grid View")
            ),
        )
        st.session_state["last_view_mode"] = view_mode

        if view_mode in ["Grid View", "Detail View"]:
            # Detail view: player selector
            if view_mode == "Detail View":
                detail_player = st.selectbox(
                    "Select player to view:",
                    selected_players,
                    key="detail_player_select"
                )
                players_to_render = [detail_player]
                cols_per_row = 1
            else:
                players_to_render = selected_players
                cols_per_row = 3

            is_compact = view_mode == "Grid View"

            for i in range(0, len(players_to_render), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, col in enumerate(cols):
                    idx = i + j
                    if idx >= len(players_to_render):
                        break
                    pname = players_to_render[idx]
                    with col:
                        player_pcts = {}
                        player_raw = {}

                        pct_split_active = split_active and not split_stats.empty
                        if pct_split_active and (split_hand == "Both" or split_venue == "Both"):
                            pct_split_active = False
                        if pct_split_active:
                            # --- SPLIT MODE: use calculated stats ---
                            name_col_split = "batter_name" if "batter_name" in split_stats.columns else "batter"
                            # For percentile charts, combine "Both" splits into one row per player
                            chart_split_stats = split_stats.copy()
                            if "Split" in chart_split_stats.columns:
                                # Recombine all split rows per player into one total
                                from utils.data_loader import combine_split_rows
                                combined_rows = []
                                for bname, group in chart_split_stats.groupby(name_col_split):
                                    combined = combine_split_rows(group)
                                    combined[name_col_split] = bname
                                    combined["Split"] = "Combined"
                                    combined_rows.append(combined)
                                if combined_rows:
                                    chart_split_stats = pd.DataFrame(combined_rows)
                            def normalize(s):
                                return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower().strip()
                            parts = pname.split(" ", 1)
                            if len(parts) == 2:
                                p_split = chart_split_stats[
                                    chart_split_stats[name_col_split].apply(normalize).str.contains(normalize(parts[-1]), case=False, na=False)
                                ]
                                if len(p_split) > 1:
                                    p_split = chart_split_stats[
                                        chart_split_stats[name_col_split].apply(normalize) == normalize(pname)
                                    ]
                            else:
                                p_split = chart_split_stats[
                                    chart_split_stats[name_col_split].apply(normalize).str.contains(normalize(pname), case=False, na=False)
                                ]

                            if not p_split.empty:
                                p_split = p_split.iloc[0]

                                split_metrics = {
                                    "AVG": "Batting Avg", "OBP": "On-Base %", "SLG": "Slugging %",
                                    "OPS": "OPS", "HR": "Home Runs", "BB": "Walks", "SO": "Strikeouts",
                                    "avg_ev": "Exit Velocity", "max_ev": "Max Exit Velo",
                                    "barrel_pct": "Barrel %", "hard_hit_pct": "Hard Hit %",
                                    "avg_la": "Avg Launch Angle",
                                }
                                if ev_threshold > 0:
                                    col_count = f"ev_{ev_threshold}_count"
                                    col_rate = f"ev_{ev_threshold}_rate"
                                    split_metrics[col_count] = f"BIP {ev_threshold}+ Count"
                                    split_metrics[col_rate] = f"BIP {ev_threshold}+ Rate %"
                                invert_split = ["SO"]

                                for m, label in split_metrics.items():
                                    if m in split_stats.columns:
                                        val = p_split[m]
                                        if pd.notna(val):
                                            player_raw[m] = val
                                            ascending = m not in invert_split
                                            # Filter to players with enough batted ball events for meaningful percentiles

                                            min_bbe = min_bbe
                                            qualified_split = chart_split_stats[chart_split_stats["PA"] >= min_bbe]
                                            if p_split[name_col_split] in qualified_split[name_col_split].values:
                                                pct_series = qualified_split[m].rank(pct=True, ascending=ascending)
                                                player_idx = qualified_split[qualified_split[name_col_split] == p_split[name_col_split]].index[0]
                                                player_pcts[m] = pct_series[player_idx] * 100

                                all_labels = split_metrics
                                available = {k: v for k, v in all_labels.items()
                                             if k in player_pcts}

                                if available:
                                    qual_tag = " ✅" if pname in qualified_players else ""
                                    split_parts = []
                                    if split_hand != "All":
                                        split_parts.append(split_hand)
                                    if split_venue != "All":
                                        split_parts.append(split_venue)
                                    if len(split_months) > 0:
                                        split_parts.extend(split_months)
                                    split_label = " [" + ", ".join(split_parts) + "]"
                                    fig = create_percentile_chart(pname + qual_tag + split_label, player_pcts, available, raw_values=player_raw)
                                    st.plotly_chart(fig, use_container_width=True)
                                else:
                                    st.warning(f"No split data for {pname}")
                            else:
                                st.warning(f"No split data for {pname}")

                        else:
                            # --- NORMAL MODE: use Savant percentiles + FanGraphs ---
                            p_trad = trad_pcts[trad_pcts[name_col_trad] == pname]
                            if not p_trad.empty:
                                for m in trad_pct_cols:
                                    val = p_trad[f"{m}_pct"].values[0]
                                    if pd.notna(val):
                                        player_pcts[m] = val

                            p_trad_raw = trad_stats[trad_stats[name_col_trad] == pname]
                            if not p_trad_raw.empty:
                                for m in trad_pct_cols:
                                    if m in p_trad_raw.columns:
                                        rv = p_trad_raw[m].values[0]
                                        if pd.notna(rv):
                                            player_raw[m] = rv

                            if not savant_pcts.empty and "player_name" in savant_pcts.columns:
                                parts = pname.split(" ", 1)
                                if len(parts) == 2:
                                    savant_name = f"{parts[1]}, {parts[0]}"
                                    def normalize(s):
                                        return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower().strip()
                                    p_sv = savant_pcts[
                                        savant_pcts["player_name"].apply(normalize) == normalize(savant_name)
                                    ]
                                else:
                                    p_sv = savant_pcts[
                                        savant_pcts["player_name"].str.contains(pname, case=False, na=False)
                                    ]
                                if not p_sv.empty:
                                    p_sv = p_sv.iloc[0]
                                    for m in sc_metrics.keys():
                                        if m in savant_pcts.columns:
                                            val = p_sv[m]
                                            if pd.notna(val):
                                                player_pcts[m] = val

                            # Get raw Statcast values from aggregate data
                            savant_to_agg = {
                                "exit_velocity": "avg_hit_speed",
                                "max_ev": "max_hit_speed",
                                "brl_percent": "brl_percent",
                                "hard_hit_percent": "hard_hit_percent",
                            }
                            if not statcast_agg.empty and "last_name, first_name" in statcast_agg.columns:
                                parts = pname.split(" ", 1)
                                if len(parts) == 2:
                                    sc_name = f"{parts[1]}, {parts[0]}"
                                    p_sc = statcast_agg[
                                        statcast_agg["last_name, first_name"].apply(normalize) == normalize(sc_name)
                                    ]
                                    if not p_sc.empty:
                                        p_sc = p_sc.iloc[0]
                                        for m in sc_metrics.keys():
                                            agg_col = savant_to_agg.get(m, m)
                                            if agg_col in statcast_agg.columns:
                                                rv = p_sc[agg_col]
                                                if pd.notna(rv):
                                                    player_raw[m] = rv

                            all_labels = {**sc_metrics, **trad_metrics}
                            available = {k: v for k, v in all_labels.items()
                                         if k in player_pcts and k in selected_metrics}
                            
                            
                            # Add EV threshold metrics from split summary
                            if ev_threshold > 0:
                                summary = load_split_summary(season)
                                if not summary.empty:
                                    def normalize(s):
                                        return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower().strip()
                                    p_sum = summary.groupby("batter_name").agg({
                                        "PA": "sum",
                                        f"ev_{ev_threshold}_count": "sum",
                                    }).reset_index()
                                    p_sum[f"ev_{ev_threshold}_rate"] = (p_sum[f"ev_{ev_threshold}_count"] / p_sum["PA"] * 100).round(1)
                                    
                                    p_match = p_sum[p_sum["batter_name"].apply(normalize).str.contains(normalize(pname.split(" ")[-1]), case=False, na=False)]
                                    if len(p_match) > 1:
                                        p_match = p_sum[p_sum["batter_name"].apply(normalize) == normalize(pname)]
                                    
                                    if not p_match.empty:
                                        p_row = p_match.iloc[0]
                                        col_count = f"ev_{ev_threshold}_count"
                                        col_rate = f"ev_{ev_threshold}_rate"
                                        
                                        player_pcts[col_count] = p_sum[col_count].rank(pct=True, ascending=True)[p_match.index[0]] * 100
                                        player_pcts[col_rate] = p_sum[col_rate].rank(pct=True, ascending=True)[p_match.index[0]] * 100
                                        player_raw[col_count] = p_row[col_count]
                                        player_raw[col_rate] = p_row[col_rate]
                                        
                                        all_labels[col_count] = f"BIP {ev_threshold}+ Count"
                                        all_labels[col_rate] = f"BIP {ev_threshold}+ Rate %"
                                        available[col_count] = f"BIP {ev_threshold}+ Count"
                                        available[col_rate] = f"BIP {ev_threshold}+ Rate %"

                            if available:
                                qual_tag = " ✅" if pname in qualified_players else ""
                                # Player name header
                                name_color = "#E87A2C"
                                qual_html = '<span style="color:#6ABF69;font-size:0.8em;margin-left:6px;">✅ Qualified</span>' if pname in qualified_players else ""
                                st.markdown(
                                    f'<div style="font-size:{"1em" if is_compact else "1.2em"};font-weight:700;'
                                    f'color:{name_color};border-bottom:2px solid #E87A2C22;'
                                    f'padding-bottom:4px;margin-bottom:2px;">'
                                    f'{pname}{qual_html}</div>',
                                    unsafe_allow_html=True
                                )
                                fig = create_percentile_chart(pname, player_pcts, available, raw_values=player_raw, compact=is_compact)
                                st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                            else:
                                st.warning(f"No percentile data found for {pname}")


        elif view_mode == "Radar Comparison":
            if player_type == "Batters":
                radar_keys = ["AVG", "OBP", "SLG", "HR", "wOBA", "WAR", "K%", "BB%"]
            else:
                radar_keys = ["ERA", "FIP", "WHIP", "K/9", "BB/9", "WAR", "K%"]
            radar_metrics = {k: trad_metrics[k] for k in radar_keys if k in trad_metrics}

            players_data = []
            for pname in selected_players:
                p_trad = trad_pcts[trad_pcts[name_col_trad] == pname]
                if not p_trad.empty:
                    vals = {}
                    for m in radar_metrics.keys():
                        pct_col = f"{m}_pct"
                        if pct_col in p_trad.columns:
                            v = p_trad[pct_col].values[0]
                            if pd.notna(v):
                                vals[m] = v
                    players_data.append({"name": pname, "values": vals})

            if players_data:
                fig = create_comparison_radar(players_data, radar_metrics)
                st.plotly_chart(fig, use_container_width=True)

        elif view_mode == "Stats Table":
            if split_active and not split_stats.empty and player_type == "Batters":
                st.markdown("### Split Stats")
                name_col_split = "batter_name" if "batter_name" in split_stats.columns else "batter"
                
                # Filter to selected players
                def normalize(s):
                    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii").lower().strip()
                
                matched_rows = []
                for pname in selected_players:
                    player_splits = split_stats[
                        split_stats[name_col_split].apply(normalize).str.contains(normalize(pname.split(" ")[-1]), case=False, na=False)
                    ]
                    if len(player_splits) > 1:
                        exact = split_stats[split_stats[name_col_split].apply(normalize) == normalize(pname)]
                        if not exact.empty:
                            player_splits = exact
                    if not player_splits.empty:
                        matched_rows.append(player_splits)
                
                if matched_rows:
                    display_split = pd.concat(matched_rows, ignore_index=True)
                    split_card_stats = ["PA", "AB", "H", "HR", "BB", "SO", "AVG", "OBP", "SLG", "OPS",
                                        "avg_ev", "max_ev", "avg_la", "barrel_pct", "hard_hit_pct"]
                    split_display_cols = [name_col_split, "Split"] + [c for c in split_card_stats if c in display_split.columns]
                    display_split = display_split[[c for c in split_display_cols if c in display_split.columns]]
                    
                    # Rename columns for readability
                    rename_map = {
                        name_col_split: "Player",
                        "avg_ev": "Avg EV",
                        "max_ev": "Max EV",
                        "avg_la": "Avg LA",
                        "barrel_pct": "Barrel%",
                        "hard_hit_pct": "HardHit%",
                    }
                    display_split = display_split.rename(columns=rename_map)
                    
                    st.dataframe(display_split.reset_index(drop=True), use_container_width=True,
                                 height=min(600, 50 + len(display_split) * 35),
                                 column_config={"Player": st.column_config.TextColumn(pinned=True)})
                else:
                    st.warning("No split data found for selected players.")
            else:
                st.markdown("### Traditional Stats")
                if player_type == "Batters":
                    card_stats = ["G", "AB", "R", "H", "2B", "3B", "HR", "RBI", "SB", "CS", "BB", "SO", "AVG", "OBP", "SLG", "OPS"]
                else:
                    card_stats = ["W", "L", "ERA", "G", "GS", "SV", "IP", "H", "R", "ER", "HR", "BB", "SO", "WHIP"]
                display_cols = [name_col_trad, "Team"] + [c for c in card_stats if c in trad_stats.columns]
                filtered = trad_stats[trad_stats[name_col_trad].isin(selected_players)]
                filtered = filtered[[c for c in display_cols if c in filtered.columns]]
                st.dataframe(filtered.reset_index(drop=True), use_container_width=True,
                             height=min(400, 50 + len(filtered) * 35),
                             column_config={"Name": st.column_config.TextColumn(pinned=True)})
    else:
        st.info("👆 Select players above to start comparing.")
else:
    st.warning("No player stats loaded. Head to **Data Manager** to download data first.")