#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Generic team-wide Kafka → Mongo consumer.

- Subscribes to ALL Kafka topics via a single regex ("^.+$").
- For each topic, writes the payload to a MongoDB collection with the SAME name as the topic.
- Creates basic indexes ONCE per collection based on the first seen payload:
    * If payload has (user_id, track_id, played_at): unique index on that triple + played_at desc.
    * If payload has (user_id, artist_id, market): unique index on that triple + generated_at desc.
    * Else if payload has generated_at: index on generated_at desc.
    * Else: no special index (fallback).
- Idempotency:
    * If (user_id, track_id, played_at) present → upsert on that triple.
    * Else if (user_id, artist_id, market) present → upsert on that triple.
    * Else if 'id' present → upsert on id.
    * Else → insert_one (best effort).
"""

import json
import os
import signal
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaException
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError


# =========================
# Env / base config
# =========================
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
GROUP_ID = os.getenv("GROUP_ID", "spotify-consumer")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://root:example@localhost:27017/?authSource=admin")
DB_NAME = os.getenv("MONGO_DB", "spotify_db")

# Regex for ALL topics (must start with '^' for regex-subscribe in librdkafka; avoid lookaheads)
ALL_TOPICS_REGEX = r"^.+$"


# =========================
# Mongo factory
# =========================
def _build_mongo():
    """Return (client, db)."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    return client, db


# =========================
# Kafka consumer factory
# =========================
def _build_consumer():
    """Create a team-wide Kafka consumer (no auto-commit, earliest on new groups)."""
    conf = {
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": GROUP_ID,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    }
    return Consumer(conf)


def _on_assign_from_beginning(consumer, partitions):
    """Seek to beginning on initial assignment (dev-friendly replay)."""
    for p in partitions:
        p.offset = 0
    consumer.assign(partitions)


# =========================
# Index bootstrap (run once per collection)
# =========================
_initialized_collections = set()

def _ensure_indexes(coll, sample_payload: dict):
    """
    Create basic indexes ONCE per collection based on the first seen payload shape.
    Idempotent: re-creating the same index does not fail.
    """
    name = coll.name
    if name in _initialized_collections:
        return

    try:
        keys = set(sample_payload.keys())

        if {"playlist_id", "track_id"} <= keys:
            coll.create_index(
                [("playlist_id", ASCENDING), ("track_id", ASCENDING)],
                unique=True
            )
            print(f"[INDEX] Ensured (playlist_id, track_id) on '{name}'")
        # Recent events shape
        elif {"user_id", "track_id", "played_at"} <= keys:
            coll.create_index(
                [("user_id", ASCENDING), ("track_id", ASCENDING), ("played_at", ASCENDING)],
                unique=True
            )
            coll.create_index([("played_at", DESCENDING)])
            print(f"[INDEX] Ensured (user_id,track_id,played_at) + played_at index on '{name}'")

        # Top-10 shape (user+artist+market snapshots)
        elif {"user_id", "artist_id", "market"} <= keys:
            coll.create_index(
                [("user_id", ASCENDING), ("artist_id", ASCENDING), ("market", ASCENDING)],
                unique=True
            )
            # Timeline index if available
            if "generated_at" in keys:
                coll.create_index([("generated_at", DESCENDING)])
            print(f"[INDEX] Ensured (user_id,artist_id,market){' + generated_at' if 'generated_at' in keys else ''} index on '{name}'")



        # Generic snapshots
        elif "generated_at" in keys:
            coll.create_index([("generated_at", DESCENDING)])
            print(f"[INDEX] Ensured generated_at index on '{name}'")

        else:
            print(f"[INDEX] No special indexes for '{name}' (fallback)")

    except PyMongoError as e:
        print(f"[WARN] Index creation warning on '{name}': {e}")
    finally:
        _initialized_collections.add(name)


# =========================
# Upsert / insert routing
# =========================
def _write_document(coll, payload: dict):
    """
    Best-effort idempotent write:
    - If (track_id, playlist_id) present -> upsert on that tuple
    - Else If (user_id, track_id, played_at) present → upsert on that triple.
    - Else if (user_id, artist_id, market) present → upsert on that triple.
    - Else if 'id' present → upsert on id.
    - Else → insert_one (may produce duplicates if messages repeat).
    """
    keys = set(payload.keys())

    if {"track_id", "playlist_id"} <= keys:
        coll.replace_one(
            {
                "track_id": payload["track_id"],
                "playlist_id": payload["playlist_id"],
            },
            payload,
            upsert=True,
        )
        return "upsert:track_analysis"
    # Recent events
    if {"user_id", "track_id", "played_at"} <= keys:
        coll.update_one(
            {
                "user_id": payload["user_id"],
                "track_id": payload["track_id"],
                "played_at": payload["played_at"],
            },
            {"$setOnInsert": payload},
            upsert=True,
        )
        return "upsert:recent_triple"

    # Top-10 snapshots (user+artist+market)
    if {"user_id", "artist_id", "market"} <= keys:
        coll.replace_one(
            {
                "user_id": payload["user_id"],
                "artist_id": payload["artist_id"],
                "market": payload["market"],
            },
            payload,
            upsert=True,
        )
        return "upsert:top10_triple"

    # Generic doc with stable id
    if "id" in keys:
        coll.update_one(
            {"id": payload["id"]},
            {"$set": payload},
            upsert=True,
        )
        return "upsert:id"

    # Last resort
    coll.insert_one(payload)
    return "insert"


# =========================
# Main loop
# =========================
def main():
    client, db = _build_mongo()
    consumer = _build_consumer()

    # Subscribe to ALL topics via a single regex string inside the list
    # NOTE: librdkafka treats items starting with '^' as regex patterns.
    consumer.subscribe([ALL_TOPICS_REGEX], on_assign=_on_assign_from_beginning)

    running = True
    def _graceful(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _graceful)
    signal.signal(signal.SIGTERM, _graceful)

    print("[INFO] Consuming ALL Kafka topics and writing to MongoDB...")
    try:
        while running:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())

            topic = msg.topic()
            raw = msg.value()

            # Skip Kafka internal topics (binary, not JSON)
            if topic.startswith("__"):
                continue

            # Decode JSON payload
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception as e:
                print(f"[WARN] JSON parse failed: {e}; topic={topic} value={raw[:200]!r}")
                continue

            # Resolve target collection = topic name
            coll = db[topic]

            # Ensure indexes once per collection
            _ensure_indexes(coll, payload)

            # Write document
            try:
                mode = _write_document(coll, payload)
                consumer.commit(message=msg)
                print(f"[MONGO] {mode} OK -> {topic} @ {datetime.now(timezone.utc).isoformat()}")

            except PyMongoError as e:
                # If duplicate key sneaks through (legacy data / race), log & commit to avoid retry loop
                msg_txt = str(e)
                if "E11000" in msg_txt:
                    print(f"[WARN] Duplicate ignored (committing offset) on '{topic}': {msg_txt}")
                    consumer.commit(message=msg)
                else:
                    print(f"[ERROR] Mongo write failed: {e}; offset NOT committed (will retry).")

            except Exception as e:
                print(f"[ERROR] Handler failed: {e}; offset NOT committed. keys={list(payload.keys())}")

    finally:
        # Clean shutdown
        try:
            consumer.close()
        except Exception:
            pass
        try:
            client.close()
        except Exception:
            pass
        print("\n[INFO] Consumer stopped.")


if __name__ == "__main__":
    main()

