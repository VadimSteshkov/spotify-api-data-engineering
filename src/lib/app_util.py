import os
import time
import json
import base64
from datetime import datetime, timezone
from dataclasses import asdict
from typing import List, Dict, Tuple, Optional
from collections import Counter

import pandas as pd
from requests import get, post
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth



def _env_any(*keys: str, required: bool = False, default: Optional[str] = None) -> Optional[str]:
    """Return first non-empty env var among keys."""
    for k in keys:
        v = os.getenv(k)
        if v and str(v).strip():
            return v.strip()
    if required and default is None:
        keys_fmt = ", ".join(keys)
        raise RuntimeError(f"Missing environment variable (any of): {keys_fmt}. Check your .env")
    return default

def _require_env(name: str) -> str:
    """Return a required env var or raise."""
    v = os.getenv(name)
    if not v or not str(v).strip():
        raise RuntimeError(f"Missing environment variable: {name} (check your .env)")
    return v.strip()

REFRESH_TOKEN_SAVED = _env_any("SPOTIPY_REFRESH_TOKEN_SAVED", "SPOTIPY_REFRESH_TOKEN", default=None)

# Accept both plain and SPOTIPY_* names
CLIENT_ID		= _env_any("CLIENT_ID", "SPOTIPY_CLIENT_ID", required=True)
CLIENT_SECRET	= _env_any("CLIENT_SECRET", "SPOTIPY_CLIENT_SECRET", required=True)
USERNAME		= _env_any("USERNAME", "SPOTIFY_USERNAME", required=True)
REDIRECT_URI	= _env_any("REDIRECT_URI", "SPOTIPY_REDIRECT_URI", required=True)

# Non-interactive refresh token (recommended in Docker)
# NOTE: Support both legacy and standard env names; first non-empty wins.
# Scopes required
SCOPE = "user-read-private user-read-email user-read-recently-played user-read-currently-playing user-top-read"

DEBUG = str(os.getenv("DEBUG", "false")).lower() == "true"

# Optional cache path (persisted via volume)
CACHE_PATH = os.getenv("SPOTIPY_CACHE", f".cache-{USERNAME}")

def get_user_token() -> str:
    """
    Authorization Code flow via SpotifyOAuth.

    Docker strategy:
    1) Try refresh via SPOTIPY_REFRESH_TOKEN_SAVED / SPOTIPY_REFRESH_TOKEN (non-interactive)
    2) Else try cache file (SPOTIPY_CACHE or .cache-<USERNAME>)
    3) Else try interactive (will fail in Docker — use only outside Docker to obtain refresh_token)
    """
    auth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=SCOPE,
        cache_path=CACHE_PATH,
        open_browser=False,		# never open browser in Docker
        show_dialog=False,
    )

    token_info = None

    # 1) Try environment refresh token (best for Docker)
    if REFRESH_TOKEN_SAVED:
        debug("Attempting token refresh using SPOTIPY_REFRESH_TOKEN_SAVED/SPOTIPY_REFRESH_TOKEN...")
        try:
            token_info = auth.refresh_access_token(REFRESH_TOKEN_SAVED)
            if token_info and "access_token" in token_info:
                # Optional: persist refreshed token in cache for other tools
                try:
                    auth._save_token_info(token_info)
                except Exception:
                    pass
                print("[INFO] User token via saved Refresh Token (env) OK.")
                return token_info["access_token"]
        except Exception as e:
            print(f"[WARNING] Refresh via env failed: {e}. Falling back to cache/interactive.")
            token_info = None

    # 2) Try cached token
    if not token_info:
        debug(f"Attempting to load token from cache: {CACHE_PATH}")
        token_info = auth.get_cached_token()

    # 3) If nothing else, attempt interactive (will fail in Docker)
    if not token_info:
        print("[WARNING] No cache. Trying interactive login (will fail inside Docker). Use a helper locally to obtain refresh_token.")
        token_info = auth.get_access_token(as_dict=True)

    if not token_info or "access_token" not in token_info:
        raise RuntimeError("Failed to obtain user token. Ensure SPOTIPY_REFRESH_TOKEN is set for Docker, and REDIRECT_URI matches Spotify App settings.")
    return token_info["access_token"]

def debug(msg: str) -> None:
    if DEBUG:
        print(f"[DEBUG] {msg}")

def bearer_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

