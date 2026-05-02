"""
config.py
App configuration. User-specific settings (Yahoo credentials, league ID) are
stored in data/user_settings.json and override these defaults.
On Streamlit Cloud, credentials are read from Streamlit Secrets.
"""
import os
import json

# Default values — overridden by user_settings.json or Streamlit secrets
_DEFAULTS = {
    "yahoo_client_id": "",
    "yahoo_client_secret": "",
    "yahoo_league_id": "",
    "yahoo_redirect_uri": "https://localhost",
    "default_season": 2026,
    "available_seasons": [2026, 2025, 2024, 2023],
}

def _load_user_settings():
    settings_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "data", "user_settings.json"
    )
    if os.path.exists(settings_file):
        with open(settings_file, "r") as f:
            return json.load(f)
    return {}

_user = _load_user_settings()

def _get_secret(key, default=""):
    try:
        import streamlit as st
        return st.secrets[key]
    except:
        return _user.get(key.lower(), default)

YAHOO_CLIENT_ID = _get_secret("YAHOO_CLIENT_ID")
YAHOO_CLIENT_SECRET = _get_secret("YAHOO_CLIENT_SECRET")
YAHOO_LEAGUE_ID = _get_secret("YAHOO_LEAGUE_ID")
YAHOO_REDIRECT_URI = _user.get("yahoo_redirect_uri", "https://localhost")

# Update this each season (or set via user settings)
DEFAULT_SEASON = _user.get("default_season", 2026)
AVAILABLE_SEASONS = _user.get("available_seasons", [2026, 2025, 2024, 2023])