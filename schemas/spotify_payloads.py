# file: schemas/spotify_payloads.py
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone


# ----------------------------
# Constants (Kafka topics, versioning)
# ----------------------------
EVENT_VERSION = "1.0"
TOPIC_RECENT_EVENTS = "spotify_recent_events"      # per play (stream)
TOPIC_RECENT_SNAPSHOT = "spotify_recent_snapshot"  # batch (last 50)


# ----------------------------
# Helpers
# ----------------------------
def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()

def _now_iso() -> str:
    return _iso(datetime.now(timezone.utc))  # type: ignore


# ----------------------------
# SCHEMA #1: Per-play event (stream)
# ----------------------------
@dataclass
class SpotifyPlayEvent:
    event_version: str
    event_type: str          # "recently_played"
    event_time: str          # producer time (ISO-8601)
    user_id: str
    country: Optional[str]

    played_at: str           # Spotify "played_at" (ISO-8601)
    track_id: str
    track_name: str
    track_duration_ms: int

    album_id: Optional[str]
    album_name: Optional[str]
    album_release_date: Optional[str]

    artist_ids: List[str]
    artist_names: List[str]

    market_used: Optional[str]  # market used elsewhere in the app (e.g., RO/AT)

    @staticmethod
    def from_spotify_item(
        item: Dict[str, Any],
        user_id: str,
        country: Optional[str],
        market_used: Optional[str],
    ) -> "SpotifyPlayEvent":
        track = item.get("track") or {}
        album = track.get("album") or {}
        artists = track.get("artists") or []

        return SpotifyPlayEvent(
            event_version=EVENT_VERSION,
            event_type="recently_played",
            event_time=_now_iso(),
            user_id=user_id,
            country=country,
            played_at=item.get("played_at"),
            track_id=track.get("id"),
            track_name=track.get("name"),
            track_duration_ms=int(track.get("duration_ms") or 0),
            album_id=album.get("id"),
            album_name=album.get("name"),
            album_release_date=album.get("release_date"),
            artist_ids=[a.get("id") for a in artists if a.get("id")],
            artist_names=[a.get("name") for a in artists if a.get("name")],
            market_used=market_used,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


# ----------------------------
# SCHEMA #2: Batch snapshot (last 50 plays)
# ----------------------------
@dataclass
class SpotifyRecentSnapshot:
    event_version: str
    event_type: str          # "recently_played_snapshot"
    event_time: str
    user_id: str
    country: Optional[str]
    market_used: Optional[str]

    item_count: int
    items: List[SpotifyPlayEvent]  # embedded events

    def to_json(self) -> str:
        payload = {
            "event_version": self.event_version,
            "event_type": self.event_type,
            "event_time": self.event_time,
            "user_id": self.user_id,
            "country": self.country,
            "market_used": self.market_used,
            "item_count": self.item_count,
            "items": [asdict(ev) for ev in self.items],
        }
        return json.dumps(payload, ensure_ascii=False)


# ----------------------------
# Builders
# ----------------------------
def build_events_from_recent_json(
    recent_json: Dict[str, Any],
    user_id: str,
    country: Optional[str],
    market_used: Optional[str],
) -> List[SpotifyPlayEvent]:
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


def build_snapshot(
    recent_json: Dict[str, Any],
    user_id: str,
    country: Optional[str],
    market_used: Optional[str],
) -> SpotifyRecentSnapshot:
    events = build_events_from_recent_json(recent_json, user_id, country, market_used)
    return SpotifyRecentSnapshot(
        event_version=EVENT_VERSION,
        event_type="recently_played_snapshot",
        event_time=_now_iso(),
        user_id=user_id,
        country=country,
        market_used=market_used,
        item_count=len(events),
        items=events,
    )

