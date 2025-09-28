# ===========
# Variables
# ===========
PY := .venv/bin/python3
KAFKA_CONTAINER ?= kafka
BROKER_INTERNAL ?= kafka:19092    # inside Kafka container
BROKER_EXTERNAL ?= localhost:9092 # from host (for manual tools)

# AVD topics (Dorin)
TOPIC_EVENTS ?= avd_spotify_recent_events
TOPIC_TOP10  ?= avd_artist_market_top_tracks

# ===========
# Phony
# ===========
.PHONY: up down logs \
	kafka-wait kafka-init kafka-list kafka-tail kafka-event kafka-delete-avd \
	run run-avd consume app

# ===========
# Docker stack
# ===========
up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

# ===========
# Kafka helpers
# ===========
kafka-wait:
	@echo "[WAIT] Waiting for Kafka to be ready..."
	@docker exec -it $(KAFKA_CONTAINER) bash -lc '\
	for i in $$(seq 1 30); do \
		kafka-topics --bootstrap-server $(BROKER_INTERNAL) --list >/dev/null 2>&1 && { echo "Kafka is ready."; exit 0; }; \
		echo "  ...not ready yet ($$i)"; \
		sleep 2; \
	done; \
	echo "ERROR: Kafka not ready in time." >&2; \
	exit 1'

# Create (idempotent) topics for AVD pipeline
kafka-init: kafka-wait
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --create --if-not-exists --topic $(TOPIC_EVENTS) --bootstrap-server $(BROKER_INTERNAL) --partitions 1 --replication-factor 1
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --create --if-not-exists --topic $(TOPIC_TOP10)  --bootstrap-server $(BROKER_INTERNAL) --partitions 1 --replication-factor 1

# List topics
kafka-list:
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --list --bootstrap-server $(BROKER_INTERNAL)

# Tail events topic from beginning
kafka-tail:
	docker exec -it $(KAFKA_CONTAINER) kafka-console-consumer --bootstrap-server $(BROKER_INTERNAL) --topic $(TOPIC_EVENTS) --from-beginning --property print.key=true --property print.value=true

# Produce a one-off JSON line manually (paste one line, Ctrl+D to end)
kafka-event:
	@echo '# Paste ONE line of JSON, then Ctrl+D'
	docker exec -i $(KAFKA_CONTAINER) kafka-console-producer --bootstrap-server $(BROKER_INTERNAL) --topic $(TOPIC_EVENTS)

# Delete AVD topics (careful!)
kafka-delete-avd:
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --delete --topic $(TOPIC_EVENTS) --bootstrap-server $(BROKER_INTERNAL) || true
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --delete --topic $(TOPIC_TOP10)  --bootstrap-server $(BROKER_INTERNAL) || true

# ===========
# Python apps (module-style to match new structure)
# ===========
# End-to-end: stack up, create topics, run AVD producer
run: up kafka-init
	$(PY) -m producers.avd_producer

# Run producer only (Kafka already up & topics exist)
run-avd:
	$(PY) -m producers.avd_producer

# Start Mongo writer (Kafka consumer)
consume:
	$(PY) -m consumers.kafka_consumer

# Streamlit app (runs from project root)
app:
	$(PY) -m streamlit run app/streamlit_app.py

