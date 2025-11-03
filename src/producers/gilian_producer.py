import json
import math
import os
import signal
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

import requests
from dotenv import load_dotenv

try:
	from lib.kafka_producer import KafkaJsonProducer
except ImportError:
	print("[WARNING] Could not import KafkaJsonProducer. Kafka disabled.")


	class KafkaJsonProducer:
		def __init__(self): self.enabled = False

		def send_str(self, topic, message): pass

		def flush(self): pass

load_dotenv(dotenv_path=".env", override=False)

CLIENT_ID = os.getenv("CLIENT_ID") or os.getenv("SPOTIPY_CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET") or os.getenv("SPOTIPY_CLIENT_SECRET")

RAPID_API_KEY = os.getenv("RAPID_API_KEY", "")
RAPID_HOST = "track-analysis.p.rapidapi.com"

RAPIDAPI_REQUESTS_PER_SECOND = float(os.getenv("RAPIDAPI_REQUESTS_PER_SECOND", "2.0"))
RAPIDAPI_RETRY_ATTEMPTS = int(os.getenv("RAPIDAPI_RETRY_ATTEMPTS", "3"))

APP_PREFIX = os.getenv("APP_PREFIX", "gilian").strip()
DEBUG = str(os.getenv("DEBUG", "false")).lower() == "true"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

TOPIC_GENRE_DANCEABILITY = f"{APP_PREFIX}_genre_danceability"
TOPIC_GENRE_BRIDGES = f"{APP_PREFIX}_genre_bridges"

GENRE_LIST = [
	"techno",
	"house",
	"dubstep",
	"rap",
	"classical",
	"latin",
	"salsa",
]

ANALYSIS_INTERVAL = int(os.getenv("ANALYSIS_INTERVAL", "3600"))

DEFAULT_BRIDGE_SOURCE = os.getenv("BRIDGE_SOURCE", "techno")
DEFAULT_BRIDGE_TARGET = os.getenv("BRIDGE_TARGET", "house")
CANDIDATES_PER_SIDE = 30
BRIDGE_TRACKS = 5


def debug(msg: str) -> None:
	if DEBUG:
		print(f"[DEBUG] {msg}")


_SPOTIFY_TOKEN = None
_SPOTIFY_TOKEN_EXP = 0


def get_spotify_token() -> str:
	global _SPOTIFY_TOKEN, _SPOTIFY_TOKEN_EXP

	now = time.time()
	if _SPOTIFY_TOKEN and now < _SPOTIFY_TOKEN_EXP - 60:
		return _SPOTIFY_TOKEN

	url = "https://accounts.spotify.com/api/token"
	data = {"grant_type": "client_credentials"}
	r = requests.post(
		url,
		data=data,
		auth=(CLIENT_ID, CLIENT_SECRET),
		timeout=30
	)
	r.raise_for_status()
	result = r.json()
	_SPOTIFY_TOKEN = result["access_token"]
	_SPOTIFY_TOKEN_EXP = now + result.get("expires_in", 3600)
	return _SPOTIFY_TOKEN


def sp_get(url: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
	token = get_spotify_token()
	headers = {"Authorization": f"Bearer {token}"}
	r = requests.get(url, headers=headers, params=params, timeout=30)
	r.raise_for_status()
	return r.json()


_RAPIDAPI_LAST_CALL = 0


def rapid_get_track_analysis(track_id: str, max_retries: int = None) -> Optional[Dict]:
	global _RAPIDAPI_LAST_CALL

	if max_retries is None:
		max_retries = RAPIDAPI_RETRY_ATTEMPTS

	min_interval = 1.0 / RAPIDAPI_REQUESTS_PER_SECOND

	for attempt in range(max_retries):
		try:

			now = time.time()
			elapsed = now - _RAPIDAPI_LAST_CALL
			if elapsed < min_interval:
				time.sleep(min_interval - elapsed)

			url = f"https://{RAPID_HOST}/pktx/spotify/{track_id}"
			headers = {
				"X-RapidAPI-Key": RAPID_API_KEY,
				"X-RapidAPI-Host": RAPID_HOST,
				"X-RapidAPI-Region": "EU",
				"Accept": "application/json",
			}

			r = requests.get(url, headers=headers, timeout=15)
			_RAPIDAPI_LAST_CALL = time.time()

			if r.status_code == 429:

				retry_after = 5 * (2 ** attempt) + 1
				if DEBUG:
					print(
						f"  [429] Rate limit hit for {track_id}, waiting {retry_after}s (attempt {attempt + 1}/{max_retries})")
				time.sleep(retry_after)
				continue

			if r.status_code != 200:
				debug(f"RapidAPI returned {r.status_code} for {track_id} | {url}")
				return None

			data = r.json()

			result = {
				"camelot": data.get("camelot") or data.get("harmonic_key") or data.get("key_camelot"),
				"key": data.get("key") or data.get("musical_key"),
				"mode": data.get("mode"),
				"tempo": data.get("tempo") or data.get("bpm"),
				"energy": _normalize_0_1(data.get("energy")),
				"danceability": _normalize_0_1(data.get("danceability")),
				"valence": _normalize_0_1(data.get("valence")),
				"loudness": data.get("loudness"),
				"speechiness": _normalize_0_1(data.get("speechiness")),
				"acousticness": _normalize_0_1(data.get("acousticness")),
				"instrumentalness": _normalize_0_1(data.get("instrumentalness")),
				"liveness": _normalize_0_1(data.get("liveness"))
			}

			return result

		except requests.exceptions.Timeout:
			debug(f"RapidAPI timeout for {track_id} (attempt {attempt + 1}/{max_retries})")
			if attempt < max_retries - 1:
				time.sleep(2)
				continue
			return None

		except Exception as e:
			debug(f"RapidAPI error for {track_id}: {e}")
			return None

	if DEBUG:
		print(f"  [FAIL] RapidAPI failed after {max_retries} attempts for {track_id}")
	return None


def _normalize_0_1(value) -> Optional[float]:
	if value is None:
		return None
	try:
		v = float(value)
		if v > 1.5:
			return v / 100.0
		return v
	except Exception:
		return None


def sanitize_for_kafka(data: Any) -> Any:
	if isinstance(data, dict):
		return {k: sanitize_for_kafka(v) for k, v in data.items()}
	elif isinstance(data, list):
		return [sanitize_for_kafka(item) for item in data]
	elif isinstance(data, float):
		if math.isnan(data) or math.isinf(data):
			return None
		return round(data, 6)
	elif isinstance(data, str):

		cleaned = data.replace('\x00', '').replace('\r', '').strip()
		return cleaned[:500] if len(cleaned) > 500 else cleaned
	else:
		return data


def safe_kafka_send(producer, topic: str, data: Dict) -> bool:
	if not producer.enabled:
		return False

	try:

		clean_data = sanitize_for_kafka(data)

		json_str = json.dumps(clean_data, ensure_ascii=False)

		if len(json_str) > 900000:
			print(f"[WARN] Message too large ({len(json_str)} bytes), skipping")
			return False

		producer.send_str(topic, json_str)
		producer.flush(timeout=5.0)
		return True

	except Exception as e:
		print(f"[ERROR] Kafka send failed: {e}")
		if DEBUG:
			import traceback
			traceback.print_exc()
		return False


def camelot_neighbors(tag: str) -> set:
	if not tag or len(tag) < 2:
		return set()
	try:
		num = int(tag[:-1])
		let = tag[-1].upper()
	except Exception:
		return set()

	nums = [(num - 2) % 12 + 1, num, (num) % 12 + 1]

	lets = {let, "A" if let == "B" else "B"}

	return {f"{n}{l}" for n in nums for l in lets}


def camelot_compatibility_score(c1: str, c2: str) -> float:
	if not c1 or not c2:
		return 0.0
	if c1 == c2:
		return 1.0
	if c2 in camelot_neighbors(c1):
		return 0.7

	neighbors_2 = set()
	for n in camelot_neighbors(c1):
		neighbors_2.update(camelot_neighbors(n))

	if c2 in neighbors_2:
		return 0.4

	return 0.1


def search_genre_playlist(genre: str, limit: int = 1) -> Optional[Dict]:
	try:
		data = sp_get(
			"https://api.spotify.com/v1/search",
			params={"q": genre, "type": "playlist", "limit": limit}
		)
		playlists = data.get("playlists", {}).get("items", [])
		if playlists:
			pl = playlists[0]
			return {
				"id": pl["id"],
				"name": pl["name"],
				"tracks_total": pl["tracks"]["total"]
			}
	except Exception as e:
		debug(f"Error searching playlist for {genre}: {e}")
	return None


def get_playlist_tracks(playlist_id: str, limit: int = 50) -> List[Dict]:
	try:
		data = sp_get(
			f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
			params={"limit": min(limit, 100), "fields": "items(track(id,name,artists))"}
		)
		tracks = []
		for item in data.get("items", []):
			track = item.get("track")
			if track and track.get("id"):
				tracks.append({
					"track_id": track["id"],
					"track_name": track["name"],
					"artists": [a["name"] for a in track.get("artists", [])]
				})
		return tracks
	except Exception as e:
		debug(f"Error getting playlist tracks: {e}")
		return []


def analyze_genre_danceability(genre: str, tracks_per_genre: int = 100) -> Dict:
	print(f"[ANALYSIS] Analyzing genre: {genre}")

	playlist = search_genre_playlist(genre)
	if not playlist:
		return {
			"genre": genre,
			"avg_danceability": None,
			"error": "No playlist found"
		}

	tracks = get_playlist_tracks(playlist["id"], limit=tracks_per_genre)
	if not tracks:
		return {
			"genre": genre,
			"avg_danceability": None,
			"error": "No tracks found"
		}

	danceability_vals = []
	energy_vals = []
	tempo_vals = []

	print(f"  → Fetching audio features for {len(tracks[:tracks_per_genre])} tracks...")
	successful = 0
	failed = 0

	for i, track in enumerate(tracks[:tracks_per_genre], 1):
		analysis = rapid_get_track_analysis(track["track_id"])
		if analysis and analysis.get("danceability") is not None:
			danceability_vals.append(analysis["danceability"])
			energy_vals.append(analysis.get("energy", 0))
			tempo_vals.append(analysis.get("tempo", 120))
			successful += 1
		else:
			failed += 1

		if i % 10 == 0:
			print(f"     Progress: {i}/{tracks_per_genre} tracks ({successful} successful, {failed} failed)")

	print(f"  → Completed: {successful} successful, {failed} failed")

	if not danceability_vals:
		return {
			"genre": genre,
			"avg_danceability": None,
			"error": "No audio features from RapidAPI"
		}

	result = {
		"genre": genre,
		"avg_danceability": sum(danceability_vals) / len(danceability_vals),
		"avg_energy": sum(energy_vals) / len(energy_vals),
		"avg_tempo": sum(tempo_vals) / len(tempo_vals),
		"track_count": len(danceability_vals),
		"playlist_name": playlist["name"],
		"data_source": "RapidAPI",
		"analyzed_at": datetime.now(timezone.utc).isoformat()
	}

	print(f"  → Danceability: {result['avg_danceability']:.3f}, Energy: {result['avg_energy']:.3f}")
	return result


def search_artists_by_genre(genre: str, limit: int = 20) -> List[str]:
	try:
		data = sp_get(
			"https://api.spotify.com/v1/search",
			params={"q": f'genre:"{genre}"', "type": "artist", "limit": min(50, limit)}
		)
		artists = data.get("artists", {}).get("items", [])
		return [a["id"] for a in artists if a.get("id")]
	except Exception as e:
		debug(f"Error searching artists for {genre}: {e}")
		return []


def get_artist_top_tracks(artist_id: str, market: str = "US") -> List[Dict]:
	try:
		data = sp_get(
			f"https://api.spotify.com/v1/artists/{artist_id}/top-tracks",
			params={"market": market}
		)
		tracks = []
		for t in data.get("tracks", [])[:5]:
			tracks.append({
				"track_id": t["id"],
				"track_name": t["name"],
				"artists": [a["name"] for a in t.get("artists", [])],
				"spotify_url": t.get("external_urls", {}).get("spotify", "")
			})
		return tracks
	except Exception as e:
		debug(f"Error getting artist top tracks: {e}")
		return []


def calculate_track_distance(f1: Dict, f2: Dict) -> float:
	diff_dance = (f1.get("danceability", 0.5) - f2.get("danceability", 0.5)) ** 2
	diff_energy = (f1.get("energy", 0.5) - f2.get("energy", 0.5)) ** 2
	diff_tempo = ((f1.get("tempo", 120) - f2.get("tempo", 120)) / 200) ** 2

	distance = math.sqrt(diff_dance + diff_energy + diff_tempo)

	if f1.get("camelot") and f2.get("camelot"):
		camelot_score = camelot_compatibility_score(f1["camelot"], f2["camelot"])

		distance = distance * (1.5 - camelot_score)

	return distance


def find_bridge_tracks(
	source_genre: str,
	target_genre: str,
	candidates_per_side: int = 30,
	bridge_length: int = 5
) -> List[Dict]:
	print(f"[BRIDGE] Building bridge from {source_genre} to {target_genre}")

	source_artists = search_artists_by_genre(source_genre, limit=10)
	target_artists = search_artists_by_genre(target_genre, limit=10)

	source_tracks = []
	target_tracks = []

	for artist_id in source_artists[:10]:
		source_tracks.extend(get_artist_top_tracks(artist_id))
		if len(source_tracks) >= candidates_per_side:
			break

	for artist_id in target_artists[:10]:
		target_tracks.extend(get_artist_top_tracks(artist_id))
		if len(target_tracks) >= candidates_per_side:
			break

	source_tracks = source_tracks[:candidates_per_side]
	target_tracks = target_tracks[:candidates_per_side]

	print(f"  → Found {len(source_tracks)} source tracks, {len(target_tracks)} target tracks")

	if len(source_tracks) < 5 or len(target_tracks) < 5:
		print(f"  ✗ Not enough tracks to build bridge (need at least 5 each)")
		return []

	for track in source_tracks + target_tracks:
		tid = track["track_id"]
		rapid_data = rapid_get_track_analysis(tid)
		if rapid_data:
			track["features"] = rapid_data
		else:
			track["features"] = {}

	for t in source_tracks:
		t["genre_seed"] = source_genre
	for t in target_tracks:
		t["genre_seed"] = target_genre

	bridge = []
	remaining_source = [t for t in source_tracks if t.get("features") and t["features"]]
	remaining_target = [t for t in target_tracks if t.get("features") and t["features"]]

	if not remaining_source or not remaining_target:
		return []

	current = max(remaining_source, key=lambda t: t["features"].get("energy", 0))
	bridge.append(current)
	remaining_source.remove(current)

	for i in range(bridge_length - 2):
		progress = i / (bridge_length - 2)
		pool = remaining_source if progress < 0.5 else remaining_target

		if not pool:
			break

		current_features = current["features"]
		closest = min(
			pool,
			key=lambda t: calculate_track_distance(
				current_features,
				t["features"]
			)
		)

		bridge.append(closest)
		pool.remove(closest)
		current = closest

	if remaining_target:
		current_features = current["features"]
		final = min(
			remaining_target,
			key=lambda t: calculate_track_distance(
				current_features,
				t["features"]
			)
		)
		bridge.append(final)

	result = []
	for i, track in enumerate(bridge, 1):
		f = track["features"]
		item = {
			"position": i,
			"track_name": track["track_name"],
			"artists": track["artists"],
			"genre_seed": track["genre_seed"],
			"danceability": f.get("danceability"),
			"energy": f.get("energy"),
			"tempo": f.get("tempo"),
			"camelot": f.get("camelot"),
			"key": f.get("key"),
			"mode": f.get("mode"),
			"spotify_url": track["spotify_url"]
		}
		result.append(item)

	print(f"  → Built bridge with {len(result)} tracks")
	camelot_count = sum(1 for t in result if t.get("camelot"))
	print(f"  → {camelot_count}/{len(result)} tracks have Camelot keys")

	return result


def run_analysis() -> None:
	print(f"\n{'=' * 70}")
	print(f"[START] DJ Analysis - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
	print(f"{'=' * 70}\n")

	producer = KafkaJsonProducer()

	print("[1/2] Analyzing genre danceability...")
	genre_results = []

	for genre in GENRE_LIST:
		try:
			result = analyze_genre_danceability(genre, tracks_per_genre=20)
			genre_results.append(result)
			time.sleep(0.5)
		except Exception as e:
			print(f"[ERROR] Failed to analyze {genre}: {e}")

	valid_results = [r for r in genre_results if r.get("avg_danceability") is not None]
	valid_results.sort(key=lambda x: x["avg_danceability"], reverse=True)

	if producer.enabled and valid_results:
		doc = {
			"event_type": f"{APP_PREFIX}_genre_danceability",
			"generated_at": datetime.now(timezone.utc).isoformat(),
			"analysis_type": "genre_danceability",
			"genres": valid_results
		}

		if safe_kafka_send(producer, TOPIC_GENRE_DANCEABILITY, doc):
			print(f"[KAFKA] ✓ Sent genre analysis -> {TOPIC_GENRE_DANCEABILITY}")
		else:
			print(f"[KAFKA] ✗ Failed to send genre analysis")

	print("\n=== Top Genres by Danceability ===")
	for i, result in enumerate(valid_results[:10], 1):
		print(f"{i:2d}. {result['genre']:20s} - Danceability: {result['avg_danceability']:.3f}")

	print(f"\n[2/2] Building genre bridge: {DEFAULT_BRIDGE_SOURCE} → {DEFAULT_BRIDGE_TARGET}...")

	try:
		bridge_tracks = find_bridge_tracks(
			DEFAULT_BRIDGE_SOURCE,
			DEFAULT_BRIDGE_TARGET,
			candidates_per_side=CANDIDATES_PER_SIDE,
			bridge_length=BRIDGE_TRACKS
		)

		if bridge_tracks and producer.enabled:
			doc = {
				"event_type": f"{APP_PREFIX}_genre_bridge",
				"generated_at": datetime.now(timezone.utc).isoformat(),
				"analysis_type": "genre_bridge",
				"source_genre": DEFAULT_BRIDGE_SOURCE,
				"target_genre": DEFAULT_BRIDGE_TARGET,
				"tracks": bridge_tracks
			}

			if safe_kafka_send(producer, TOPIC_GENRE_BRIDGES, doc):
				print(f"[KAFKA] ✓ Sent bridge analysis -> {TOPIC_GENRE_BRIDGES}")
			else:
				print(f"[KAFKA] ✗ Failed to send bridge analysis")
		elif not bridge_tracks:
			print(f"[WARNING] No bridge tracks found - try different genres or check Spotify search results")

		if bridge_tracks:
			print(f"\n=== Bridge: {DEFAULT_BRIDGE_SOURCE} → {DEFAULT_BRIDGE_TARGET} ===")
			for track in bridge_tracks:
				camelot_str = f"Key: {track['camelot']}" if track.get('camelot') else "Key: N/A"
				print(f"{track['position']}. {track['track_name']} - {', '.join(track['artists'])}")
				print(
					f"   {track['genre_seed']:15s} | {camelot_str:10s} | Dance: {track.get('danceability', 0):.2f} | Energy: {track.get('energy', 0):.2f} | {track.get('tempo', 0):.0f} BPM")

	except Exception as e:
		print(f"[ERROR] Failed to build bridge: {e}")
		if DEBUG:
			import traceback
			traceback.print_exc()

	print(f"\n{'=' * 70}")
	print(f"[DONE] Analysis complete")
	print(f"{'=' * 70}\n")


_STOP = False


def _graceful_exit(signum, frame):
	global _STOP
	_STOP = True
	print(f"\n[INFO] Shutting down...")


def main() -> None:
	try:
		signal.signal(signal.SIGINT, _graceful_exit)
		signal.signal(signal.SIGTERM, _graceful_exit)
	except Exception:
		pass

	print(f"[BOOT] Gilian's DJ Producer (with safe MongoDB writes)")
	print(f"  Analysis interval: {ANALYSIS_INTERVAL}s ({ANALYSIS_INTERVAL / 3600:.1f}h)")
	print(f"  Bridge: {DEFAULT_BRIDGE_SOURCE} → {DEFAULT_BRIDGE_TARGET}")
	print(f"  Genres: {len(GENRE_LIST)}")

	while not _STOP:
		start = time.time()
		try:
			run_analysis()
		except Exception as e:
			print(f"[ERROR] Analysis failed: {e}")
			if DEBUG:
				import traceback
				traceback.print_exc()

		elapsed = time.time() - start
		nap = max(60, ANALYSIS_INTERVAL - elapsed)
		print(f"[SLEEP] Next analysis in {nap / 60:.1f} minutes...\n")

		for _ in range(int(nap)):
			if _STOP:
				break
			time.sleep(1)


if __name__ == "__main__":
	main()
