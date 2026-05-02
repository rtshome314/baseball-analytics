"""
setup.py
Handles first-run setup and user settings for the Baseball Analytics app.
Settings are stored in data/user_settings.json so each user can have their own.
On Streamlit Cloud, settings are read from Streamlit Secrets.
"""

import os
import json
import streamlit as st

SETTINGS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "user_settings.json"
)

DEFAULTS = {
    "yahoo_client_id": "",
    "yahoo_client_secret": "",
    "yahoo_league_id": "",
    "yahoo_redirect_uri": "https://localhost",
    "default_season": 2026,
    "available_seasons": [2026, 2025, 2024, 2023],
    "setup_complete": False,
}


def load_settings():
    """Load user settings from file, falling back to defaults."""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            stored = json.load(f)
        settings = {**DEFAULTS, **stored}
        return settings
    return dict(DEFAULTS)


def save_settings(settings):
    """Save user settings to file."""
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


def settings_complete(settings=None):
    """Check if required settings are filled in."""
    # Check Streamlit Secrets first (cloud deployment)
    try:
        if (st.secrets.get("YAHOO_CLIENT_ID") and
            st.secrets.get("YAHOO_CLIENT_SECRET") and
            st.secrets.get("YAHOO_LEAGUE_ID")):
            return True
    except:
        pass

    # Fall back to checking user_settings.json (local deployment)
    if settings is None:
        settings = load_settings()
    return (
        settings.get("setup_complete", False) and
        settings.get("yahoo_client_id", "") != "" and
        settings.get("yahoo_client_secret", "") != "" and
        settings.get("yahoo_league_id", "") != ""
    )


def get_setting(key, fallback=None):
    """Get a single setting value."""
    settings = load_settings()
    return settings.get(key, fallback)


def render_setup_wizard():
    """
    Render the first-run setup wizard.
    Returns True if setup is complete, False otherwise.
    """
    settings = load_settings()

    st.markdown("## ⚾ Baseball Analytics — Setup")
    st.markdown("Welcome! Let's get your app configured. This only needs to be done once.")

    st.markdown("---")

    # Step 1: Yahoo Developer Credentials
    st.markdown("### Step 1: Yahoo Developer Credentials")
    st.markdown("""
    You need a free Yahoo Developer account to connect to your fantasy league.
    
    1. Go to **[developer.yahoo.com/apps/create](https://developer.yahoo.com/apps/create)**
    2. Sign in with your Yahoo account
    3. Fill in any app name (e.g. "Baseball Analytics")
    4. Set Redirect URI to: `https://localhost`
    5. Check **Fantasy Sports → Read**
    6. Click **Create App** and copy your Client ID and Client Secret below
    """)

    col1, col2 = st.columns(2)
    with col1:
        client_id = st.text_input(
            "Client ID (Consumer Key)",
            value=settings.get("yahoo_client_id", ""),
            type="password",
            key="setup_client_id"
        )
    with col2:
        client_secret = st.text_input(
            "Client Secret (Consumer Secret)",
            value=settings.get("yahoo_client_secret", ""),
            type="password",
            key="setup_client_secret"
        )

    st.markdown("### Step 2: Your Fantasy League")
    league_id = st.text_input(
        "Yahoo Fantasy League ID",
        value=settings.get("yahoo_league_id", ""),
        placeholder="e.g. 123456",
        help="Find this in your league URL: football.fantasysports.yahoo.com/baseball/XXXXXX",
        key="setup_league_id"
    )

    st.markdown("### Step 3: Season Settings")
    col3, col4 = st.columns(2)
    with col3:
        default_season = st.selectbox(
            "Current Season",
            [2026, 2025, 2024, 2023],
            index=0,
            key="setup_season"
        )
    with col4:
        available_seasons = st.multiselect(
            "Available Seasons",
            [2026, 2025, 2024, 2023],
            default=settings.get("available_seasons", [2026, 2025, 2024, 2023]),
            key="setup_available_seasons"
        )

    st.markdown("---")

    if st.button("✅ Save Settings & Continue", type="primary", use_container_width=True):
        if not client_id or not client_secret or not league_id:
            st.error("Please fill in all required fields (Client ID, Client Secret, League ID).")
        else:
            new_settings = {
                "yahoo_client_id": client_id,
                "yahoo_client_secret": client_secret,
                "yahoo_league_id": league_id,
                "yahoo_redirect_uri": "https://localhost",
                "default_season": default_season,
                "available_seasons": sorted(available_seasons or [default_season], reverse=True),
                "setup_complete": True,
            }
            save_settings(new_settings)
            st.success("✅ Settings saved! Restarting...")
            st.rerun()

    return False