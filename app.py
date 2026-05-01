import streamlit as st
from utils.style import inject_custom_css, render_header
from utils.data_loader import data_is_fresh, get_data_status, _load_metadata
from utils.setup import settings_complete, render_setup_wizard
from config import DEFAULT_SEASON, AVAILABLE_SEASONS

st.set_page_config(
    page_title="Baseball Analytics",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()
render_header()

# --- First-run setup check ---
if not settings_complete():
    render_setup_wizard()
    st.stop()

# --- Auto-freshness check ---
season = DEFAULT_SEASON
if not data_is_fresh(season):
    status = get_data_status(season)
    missing = [k for k, v in status.items() if not v["exists"]]
    stale = [k for k, v in status.items() if v["exists"] and v["stale"]]

    if missing:
        st.warning(
            f"⚠️ **Missing data:** {len(missing)} dataset(s) not yet downloaded. "
            f"Head to **Data Manager** in the sidebar to download."
        )
    elif stale:
        st.info(
            f"🔄 **Data is stale:** {len(stale)} dataset(s) haven't been refreshed in 24+ hours. "
            f"Visit **Data Manager** to refresh."
        )
else:
    st.success("✅ All data is up to date.")

st.markdown("### Welcome")
st.markdown("""
Use the **sidebar** to navigate between features:

- **Player Comparison** — Compare up to 10 players with Baseball Savant-style percentile charts
- **Statcast Viewer** — Browse the full season of pitch-level Statcast data
- **Stats Browser** — Explore traditional batting and pitching stats
- **Data Manager** — Download, refresh, and monitor your local data
- **Fantasy** — Fantasy league standings, scoring, and trends
""")

st.markdown("---")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    <div class="stat-card">
        <div class="label">Data Source</div>
        <div class="value">Statcast</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="stat-card">
        <div class="label">Season</div>
        <div class="value">{season}</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    meta = _load_metadata()
    rows = meta.get(f"statcast_{season}_rows", "—")
    if isinstance(rows, int):
        rows = f"{rows:,}"
    st.markdown(f"""
    <div class="stat-card">
        <div class="label">Statcast Pitches</div>
        <div class="value">{rows}</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("""
<br>
<div style="color: #8B8D93; font-size: 0.85rem;">
    💡 <strong>First time?</strong> Head to <strong>Data Manager</strong> in the sidebar
    to download your season data. After that, everything runs locally.
</div>
""", unsafe_allow_html=True)

# --- Settings link in sidebar ---
with st.sidebar:
    st.markdown("---")
    if st.button("⚙️ App Settings", use_container_width=True):
        st.session_state["show_settings"] = True
        st.rerun()

# --- Settings panel ---
if st.session_state.get("show_settings", False):
    st.markdown("---")
    st.markdown("### ⚙️ App Settings")
    from utils.setup import load_settings, save_settings
    settings = load_settings()

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        new_client_id = st.text_input("Yahoo Client ID", value=settings.get("yahoo_client_id", ""), type="password", key="settings_cid")
        new_league_id = st.text_input("Yahoo League ID", value=settings.get("yahoo_league_id", ""), key="settings_lid")
        new_season = st.selectbox("Default Season", AVAILABLE_SEASONS, index=AVAILABLE_SEASONS.index(settings.get("default_season", DEFAULT_SEASON)), key="settings_season")
    with col_s2:
        new_client_secret = st.text_input("Yahoo Client Secret", value=settings.get("yahoo_client_secret", ""), type="password", key="settings_cs")

    if st.button("💾 Save Settings", type="primary", key="settings_save"):
        updated = {**settings, "yahoo_client_id": new_client_id, "yahoo_client_secret": new_client_secret,
                   "yahoo_league_id": new_league_id, "default_season": new_season, "setup_complete": True}
        save_settings(updated)
        st.session_state["show_settings"] = False
        st.success("Settings saved!")
        st.rerun()
    if st.button("Cancel", key="settings_cancel"):
        st.session_state["show_settings"] = False
        st.rerun()
