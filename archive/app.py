import streamlit as st
from utils.style import inject_custom_css, render_header
from utils.data_loader import data_is_fresh, get_data_status, _load_metadata

st.set_page_config(
    page_title="Baseball Analytics",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_custom_css()
render_header()

# --- Auto-freshness check ---
season = 2025
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
- **Correlations** — Analyze relationships between stats and run predictions
- **Data Manager** — Download, refresh, and monitor your local data
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