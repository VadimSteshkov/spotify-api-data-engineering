#!/usr/bin/env python3
"""
Vadim's New Spotify Producer
Collects data into 4 collections:
- vadim_tracks - tracks (with playlist_id for linking to playlists)
- vadim_playlists - playlists
- vadim_weekly_stats - weekly statistics
- vadim_monthly_stats - monthly statistics
"""

import os
import time
import json
import base64
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Set, Tuple, Optional
from collections import Counter, defaultdict

from requests import get, post
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from pymongo import MongoClient
from pymongo.errors import BulkWriteError
from lib.app_util import get_user_token

from lib.kafka_producer import KafkaJsonProducer

# ================== ENV / CONFIG ==================
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

# Spotify credentials
CLIENT_ID = _env_any("CLIENT_ID", "SPOTIFY_CLIENT_ID", required=True)
CLIENT_SECRET = _env_any("CLIENT_SECRET", "SPOTIFY_CLIENT_SECRET", required=True)
USERNAME = _env_any("USERNAME", "SPOTIFY_USERNAME", required=True)
REDIRECT_URI = _env_any("REDIRECT_URI", "SPOTIFY_REDIRECT_URI", required=True)

# MongoDB config
MONGO_URI = os.getenv("MONGO_URL", "mongodb://root:example@mongo:27017/?authSource=admin")
MONGO_DB = "spotify_db"  # Принудительно используем spotify_db

# Kafka config
KAFKA_ENABLED = str(os.getenv("KAFKA_ENABLED", "false")).lower() == "true"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

# Topics
TOPIC_TRACKS = "vadim_tracks"
TOPIC_PLAYLISTS = "vadim_playlists"
TOPIC_WEEKLY_STATS = "vadim_weekly_stats"
TOPIC_MONTHLY_STATS = "vadim_monthly_stats"

SCOPE = "user-read-private user-read-email user-read-recently-played user-read-currently-playing user-top-read playlist-read-private"

# ==================================================

class VadimNewProducer:
    def __init__(self):
        # Spotify
        self.client_id = CLIENT_ID
        self.client_secret = CLIENT_SECRET
        self.redirect_uri = REDIRECT_URI
        self.username = USERNAME

        # MongoDB
        self.mongo = MongoClient(MONGO_URI)
        self.db = self.mongo[MONGO_DB]

        # Collections
        self.coll_tracks = self.db["vadim_tracks"]
        self.coll_weekly_stats = self.db["vadim_weekly_stats"]
        self.coll_monthly_stats = self.db["vadim_monthly_stats"]

        # Kafka
        self.kafka_producer = KafkaJsonProducer()
        self.kafka_enabled = KAFKA_ENABLED

        # Spotify client
        self.sp: Optional[spotipy.Spotify] = None
        self.user_id: Optional[str] = None

    def init_spotify(self) -> bool:
        """Initialize Spotify client and authenticate."""
        try:
            token = get_user_token()
            self.sp = spotipy.Spotify(
				auth=token,
                auth_manager=SpotifyOAuth(
                    client_id=self.client_id,
                    client_secret=self.client_secret,
                    redirect_uri=self.redirect_uri,
                    username=self.username,
                    scope=SCOPE,
                    cache_path=f".cache-{self.username}",
                )
            )
            me = self.sp.current_user()
            self.user_id = me["id"]
            print(f"[SPOTIFY] Connected as {me.get('display_name')} ({self.user_id})")
            return True
        except Exception as e:
            print(f"[SPOTIFY] Error: {e}")
            return False

    def ensure_indexes(self):
        """Create MongoDB indexes for optimal performance."""
        # Tracks indexes - только для треков с played_at
        self.coll_tracks.create_index("played_at_dt", name="tracks_played_at_dt")
        self.coll_tracks.create_index("album_id", name="tracks_album_id")
        self.coll_tracks.create_index("track_id", name="tracks_track_id")

        # No separate playlists collection - playlists info is in tracks

        # Weekly stats indexes
        self.coll_weekly_stats.create_index(
            [("user_id", 1), ("iso_year", 1), ("iso_week", 1)],
            unique=True,
            name="user_week_unique"
        )

        # Monthly stats indexes
        self.coll_monthly_stats.create_index(
            [("user_id", 1), ("year", 1), ("month", 1)],
            unique=True,
            name="user_month_unique"
        )

    def collect_recent_tracks(self, limit: int = 50) -> List[Dict]:
        """Collect recently played tracks."""
        print("=== Collecting recent tracks ===")
        tracks = []
        try:
            res = self.sp.current_user_recently_played(limit=limit)
            for item in res.get("items", []):
                track = item.get("track")
                if not track or not track.get("id"):
                    continue

                played_at = item.get("played_at")
                played_at_dt = None
                if played_at:
                    try:
                        played_at_dt = datetime.fromisoformat(played_at.replace('Z', '+00:00'))
                    except:
                        played_at_dt = None

                # Get album info
                album = track.get("album", {})
                album_data = {
                    "album_id": album.get("id"),
                    "album_name": album.get("name"),
                    "album_artists": [a.get("name") for a in album.get("artists", [])],
                    "album_artist_ids": [a.get("id") for a in album.get("artists", [])],
                    "album_release_date": album.get("release_date"),
                    "album_total_tracks": album.get("total_tracks"),
                    "album_popularity": album.get("popularity"),
                    "album_genres": album.get("genres", []),
                }

                track_data = {
                    "track_id": track["id"],
                    "track_name": track.get("name"),
                    "artists": [a.get("name") for a in track.get("artists", [])],
                    "artist_ids": [a.get("id") for a in track.get("artists", [])],
                    "duration_ms": track.get("duration_ms"),
                    "popularity": track.get("popularity"),
                    "explicit": track.get("explicit"),
                    "played_at": played_at,
                    "played_at_dt": played_at_dt,
                    "album": album_data,  # Вся информация об альбоме в треке
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                tracks.append(track_data)

            print(f"[OK] Recent tracks: {len(tracks)}")
        except Exception as e:
            print(f"[ERR] recent_tracks: {e}")

        return tracks

    def collect_playlist_tracks(self, limit: int = 5) -> List[Dict]:
        """Collect tracks from playlists."""
        print("=== Collecting playlist tracks ===")
        all_tracks = []
        try:
            playlists = self.sp.current_user_playlists(limit=limit)
            for playlist in playlists.get("items", []):
                playlist_id = playlist["id"]
                playlist_name = playlist["name"]

                res = self.sp.playlist_tracks(playlist_id, limit=100)
                for item in res.get("items", []):
                    track = item.get("track")
                    if not track or not track.get("id"):
                        continue

                    added_at = item.get("added_at")
                    added_at_dt = None
                    if added_at:
                        try:
                            added_at_dt = datetime.fromisoformat(added_at.replace('Z', '+00:00'))
                        except:
                            added_at_dt = None

                    # Get album info
                    album = track.get("album", {})
                    print(f"[DEBUG] Track: {track.get('name')}, Album from API: {album}")

                    # Get artist info for genres
                    artist_ids = [a.get("id") for a in track.get("artists", [])]
                    artist_genres = []
                    if artist_ids:
                        try:
                            # Get artist info in batches
                            for i in range(0, min(len(artist_ids), 5), 5):
                                batch = artist_ids[i:i+5]
                                artists_info = self.sp.artists(batch)
                                for artist in artists_info.get("artists", []):
                                    if artist and artist.get("genres"):
                                        artist_genres.extend(artist.get("genres", []))
                                time.sleep(0.1)  # Rate limiting
                        except Exception as e:
                            print(f"[WARN] Could not get artist genres: {e}")

                    album_data = {
                        "album_id": album.get("id"),
                        "album_name": album.get("name"),
                        "album_artists": [a.get("name") for a in album.get("artists", [])],
                        "album_artist_ids": [a.get("id") for a in album.get("artists", [])],
                        "album_release_date": album.get("release_date"),
                        "album_total_tracks": album.get("total_tracks"),
                        "album_popularity": album.get("popularity"),
                        "album_genres": album.get("genres", []),
                        "artist_genres": list(set(artist_genres)),  # Add artist genres
                    }

                    track_data = {
                        "track_id": track["id"],
                        "track_name": track.get("name"),
                        "artists": [a.get("name") for a in track.get("artists", [])],
                        "artist_ids": [a.get("id") for a in track.get("artists", [])],
                        "duration_ms": track.get("duration_ms"),
                        "popularity": track.get("popularity"),
                        "explicit": track.get("explicit"),
                        "playlist_id": playlist_id,
                        "playlist_name": playlist_name,
                        "added_at": added_at,
                        "added_at_dt": added_at_dt,
                        "album": album_data,  # Вся информация об альбоме в треке
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    all_tracks.append(track_data)

            print(f"[OK] Playlist tracks: {len(all_tracks)}")
        except Exception as e:
            print(f"[ERR] playlist_tracks: {e}")

        return all_tracks

    def collect_playlists(self) -> List[Dict]:
        """Collect user playlists."""
        print("=== Collecting playlists ===")
        playlists = []

        try:
            # Get user playlists
            results = self.sp.current_user_playlists(limit=50)

            while results:
                for playlist in results.get("items", []):
                    playlist_data = {
                        "playlist_id": playlist["id"],
                        "name": playlist.get("name"),
                        "description": playlist.get("description", ""),
                        "owner": playlist.get("owner", {}).get("display_name", ""),
                        "owner_id": playlist.get("owner", {}).get("id", ""),
                        "tracks_count": playlist.get("tracks", {}).get("total", 0),
                        "public": playlist.get("public", False),
                        "collaborative": playlist.get("collaborative", False),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                    playlists.append(playlist_data)

                if results.get("next"):
                    results = self.sp.next(results)
                else:
                    break

        except Exception as e:
            print(f"[ERR] playlists: {e}")

        print(f"[OK] Playlists: {len(playlists)}")
        return playlists

    def calculate_weekly_stats(self, tracks: List[Dict]) -> Dict:
        """Calculate weekly statistics."""
        print("=== Calculating weekly stats ===")

        # Get current week
        today = datetime.now(timezone.utc).date()
        iso_year, iso_week, _ = today.isocalendar()

        # Filter tracks for current week
        week_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
        week_start = week_start - timedelta(days=week_start.weekday())
        week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)

        weekly_tracks = []
        for track in tracks:
            played_at_dt = track.get("played_at_dt")
            if played_at_dt and week_start <= played_at_dt <= week_end:
                weekly_tracks.append(track)

        # Calculate stats
        artist_counts = Counter()
        track_counts = Counter()
        album_counts = Counter()

        for track in weekly_tracks:
            for artist in track.get("artists", []):
                artist_counts[artist] += 1
            track_counts[track.get("track_name")] += 1
            album_counts[track.get("album_name")] += 1

        weekly_stats = {
            "user_id": self.user_id,
            "iso_year": iso_year,
            "iso_week": iso_week,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "total_tracks": len(weekly_tracks),
            "unique_artists": len(artist_counts),
            "unique_albums": len(album_counts),
            "top_artists": [{"artist": name, "count": count} for name, count in artist_counts.most_common(10)],
            "top_tracks": [{"track": name, "count": count} for name, count in track_counts.most_common(10)],
            "top_albums": [{"album": name, "count": count} for name, count in album_counts.most_common(10)],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        print(f"[OK] Weekly stats calculated for {len(weekly_tracks)} tracks")
        return weekly_stats

    def calculate_monthly_stats(self, tracks: List[Dict]) -> Dict:
        """Calculate monthly statistics."""
        print("=== Calculating monthly stats ===")

        # Get current month
        today = datetime.now(timezone.utc).date()
        year = today.year
        month = today.month

        # Filter tracks for current month
        month_start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            month_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
        else:
            month_end = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)

        monthly_tracks = []
        for track in tracks:
            played_at_dt = track.get("played_at_dt")
            if played_at_dt and month_start <= played_at_dt <= month_end:
                monthly_tracks.append(track)

        # Calculate stats
        artist_counts = Counter()
        track_counts = Counter()
        album_counts = Counter()

        for track in monthly_tracks:
            for artist in track.get("artists", []):
                artist_counts[artist] += 1
            track_counts[track.get("track_name")] += 1
            album_counts[track.get("album_name")] += 1

        monthly_stats = {
            "user_id": self.user_id,
            "year": year,
            "month": month,
            "month_start": month_start.isoformat(),
            "month_end": month_end.isoformat(),
            "total_tracks": len(monthly_tracks),
            "unique_artists": len(artist_counts),
            "unique_albums": len(album_counts),
            "top_artists": [{"artist": name, "count": count} for name, count in artist_counts.most_common(20)],
            "top_tracks": [{"track": name, "count": count} for name, count in track_counts.most_common(20)],
            "top_albums": [{"album": name, "count": count} for name, count in album_counts.most_common(20)],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        print(f"[OK] Monthly stats calculated for {len(monthly_tracks)} tracks")
        return monthly_stats

    def save_to_mongodb(self, tracks: List[Dict], weekly_stats: Dict, monthly_stats: Dict):
        """Save all data to MongoDB."""
        print("=== Saving to MongoDB ===")

        try:
            # Save tracks
            if tracks:
                try:
                    self.coll_tracks.insert_many(tracks, ordered=False)
                    print(f"[MONGO] Tracks inserted: {len(tracks)}")
                except BulkWriteError as bwe:
                    inserted = len([w for w in bwe.details.get("writeErrors", []) if w.get("code") != 11000])
                    total = len(tracks)
                    dup = total - inserted
                    print(f"[MONGO] Tracks inserted with duplicates ignored. total={total}, dup={dup}")

            # No separate playlists collection - playlists info is in tracks

            # Save weekly stats
            if weekly_stats:
                self.coll_weekly_stats.update_one(
                    {"user_id": weekly_stats["user_id"], "iso_year": weekly_stats["iso_year"], "iso_week": weekly_stats["iso_week"]},
                    {"$set": weekly_stats},
                    upsert=True
                )
                print("[MONGO] Weekly stats upserted")

            # Save monthly stats
            if monthly_stats:
                self.coll_monthly_stats.update_one(
                    {"user_id": monthly_stats["user_id"], "year": monthly_stats["year"], "month": monthly_stats["month"]},
                    {"$set": monthly_stats},
                    upsert=True
                )
                print("[MONGO] Monthly stats upserted")

        except Exception as e:
            print(f"[MONGO ERR] save: {e}")

    def send_to_kafka(self, tracks: List[Dict], weekly_stats: Dict, monthly_stats: Dict):
        """Send data to Kafka topics."""
        if not self.kafka_enabled:
            return

        print("=== Sending to Kafka ===")

        try:
            # Send tracks
            for track in tracks:
                self.kafka_producer.send_json(TOPIC_TRACKS, track)
            print(f"[KAFKA] Sent {len(tracks)} tracks to {TOPIC_TRACKS}")

            # No separate playlists collection - playlists info is in tracks

            # Send weekly stats
            if weekly_stats:
                self.kafka_producer.send_json(TOPIC_WEEKLY_STATS, weekly_stats)
                print(f"[KAFKA] Sent weekly stats to {TOPIC_WEEKLY_STATS}")

            # Send monthly stats
            if monthly_stats:
                self.kafka_producer.send_json(TOPIC_MONTHLY_STATS, monthly_stats)
                print(f"[KAFKA] Sent monthly stats to {TOPIC_MONTHLY_STATS}")

        except Exception as e:
            print(f"[KAFKA ERR] {e}")

    def run(self):
        """Main execution method."""
        if not self.init_spotify():
            print("Spotify auth failed")
            return

        self.ensure_indexes()

        # Collect data
        recent_tracks = self.collect_recent_tracks(limit=50)
        playlist_tracks = self.collect_playlist_tracks(limit=5)

        # Combine all tracks
        all_tracks = recent_tracks + playlist_tracks

        # No separate playlists collection - playlists info is in tracks

        # Calculate statistics
        weekly_stats = self.calculate_weekly_stats(all_tracks)
        monthly_stats = self.calculate_monthly_stats(all_tracks)

        # Save to MongoDB
        self.save_to_mongodb(all_tracks, weekly_stats, monthly_stats)

        # Send to Kafka
        self.send_to_kafka(all_tracks, weekly_stats, monthly_stats)

        print("Data collection completed successfully!")


def main():
    producer = VadimNewProducer()
    producer.run()


if __name__ == "__main__":
    main()
