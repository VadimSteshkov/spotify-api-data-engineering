#!/usr/bin/env python3
"""
Payload builders for Spotify data (events only).
- Build per-play events from 'recently played' JSON
- No snapshot logic here (kept minimal for pipeline clarity)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import pandas as pd

# ----------------------------
# Constants
# ----------------------------
EVENT_VERSION = "1.0"

# ----------------------------
# Helpers
# ----------------------------
def _now_iso_utc() -> str:
    """Return current UTC timestamp"""
    return datetime.now(timezone.utc).isoformat()

# ----------------------------
# Per-play event schema
# ----------------------------
@dataclass
class SpotifyPlayEvent:
    """
    Represents a single listening event (append-only).
    This is the canonical event document we store in Mongo (via Kafka consumer).
    """
    event_version: str
    event_type: str          # "recent_play"
    generated_at: str        # producer timestamp (UTC)

    user_id: str
    country: Optional[str]
    market_used: Optional[str]

    played_at: str           # Spotify "played_at"
    track_id: str
    track_name: str
    track_duration_ms: int

    album_id: Optional[str]
    album_name: Optional[str]
    album_release_date: Optional[str]

    artist_ids: List[str]    # <— added for robust analytics & joins
    artist_names: List[str]

    @staticmethod
    def from_spotify_item(
        item: Dict[str, Any],
        user_id: str,
        country: Optional[str],
        market_used: Optional[str],
    ) -> "SpotifyPlayEvent":
        """Build a SpotifyPlayEvent from a single item in 'recently played' JSON."""
        track = item.get("track") or {}
        album = track.get("album") or {}
        artists = track.get("artists") or []

        return SpotifyPlayEvent(
            event_version=EVENT_VERSION,
            event_type="recent_play",
            generated_at=_now_iso_utc(),
            user_id=user_id,
            country=country,
            market_used=market_used,
            played_at=item.get("played_at"),
            track_id=track.get("id"),
            track_name=track.get("name"),
            track_duration_ms=int(track.get("duration_ms") or 0),
            album_id=album.get("id"),
            album_name=album.get("name"),
            album_release_date=album.get("release_date"),
            artist_ids=[a.get("id") for a in artists if a.get("id")],
            artist_names=[a.get("name") for a in artists if a.get("name")],
        )

    def to_json(self) -> str:
        """Return JSON string of the event (UTF-8, no ASCII escaping)."""
        return json.dumps(asdict(self), ensure_ascii=False)



@dataclass
class SpotifyPlaylistAnalysisEvent:
    """
    Represents an analyzed playlist–track item.
    Stored in Mongo (via Kafka consumer) for analytics/enrichment.
    """
    event_version: str
    event_type: str          # "playlist_analysis"
    generated_at: str        # producer timestamp (UTC)

    user_id: str             # the Spotify user that owns/runs the analysis

    playlist_id: str
    playlist_name: str
    owner_id: str

    track_id: str
    track_name: str
    album_id: str
    album_name: str

    available_markets: List[str]
    preview_url: Optional[str]

    analysis: Dict[str, Any]  # analysis payload from Recko / Spotify

    @staticmethod
    def from_item(
        item: Dict[Any, Any],
        user_id: str
    ) -> "SpotifyPlaylistAnalysisEvent":
        """Build a SpotifyPlaylistAnalysisEvent from a playlist analysis item dict."""
        track = item.get("track") or {}
        return SpotifyPlaylistAnalysisEvent(
            event_version=EVENT_VERSION,
            event_type="playlist_analysis",
            generated_at=_now_iso_utc(),
            user_id=user_id,
            playlist_id=item.get("playlist_id"),
            playlist_name=item.get("playlist_name"),
            owner_id=item.get("owner_id"),
            track_id=item.get("track_id"),
            track_name=item.get("track_name"),
            album_id=item.get("album_id"),
            album_name=item.get("album_name"),
            available_markets=track.get("available_markets", []),
            preview_url=track.get("preview_url"),
            analysis=item.get("analysis") or {}
        )

    def to_json(self) -> str:
        """Return JSON string of the event (UTF-8, no ASCII escaping)."""
        return json.dumps(asdict(self), ensure_ascii=False)

# ----------------------------
# Builders
# ----------------------------
def build_events_from_recent_json(
    recent_json: Dict[str, Any],
    user_id: str,
    country: Optional[str],
    market_used: Optional[str],
) -> List[SpotifyPlayEvent]:
    """
    Convert Spotify 'recently played' JSON into a list of SpotifyPlayEvent.
    Each 'item' becomes a single event (append-only).
    """
    events: List[SpotifyPlayEvent] = []
    for item in recent_json.get("items", []):
        ev = SpotifyPlayEvent.from_spotify_item(
            item=item,
            user_id=user_id,
            country=country,
            market_used=market_used,
        )
        events.append(ev)
    return events

def build_events_from_playlist_analysis_json(
    track_playlist_analysis_json: pd.DataFrame,
    user_id: str) -> List[SpotifyPlaylistAnalysisEvent]:
    events: List[SpotifyPlaylistAnalysisEvent] = []
    for item in track_playlist_analysis_json.to_dict(orient="records"):
        ev = SpotifyPlaylistAnalysisEvent.from_item(
            item=item,
            user_id=user_id
        )
        events.append(ev)
    return events

