#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Example Kafka producer template.
- Each teammate should copy this file and rename it, e.g., alex_producer.py
- Use your own topic prefix (e.g., alex_recent_events).
- Adjust payload structure as needed.

Run:
	.venv/bin/python3 src/topic_producer/example_producer.py
"""

import os
import json
import time
import random
from datetime import datetime
from kafka import KafkaProducer

# -----------------------------
# Config (env with safe defaults)
# -----------------------------
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC_NAME = os.getenv("TOPIC_NAME", "example_recent_events")

# -----------------------------
# Kafka Producer (singleton)
# -----------------------------
def get_producer() -> KafkaProducer:
	"""
	Create a Kafka producer with JSON serialization.
	"""
	return KafkaProducer(
		bootstrap_servers=KAFKA_BOOTSTRAP,
		value_serializer=lambda v: json.dumps(v).encode("utf-8"),
		key_serializer=lambda v: str(v).encode("utf-8"),
		retries=3,
	)

# -----------------------------
# Example payload generator
# -----------------------------
def generate_fake_event(user_id: str) -> dict:
	"""
	Generate a fake play event (replace with real Spotify data if available).
	"""
	return {
		"user_id": user_id,
		"track_id": f"track_{random.randint(1, 100)}",
		"track_name": f"Song {random.randint(1, 100)}",
		"artist_ids": [f"artist_{random.randint(1, 10)}"],
		"artist_names": [f"Artist {random.randint(1, 10)}"],
		"album_id": f"album_{random.randint(1, 50)}",
		"album_name": f"Album {random.randint(1, 50)}",
		"market_used": random.choice(["US", "AT", "DE"]),
		"played_at": datetime.utcnow().isoformat(),
	}

# -----------------------------
# Main loop
# -----------------------------
if __name__ == "__main__":
	producer = get_producer()
	print(f"[INFO] Producer connected to {KAFKA_BOOTSTRAP}, sending to topic: {TOPIC_NAME}")

	try:
		while True:
			event = generate_fake_event(user_id="example_user")
			producer.send(TOPIC_NAME, key=event["user_id"], value=event)
			print(f"[DEBUG] Sent event: {event}")
			time.sleep(2)  # simulate delay between events
	except KeyboardInterrupt:
		print("\n[INFO] Stopping producer.")
	finally:
		producer.close()

