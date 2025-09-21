#!/usr/bin/env python3
"""
Main script:
- Authenticates to Spotify
- Pulls last 50 "recently played"
- Prints leaderboards (albums/tracks), album tracklists (US1),
  and top tracks for the dominant recent artist (US2)
- Builds JSON payloads and (optionally) produces them to Kafka
"""

import os
import time
import base64
from datetime import datetime, timezone

from dataclasses import asdict
from typing import List, Dict, Set, Tuple, Optional
from collections import Counter

from requests import get, post
from dotenv import load_dotenv, find_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth
import spotipy.util as util

from spotify_payloads import (
	build_events_from_recent_json,
	build_snapshot,
	TOPIC_RECENT_EVENTS,
	TOPIC_RECENT_SNAPSHOT,
)

from kafka_producer import KafkaJsonProducer

# ================== ENV / CONFIG ==================
# Load .env from either repo root or src/, whichever exists
load_dotenv(find_dotenv(), override=False)

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
	v = os.getenv(name)
	if not v or not str(v).strip():
		raise RuntimeError(f"Missing environment variable: {name} (check your .env)")
	return v.strip()

# Accept both legacy and SPOTIFY_* names so your team can use either style
CLIENT_ID      = _env_any("CLIENT_ID", "SPOTIFY_APP_CLIENT_ID", required=True)
CLIENT_SECRET  = _env_any("CLIENT_SECRET", "SPOTIFY_APP_CLIENT_SECRET", required=True)
USERNAME       = _env_any("USERNAME", "SPOTIFY_USERNAME", required=True)
REDIRECT_URI   = _env_any("REDIRECT_URI", "SPOTIFY_REDIRECT_URI", required=True)

MARKET_OVERRIDE = _env_any("MARKET_OVERRIDE", default=None)  # e.g. "AT" / "RO"
DEBUG = str(os.getenv("DEBUG", "false")).lower() == "true"

# Kafka config (optional)
KAFKA_ENABLED = str(os.getenv("KAFKA_ENABLED", "false")).lower() == "true"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_LINGER_MS = int(os.getenv("KAFKA_LINGER_MS", "50"))
KAFKA_BATCH_SIZE = int(os.getenv("KAFKA_BATCH_SIZE", "16384"))

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
		# Helpful diagnostics
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
		redirect_uri=REDIRECT_URI,     # must also be added in Spotify Dashboard
		scope=SCOPE,
		cache_path=f".cache-{USERNAME}",
		open_browser=False,            # prevents browser auto-opening if cache exists
		show_dialog=False,
	)

	# Try to load token from cache
	token_info = auth.get_cached_token()
	if not token_info:
		# If no cache exists, requests user login once; afterwards cache is reused
		token_info = auth.get_access_token(as_dict=True)

	if not token_info or "access_token" not in token_info:
		raise RuntimeError("Failed to obtain user token (SpotifyOAuth). Check .env and Redirect URI.")
	return token_info["access_token"]


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
	"""
	Extract up to `max_unique` distinct album IDs from recently played items (newest first).
	"""
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


# ---------------- Leaderboards from "recently played" ----------------
def compute_listening_stats(recent_json: Dict) -> Tuple[Dict[str, Dict], Dict[str, Dict]]:
	"""
	Build frequency and recency stats for albums and tracks from recently played.
	Returns:
	  album_stats: {album_id: {"count": int, "first_idx": int, "latest_played_at": str,
							   "album_name": str, "artists": str}}
	  track_stats: {track_id: {"count": int, "first_idx": int, "latest_played_at": str,
							   "track_name": str, "artists": str}}
	Notes:
	  - Items are newest-first.
	  - first_idx is the first index encountered (smaller == more recent).
	"""
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
				# Keep the most recent timestamp (items are newest-first)
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
	"""Sort: count desc, first_idx asc (more recent first), name asc as tiebreaker."""
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


# ---------------- Printers (US1 & US2) ----------------
def print_tracklists_for_albums(app_token: str, album_ids: List[str]) -> None:
	"""
	US1: print ordered tracklist + total duration for each album id.
	Albums come from the last 50 recently played items (distinct, most recent first, capped to 10 by default).
	"""
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
	"""US2: print top tracks for the dominant recent artist in the selected market."""
	tracks = get_artist_top_tracks(app_token, artist_id, market)
	if not tracks:
		print("No top tracks found for that artist.")
		return

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


# ---------------- Debug helpers ----------------
def debug_print_top_artists_from_recent(recent_json: Dict, top_n: int = 5, app_token: Optional[str] = None) -> None:
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
	if not DEBUG:
		return
	r = get("https://api.spotify.com/v1/me", headers=_bearer_headers(user_token), timeout=30)
	if r.ok:
		p = r.json()
		print(f"[DEBUG] Profile: id={p.get('id')} display_name={p.get('display_name')} email={p.get('email')} country={p.get('country')}")

def debug_print_currently_playing(user_token: str) -> None:
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
		prog = js.get("progress_ms", 0) // 1000
		print(f"[DEBUG] Now playing: {name} — {artists} (progress {prog}s, is_playing={js.get('is_playing')})")
	else:
		print(f"[DEBUG] Currently playing fetch failed: {r.status_code} {r.text}")


# ---------------- Main ----------------
def main():
	# Tokens
	app_token = get_app_token()
	user_token = get_user_token()

	# Profile + market
	profile, market = get_profile_and_market(user_token)
	print(f"[INFO] Using market: {market}")

	# Recently played (last 50)
	recent = get_recently_played(user_token, limit=50)
	debug(f"Recently played count: {len(recent.get('items', []))}")
	if recent.get("items"):
		newest = recent["items"][0].get("played_at")
		if newest:
			debug(f"Most recent played_at: {newest}")

	# Build JSON payloads
	user_id = profile.get("id")
	country = profile.get("country")
	events = build_events_from_recent_json(recent, user_id=user_id, country=country, market_used=market)
	snapshot = build_snapshot(recent, user_id=user_id, country=country, market_used=market)

	# Produce to Kafka if enabled
	producer = KafkaJsonProducer()
	print(f"[DEBUG] Kafka enabled={producer.enabled} bootstrap={KAFKA_BOOTSTRAP}")
	if producer.enabled:
		ev_dicts = [asdict(e) for e in events]  # dataclass -> dict
		producer.send_many_json(TOPIC_RECENT_EVENTS, ev_dicts)
		producer.send_str(TOPIC_RECENT_SNAPSHOT, snapshot.to_json())
		producer.flush()
		print(f"[KAFKA] Sent {len(events)} events to {TOPIC_RECENT_EVENTS} and 1 snapshot to {TOPIC_RECENT_SNAPSHOT}")

	# Leaderboards
	print_album_leaderboard(recent, limit=10)
	print_track_leaderboard(recent, limit=10)

	# US1 – album tracklists for up to 10 distinct recently-played albums
	album_ids = collect_recent_album_ids(recent, max_unique=10)
	print_tracklists_for_albums(app_token, album_ids)

	# Debug: most common artists in recent plays
	debug_print_top_artists_from_recent(recent, top_n=5, app_token=app_token)

	# US2 – top tracks for dominant recent artist in selected market
	artist_id = most_common_artist_id_from_recent(recent)
	if artist_id:
		a = get(
			f"https://api.spotify.com/v1/artists/{artist_id}",
			headers=_bearer_headers(app_token),
			timeout=30
		).json()
		print(f"[INFO] Dominant recent artist: {a.get('name','?')} (id={artist_id})")
		print_top_tracks_for_artist(app_token, artist_id, market=market, limit=10)
	else:
		print("\nNo dominant artist found in your recent plays; skipping US2.")

	# Debug identity and currently playing
	debug_print_identity(user_token)
	debug_print_currently_playing(user_token)

	# Always print a UTC timestamp to align with consumer logs
	print(f"[MONGO] Inserted payloads at {datetime.now(timezone.utc).isoformat()}")

if __name__ == "__main__":
	main()

