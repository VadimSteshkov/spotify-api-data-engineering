#!/usr/bin/env python3
"""
Main script:
- Authenticates to Spotify
- Pulls last 50 "recently played"
- Prints leaderboards (albums/tracks)
- Computes dominant artist from last 50 and fetches Top 10 tracks in a given market
- Produces:
    * spotify_recent_events -> per-play events (append-only)
    * artist_market_top_tracks -> Top 10 for dominant artist in selected market
"""

import os
import time
import json
import base64
from datetime import datetime, timezone

from dataclasses import asdict
from typing import List, Dict, Set, Tuple, Optional
from collections import Counter

from requests import get, post
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

from spotify_payloads import (
	build_events_from_recent_json,
)

from kafka_producer import KafkaJsonProducer

# ================== ENV / CONFIG ==================
# Load .env from the current working dir
load_dotenv(dotenv_path=".env", override=True)

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

# Accept both legacy and SPOTIFY_* names
CLIENT_ID      = _env_any("CLIENT_ID", "SPOTIFY_APP_CLIENT_ID", required=True)
CLIENT_SECRET  = _env_any("CLIENT_SECRET", "SPOTIFY_APP_CLIENT_SECRET", required=True)
USERNAME       = _env_any("USERNAME", "SPOTIFY_USERNAME", required=True)
REDIRECT_URI   = _env_any("REDIRECT_URI", "SPOTIFY_REDIRECT_URI", required=True)

MARKET_OVERRIDE = _env_any("MARKET_OVERRIDE", default=None)  # e.g. "AT" / "RO"
DEBUG = str(os.getenv("DEBUG", "false")).lower() == "true"

# Kafka config
KAFKA_ENABLED = str(os.getenv("KAFKA_ENABLED", "false")).lower() == "true"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

# Topics
TOPIC_RECENT_EVENTS = "spotify_recent_events"
TOPIC_ARTIST_MARKET_TOP = "artist_market_top_tracks"

SCOPE = "user-read-private user-read-email user-read-recently-played user-read-currently-playing user-top-read"
# ==================================================


# ---------------- Utilities ----------------
def debug(msg: str) -> None:
	if DEBUG:
		print(f"[DEBUG] {msg}")

def _bearer_headers(token: str) -> Dict[str, str]:
	return {"Authorization": f"Bearer {token}"}

def _ms_to_mmss(ms: int) -> str:
	s = (ms or 0) // 1000
	m, s = divmod(s, 60)
	return f"{m:02d}:{s:02d}"


# ---------------- Auth ----------------
def get_app_token() -> str:
	"""Client Credentials flow – for public catalog endpoints."""
	auth_b64 = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
	r = post(
		"https://accounts.spotify.com/api/token",
		headers={
			"Authorization": f"Basic {auth_b64}",
			"Content-Type": "application/x-www-form-urlencoded",
		},
		data={"grant_type": "client_credentials"},
		timeout=30,
	)
	if r.status_code >= 400:
		print("[ERROR] App token fetch failed:", f"status={r.status_code}, body={r.text[:300]}")
	r.raise_for_status()
	return r.json()["access_token"]

def get_user_token() -> str:
	"""
	Authorization Code flow via SpotifyOAuth.
	Caches token in .cache-<USERNAME> so subsequent runs won't open a browser.
	"""
	auth = SpotifyOAuth(
		client_id=CLIENT_ID,
		client_secret=CLIENT_SECRET,
		redirect_uri=REDIRECT_URI,
		scope=SCOPE,
		cache_path=f".cache-{USERNAME}",
		open_browser=True,
		show_dialog=False,
	)
	token_info = auth.get_cached_token()
	if not token_info:
		token_info = auth.get_access_token(as_dict=True)
	if not token_info or "access_token" not in token_info:
		raise RuntimeError("Failed to obtain user token (SpotifyOAuth). Check .env and Redirect URI.")
	return token_info["access_token"]


# ---------------- Basic fetchers ----------------
def get_profile_and_market(user_token: str) -> Tuple[Dict, str]:
	"""Return user profile JSON and selected market (env override > profile.country > 'AT')."""
	r = get("https://api.spotify.com/v1/me", headers=_bearer_headers(user_token), timeout=30)
	r.raise_for_status()
	profile = r.json()
	market = MARKET_OVERRIDE or profile.get("country") or "AT"
	return profile, market

def get_recently_played(user_token: str, limit: int = 50) -> Dict:
	"""Return last N recently played (max 50)."""
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
def most_common_artist_id_from_recent(recent_json: Dict) -> Optional[str]:
	"""Return the most frequent artist ID from the 50 recently played items."""
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


# ---------------- Leaderboards (console pretty-print) ----------------
def compute_listening_stats(recent_json: Dict) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
	"""Return frequency + recency maps for albums and tracks."""
	album_stats: Dict[str, Dict] = {}
	track_stats: Dict[str, Dict] = {}

	items = recent_json.get("items", [])
	for idx, item in enumerate(items):
		track = item.get("track") or {}
		played_at = item.get("played_at")

		# Track stats
		tid = track.get("id")
		tname = track.get("name", "?")
		tartists = ", ".join(a.get("name", "?") for a in track.get("artists", []))
		if tid:
			s = track_stats.get(tid)
			if not s:
				track_stats[tid] = {
					"count": 1,
					"first_idx": idx,
					"latest_played_at": played_at,
					"track_name": tname,
					"artists": tartists,
				}
			else:
				s["count"] += 1
				if idx < s["first_idx"]:
					s["first_idx"] = idx
				s["latest_played_at"] = s["latest_played_at"] or played_at

		# Album stats
		album = track.get("album") or {}
		aid = album.get("id")
		aname = album.get("name", "?")
		aart = ", ".join(a.get("name", "?") for a in album.get("artists", []))
		if aid:
			sa = album_stats.get(aid)
			if not sa:
				album_stats[aid] = {
					"count": 1,
					"first_idx": idx,
					"latest_played_at": played_at,
					"album_name": aname,
					"artists": aart,
				}
			else:
				sa["count"] += 1
				if idx < sa["first_idx"]:
					sa["first_idx"] = idx
				sa["latest_played_at"] = sa["latest_played_at"] or played_at

	return album_stats, track_stats

def _sorted_leaderboard(entries: Dict[str, Dict]) -> List[Tuple[str, Dict]]:
	"""Sort by (count desc, first_idx asc, name asc)."""
	return sorted(
		entries.items(),
		key=lambda kv: (
			-kv[1].get("count", 0),
			kv[1].get("first_idx", 1_000_000),
			kv[1].get("album_name", kv[1].get("track_name", "")).lower(),
		),
	)

def print_album_leaderboard(recent_json: Dict, limit: int = 10) -> None:
	album_stats, _ = compute_listening_stats(recent_json)
	rows = _sorted_leaderboard(album_stats)[:limit]
	print("\n=== Album leaderboard (last 50 plays) ===")
	if not rows:
		print("No data.")
		return
	for rank, (_aid, s) in enumerate(rows, start=1):
		print(f"{rank:02d}. {s['album_name']} — {s['artists']}  | plays={s['count']}  | latest={s['latest_played_at']}")

def print_track_leaderboard(recent_json: Dict, limit: int = 10) -> None:
	_, track_stats = compute_listening_stats(recent_json)
	rows = _sorted_leaderboard(track_stats)[:limit]
	print("\n=== Track leaderboard (last 50 plays) ===")
	if not rows:
		print("No data.")
		return
	for rank, (_tid, s) in enumerate(rows, start=1):
		print(f"{rank:02d}. {s['track_name']} — {s['artists']}  | plays={s['count']}  | latest={s['latest_played_at']}")


# ---------------- Debug helpers ----------------
def debug_print_top_artists_from_recent(recent_json: Dict, top_n: int = 5, app_token: Optional[str] = None) -> None:
	"""Print the most frequent artist IDs from the 'recently played' list."""
	if not DEBUG:
		return
	ids: List[str] = []
	for item in recent_json.get("items", []):
		track = item.get("track") or {}
		for a in (track.get("artists") or []):
			if a.get("id"):
				ids.append(a["id"])
	counts = Counter(ids).most_common(top_n)
	print("[DEBUG] Top artists in recently played:")
	token = app_token or get_app_token()
	for aid, c in counts:
		aj = get(f"https://api.spotify.com/v1/artists/{aid}", headers=_bearer_headers(token), timeout=30).json()
		print(f"  - {aj.get('name','?')} ({aid}): {c}")

def debug_print_identity(user_token: str) -> None:
	"""Print the authenticated user's profile (id, display name, email, country)."""
	if not DEBUG:
		return
	r = get("https://api.spotify.com/v1/me", headers=_bearer_headers(user_token), timeout=30)
	if r.ok:
		p = r.json()
		print(f"[DEBUG] Profile: id={p.get('id')} display_name={p.get('display_name')} email={p.get('email')} country={p.get('country')}")

def debug_print_currently_playing(user_token: str) -> None:
	"""Print the currently playing track, if any (204 means nothing playing)."""
	if not DEBUG:
		return
	r = get("https://api.spotify.com/v1/me/player/currently-playing", headers=_bearer_headers(user_token), timeout=30)
	if r.status_code == 204:
		print("[DEBUG] Currently playing: nothing (204)")
		return
	if r.ok:
		js = r.json()
		item = js.get("item") or {}
		name = item.get("name")
		artists = ", ".join(a.get("name","?") for a in item.get("artists", []))
		prog = (js.get("progress_ms") or 0) // 1000
		print(f"[DEBUG] Now playing: {name} — {artists} (progress {prog}s, is_playing={js.get('is_playing')})")
	else:
		print(f"[DEBUG] Currently playing fetch failed: {r.status_code} {r.text}")


# ---------------- Main ----------------
def main():
	# Tokens & profile/market
	app_token = get_app_token()
	user_token = get_user_token()
	profile, market = get_profile_and_market(user_token)
	print(f"[INFO] Using market: {market}")

	# Recently played (50)
	recent = get_recently_played(user_token, limit=50)
	debug(f"Recently played count: {len(recent.get('items', []))}")
	if recent.get("items"):
		newest = recent["items"][0].get("played_at")
		if newest:
			debug(f"Most recent played_at: {newest}")

	# Build & produce per-play events (append-only plays)
	user_id = profile.get("id")
	country = profile.get("country")
	events = build_events_from_recent_json(recent, user_id=user_id, country=country, market_used=market)

	producer = KafkaJsonProducer()
	print(f"[DEBUG] Kafka enabled={producer.enabled} bootstrap={KAFKA_BOOTSTRAP}")
	if producer.enabled:
		ev_dicts = [asdict(e) for e in events]
		producer.send_many_json(TOPIC_RECENT_EVENTS, ev_dicts)
		producer.flush()
		print(f"[KAFKA] Sent {len(ev_dicts)} events to {TOPIC_RECENT_EVENTS}")

	# Console leaderboards
	print_album_leaderboard(recent, limit=10)
	print_track_leaderboard(recent, limit=10)

	# Debug (controlled by DEBUG env)
	debug_print_top_artists_from_recent(recent, top_n=5, app_token=app_token)
	debug_print_identity(user_token)
	debug_print_currently_playing(user_token)

	# Dominant artist -> Top 10 tracks in selected market
	artist_id = most_common_artist_id_from_recent(recent)
	if artist_id:
		artist_meta = get(f"https://api.spotify.com/v1/artists/{artist_id}",
			headers=_bearer_headers(app_token), timeout=30).json()
		artist_name = artist_meta.get("name", "?")
		print(f"[INFO] Dominant recent artist: {artist_name} (id={artist_id})")

		top_tracks = get_artist_top_tracks(app_token, artist_id, market)
		print(f"\n=== Top {min(10, len(top_tracks))} tracks for {artist_name} (market={market}) ===")
		for i, t in enumerate(top_tracks[:10], start=1):
			name = t.get("name", "?")
			artists = ", ".join(a.get("name", "?") for a in t.get("artists", []))
			dur = _ms_to_mmss(t.get("duration_ms", 0))
			print(f"{i:02d}. {name} — {artists} ({dur})")

		top10 = []
		for rank, t in enumerate(top_tracks[:10], start=1):
			top10.append({
				"rank": rank,
				"track_id": t.get("id"),
				"track_name": t.get("name"),
				"duration_ms": t.get("duration_ms"),
				"album_id": (t.get("album") or {}).get("id"),
				"album_name": (t.get("album") or {}).get("name"),
				"artists": [a.get("name") for a in (t.get("artists") or [])],
			})

		top_doc = {
			"event_version": "1.0",
			"event_type": "artist_market_top_tracks",
			"generated_at": datetime.now(timezone.utc).isoformat(),
			"user_id": user_id,
			"country": country,
			"market": market,
			"artist_id": artist_id,
			"artist_name": artist_name,
			"tracks": top10
		}

		if producer.enabled:
			producer.send_str(TOPIC_ARTIST_MARKET_TOP, json.dumps(top_doc))
			producer.flush()
			print(f"[KAFKA] Sent artist market top tracks to {TOPIC_ARTIST_MARKET_TOP}")
	else:
		print("\nNo dominant artist found in your recent plays; skipping market Top 10.")

	print(f"[MONGO] Inserted payloads at {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
	main()

