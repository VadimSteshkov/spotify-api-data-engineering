.PHONY: kafka-init kafka-list kafka-events kafka-snapshot run demo

# Create required Kafka topics (only once per setup)
kafka-init:
	docker exec -it kafka kafka-topics --create --if-not-exists --topic spotify_recent_events --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
	docker exec -it kafka kafka-topics --create --if-not-exists --topic spotify_recent_snapshot --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
	docker exec -it kafka kafka-topics --list --bootstrap-server localhost:9092

# List all existing Kafka topics
kafka-list:
	docker exec -it kafka kafka-topics --list --bootstrap-server localhost:9092

# Consume all messages from the "spotify_recent_events" topic
kafka-events:
	kcat -b localhost:9092 -t spotify_recent_events -C -o beginning -q

# Consume all messages from the "spotify_recent_snapshot" topic
kafka-snapshot:
	kcat -b localhost:9092 -t spotify_recent_snapshot -C -o beginning -q

# Run the main ingestion script (will also ensure topics exist)
run: kafka-init
	.venv/bin/python3 DE-Spotify.py

# Demo mode: start both consumers in parallel
run-consumers:
	@echo ">>> Press Ctrl+C to stop each consumer"
	$(MAKE) -s kafka-events & \
	$(MAKE) -s kafka-snapshot

#Run Kafka ->oMongoDB cnsumer
consume:
	.venv/bin/python3 kafka_consumer.py
