# ======================================================
# Generic Makefile (tabs only) — comments in English
# Supports:
#   - Host mode: producer/consumer/streamlit using localhost
#   - Docker mode: ephemeral python containers on Docker network
#   - Spark Structured Streaming container (docker-compose service)
# ======================================================

# ----------------
# Python / paths
# ----------------
PY := .venv/bin/python3

# Environment presets
ENV_HOST  := envs/.env.host     # host: KAFKA_BOOTSTRAP=localhost:9092, MONGO_URL=...localhost...
ENV_SPARK := envs/.env.spark    # docker: KAFKA_BOOTSTRAP=kafka:19092, MONGO_URL=...mongo...

# Docker container names (see docker-compose.yml)
KAFKA_CONTAINER ?= kafka
MONGO_CONTAINER ?= mongo

# Kafka brokers (reference)
BROKER_INTERNAL ?= kafka:19092     # used inside Docker network
BROKER_EXTERNAL ?= localhost:9092  # used from host tools

# Spark extra packages
export SPARK_PACKAGES ?= org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.kafka:kafka-clients:3.5.2

# Allow "python -m" imports from project root
export PYTHONPATH := $(shell pwd)

# ----------------
# PHONY targets
# ----------------
.PHONY: \
	up down logs \
	env-host env-spark show-env test-env \
	kafka-wait kafka-init-from-env kafka-list kafka-tail-topic kafka-event-topic kafka-delete-topic \
	run run-host run-avd \
	producer-build producer-run producer-logs run-docker \
	consume-host consumer-build consume-docker \
	app-host app-docker app-build app-up app-stop app-logs app-docker-logs app-docker-kill-port \
	spark-build spark-up spark-logs spark-down spark-run-local

# ======================================================
# Docker stack (Kafka, Mongo, Spark service)
# ======================================================

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

# ======================================================
# Environment helpers
# ======================================================

env-host:
	@if [ ! -f $(ENV_HOST) ]; then echo "Missing $(ENV_HOST)"; exit 1; fi
	@cp $(ENV_HOST) .env
	@echo "Loaded host environment -> .env"

env-spark:
	@if [ ! -f $(ENV_SPARK) ]; then echo "Missing $(ENV_SPARK)"; exit 1; fi
	@cp $(ENV_SPARK) .env
	@echo "Loaded spark/docker environment -> .env"

show-env:
	@echo "Active .env (key vars):"
	@grep -E '^(APP_PREFIX|KAFKA_BOOTSTRAP|MONGO_URL|KAFKA_TOPICS|SPARK_MODE|SPARK_FEATURE|SPARK_GROUP)=' .env || true

# ======================================================
# Kafka utilities
# ======================================================

# Wait for Kafka to accept commands
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

# Create topics from KAFKA_TOPICS in .env (idempotent)
kafka-init-from-env: kafka-wait
	@bash -lc 'set -a; [ -f .env ] && . .env; \
	if [ -z "$$KAFKA_TOPICS" ]; then echo "No KAFKA_TOPICS found. Skipping."; exit 0; fi; \
	for t in $${KAFKA_TOPICS//,/ }; do \
		echo "Creating topic: $$t"; \
		docker exec -it $(KAFKA_CONTAINER) kafka-topics --create --if-not-exists --topic $$t --bootstrap-server $(BROKER_INTERNAL) --partitions 1 --replication-factor 1; \
	done'

# List topics
kafka-list:
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --list --bootstrap-server $(BROKER_INTERNAL)

# Tail a topic from beginning (Usage: make kafka-tail-topic TOPIC=name)
kafka-tail-topic:
	@if [ -z "$(TOPIC)" ]; then echo "Usage: make kafka-tail-topic TOPIC=<name>"; exit 1; fi
	docker exec -it $(KAFKA_CONTAINER) kafka-console-consumer --bootstrap-server $(BROKER_INTERNAL) --topic $(TOPIC) --from-beginning --property print.key=true --property print.value=true

# Produce one JSON line to a topic (Usage: make kafka-event-topic TOPIC=name)
kafka-event-topic:
	@if [ -z "$(TOPIC)" ]; then echo "Usage: make kafka-event-topic TOPIC=<name>"; exit 1; fi
	@echo '# Paste ONE line of JSON, then Ctrl+D'
	docker exec -i $(KAFKA_CONTAINER) kafka-console-producer --bootstrap-server $(BROKER_INTERNAL) --topic $(TOPIC)

# Delete a topic (Usage: make kafka-delete-topic TOPIC=name)
kafka-delete-topic:
	@if [ -z "$(TOPIC)" ]; then echo "Usage: make kafka-delete-topic TOPIC=<name>"; exit 1; fi
	docker exec -it $(KAFKA_CONTAINER) kafka-topics --delete --topic $(TOPIC) --bootstrap-server $(BROKER_INTERNAL) || true

# ======================================================
# HOST MODE (your default workflow on laptop)
# ======================================================

# Alias: "make run" should run Dorin's AVD producer on host
run: run-avd

# Run AVD producer on host (uses envs/.env.host)
run-host run-avd: env-host up kafka-init-from-env
	$(PY) -m producers.avd_producer

# Run Mongo writer (consumer) on host
consume-host: env-host up
	$(PY) -m consumers.kafka_consumer

# Run Streamlit dashboard on host
app-host: env-host up
	$(PY) -m streamlit run app/streamlit_app.py

# ======================================================
# DOCKER MODE (no localhost assumptions)
# ======================================================

# Run producer in a temporary Python container on Docker network
run-docker: producer-run
	# This is now just an alias for producer-run
	
# Run consumer (this is now the efficient target added earlier)
consume-docker: consumer-build up
	docker compose run --rm consumer

# Run Streamlit from the dedicated Docker Compose service
PORT ?= 8501

app-docker: app-build up
	docker compose up -d app

# Tail logs from the running app container
app-docker-logs:
	docker logs -f streamlit-app || true

# Free the port in case a stray container or process still owns it
app-docker-kill-port:
	-@lsof -ti :$(PORT) | xargs -r kill -9	
# ======================================================
# SPARK (Structured Streaming) — docker-compose service
# ======================================================

# Build the Spark image
spark-build:
	docker compose build spark-app

# Start Spark service with envs/.env.spark (uses kafka:19092, mongo:27017)
spark-up:
	docker compose --env-file $(ENV_SPARK) up -d spark-app

# Stream Spark logs
spark-logs:
	docker compose logs -f spark-app

# Remove Spark service container
spark-down:
	docker compose rm -sf spark-app

# ======================================================
# SPARK local (debug only)
# ======================================================

spark-run-local:
	$(PY) -m pip install -r spark/requirements.txt
	PYSPARK_SUBMIT_ARGS="--packages $(SPARK_PACKAGES) pyspark-shell" \
	$(PY) -m spark.streaming_job
	
# ============================
# Environment quick test
# ============================
# Displays key environment variables loaded from .env
# Useful for verifying Docker vs Local configurations
.PHONY: test-env
test-env:
	@echo ""
	@echo "  Environment check:"
	@echo "----------------------------"
	@bash -lc 'set -a; [ -f .env ] && . .env; \
		echo "APP_PREFIX       = $$APP_PREFIX"; \
		echo "KAFKA_BOOTSTRAP  = $$KAFKA_BOOTSTRAP"; \
		echo "MONGO_URL        = $$MONGO_URL"; \
		echo "SPARK_MODE       = $$SPARK_MODE"; \
		echo "PRODUCER_ENTRY   = $$PRODUCER_ENTRY"; \
		echo "----------------------------"; \
		echo " Environment loaded successfully."'

# --- Producer image (build once, then run many times) ---
producer-build:
	docker compose build producer

producer-run: up
	docker compose run --rm producer

producer-logs:
	docker compose logs -f producer

# --- Consumer image (build once, then run many times) ---
consumer-build:
	docker compose build consumer

# Update the consume-docker target to use the pre-built image
consume-docker: consumer-build up
	docker compose run --rm consumer
	
# --- Streamlit App image (build once, then run many times) ---
app-build:
	docker compose build app

app-up: app-build up
	docker compose up -d app

app-stop:
	docker compose stop app

app-logs:
	docker compose logs -f streamlit-app
