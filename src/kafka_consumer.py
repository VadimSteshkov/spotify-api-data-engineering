import json
import os
import signal
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaException, TopicPartition
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

# --- Config from environment (with sane defaults) ---
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
MONGO_URL = os.getenv(
	"MONGO_URL",
	"mongodb://root:example@localhost:27017/?authSource=admin"
)

TOPIC_EVENTS = os.getenv("TOPIC_EVENTS", "spotify_recent_events")
TOPIC_SNAPSHOT = os.getenv("TOPIC_SNAPSHOT", "spotify_recent_snapshot")

# --- MongoDB client and collections ---
client = MongoClient(MONGO_URL)
db = client["spotify_db"]
coll_events = db["recent_events"]
coll_snapshots = db["recent_snapshots"]

# Useful indexes for queries and deduplication
coll_events.create_index([("user_id", ASCENDING), ("played_at", ASCENDING)])
coll_snapshots.create_index([("user_id", ASCENDING)], unique=True)

# --- Kafka Consumer config & subscription ---
GROUP_ID = os.getenv("GROUP_ID", "spotify-consumer")

conf = {
	"bootstrap.servers": KAFKA_BOOTSTRAP,
	"group.id": GROUP_ID,
	"auto.offset.reset": "earliest",   # start at earliest for new groups
	"enable.auto.commit": False,       # manual commit after successful writes
}

def on_assign(consumer, partitions):
	"""
	Force the initial read from the beginning for all assigned partitions.
	Useful in dev/debug to replay the entire topic.
	"""
	for p in partitions:
		p.offset = 0  # 0 = beginning of partition
	consumer.assign(partitions)

	# Optional: explicit seek per topic
	# consumer.seek(TopicPartition(TOPIC_EVENTS, 0, 0))
	# consumer.seek(TopicPartition(TOPIC_SNAPSHOT, 0, 0))

consumer = Consumer(conf)
consumer.subscribe([TOPIC_EVENTS, TOPIC_SNAPSHOT], on_assign=on_assign)

# --- Graceful shutdown handler ---
running = True
def _graceful(*_):
	global running
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

		# --- Parse JSON payload ---
		try:
			payload = json.loads(msg.value().decode("utf-8"))
		except Exception as e:
			print(f"[WARN] JSON parse failed: {e}; topic={msg.topic()} value={msg.value()[:120]!r}")
			# Skip corrupted message (do not commit offset)
			continue

		try:
			if msg.topic() == TOPIC_EVENTS:
				# Append-only documents (one per event)
				coll_events.insert_one(payload)
			else:
				# Maintain one snapshot per user_id (replace if exists)
				user_id = payload.get("user_id")
				if not user_id:
					# Fallback: store as-is if user_id is missing
					coll_snapshots.insert_one(payload)
				else:
					coll_snapshots.replace_one({"user_id": user_id}, payload, upsert=True)

			# Commit offset only after successful MongoDB insert
			consumer.commit(message=msg)
			print(f"[MONGO] Inserted from {msg.topic()} at {datetime.utcnow().isoformat()}Z")
		except PyMongoError as e:
			print(f"[ERROR] Mongo write failed: {e}; will NOT commit offset (message will retry)")

finally:
	try:
		consumer.close()
	except Exception:
		pass
	client.close()
	print("\n[INFO] Consumer stopped.")

