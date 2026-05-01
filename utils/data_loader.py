import streamlit as st
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, date, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
METADATA_FILE = os.path.join(DATA_DIR, "metadata.json")

SEASON_DATES = {
    2023: ("2023-03-30", "2023-10-01"),
    2024: ("2024-03-28", "2024-09-29"),
    2025: ("2025-03-27", "2025-09-28"),
    2026: ("2026-03-26", "2026-09-27"),
}


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def _load_metadata():
    ensure_data_dir()
    if os.path.exists(METADATA_FILE):
        with open(METADATA_FILE, "r") as f:
            return json.load(f)
    return {}


def _save_metadata(meta):
    ensure_data_dir()
    with open(METADATA_FILE, "w") as f:
        json.dump(meta, f, indent=2, default=str)


def get_data_status(season=2025):
    meta = _load_metadata()
    season_key = str(season)

    status = {}
    datasets = [
        ("statcast", f"statcast_{season}.parquet"),
        ("batting_stats", f"batting_stats_{season}.parquet"),
        ("pitching_stats", f"pitching_stats_{season}.parquet"),
        ("statcast_batting_agg", f"statcast_batting_agg_{season}.parquet"),
        ("statcast_pitching_agg", f"statcast_pitching_agg_{season}.parquet"),
        ("statcast_batter_pcts", f"statcast_batter_pcts_{season}.parquet"),
        ("statcast_pitcher_pcts", f"statcast_pitcher_pcts_{season}.parquet"),
        ("team_batting", f"team_batting_{season}.parquet"),
        ("team_pitching", f"team_pitching_{season}.parquet"),
        ("batter_lookup", f"batter_lookup_{season}.parquet"),
        ("split_summary", f"split_summary_{season}.parquet"),
    ]

    for name, filename in datasets:
        filepath = os.path.join(DATA_DIR, filename)
        exists = os.path.exists(filepath)

        last_refresh = None
        meta_key = f"{name}_{season_key}_last_refresh"
        if meta_key in meta:
            last_refresh = datetime.fromisoformat(meta[meta_key])

        stale = True
        if last_refresh:
            hours_since = (datetime.now() - last_refresh).total_seconds() / 3600
            stale = hours_since > 24

        status[name] = {
            "exists": exists,
            "last_refresh": last_refresh,
            "stale": stale,
            "filepath": filepath,
        }

    return status


def data_is_fresh(season=2025):
    status = get_data_status(season)
    return all(s["exists"] and not s["stale"] for s in status.values())



# ===========================================================
# YAHOO FANTASY DATA - LOCAL SAVE/LOAD
# ===========================================================

YAHOO_DATA_FILE = os.path.join(DATA_DIR, "yahoo_fantasy_data.json")



def save_weekly_player_stats(df):
    """Save weekly per-player Yahoo stats locally."""
    ensure_data_dir()
    if df is not None and not df.empty:
        df.to_parquet(os.path.join(DATA_DIR, "yahoo_weekly_player_stats.parquet"), index=False)
        meta = _load_metadata()
        meta["yahoo_weekly_player_stats_last_refresh"] = datetime.now().isoformat()
        meta["yahoo_weekly_player_stats_rows"] = len(df)
        _save_metadata(meta)


def load_weekly_player_stats():
    """Load locally saved weekly per-player Yahoo stats."""
    filepath = os.path.join(DATA_DIR, "yahoo_weekly_player_stats.parquet")
    if os.path.exists(filepath):
        return pd.read_parquet(filepath)
    return pd.DataFrame()

def save_fantasy_scoring(batter_df, pitcher_df, standings):
    """Save calculated fantasy scoring tables locally."""
    import json
    ensure_data_dir()
    if batter_df is not None and not batter_df.empty:
        batter_df.to_parquet(os.path.join(DATA_DIR, "fantasy_batters.parquet"), index=False)
    if pitcher_df is not None and not pitcher_df.empty:
        pitcher_df.to_parquet(os.path.join(DATA_DIR, "fantasy_pitchers.parquet"), index=False)
    if standings:
        with open(os.path.join(DATA_DIR, "fantasy_standings.json"), "w") as f:
            json.dump(standings, f, indent=2, default=str)


def load_fantasy_scoring():
    """Load locally saved fantasy scoring tables. Returns (batter_df, pitcher_df, standings)."""
    import json
    batter_path = os.path.join(DATA_DIR, "fantasy_batters.parquet")
    pitcher_path = os.path.join(DATA_DIR, "fantasy_pitchers.parquet")
    standings_path = os.path.join(DATA_DIR, "fantasy_standings.json")

    batter_df = pd.read_parquet(batter_path) if os.path.exists(batter_path) else pd.DataFrame()
    pitcher_df = pd.read_parquet(pitcher_path) if os.path.exists(pitcher_path) else pd.DataFrame()
    standings = []
    if os.path.exists(standings_path):
        with open(standings_path, "r") as f:
            standings = json.load(f)
    return batter_df, pitcher_df, standings

def save_yahoo_data(league_info, teams, rosters, standings):
    """Save Yahoo fantasy data locally to avoid repeated API calls."""
    ensure_data_dir()
    data = {
        "league_info": league_info,
        "teams": teams,
        "rosters": {k: v for k, v in rosters.items()},
        "standings": standings,
        "last_refresh": datetime.now().isoformat(),
    }
    with open(YAHOO_DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_yahoo_data():
    """Load locally cached Yahoo fantasy data. Returns None if not found or stale (>1 hour)."""
    if not os.path.exists(YAHOO_DATA_FILE):
        return None
    with open(YAHOO_DATA_FILE, "r") as f:
        data = json.load(f)
    last_refresh = data.get("last_refresh")
    if last_refresh:
        age_hours = (datetime.now() - datetime.fromisoformat(last_refresh)).total_seconds() / 3600
        if age_hours > 1:
            return None  # Stale, force refresh
    return data


def yahoo_data_is_fresh():
    """Check if local Yahoo data exists and is less than 1 hour old."""
    data = load_yahoo_data()
    return data is not None

# ===========================================================
# STATCAST PITCH DATA
# ===========================================================

def download_statcast_full_season(season=2025, progress_callback=None):
    from pybaseball import statcast
    ensure_data_dir()

    start_str, end_str = SEASON_DATES.get(season, ("2025-03-27", "2025-09-28"))
    start = datetime.strptime(start_str, "%Y-%m-%d").date()
    end = min(datetime.strptime(end_str, "%Y-%m-%d").date(), date.today())

    all_chunks = []
    current = start
    total_days = (end - start).days
    days_done = 0

    while current <= end:
        chunk_end = min(current + timedelta(days=6), end)
        try:
            chunk = statcast(
                start_dt=current.strftime("%Y-%m-%d"),
                end_dt=chunk_end.strftime("%Y-%m-%d"),
            )
            if chunk is not None and not chunk.empty:
                all_chunks.append(chunk)
        except Exception as e:
            st.warning(f"Failed to fetch {current} to {chunk_end}: {e}")

        days_done += (chunk_end - current).days + 1
        if progress_callback:
            progress_callback(min(days_done / max(total_days, 1), 1.0))

        current = chunk_end + timedelta(days=1)

    if all_chunks:
        df = pd.concat(all_chunks, ignore_index=True)
        filepath = os.path.join(DATA_DIR, f"statcast_{season}.parquet")
        df.to_parquet(filepath, index=False)

        meta = _load_metadata()
        meta[f"statcast_{season}_last_refresh"] = datetime.now().isoformat()
        meta[f"statcast_{season}_last_date"] = end.isoformat()
        meta[f"statcast_{season}_rows"] = len(df)
        _save_metadata(meta)

        return df
    return pd.DataFrame()


def update_statcast_incremental(season=2025, progress_callback=None):
    from pybaseball import statcast
    ensure_data_dir()

    meta = _load_metadata()
    last_date_key = f"statcast_{season}_last_date"
    filepath = os.path.join(DATA_DIR, f"statcast_{season}.parquet")

    if last_date_key not in meta or not os.path.exists(filepath):
        return download_statcast_full_season(season, progress_callback)

    last_date = datetime.strptime(meta[last_date_key], "%Y-%m-%d").date()
    start = last_date + timedelta(days=1)
    _, end_str = SEASON_DATES.get(season, ("2025-03-27", "2025-09-28"))
    end = min(datetime.strptime(end_str, "%Y-%m-%d").date(), date.today())

    if start > end:
        if progress_callback:
            progress_callback(1.0)
        return load_statcast_local(season)

    new_chunks = []
    current = start
    total_days = (end - start).days
    days_done = 0

    while current <= end:
        chunk_end = min(current + timedelta(days=6), end)
        try:
            chunk = statcast(
                start_dt=current.strftime("%Y-%m-%d"),
                end_dt=chunk_end.strftime("%Y-%m-%d"),
            )
            if chunk is not None and not chunk.empty:
                new_chunks.append(chunk)
        except Exception as e:
            st.warning(f"Failed to fetch {current} to {chunk_end}: {e}")

        days_done += (chunk_end - current).days + 1
        if progress_callback:
            progress_callback(min(days_done / max(total_days, 1), 1.0))

        current = chunk_end + timedelta(days=1)

    if new_chunks:
        new_df = pd.concat(new_chunks, ignore_index=True)
        existing = pd.read_parquet(filepath)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["game_pk", "at_bat_number", "pitch_number"],
            keep="last"
        )
        combined.to_parquet(filepath, index=False)

        meta[f"statcast_{season}_last_refresh"] = datetime.now().isoformat()
        meta[f"statcast_{season}_last_date"] = end.isoformat()
        meta[f"statcast_{season}_rows"] = len(combined)
        _save_metadata(meta)

        return combined

    if progress_callback:
        progress_callback(1.0)
    return load_statcast_local(season)


def load_statcast_local(season=2025):
    filepath = os.path.join(DATA_DIR, f"statcast_{season}.parquet")
    if os.path.exists(filepath):
        return pd.read_parquet(filepath)
    return pd.DataFrame()


# ===========================================================
# TRADITIONAL STATS
# ===========================================================

def download_batting_stats(season=2025):
    from pybaseball import batting_stats_bref
    ensure_data_dir()
    try:
        df = batting_stats_bref(season)
        filepath = os.path.join(DATA_DIR, f"batting_stats_{season}.parquet")
        df.to_parquet(filepath, index=False)
        meta = _load_metadata()
        meta[f"batting_stats_{season}_last_refresh"] = datetime.now().isoformat()
        meta[f"batting_stats_{season}_rows"] = len(df)
        _save_metadata(meta)
        return df
    except Exception as e:
        st.error(f"Error downloading batting stats: {e}")
        return pd.DataFrame()


def download_pitching_stats(season=2025):
    from pybaseball import pitching_stats_bref
    ensure_data_dir()
    try:
        df = pitching_stats_bref(season)
        filepath = os.path.join(DATA_DIR, f"pitching_stats_{season}.parquet")
        df.to_parquet(filepath, index=False)
        meta = _load_metadata()
        meta[f"pitching_stats_{season}_last_refresh"] = datetime.now().isoformat()
        meta[f"pitching_stats_{season}_rows"] = len(df)
        _save_metadata(meta)
        return df
    except Exception as e:
        st.error(f"Error downloading pitching stats: {e}")
        return pd.DataFrame()


def download_statcast_batting_agg(season=2025):
    from pybaseball import statcast_batter_exitvelo_barrels
    ensure_data_dir()
    try:
        df = statcast_batter_exitvelo_barrels(season, minBBE=50)
        filepath = os.path.join(DATA_DIR, f"statcast_batting_agg_{season}.parquet")
        df.to_parquet(filepath, index=False)
        meta = _load_metadata()
        meta[f"statcast_batting_agg_{season}_last_refresh"] = datetime.now().isoformat()
        _save_metadata(meta)
        return df
    except Exception as e:
        st.error(f"Error downloading Statcast batting aggregates: {e}")
        return pd.DataFrame()


def download_statcast_pitching_agg(season=2025):
    from pybaseball import statcast_pitcher_exitvelo_barrels
    ensure_data_dir()
    try:
        df = statcast_pitcher_exitvelo_barrels(season, minBBE=50)
        filepath = os.path.join(DATA_DIR, f"statcast_pitching_agg_{season}.parquet")
        df.to_parquet(filepath, index=False)
        meta = _load_metadata()
        meta[f"statcast_pitching_agg_{season}_last_refresh"] = datetime.now().isoformat()
        _save_metadata(meta)
        return df
    except Exception as e:
        st.error(f"Error downloading Statcast pitching aggregates: {e}")
        return pd.DataFrame()
    
def download_team_batting(season=2025):
    from pybaseball import team_batting
    ensure_data_dir()
    # Load existing data if available to avoid losing it on FanGraphs errors
    filepath = os.path.join(DATA_DIR, f"team_batting_{season}.parquet")
    try:
        df = team_batting(season)
        df.to_parquet(filepath, index=False)
        meta = _load_metadata()
        meta[f"team_batting_{season}_last_refresh"] = datetime.now().isoformat()
        meta[f"team_batting_{season}_rows"] = len(df)
        _save_metadata(meta)
        return df
    except Exception as e:
        st.warning(f"Could not refresh team batting from FanGraphs (likely blocked): {e}. Using cached data if available.")
        if os.path.exists(filepath):
            return pd.read_parquet(filepath)
        return pd.DataFrame()


def download_team_pitching(season=2025):
    from pybaseball import team_pitching
    ensure_data_dir()
    filepath = os.path.join(DATA_DIR, f"team_pitching_{season}.parquet")
    try:
        df = team_pitching(season)
        df.to_parquet(filepath, index=False)
        meta = _load_metadata()
        meta[f"team_pitching_{season}_last_refresh"] = datetime.now().isoformat()
        meta[f"team_pitching_{season}_rows"] = len(df)
        _save_metadata(meta)
        return df
    except Exception as e:
        st.warning(f"Could not refresh team pitching from FanGraphs (likely blocked): {e}. Using cached data if available.")
        if os.path.exists(filepath):
            return pd.read_parquet(filepath)
        return pd.DataFrame()

def download_batter_lookup(season=2025):
    from pybaseball import playerid_reverse_lookup
    ensure_data_dir()
    try:
        # Get all unique batter IDs from Statcast data
        sc_path = os.path.join(DATA_DIR, f"statcast_{season}.parquet")
        if not os.path.exists(sc_path):
            st.warning("Download Statcast data first before building batter lookup.")
            return pd.DataFrame()
        
        sc = pd.read_parquet(sc_path, columns=["batter"])
        batter_ids = sc["batter"].dropna().unique().tolist()
        batter_ids = [int(b) for b in batter_ids]
        
        # Lookup in chunks of 50 to avoid timeouts
        all_results = []
        for i in range(0, len(batter_ids), 50):
            chunk = batter_ids[i:i+50]
            try:
                result = playerid_reverse_lookup(chunk, key_type="mlbam")
                if result is not None and not result.empty:
                    all_results.append(result)
            except Exception:
                pass
        
        if all_results:
            lookup = pd.concat(all_results, ignore_index=True)
            lookup["batter_name"] = lookup["name_first"].str.capitalize() + " " + lookup["name_last"].str.capitalize()
            lookup = lookup[["key_mlbam", "batter_name"]].rename(columns={"key_mlbam": "batter"})
            filepath = os.path.join(DATA_DIR, f"batter_lookup_{season}.parquet")
            lookup.to_parquet(filepath, index=False)
            
            meta = _load_metadata()
            meta[f"batter_lookup_{season}_last_refresh"] = datetime.now().isoformat()
            meta[f"batter_lookup_{season}_rows"] = len(lookup)
            _save_metadata(meta)
            return lookup
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error building batter lookup: {e}")
        return pd.DataFrame()
    
def download_statcast_batter_percentiles(season=2025):
    from pybaseball import statcast_batter_percentile_ranks
    ensure_data_dir()
    try:
        df = statcast_batter_percentile_ranks(season)
        filepath = os.path.join(DATA_DIR, f"statcast_batter_pcts_{season}.parquet")
        df.to_parquet(filepath, index=False)
        meta = _load_metadata()
        meta[f"statcast_batter_pcts_{season}_last_refresh"] = datetime.now().isoformat()
        _save_metadata(meta)
        return df
    except Exception as e:
        st.error(f"Error downloading Statcast batter percentiles: {e}")
        return pd.DataFrame()


def download_statcast_pitcher_percentiles(season=2025):
    from pybaseball import statcast_pitcher_percentile_ranks
    ensure_data_dir()
    try:
        df = statcast_pitcher_percentile_ranks(season)
        filepath = os.path.join(DATA_DIR, f"statcast_pitcher_pcts_{season}.parquet")
        df.to_parquet(filepath, index=False)
        meta = _load_metadata()
        meta[f"statcast_pitcher_pcts_{season}_last_refresh"] = datetime.now().isoformat()
        _save_metadata(meta)
        return df
    except Exception as e:
        st.error(f"Error downloading Statcast pitcher percentiles: {e}")
        return pd.DataFrame()


# ===========================================================
# LOAD FROM LOCAL
# ===========================================================

def _fix_name_encoding(df):
    """Fix corrupted UTF-8 encoding in Name column from Baseball Reference."""
    if "Name" in df.columns:
        import re as _re
        def decode_name(name):
            if not isinstance(name, str):
                return name
            # Step 1: interpret literal \xNN escape sequences in the string
            try:
                fixed = _re.sub(
                    r'\\x([0-9a-fA-F]{2})',
                    lambda m: bytes([int(m.group(1), 16)]).decode('latin-1'),
                    name
                )
            except Exception:
                fixed = name
            # Step 2: fix mojibake (UTF-8 bytes interpreted as latin-1)
            try:
                return fixed.encode("latin-1").decode("utf-8")
            except (UnicodeDecodeError, UnicodeEncodeError):
                return fixed
        df = df.copy()
        df["Name"] = df["Name"].apply(decode_name)
    return df


def load_batting_stats(season=2025):
    filepath = os.path.join(DATA_DIR, f"batting_stats_{season}.parquet")
    if os.path.exists(filepath):
        return _fix_name_encoding(pd.read_parquet(filepath))
    return pd.DataFrame()


def load_pitching_stats(season=2025):
    filepath = os.path.join(DATA_DIR, f"pitching_stats_{season}.parquet")
    if os.path.exists(filepath):
        return _fix_name_encoding(pd.read_parquet(filepath))
    return pd.DataFrame()


def load_statcast_batting_agg(season=2025):
    filepath = os.path.join(DATA_DIR, f"statcast_batting_agg_{season}.parquet")
    if os.path.exists(filepath):
        return pd.read_parquet(filepath)
    return pd.DataFrame()


def load_statcast_pitching_agg(season=2025):
    filepath = os.path.join(DATA_DIR, f"statcast_pitching_agg_{season}.parquet")
    if os.path.exists(filepath):
        return pd.read_parquet(filepath)
    return pd.DataFrame()

def load_team_batting(season=2025):
    filepath = os.path.join(DATA_DIR, f"team_batting_{season}.parquet")
    if os.path.exists(filepath):
        return pd.read_parquet(filepath)
    return pd.DataFrame()


def load_team_pitching(season=2025):
    filepath = os.path.join(DATA_DIR, f"team_pitching_{season}.parquet")
    if os.path.exists(filepath):
        return pd.read_parquet(filepath)
    return pd.DataFrame()

def load_batter_lookup(season=2025):
    filepath = os.path.join(DATA_DIR, f"batter_lookup_{season}.parquet")
    if os.path.exists(filepath):
        return pd.read_parquet(filepath)
    return pd.DataFrame()

def load_statcast_batter_percentiles(season=2025):
    filepath = os.path.join(DATA_DIR, f"statcast_batter_pcts_{season}.parquet")
    if os.path.exists(filepath):
        return pd.read_parquet(filepath)
    return pd.DataFrame()


def load_statcast_pitcher_percentiles(season=2025):
    filepath = os.path.join(DATA_DIR, f"statcast_pitcher_pcts_{season}.parquet")
    if os.path.exists(filepath):
        return pd.read_parquet(filepath)
    return pd.DataFrame()


# ===========================================================
# MASTER REFRESH
# ===========================================================

def refresh_all_data(season=2025, full_statcast=False):
    results = {}

    with st.spinner("Downloading batting stats..."):
        df = download_batting_stats(season)
        results["batting"] = len(df)

    with st.spinner("Downloading pitching stats..."):
        df = download_pitching_stats(season)
        results["pitching"] = len(df)

    with st.spinner("Downloading Statcast batting aggregates..."):
        df = download_statcast_batting_agg(season)
        results["sc_batting"] = len(df)
    
    with st.spinner("Downloading team batting stats..."):
        df = download_team_batting(season)
        results["team_batting"] = len(df)

    

    with st.spinner("Downloading team pitching stats..."):
        df = download_team_pitching(season)
        results["team_pitching"] = len(df)

    with st.spinner("Building batter name lookup (this may take a minute)..."):
        df = download_batter_lookup(season)
        results["batter_lookup"] = len(df)

    with st.spinner("Downloading Statcast pitching aggregates..."):
        df = download_statcast_pitching_agg(season)
        results["sc_pitching"] = len(df)
    
    with st.spinner("Downloading Statcast batter percentiles..."):
        df = download_statcast_batter_percentiles(season)
        results["sc_batter_pcts"] = len(df)

    with st.spinner("Downloading Statcast pitcher percentiles..."):
        df = download_statcast_pitcher_percentiles(season)
        results["sc_pitcher_pcts"] = len(df)

    st.markdown("### ⚾ Downloading Statcast pitch data...")
    st.caption("Fetching every pitch of the season in weekly chunks.")
    progress_bar = st.progress(0.0)

    def update_progress(pct):
        progress_bar.progress(pct)

    if full_statcast:
        df = download_statcast_full_season(season, progress_callback=update_progress)
    else:
        df = update_statcast_incremental(season, progress_callback=update_progress)

    results["statcast"] = len(df)
    progress_bar.progress(1.0)

    with st.spinner("Building split summary..."):
        df = build_split_summary(season)
        results["split_summary"] = len(df)

    return results


# ===========================================================
# PERCENTILE HELPERS
# ===========================================================

def compute_percentiles(df, columns, player_col="player_name"):
    result = df[[player_col]].copy()
    for col in columns:
        if col in df.columns:
            result[col] = df[col].rank(pct=True) * 100
    return result


def get_percentile_color(value):
    if value >= 90:
        return "#C6011F"
    elif value >= 75:
        return "#E87A2C"
    elif value >= 60:
        return "#F5C242"
    elif value >= 40:
        return "#8B8D93"
    elif value >= 25:
        return "#5B9BD5"
    else:
        return "#2171B5"
    
# ===========================================================
# Stat Calculations
# ===========================================================

def calculate_stats_from_statcast(df):
    """
    Calculate batting stats from raw Statcast pitch data.
    Expects a DataFrame already filtered to the desired split.
    Groups by batter.
    """
    if df.empty:
        return pd.DataFrame()
    
    # Filter to at-bat ending events only
    ab_events = df[df["events"].notna()].copy()
    
    if ab_events.empty:
        return pd.DataFrame()
    
    # Define hit types
    hits = ["single", "double", "triple", "home_run"]
    ab_only_events = ["single", "double", "triple", "home_run", "strikeout",
                      "field_out", "grounded_into_double_play", "force_out",
                      "fielders_choice", "fielders_choice_out", "double_play",
                      "field_error", "strikeout_double_play", "triple_play"]
    
    # Need batter name - check if batter_name column exists
    if "batter_name" in ab_events.columns:
        name_col = "batter_name"
    elif "batter" in ab_events.columns:
        name_col = "batter"
    else:
        return pd.DataFrame()
    
    results = []
    for batter, group in ab_events.groupby(name_col):
        pa = len(group)
        ab_group = group[group["events"].isin(ab_only_events)]
        ab = len(ab_group)
        
        h = len(group[group["events"].isin(hits)])
        singles = len(group[group["events"] == "single"])
        doubles = len(group[group["events"] == "double"])
        triples = len(group[group["events"] == "triple"])
        hr = len(group[group["events"] == "home_run"])
        bb = len(group[group["events"].isin(["walk", "intent_walk"])])
        hbp = len(group[group["events"].isin(["hit_by_pitch"])])
        so = len(group[group["events"].str.contains("strikeout", na=False)])
        sf = len(group[group["events"].isin(["sac_fly"])])
        
        avg = h / ab if ab > 0 else 0
        obp = (h + bb + hbp) / (ab + bb + hbp + sf) if (ab + bb + hbp + sf) > 0 else 0
        slg = (singles + 2*doubles + 3*triples + 4*hr) / ab if ab > 0 else 0
        ops = obp + slg
        
        # Statcast metrics
        batted = group[group["launch_speed"].notna()]
        avg_ev = batted["launch_speed"].mean() if len(batted) > 0 else 0
        max_ev = batted["launch_speed"].max() if len(batted) > 0 else 0
        avg_la = batted["launch_angle"].mean() if len(batted) > 0 else 0
        def is_barrel(row):
            ev = row["launch_speed"]
            la = row["launch_angle"]
            if pd.isna(ev) or pd.isna(la) or ev < 98:
                return False
            if ev == 98:
                return 26 <= la <= 30
            extra = ev - 98
            la_min = max(8, 26 - (extra * 1.0))
            la_max = min(50, 30 + (extra * 1.2))
            return la_min <= la <= la_max
        barrel_count = len(batted[batted.apply(is_barrel, axis=1)]) if len(batted) > 0 else 0
        barrel_pct = barrel_count / len(batted) * 100 if len(batted) > 0 else 0
        hard_hit = len(batted[batted["launch_speed"] >= 95]) / len(batted) * 100 if len(batted) > 0 else 0
        
        results.append({
            name_col: batter,
            "PA": pa,
            "AB": ab,
            "H": h,
            "HR": hr,
            "BB": bb,
            "SO": so,
            "AVG": round(avg, 3),
            "OBP": round(obp, 3),
            "SLG": round(slg, 3),
            "OPS": round(ops, 3),
            "avg_ev": round(avg_ev, 1),
            "max_ev": round(max_ev, 1),
            "avg_la": round(avg_la, 1),
            "barrel_pct": round(barrel_pct, 1),
            "hard_hit_pct": round(hard_hit, 1),
        })
    
    return pd.DataFrame(results)

def build_split_summary(season=2025):
    """
    Pre-aggregate Statcast data by batter + pitcher hand + venue + month.
    Stores raw counts and sums so splits can be combined accurately.
    """
    ensure_data_dir()
    
    sc_path = os.path.join(DATA_DIR, f"statcast_{season}.parquet")
    lookup_path = os.path.join(DATA_DIR, f"batter_lookup_{season}.parquet")
    
    if not os.path.exists(sc_path):
        return pd.DataFrame()
    
    df = pd.read_parquet(sc_path)
    
    if os.path.exists(lookup_path):
        lookup = pd.read_parquet(lookup_path)
        df["batter"] = df["batter"].astype(int)
        lookup["batter"] = lookup["batter"].astype(int)
        df = df.merge(lookup, on="batter", how="left")
    
    if "batter_name" not in df.columns:
        return pd.DataFrame()
    
    df["game_date"] = pd.to_datetime(df["game_date"])
    df["month"] = df["game_date"].dt.month
    
    # Map months to labels
    month_label_map = {
        3: "March/April", 4: "March/April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September/October", 10: "September/October",
    }
    df["month_label"] = df["month"].map(month_label_map)
    
    # Venue from inning_topbot
    df["venue"] = df["inning_topbot"].map({"Bot": "Home", "Top": "Away"})
    
    # Only at-bat ending events
    ab_events = df[df["events"].notna()].copy()
    
    hits = ["single", "double", "triple", "home_run"]
    ab_only_events = ["single", "double", "triple", "home_run", "strikeout",
                      "field_out", "grounded_into_double_play", "force_out",
                      "fielders_choice", "fielders_choice_out", "double_play",
                      "field_error", "strikeout_double_play", "triple_play"]
    
    ab_events["is_hit"] = ab_events["events"].isin(hits).astype(int)
    ab_events["is_single"] = (ab_events["events"] == "single").astype(int)
    ab_events["is_double"] = (ab_events["events"] == "double").astype(int)
    ab_events["is_triple"] = (ab_events["events"] == "triple").astype(int)
    ab_events["is_hr"] = (ab_events["events"] == "home_run").astype(int)
    ab_events["is_bb"] = ab_events["events"].isin(["walk", "intent_walk"]).astype(int)
    ab_events["is_hbp"] = (ab_events["events"] == "hit_by_pitch").astype(int)
    ab_events["is_so"] = ab_events["events"].str.contains("strikeout", na=False).astype(int)
    ab_events["is_sf"] = (ab_events["events"] == "sac_fly").astype(int)
    ab_events["is_ab"] = ab_events["events"].isin(ab_only_events).astype(int)
    
    # Batted ball metrics
    ab_events["has_ev"] = ab_events["launch_speed"].notna().astype(int)
    ab_events["ev_value"] = ab_events["launch_speed"].fillna(0) * ab_events["has_ev"]
    ab_events["la_value"] = ab_events["launch_angle"].fillna(0) * ab_events["has_ev"]
    ab_events["max_ev_value"] = ab_events["launch_speed"].fillna(0)
    ab_events["is_hard_hit"] = ((ab_events["launch_speed"] >= 95) & ab_events["launch_speed"].notna()).astype(int)
    ab_events["is_barrel"] = (ab_events["launch_speed_angle"].fillna(0) == 6).astype(int)
    ab_events["is_bip"] = (ab_events["type"] == "X").astype(int)

    ab_events["ev_90_count"] = ((ab_events["launch_speed"] >= 90) & ab_events["launch_speed"].notna()).astype(int)
    
    ab_events["ev_90_count"] = ((ab_events["launch_speed"] >= 90) & ab_events["launch_speed"].notna()).astype(int)
    ab_events["ev_95_count"] = ((ab_events["launch_speed"] >= 95) & ab_events["launch_speed"].notna()).astype(int)
    ab_events["ev_100_count"] = ((ab_events["launch_speed"] >= 100) & ab_events["launch_speed"].notna()).astype(int)
    ab_events["ev_105_count"] = ((ab_events["launch_speed"] >= 105) & ab_events["launch_speed"].notna()).astype(int)
    ab_events["ev_110_count"] = ((ab_events["launch_speed"] >= 110) & ab_events["launch_speed"].notna()).astype(int)

    group_cols = ["batter_name", "p_throws", "venue", "month_label"]
    
    agg_dict = {
        "events": "count",  # PA
        "is_ab": "sum",
        "is_hit": "sum",
        "is_single": "sum",
        "is_double": "sum",
        "is_triple": "sum",
        "is_hr": "sum",
        "is_bb": "sum",
        "is_hbp": "sum",
        "is_so": "sum",
        "is_sf": "sum",
        "has_ev": "sum",
        "ev_value": "sum",
        "la_value": "sum",
        "max_ev_value": "max",
        "is_hard_hit": "sum",
        "is_barrel": "sum",
        "is_bip": "sum",
        "ev_90_count": "sum",
        "ev_95_count": "sum",
        "ev_100_count": "sum",
        "ev_105_count": "sum",
        "ev_110_count": "sum",
    }
    
    summary = ab_events.groupby(group_cols).agg(agg_dict).reset_index()
    
    summary = summary.rename(columns={
        "events": "PA",
        "is_ab": "AB",
        "is_hit": "H",
        "is_single": "1B",
        "is_double": "2B",
        "is_triple": "3B",
        "is_hr": "HR",
        "is_bb": "BB",
        "is_hbp": "HBP",
        "is_so": "SO",
        "is_sf": "SF",
        "has_ev": "batted_ball_count",
        "ev_value": "ev_sum",
        "la_value": "la_sum",
        "max_ev_value": "max_ev",
        "is_hard_hit": "hard_hit_count",
        "is_barrel": "barrel_count",
        "is_bip": "bip_count",
    })
    
    filepath = os.path.join(DATA_DIR, f"split_summary_{season}.parquet")
    summary.to_parquet(filepath, index=False)
    
    meta = _load_metadata()
    meta[f"split_summary_{season}_last_refresh"] = datetime.now().isoformat()
    meta[f"split_summary_{season}_rows"] = len(summary)
    _save_metadata(meta)
    
    return summary


def load_split_summary(season=2025):
    filepath = os.path.join(DATA_DIR, f"split_summary_{season}.parquet")
    if os.path.exists(filepath):
        return pd.read_parquet(filepath)
    return pd.DataFrame()


def combine_split_rows(df):
    """
    Combine multiple split rows into totals and calculate rate stats.
    Input should be pre-filtered split_summary rows.
    """
    if df.empty:
        return pd.Series()
    
    counting = df[["PA", "AB", "H", "1B", "2B", "3B", "HR", "BB", "HBP", "SO", "SF",
                    "batted_ball_count", "ev_sum", "la_sum", "hard_hit_count", "barrel_count", "bip_count",
                    "ev_90_count", "ev_95_count", "ev_100_count", "ev_105_count", "ev_110_count"]].sum()
    counting["max_ev"] = df["max_ev"].max()
    
    # Calculate rate stats
    ab = counting["AB"]
    pa = counting["PA"]
    h = counting["H"]
    bb = counting["BB"]
    hbp = counting["HBP"]
    sf = counting["SF"]
    bbc = counting["batted_ball_count"]
    
    counting["AVG"] = round(h / ab, 3) if ab > 0 else 0
    counting["OBP"] = round((h + bb + hbp) / (ab + bb + hbp + sf), 3) if (ab + bb + hbp + sf) > 0 else 0
    counting["SLG"] = round((counting["1B"] + 2*counting["2B"] + 3*counting["3B"] + 4*counting["HR"]) / ab, 3) if ab > 0 else 0
    counting["OPS"] = round(counting["OBP"] + counting["SLG"], 3)
    counting["avg_ev"] = round(counting["ev_sum"] / bbc, 1) if bbc > 0 else 0
    counting["avg_la"] = round(counting["la_sum"] / bbc, 1) if bbc > 0 else 0
    counting["max_ev"] = round(counting["max_ev"], 1)
    bip = counting["bip_count"]
    counting["barrel_pct"] = round(counting["barrel_count"] / bip * 100, 1) if bip > 0 else 0
    counting["hard_hit_pct"] = round(counting["hard_hit_count"] / bbc * 100, 1) if bbc > 0 else 0
    
    pa = counting["PA"]
    for thresh in [90, 95, 100, 105, 110]:
        col = f"ev_{thresh}_count"
        counting[f"ev_{thresh}_rate"] = round(counting[col] / pa * 100, 1) if pa > 0 else 0

    return counting

    
PITCH_TYPE_MAP = {
    "FF": "4-Seam Fastball",
    "SI": "Sinker",
    "FC": "Cutter",
    "SL": "Slider",
    "CH": "Changeup",
    "CU": "Curveball",
    "KC": "Knuckle Curve",
    "FS": "Splitter",
    "KN": "Knuckleball",
    "ST": "Sweeper",
    "SV": "Slurve",
    "CS": "Slow Curve",
    "EP": "Eephus",
    "FA": "Fastball",
    "SC": "Screwball",
    "PO": "Pitchout",
    "IN": "Intentional Ball",
    "AB": "Auto Ball",
}

ZONE_MAP = {
    1: "Top Left",
    2: "Top Middle",
    3: "Top Right",
    4: "Middle Left",
    5: "Middle Middle",
    6: "Middle Right",
    7: "Bottom Left",
    8: "Bottom Middle",
    9: "Bottom Right",
    11: "Out Top Left",
    12: "Out Top Right",
    13: "Out Bottom Left",
    14: "Out Bottom Right",
}