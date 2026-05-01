import streamlit as st

def inject_custom_css():
    """Inject dark mode baseball theme CSS."""
    st.markdown("""
    <style>
        /* === BASE OVERRIDES === */
        .stApp {
            background-color: #0E1117;
        }

        /* === HEADER BRANDING === */
        .baseball-header {
            background: linear-gradient(135deg, #1A1D23 0%, #0E1117 100%);
            border-bottom: 3px solid #E87A2C;
            padding: 1.5rem 2rem;
            margin-bottom: 1.5rem;
            border-radius: 0 0 12px 12px;
        }
        .baseball-header h1 {
            color: #FAFAFA;
            font-size: 2rem;
            margin: 0;
        }
        .baseball-header .accent {
            color: #E87A2C;
        }
        .baseball-header .subtitle {
            color: #8B8D93;
            font-size: 0.9rem;
            margin-top: 0.25rem;
        }

        /* === CARD CONTAINERS === */
        .stat-card {
            background: #1A1D23;
            border: 1px solid #2A2D35;
            border-radius: 10px;
            padding: 1.25rem;
            margin-bottom: 1rem;
            transition: border-color 0.2s;
        }
        .stat-card:hover {
            border-color: #E87A2C;
        }
        .stat-card .label {
            color: #8B8D93;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .stat-card .value {
            color: #FAFAFA;
            font-size: 1.8rem;
            font-weight: 700;
        }

        /* === PERCENTILE BAR === */
        .pct-bar-container {
            background: #2A2D35;
            border-radius: 6px;
            height: 28px;
            position: relative;
            margin: 4px 0;
            overflow: hidden;
        }
        .pct-bar-fill {
            height: 100%;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            padding-right: 8px;
            font-size: 0.75rem;
            font-weight: 700;
            color: #fff;
            transition: width 0.5s ease;
        }

        /* === PLAYER COMPARISON GRID === */
        .player-card {
            background: #1A1D23;
            border: 1px solid #2A2D35;
            border-radius: 12px;
            padding: 1.5rem;
            text-align: center;
        }
        .player-card .player-name {
            color: #FAFAFA;
            font-size: 1.1rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        .player-card .player-team {
            color: #E87A2C;
            font-size: 0.85rem;
        }

        /* === SIDEBAR STYLING === */
        [data-testid="stSidebar"] {
            background-color: #1A1D23;
            border-right: 1px solid #2A2D35;
        }
        [data-testid="stSidebar"] .stMarkdown h3 {
            color: #E87A2C;
        }

        /* === TABLE OVERRIDES === */
        .stDataFrame {
            border-radius: 8px;
            overflow: hidden;
        }

        /* === TAB STYLING === */
        .stTabs [data-baseweb="tab"] {
            color: #8B8D93;
        }
        .stTabs [aria-selected="true"] {
            color: #E87A2C !important;
            border-bottom-color: #E87A2C !important;
        }

        /* === METRIC CARDS === */
        [data-testid="stMetricValue"] {
            color: #E87A2C;
        }

        /* === MULTISELECT / SELECT === */
        .stMultiSelect [data-baseweb="tag"] {
            background-color: #E87A2C;
        }

        /* === HIDE STREAMLIT BRANDING === */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)


def render_header():
    """Render the branded app header."""
    st.markdown("""
    <div class="baseball-header">
        <h1>⚾ Baseball <span class="accent">Analytics</span></h1>
        <div class="subtitle">Statcast Data • Player Comparisons • Predictive Modeling</div>
    </div>
    """, unsafe_allow_html=True)