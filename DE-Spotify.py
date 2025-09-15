import os
import json
import time
import base64
from typing import List, Dict, Set, Tuple, Optional
from collections import Counter

from requests import get, post
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import spotipy.util as util

# ================== ENV / CONFIG ==================
load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
USERNAME = os.getenv("USERNAME")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# Optional market override; if set, it will be used instead of the profile country
MARKET_OVERRIDE = os.getenv("MARKET_OVERRIDE")

# Scope needed for /v1/me/* endpoints
SCOPE = "user-read-private user-read-email user-read-recently-played user-read-currently-playing user-top-read"
# ==================================================


# ---------------- Utilities ----------------
def _bearer_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

def _ms_to_mmss(ms: int) -> str:
    s = (ms or 0) // 1000
    m, s = divmod(s, 60)
    return f"{m:02d}:{s:02d}"

def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"Missing environment variable: {name} (check your .env)")
    return val


# ---------------- Auth ----------------
def get_app_token() -> str:
    """Client Credentials flow – for public catalog endpoints."""
    client_id = _require_env("CLIENT_ID")
    client_secret = _require_env("CLIENT_SECRET")

    auth_b64 = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    r = post(
        "https://accounts.spotify.com/api/token",
        headers={
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"grant_type": "client_credentials"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]

def get_user_token() -> str:
    """
    Authorization Code flow – required for /v1/me/* endpoints.
    Spotipy caches a refresh token in `.cache-<USERNAME>` so subsequent runs shouldn't prompt.
    """
    _require_env("CLIENT_ID"); _require_env("CLIENT_SECRET")
    username = _require_env("USERNAME"); redirect_uri = _require_env("REDIRECT_URI")

    # Initialize Spotipy (harmless no-op here; keeps imports consistent)
    _ = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    )
    token = util.prompt_for_user_token(
        username,
        SCOPE,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=redirect_uri,
    )
    if not token:
        raise RuntimeError("Failed to obtain user token. Check .env values and redirect URI.")
    return token


# ---------------- Basic fetchers ----------------
def get_profile_and_market(user_token: str) -> Tuple[Dict, str]:
    """
    Return user profile JSON and selected market.
    Priority: MARKET_OVERRIDE (.env) > profile['country'] > 'AT'
    """
    r = get("https://api.spotify.com/v1/me", headers=_bearer_headers(user_token), timeout=30)
    r.raise_for_status()
    profile = r.json()
    market = MARKET_OVERRIDE or profile.get("country") or "AT"
    return profile, market

def get_recently_played(user_token: str, limit: int = 50) -> Dict:
    r = get(
        "https://api.spotify.com/v1/me/player/recently-played",
        headers=_bearer_headers(user_token),
        params={"limit": min(limit, 50)},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

def get_album_meta(app_token: str, album_id: str) -> Dict:
    r = get(f"https://api.spotify.com/v1/albums/{album_id}", headers=_bearer_headers(app_token), timeout=30)
    r.raise_for_status()
    return r.json()

def get_album_tracks(app_token: str, album_id: str) -> List[Dict]:
    """Fetch full tracklist with pagination if needed."""
    tracks: List[Dict] = []
    url = f"https://api.spotify.com/v1/albums/{album_id}/tracks"
    params = {"limit": 50, "offset": 0}
    while True:
        r = get(url, headers=_bearer_headers(app_token), params=params, timeout=30)
        r.raise_for_status()
        page = r.json()
        items = page.get("items", [])
        tracks.extend(items)
        if page.get("next"):
            params["offset"] += params["limit"]
            time.sleep(0.05)
        else:
            break
    return tracks

def get_artist_top_tracks(app_token: str, artist_id: str, market: str) -> List[Dict]:
    r = get(
        f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks",
        headers=_bearer_headers(app_token),
        params={"market": market},
        timeout=30,
    )
    r.raise_for_status()
    return r.json().get("tracks", [])


# ---------------- Derivations from "recently played" ----------------
def collect_recent_album_ids(recent_json: Dict, max_unique: int = 10) -> List[str]:
    """Extract up to `max_unique` distinct album IDs from recently played items."""
    seen: Set[str] = set()
    ordered: List[str] = []
    for item in recent_json.get("items", []):
        track = item.get("track") or {}
        album_id = (track.get("album") or {}).get("id")
        if album_id and album_id not in seen:
            seen.add(album_id)
            ordered.append(album_id)
        if len(ordered) >= max_unique:
            break
    return ordered

def most_common_artist_id_from_recent(recent_json: Dict) -> Optional[str]:
    """Return the most frequent artist ID from recently played items."""
    ids: List[str] = []
    for item in recent_json.get("items", []):
        track = item.get("track") or {}
        for a in (track.get("artists") or []):
            if a.get("id"):
                ids.append(a["id"])
    if not ids:
        return None
    cnt = Counter(ids).most_common(1)
    return cnt[0][0] if cnt else None


# ---------------- Printers (US1 & US2) ----------------
def print_tracklists_for_albums(app_token: str, album_ids: List[str]) -> None:
    """US1: print ordered tracklist + total length for each album id."""
    if not album_ids:
        print("No albums to print.")
        return

    for idx, album_id in enumerate(album_ids, start=1):
        meta = get_album_meta(app_token, album_id)
        album_name = meta.get("name", "Unknown album")
        artists = ", ".join(a.get("name", "Unknown artist") for a in meta.get("artists", []))
        release = meta.get("release_date", "Unknown date")
        print(f"\n=== Album #{idx}: {album_name} — {artists} (release: {release}) ===")

        tracks = get_album_tracks(app_token, album_id)
        if not tracks:
            print("No tracks returned for this album.")
            continue

        total_ms = 0
        for i, t in enumerate(tracks, start=1):
            name = t.get("name", "Unknown track")
            dur = t.get("duration_ms", 0)
            total_ms += dur
            print(f"{i:02d}. {name} ({_ms_to_mmss(dur)})")

        print(f"--- Total album length: {_ms_to_mmss(total_ms)} ---")

def print_top_tracks_for_artist(app_token: str, artist_id: str, market: str, limit: int = 10) -> None:
    """US2: print top tracks for a given artist id in a market."""
    tracks = get_artist_top_tracks(app_token, artist_id, market)
    if not tracks:
        print("No top tracks found for that artist.")
        return

    # Fetch artist name for clarity
    a = get(
        f"https://api.spotify.com/v1/artists/{artist_id}",
        headers=_bearer_headers(app_token),
        timeout=30
    ).json()
    artist_name = a.get("name", "?")

    print(f"\n=== Top {min(limit, len(tracks))} tracks for {artist_name} (market={market}) ===")
    for i, t in enumerate(tracks[:limit], start=1):
        name = t.get("name", "?")
        artists = ", ".join(a.get("name", "?") for a in t.get("artists", []))
        dur = _ms_to_mmss(t.get("duration_ms", 0))
        print(f"{i:02d}. {name} — {artists} ({dur})")


# ---------------- Main (no CLI prompts after first login) ----------------
def main():
    # 1) Tokens
    app_token = get_app_token()
    user_token = get_user_token()

    # 2) Profile + market
    _, market = get_profile_and_market(user_token)
    print(f"[INFO] Using market: {market}")

    # 3) Pull recent plays once
    recent = get_recently_played(user_token, limit=50)

    # 4) US1
    album_ids = collect_recent_album_ids(recent, max_unique=10)
    print_tracklists_for_albums(app_token, album_ids)

    # 5) US2
    artist_id = most_common_artist_id_from_recent(recent)
    if artist_id:
        # Log the dominant artist for visibility
        a = get(
            f"https://api.spotify.com/v1/artists/{artist_id}",
            headers=_bearer_headers(app_token),
            timeout=30
        ).json()
        print(f"[INFO] Dominant recent artist: {a.get('name','?')} (id={artist_id})")

        print_top_tracks_for_artist(app_token, artist_id, market=market, limit=10)
    else:
        print("\nNo dominant artist found in your recent plays; skipping US2.")


if __name__ == "__main__":
    main()

