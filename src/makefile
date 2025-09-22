# ---- Makefile for spotify-api-data-engineering/src ----
# Assumes containers named: kafka, mongo
# Python venv: .venv/bin/python3
# All recipes MUST be indented with TABs.

.PHONY: run consume kafka-consumer kafka-init kafka-list kafka-event kafka-tail delete-old-topic up down

# Create topics, then run the producer script once
run: kafka-init
	.venv/bin/python3 DE-Spotify.py

# Start the Kafka→MongoDB consumer
kafka-consumer:
	.venv/bin/python3 kafka_consumer.py

# Alias for convenience
consume: kafka-consumer

# Create (idempotent) topics needed by the pipeline
kafka-init:
	docker exec -it kafka kafka-topics --create --if-not-exists --topic avd_spotify_recent_events --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
	docker exec -it kafka kafka-topics --create --if-not-exists --topic avd_artist_market_top_tracks --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1

# List topics in the cluster
kafka-list:
	docker exec -it kafka kafka-topics --list --bootstrap-server localhost:9092

# Produce a single test JSON message into spotify_recent_events (for quick sanity checks)
kafka-event:
	echo '{"event_type":"recently_played","user_id":"test-user","track_id":"test-track","played_at":"2025-01-01T00:00:00Z"}' | \
	docker exec -i kafka kafka-console-producer --bootstrap-server localhost:9092 --topic spotify_recent_events

# Tail a topic from the beginning (CTRL+C to stop)
kafka-tail:
	docker exec -it kafka kafka-console-consumer --bootstrap-server localhost:9092 --topic spotify_recent_events --from-beginning --property print.key=true --property print.value=true

# (Optional) compose helpers if you keep docker-compose.yml in this folder
up:
	docker compose up -d

down:
	docker compose down
delete-topic:
	# Delete old topics
	docker exec -it kafka kafka-topics --delete --topic spotify_recent_events --bootstrap-server localhost:9092
	docker exec -it kafka kafka-topics --delete --topic artist_market_top_tracks --bootstrap-server localhost:9092


