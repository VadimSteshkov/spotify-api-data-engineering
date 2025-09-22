#!/usr/bin/env python3
import json
import os
import signal
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaException
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError

# =========================
# Env / config
# =========================
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
GROUP_ID = os.getenv("GROUP_ID", "spotify-consumer")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://root:example@localhost:27017/?authSource=admin")
DB_NAME = os.getenv("MONGO_DB", "spotify_db")

TOPIC_EVENTS = os.getenv("TOPIC_EVENTS", "avd_spotify_recent_events")
TOPIC_TOP10 = os.getenv("TOPIC_TOP10", "avd_artist_market_top_tracks")

# =========================
# Mongo helpers
# =========================
def _build_mongo():
	"""
	Return (client, events_collection, top_tracks_collection).
	Creates idempotent indexes (will not fail if an equivalent index already exists).
	"""
	client = MongoClient(MONGO_URL)
	db = client[DB_NAME]

	c_events = db["avd_recent_events"]
	c_top = db["avd_artist_market_top_tracks"]

	# Query index for timelines (newest first by played_at)
	c_events.create_index([("user_id", ASCENDING), ("played_at", DESCENDING)])

	# Unique identity for a play event: (user_id, track_id, played_at)
	# Do NOT pass a custom name to avoid IndexOptionsConflict if an index already exists with a different name.
	try:
		c_events.create_index(
			[("user_id", ASCENDING), ("track_id", ASCENDING), ("played_at", ASCENDING)],
			unique=True
		)
	except PyMongoError as e:
		print(f"[WARN] create_index (avd_recent_events unique) warning: {e}")

	# Top10 per (user, artist, market) — keep latest via upsert on (user_id, artist_id, market)
	c_top.create_index([("user_id", ASCENDING), ("artist_id", ASCENDING), ("market", ASCENDING)], unique=True)
	c_top.create_index([("generated_at", DESCENDING)])

	return client, c_events, c_top

# =========================
# Kafka consumer config
# =========================
def _build_consumer():
	conf = {
		"bootstrap.servers": KAFKA_BOOTSTRAP,
		"group.id": GROUP_ID,
		"auto.offset.reset": "earliest",   # for new groups read from beginning
		"enable.auto.commit": False,       # commit only after successful Mongo write
	}
	consumer = Consumer(conf)
	return consumer

def _on_assign_from_beginning(consumer, partitions):
	"""
	When partitions are assigned, start reading from the beginning.
	Useful in development to replay entire topics.
	"""
	for p in partitions:
		p.offset = 0
	consumer.assign(partitions)

# =========================
# Upserts / writes
# =========================
def _upsert_recent_event(c_events, payload: dict):
	"""
	Insert a single play event idempotently.
	Unique key = (user_id, track_id, played_at)
	"""
	uid = payload.get("user_id")
	tid = payload.get("track_id")
	played_at = payload.get("played_at")
	if not (uid and tid and played_at):
		raise ValueError("recent_event missing one of required keys: user_id, track_id, played_at")

	c_events.update_one(
		{"user_id": uid, "track_id": tid, "played_at": played_at},
		{"$setOnInsert": payload},
		upsert=True
	)

def _upsert_artist_market_top10(c_top, payload: dict):
	"""
	Upsert Top 10 tracks for (user, artist, market).
	We keep only the latest document per triplet by replacing on upsert.
	"""
	if payload.get("event_type") != "avd_artist_market_top_tracks":
		raise ValueError("unexpected event_type for top10 payload")

	uid = payload.get("user_id")
	aid = payload.get("artist_id")
	market = payload.get("market")
	if not (uid and aid and market):
		raise ValueError("top10 payload missing one of required keys: user_id, artist_id, market")

	c_top.replace_one(
		{"user_id": uid, "artist_id": aid, "market": market},
		payload,
		upsert=True
	)

# =========================
# Main loop
# =========================
def main():
	client, coll_events, coll_top = _build_mongo()

	consumer = _build_consumer()
	consumer.subscribe([TOPIC_EVENTS, TOPIC_TOP10], on_assign=_on_assign_from_beginning)

	running = True
	def _graceful(*_):
		nonlocal running
		running = False

	signal.signal(signal.SIGINT, _graceful)
	signal.signal(signal.SIGTERM, _graceful)

	print("[INFO] Consuming from Kafka and writing to MongoDB...")
	try:
		while running:
			msg = consumer.poll(1.0)
			if msg is None:
				continue
			if msg.error():
				raise KafkaException(msg.error())

			topic = msg.topic()
			raw = msg.value()

			# Decode JSON
			try:
				payload = json.loads(raw.decode("utf-8"))
			except Exception as e:
				print(f"[WARN] JSON parse failed: {e}; topic={topic} value={raw[:120]!r}")
				# Skip this message (do not commit)
				continue

			# Route by topic
			try:
				if topic == TOPIC_EVENTS:
					_upsert_recent_event(coll_events, payload)
				elif topic == TOPIC_TOP10:
					_upsert_artist_market_top10(coll_top, payload)
				else:
					print(f"[WARN] Unexpected topic: {topic}; skipping.")
					continue

				# Commit offset only after a successful write
				consumer.commit(message=msg)
				print(f"[MONGO] Inserted from {topic} at {datetime.now(timezone.utc).isoformat()}")
			except PyMongoError as e:
				print(f"[ERROR] Mongo write failed: {e}; offset NOT committed (message will retry).")
			except Exception as e:
				print(f"[ERROR] Handler failed: {e}; offset NOT committed.")

	finally:
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

