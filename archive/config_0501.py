"""
config.py
App configuration. User-specific settings (Yahoo credentials, league ID) are
stored in data/user_settings.json and override these defaults.
"""

import os
import json

# Default values — overridden by user_settings.json if it exists
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

YAHOO_CLIENT_ID = _user.get("yahoo_client_id") or "dj0yJmk9VU55TVRWQXluRUZkJmQ9WVdrOWMybFhNazlCVURZbWNHbzlNQT09JnM9Y29uc3VtZXJzZWNyZXQmc3Y9MCZ4PTIz"
YAHOO_CLIENT_SECRET = _user.get("yahoo_client_secret") or "4ca2008a604b2234f26b6630d489ab44b8b9c2d1"
YAHOO_LEAGUE_ID = _user.get("yahoo_league_id") or "123192"
YAHOO_REDIRECT_URI = _user.get("yahoo_redirect_uri", "https://localhost")

# Update this each season (or set via user settings)
DEFAULT_SEASON = _user.get("default_season", 2026)
AVAILABLE_SEASONS = _user.get("available_seasons", [2026, 2025, 2024, 2023])
