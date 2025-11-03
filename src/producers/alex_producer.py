#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Docker-friendly Spotify Producer (headless OAuth).

What it does:
- Auth via:
	1) SPOTIPY_REFRESH_TOKEN_SAVED or SPOTIPY_REFRESH_TOKEN (non-interactive)
	2) Cache file (SPOTIPY_CACHE or .cache-<USERNAME>)
	3) Interactive (fallback, will fail inside Docker)
- Fetch last 50 "recently played", build per-play events and send to Kafka
- Detect dominant artist and send "Top 10 tracks in market" doc to Kafka
"""

import os
import time
from dataclasses import asdict
from typing import Dict, Tuple

import pandas as pd
from requests import get
from dotenv import load_dotenv

# --- local libs ---
from lib.spotify_payloads import build_events_from_playlist_analysis_json
from lib.app_util import bearer_headers, get_user_token

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

# Market override

# Flags
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:19092")

# Topics (derived from APP_PREFIX if available)
TOPIC_PLAYLIST_ANALYSIS = "alex_playlist_analysis"


# ==================================================




# ---------------- Spotify fetchers ----------------
def get_profile(user_token: str) -> Tuple[Dict, str]:
	"""Return profile and chosen market (env override > profile.country > 'AT')."""
	r = get("https://api.spotify.com/v1/me", headers=bearer_headers(user_token), timeout=30)
	r.raise_for_status()
	profile = r.json()
	return profile

def get_user_playlists(user_token: str):
	url = "https://api.spotify.com/v1/me/playlists"
	result = get(url,  headers=bearer_headers(user_token), timeout=30)
	data = result.json()
	return data

def get_recently_played(user_token: str, limit: int = 50) -> Dict:
	"""Return last N recently played (max 50)."""
	r = get(
		"https://api.spotify.com/v1/me/player/recently-played",
		headers=bearer_headers(user_token),
		params={"limit": min(limit, 50)},
		timeout=30,
	)
	r.raise_for_status()
	return r.json()

def get_tracks_from_playlist(user_token: str, url:str) -> Dict:
	result = get(url, headers=bearer_headers(user_token))
	data = result.json()
	return data

def build_playlist_track_dataframe(user_token, playlists: Dict) -> pd.DataFrame:
	tracks_playlists_df = pd.DataFrame()
	playlists = playlists.get("items", [])
	for playlist in playlists:
		href = playlist["tracks"]["href"]
		tracks_array = get_tracks_from_playlist(user_token,href + "?limit=100")["items"]  # limit 100
		tracks_df = pd.DataFrame(tracks_array)
		tracks_df["owner_id"] = playlist["owner"]["id"]
		tracks_df["playlist_id"] = playlist["id"]
		tracks_df["playlist_name"] = playlist["name"]
		tracks_playlists_df = pd.concat([tracks_playlists_df, tracks_df], ignore_index=True)
	tracks_playlists_df.drop(["added_at", "is_local", "primary_color", "added_by", "video_thumbnail"], axis=1,
						   inplace=True)

	# add for the columns with null vaules
	tracks_playlists_df["track_id"] = {}
	tracks_playlists_df["album_id"] = {}
	tracks_playlists_df["track_name"] = {}
	tracks_playlists_df["album_name"] = {}
	tracks_playlists_df["analysis"] = {}
	return tracks_playlists_df

def get_recko_api_properties(spotify_track_id: str):
	url = "https://api.reccobeats.com/v1/track?ids=" + spotify_track_id
	payload = {}
	headers = {
		'Accept': 'application/json'
	}
	response = get(url, headers=headers, data=payload)
	data = response.json()
	return data

def get_recko_api_analysis(recko_beats_id):
	url = "https://api.reccobeats.com/v1/track/" + recko_beats_id + "/audio-features"
	payload = {}
	headers = {
		'Accept': 'application/json'
	}
	response = get(url, headers=headers, data=payload)
	return response.json()

def build_recko_properties_df(tracks_playlists_df: pd.DataFrame) -> pd.DataFrame:
	df_recko = pd.DataFrame()
	df_recko["reckoProp"] = {}
	for idx, track in enumerate(tracks_playlists_df["track"]):
		track_id = track["id"]
		df_recko.at[idx, "trackId"] = track_id
		try:
			data = get_recko_api_properties(track_id)
			df_recko.at[idx, "reckoProp"] = data
			try:
				response = data.get("content")
			except Exception as e:
				status = data["status"]
				print(f"[WARN] will retry in 10 seconds status: {status} ")
				time.sleep(10)
				data = get_recko_api_properties(track_id)
				df_recko.at[idx, "reckoProp"] = data
		except:
			print(f"[WARN] failed for track_id {track_id}")
			df_recko.at[idx, "reckoProp"] = 'Failed'
			continue

	return df_recko

def build_recko_analysis_df(df_recko: pd.DataFrame) -> pd.DataFrame:
	df_recko["reckoAnalysis"] = {}
	for idx, prop in enumerate(df_recko["reckoProp"]):
		if prop == "Failed":
			df_recko.at[idx, "reckoAnalysis"] = "Failed"
			continue
		content = prop.get("content")
		if (not content == []) and content and (len(content) > 0):
			recko_beats_id = content[0]["id"]
		else:
			df_recko.at[idx, "reckoAnalysis"] = "Failed"
			continue
		try:
			data = get_recko_api_analysis(recko_beats_id)
			df_recko.at[idx, "reckoAnalysis"] = data
			try:
				response = data["id"]
			except:
				status = data["status"]
				print(f"[WARN] will retry in 30 seconds status: {status} ")
				time.sleep(30)
				data = get_recko_api_analysis(recko_beats_id)
				df_recko.at[idx, "reckoAnalysis"] = data
		except:
			df_recko.at[idx, "reckoAnalysis"] = 'Failed'
			continue

	return df_recko

def add_analysis_to_df(playlist_track_dataframe: pd.DataFrame, df_recko_analysis: pd.DataFrame) -> pd.DataFrame:
	for idx, track in enumerate(playlist_track_dataframe["track"]):
		trackId = track["id"]
		playlist_track_dataframe.at[idx, "track_id"] = trackId
		playlist_track_dataframe.at[idx, "album_id"] = track["album"]["id"]
		playlist_track_dataframe.at[idx, "track_name"] = track["name"]
		playlist_track_dataframe.at[idx, "album_name"] = track["album"]["name"]
		playlist_track_dataframe.at[idx, "analysis"] = df_recko_analysis[df_recko_analysis["trackId"] == trackId]["reckoAnalysis"].iloc[0]

	playlist_track_dataframe.drop(playlist_track_dataframe[playlist_track_dataframe["analysis"] == "Failed"].index,
								  inplace=True)
	return playlist_track_dataframe





# ---------------- Main ----------------
def main() -> None:
	user_token = get_user_token()
	profile = get_profile(user_token)
	user_id = profile.get("id")
	user_playlists = get_user_playlists(user_token)
	print(f"[INFO] {len(user_playlists['items'])} playlists found for user {user_id}.")
	playlist_track_dataframe = build_playlist_track_dataframe(user_token, user_playlists)
	print(f"[INFO] getting recko properties for tracks in playlists.")
	df_recko = build_recko_properties_df(playlist_track_dataframe)
	print(f"[INFO] getting recko analysis for tracks in playlists.")
	df_recko_analysis = build_recko_analysis_df(df_recko)
	add_analysis_to_df(playlist_track_dataframe, df_recko_analysis)
	events = build_events_from_playlist_analysis_json(playlist_track_dataframe, user_id=user_id)
	# Produce to Kafka (if available)
	producer = KafkaJsonProducer()
	print(f"[DEBUG] Kafka bootstrap={KAFKA_BOOTSTRAP} enabled={producer.enabled}")
	if producer.enabled:
		producer.send_many_json(TOPIC_PLAYLIST_ANALYSIS, [asdict(e) for e in events])
		producer.flush()
		print(f"[KAFKA] Sent {len(events)} events -> {TOPIC_PLAYLIST_ANALYSIS}")




if __name__ == "__main__":
	while True:
		try:
			main()
		except Exception as e:
			import traceback
			traceback.print_exc()
			print(f"[ERROR] Producer crashed: {e}. Retrying in 5min...", flush=True)
		time.sleep(300) # run every 5 minutes

