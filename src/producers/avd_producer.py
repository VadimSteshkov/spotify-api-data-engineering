# tabs
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Docker-friendly Spotify Producer (headless OAuth) — POLLED EVERY 60s.

What it does each cycle:
- Auth (user + app)
- Fetch last 50 "recently played"
- Build per-play events and send to Kafka
- Detect dominant artist and send "Top 10 tracks in market"
Then sleeps SLEEP_SECS (default 60) and repeats.

Notes:
- Exit cleanly on SIGINT/SIGTERM (Ctrl+C / docker stop)
- Keep KAFKA_BOOTSTRAP as service name inside Docker (kafka:19092)
"""

import os
import time
import json
import base64
import signal
from datetime import datetime, timezone
from dataclasses import asdict
from typing import List, Dict, Tuple, Optional
from collections import Counter

from requests import get, post
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# --- local libs ---
from lib.spotify_payloads import build_events_from_recent_json

# --- Kafka producer (safe import) ---
try:
	from lib.kafka_producer import KafkaJsonProducer
except ImportError:
	print("[WARNING] Could not import KafkaJsonProducer. Kafka operations will be disabled.")
	class KafkaJsonProducer:
		def __init__(self): self.enabled = False
		def send_many_json(self, topic, messages): pass
		def send_str(self, topic, message): pass
		def flush(self): pass


# ================== ENV / CONFIG ==================
# Load .env from CWD (but do NOT override env injected by Docker)
load_dotenv(dotenv_path=".env", override=False)

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

# Accept both plain and SPOTIPY_* names
CLIENT_ID		= _env_any("CLIENT_ID", "SPOTIPY_CLIENT_ID", required=True)
CLIENT_SECRET	= _env_any("CLIENT_SECRET", "SPOTIPY_CLIENT_SECRET", required=True)
USERNAME		= _env_any("USERNAME", "SPOTIFY_USERNAME", required=True)
REDIRECT_URI	= _env_any("REDIRECT_URI", "SPOTIPY_REDIRECT_URI", required=True)

# Non-interactive refresh token (recommended in Docker)
# NOTE: Support both legacy and standard env names; first non-empty wins.
REFRESH_TOKEN_SAVED = _env_any("SPOTIPY_REFRESH_TOKEN_SAVED", "SPOTIPY_REFRESH_TOKEN", default=None)

# Optional cache path (persisted via volume)
CACHE_PATH = os.getenv("SPOTIPY_CACHE", f".cache-{USERNAME}")

# Market override
MARKET_OVERRIDE = os.getenv("MARKET_OVERRIDE") or None

# Flags
DEBUG = str(os.getenv("DEBUG", "false")).lower() == "true"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

# Topics (derived from APP_PREFIX if available)
APP_PREFIX = os.getenv("APP_PREFIX", "avd").strip()
TOPIC_RECENT_EVENTS = "avd_recent_events"
TOPIC_ARTIST_MARKET_TOP = "avd_artist_market_top_tracks"

# Polling interval (seconds) — default 60
SLEEP_SECS = int(os.getenv("PRODUCER_POLL_SEC", "60"))

# Polling interval (seconds) — default 60
SLEEP_SECS = int(os.getenv("PRODUCER_POLL_SEC", "60"))

# Scopes required
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


# ---------------- Auth helpers ----------------
def get_app_token() -> str:
	"""Client Credentials flow — for public catalog endpoints (short-lived, safe to refresh per cycle)."""
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


# ---------------- Spotify fetchers ----------------
def get_profile_and_market(user_token: str) -> Tuple[Dict, str]:
	"""Return profile and chosen market (env override > profile.country > 'AT')."""
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

def get_artist_top_tracks(app_token: str, artist_id: str, market: str) -> List[Dict]:
	r = get(
		f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks",
		headers=_bearer_headers(app_token),
		params={"market": market},
		timeout=30,
	)
	r.raise_for_status()
	return r.json().get("tracks", [])


# ---------------- Derivations ----------------
def most_common_artist_id_from_recent(recent_json: Dict) -> Optional[str]:
	"""Return most frequent artist ID from last 50 items."""
	ids: List[str] = []
	for item in recent_json.get("items", []):
		track = item.get("track") or {}
		for a in (track.get("artists") or []):
			if a.get("id"):
				ids.append(a["id"])
	if not ids:
		return None
	return Counter(ids).most_common(1)[0][0]


# ---------------- Pretty prints ----------------
def print_album_leaderboard(recent_json: Dict, limit: int = 10) -> None:
	album_stats = {}
	items = recent_json.get("items", [])
	for idx, item in enumerate(items):
		track = item.get("track") or {}
		album = track.get("album") or {}
		aid = album.get("id")
		if not aid:
			continue
		entry = album_stats.setdefault(aid, {
			"count": 0,
			"first_idx": idx,
			"latest_played_at": item.get("played_at"),
			"album_name": album.get("name", "?"),
			"artists": ", ".join(a.get("name","?") for a in album.get("artists", [])),
		})
		entry["count"] += 1
		entry["first_idx"] = min(entry["first_idx"], idx)
		entry["latest_played_at"] = entry["latest_played_at"] or item.get("played_at")

	rows = sorted(
		album_stats.items(),
		key=lambda kv: (-kv[1]["count"], kv[1]["first_idx"], kv[1]["album_name"].lower()),
	)[:limit]

	print("\n=== Album leaderboard (last 50 plays) ===")
	for i, (_aid, s) in enumerate(rows, start=1):
		print(f"{i:02d}. {s['album_name']} — {s['artists']}\t| plays={s['count']}\t| latest={s['latest_played_at']}")

def print_track_leaderboard(recent_json: Dict, limit: int = 10) -> None:
	track_stats = {}
	items = recent_json.get("items", [])
	for idx, item in enumerate(items):
		track = item.get("track") or {}
		tid = track.get("id")
		if not tid:
			continue
		entry = track_stats.setdefault(tid, {
			"count": 0,
			"first_idx": idx,
			"latest_played_at": item.get("played_at"),
			"track_name": track.get("name","?"),
			"artists": ", ".join(a.get("name","?") for a in track.get("artists", [])),
		})
		entry["count"] += 1
		entry["first_idx"] = min(entry["first_idx"], idx)
		entry["latest_played_at"] = entry["latest_played_at"] or item.get("played_at")

	rows = sorted(
		track_stats.items(),
		key=lambda kv: (-kv[1]["count"], kv[1]["first_idx"], kv[1]["track_name"].lower()),
	)[:limit]

	print("\n=== Track leaderboard (last 50 plays) ===")
	for i, (_tid, s) in enumerate(rows, start=1):
		print(f"{i:02d}. {s['track_name']} — {s['artists']}\t| plays={s['count']}\t| latest={s['latest_played_at']}")


# ---------------- One cycle (fetch + produce) ----------------
def run_once() -> None:
	"""Run one full cycle: auth, fetch, build events, produce."""
	app_token = get_app_token()
	user_token = get_user_token()
	profile, market = get_profile_and_market(user_token)
	print(f"[INFO] Using market: {market}")

	recent = get_recently_played(user_token, limit=50)
	debug(f"Recently played count: {len(recent.get('items', []))}")
	if recent.get("items"):
		newest = recent["items"][0].get("played_at")
		if newest:
			debug(f"Most recent played_at: {newest}")

	# Build per-play events
	user_id = profile.get("id")
	country = profile.get("country")
	events = build_events_from_recent_json(recent, user_id=user_id, country=country, market_used=market)

	# Produce to Kafka (if available)
	producer = KafkaJsonProducer()
	print(f"[DEBUG] Kafka bootstrap={KAFKA_BOOTSTRAP} enabled={producer.enabled}")
	if producer.enabled:
		producer.send_many_json(TOPIC_RECENT_EVENTS, [asdict(e) for e in events])
		producer.flush()
		print(f"[KAFKA] Sent {len(events)} events -> {TOPIC_RECENT_EVENTS}")

	# Console leaderboards
	print_album_leaderboard(recent, limit=10)
	print_track_leaderboard(recent, limit=10)

	# Dominant artist -> Top 10 in market
	artist_id = most_common_artist_id_from_recent(recent)
	if artist_id:
		artist_meta = get(f"https://api.spotify.com/v1/artists/{artist_id}", headers=_bearer_headers(app_token), timeout=30).json()
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

		doc = {
			"event_version": "1.0",
			"event_type": f"{APP_PREFIX}_artist_market_top_tracks",
			"generated_at": datetime.now(timezone.utc).isoformat(),
			"user_id": user_id,
			"country": country,
			"market": market,
			"artist_id": artist_id,
			"artist_name": artist_name,
			"tracks": top10
		}
		if producer.enabled:
			producer.send_str(TOPIC_ARTIST_MARKET_TOP, json.dumps(doc))
			producer.flush()
			print(f"[KAFKA] Sent artist market top tracks -> {TOPIC_ARTIST_MARKET_TOP}")
	else:
		print("[INFO] No dominant artist found in recent plays; skipping Top 10 doc.")

	print(f"[MONGO] Inserted payloads at {datetime.now(timezone.utc).isoformat()}")


# ---------------- Main loop ----------------
_STOP = False

def _graceful_exit(signum, frame):
	"""Flip stop flag for a clean shutdown inside Docker."""
	global _STOP
	_STOP = True
	print(f"\n[INFO] Caught signal {signum}. Shutting down gracefully...")

def main() -> None:
	# Register signal handlers for clean exit
	try:
		signal.signal(signal.SIGINT, _graceful_exit)
		signal.signal(signal.SIGTERM, _graceful_exit)
	except Exception:
		# Some environments may not allow installing signal handlers
		pass

	print(f"[BOOT] {APP_PREFIX} producer polling every {SLEEP_SECS}s")
	while not _STOP:
		start = time.time()
		try:
			run_once()
		except Exception as e:
			# Never crash the container: log and continue
			print(f"[ERROR] Producer cycle failed: {e}")
		# Sleep the remaining of the interval (min 1s)
		elapsed = max(0.0, time.time() - start)
		nap = max(1.0, SLEEP_SECS - elapsed)
		for _ in range(int(nap)):
			if _STOP:
				break
			time.sleep(1)


if __name__ == "__main__":
	main()

