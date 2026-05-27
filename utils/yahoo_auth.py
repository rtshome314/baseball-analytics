"""
yahoo_auth.py
Handles Yahoo OAuth2 authentication flow for local Streamlit app.
Stores tokens in a local file so you don't have to re-auth every time.
"""

import os
import json
import time
import requests
from urllib.parse import urlencode, urlparse, parse_qs
import streamlit as st

TOKEN_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".yahoo_token.json")

YAHOO_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"


def _load_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return None


def _save_token(token_data):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)


def _token_is_expired(token_data):
    expires_at = token_data.get("expires_at", 0)
    return time.time() > expires_at - 60  # 60s buffer


def _refresh_token(token_data, client_id, client_secret):
    resp = requests.post(
        YAHOO_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": token_data["refresh_token"],
            "redirect_uri": "https://localhost",
        },
        auth=(client_id, client_secret),
    )
    if resp.status_code == 200:
        new_token = resp.json()
        new_token["expires_at"] = time.time() + new_token.get("expires_in", 3600)
        # Preserve refresh token if not returned
        if "refresh_token" not in new_token:
            new_token["refresh_token"] = token_data["refresh_token"]
        _save_token(new_token)
        return new_token
    else:
        # Refresh failed — delete the bad token so the app prompts re-auth cleanly
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        return None


def get_auth_url(client_id):
    params = {
        "client_id": client_id,
        "redirect_uri": "https://localhost",
        "response_type": "code",
        "scope": "openid fspt-r",
    }
    return f"{YAHOO_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_token(code, client_id, client_secret):
    resp = requests.post(
        YAHOO_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://localhost",
        },
        auth=(client_id, client_secret),
    )
    if resp.status_code == 200:
        token_data = resp.json()
        token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)
        _save_token(token_data)
        return token_data
    else:
        st.error(f"Token exchange failed: {resp.text}")
        return None


def get_valid_token(client_id, client_secret):
    """
    Returns a valid access token, refreshing if needed.
    Returns None if not authenticated yet.
    """
    token_data = _load_token()
    if not token_data:
        return None

    if _token_is_expired(token_data):
        token_data = _refresh_token(token_data, client_id, client_secret)

    return token_data.get("access_token") if token_data else None


def render_auth_flow(client_id, client_secret):
    """
    Renders the OAuth flow UI in Streamlit.
    Returns True if authenticated, False otherwise.
    """
    token = get_valid_token(client_id, client_secret)
    if token:
        return True

    # Check if we just had a refresh failure (token file gone but session flag set)
    if not os.path.exists(TOKEN_FILE):
        if st.session_state.get("_yahoo_was_authed"):
            st.warning("⚠️ Your Yahoo session expired and could not be refreshed. Please reconnect below.")
            st.session_state.pop("_yahoo_was_authed", None)
        else:
            st.warning("⚠️ You need to connect your Yahoo account first.")
    else:
        st.warning("⚠️ You need to connect your Yahoo account first.")

    auth_url = get_auth_url(client_id)
    st.markdown(f"**Step 1:** [Click here to authorize with Yahoo]({auth_url})")
    st.markdown("**Step 2:** Yahoo will redirect to a localhost URL that won't load — that's expected. Copy the full URL from your browser's address bar and paste it below.")

    callback_url = st.text_input("Paste the full redirect URL here:")

    if callback_url:
        try:
            parsed = urlparse(callback_url)
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            if code:
                token_data = exchange_code_for_token(code, client_id, client_secret)
                if token_data:
                    st.session_state["_yahoo_was_authed"] = True
                    st.success("✅ Successfully connected to Yahoo!")
                    st.rerun()
            else:
                st.error("Could not find authorization code in URL. Make sure you copied the full URL.")
        except Exception as e:
            st.error(f"Error parsing URL: {e}")

    return False


def logout():
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
