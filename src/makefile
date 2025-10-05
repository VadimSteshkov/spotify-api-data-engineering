# ===========
# Variables
# ===========
PY := .venv/bin/python3

# Containers in docker-compose.yml
KAFKA_CONTAINER ?= kafka
MONGO_CONTAINER ?= mongo

# Kafka brokers
BROKER_INTERNAL ?= kafka:19092    # used from inside containers (docker exec)
BROKER_EXTERNAL ?= localhost:9092 # used from host tools

# AVD Kafka topics (Dorin) — kept for backward compatibility
TOPIC_EVENTS ?= avd_recent_events
TOPIC_TOP10  ?= avd_artist_market_top_tracks

# Default Spark packages (can be overridden via environment/.env)
export SPARK_PACKAGES ?= org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.kafka:kafka-clients:3.5.2

# Allow 'python -m' imports from current folder
export PYTHONPATH := $(shell pwd)

# ===========
# Phony
# ===========
.PHONY: up down logs \
	kafka-wait kafka-init kafka-init-from-env kafka-list \
	kafka-tail kafka-tail-topic kafka-event kafka-event-topic \
	kafka-delete-avd kafka-delete-topic \
	run-avd run-% consume app \
	env-avd env-alex env-vadim \
	spark-run

# ===========
# Spark (Structured Streaming)
# ===========
spark-run:
	$(PY) -m pip install -r spark/requirements.txt
	PYSPARK_SUBMIT_ARGS="--packages $(SPARK_PACKAGES) pyspark-shell" \
	$(PY) -m spark.streaming_job


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
# Kafka helpers (readiness)
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

# ===========
# Topic management
# ===========
# AVD: create Dorin's topics (idempotent)
kafka-init: kafka-wait
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --create --if-not-exists --topic $(TOPIC_EVENTS) --bootstrap-server $(BROKER_INTERNAL) --partitions 1 --replication-factor 1
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --create --if-not-exists --topic $(TOPIC_TOP10)  --bootstrap-server $(BROKER_INTERNAL) --partitions 1 --replication-factor 1

# Generic: create topics listed in KAFKA_TOPICS from current .env
kafka-init-from-env: kafka-wait
	@bash -lc 'set -a; [ -f .env ] && . .env; \
	if [ -z "$$KAFKA_TOPICS" ]; then \
		echo "No KAFKA_TOPICS in .env. Skipping."; exit 0; \
	fi; \
	for t in $${KAFKA_TOPICS//,/ }; do \
		echo "Creating topic: $$t"; \
		docker exec -it $(KAFKA_CONTAINER) kafka-topics --create --if-not-exists --topic $$t --bootstrap-server $(BROKER_INTERNAL) --partitions 1 --replication-factor 1; \
	done'

# List topics
kafka-list:
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --list --bootstrap-server $(BROKER_INTERNAL)

# Tail AVD events from beginning
kafka-tail:
	docker exec -it $(KAFKA_CONTAINER) kafka-console-consumer --bootstrap-server $(BROKER_INTERNAL) --topic $(TOPIC_EVENTS) --from-beginning --property print.key=true --property print.value=true

# Tail an arbitrary topic: make kafka-tail-topic TOPIC=alex_events
kafka-tail-topic:
	@if [ -z "$(TOPIC)" ]; then echo "Usage: make kafka-tail-topic TOPIC=<name>"; exit 1; fi
	docker exec -it $(KAFKA_CONTAINER) kafka-console-consumer --bootstrap-server $(BROKER_INTERNAL) --topic $(TOPIC) --from-beginning --property print.key=true --property print.value=true

# Produce a one-off JSON line to AVD events (paste one line, Ctrl+D to end)
kafka-event:
	@echo '# Paste ONE line of JSON, then Ctrl+D'
	docker exec -i $(KAFKA_CONTAINER) kafka-console-producer --bootstrap-server $(BROKER_INTERNAL) --topic $(TOPIC_EVENTS)

# Produce a one-off JSON line to arbitrary topic: make kafka-event-topic TOPIC=alex_events
kafka-event-topic:
	@if [ -z "$(TOPIC)" ]; then echo "Usage: make kafka-event-topic TOPIC=<name>"; exit 1; fi
	@echo '# Paste ONE line of JSON, then Ctrl+D'
	docker exec -i $(KAFKA_CONTAINER) kafka-console-producer --bootstrap-server $(BROKER_INTERNAL) --topic $(TOPIC)

# Delete AVD topics (careful!)
kafka-delete-avd:
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --delete --topic $(TOPIC_EVENTS) --bootstrap-server $(BROKER_INTERNAL) || true
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --delete --topic $(TOPIC_TOP10)  --bootstrap-server $(BROKER_INTERNAL) || true

# Delete arbitrary topic: make kafka-delete-topic TOPIC=alex_events
kafka-delete-topic:
	@if [ -z "$(TOPIC)" ]; then echo "Usage: make kafka-delete-topic TOPIC=<name>"; exit 1; fi
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --delete --topic $(TOPIC) --bootstrap-server $(BROKER_INTERNAL) || true

# ===========
# Python apps
# ===========
# Dorin (AVD) end-to-end: stack up, create AVD topics, run producer
run-avd: up kafka-init-from-env
	$(PY) -m producers.avd_producer

# Generic: run teammate by prefix (expects envs/.env.<prefix> that sets PRODUCER_ENTRY + KAFKA_TOPICS)
# Example: make run-alex  -> copies envs/.env.alex to .env, creates topics from KAFKA_TOPICS, runs PRODUCER_ENTRY
run-%: env-% up kafka-init-from-env
	@bash -lc 'set -a; . .env; \
	if [ -z "$$PRODUCER_ENTRY" ]; then \
		echo "ERROR: PRODUCER_ENTRY not set in .env.$*"; exit 1; \
	fi; \
	echo "Running producer: $$PRODUCER_ENTRY"; \
	$(PY) $$PRODUCER_ENTRY'

# Start the Mongo writer (Kafka consumer)
consume:
	$(PY) -m consumers.kafka_consumer

# Streamlit app (runs from src/)
app:
	$(PY) -m streamlit run app/streamlit_app.py

# ===========
# Env shortcuts
# ===========
env-avd:
	cp envs/.env.avd .env
	@echo "Loaded env: envs/.env.avd -> .env"

env-alex:
	cp envs/.env.alex .env
	@echo "Loaded env: envs/.env.alex -> .env"

env-vadim:
	cp envs/.env.vadim .env
	@echo "Loaded env: envs/.env.vadim -> .env"

