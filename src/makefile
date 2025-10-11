# ======================================================
# Docker-only Makefile (tabs only) — English comments
# Stack: Zookeeper, Kafka, Mongo, Mongo-Express, Producer, Spark, Streamlit (+ optional Consumer)
# No host/venv logic. No local Python execution.
# ======================================================

# Kafka & Mongo container names used by utilities
KAFKA_CONTAINER ?= kafka
MONGO_CONTAINER ?= mongo

# Kafka brokers (reference)
BROKER_INTERNAL ?= kafka:19092     # inside Docker network
BROKER_EXTERNAL ?= localhost:9092  # from host tools

# Expose PYTHONPATH in containers if needed by your Dockerfiles
export PYTHONPATH := $(shell pwd)/src

# Spark extra packages (Kafka source + Kafka client)
export SPARK_PACKAGES ?= org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.kafka:kafka-clients:3.5.2

# ----------------
# PHONY targets
# ----------------
.PHONY: \
  env-user show-env \
  up down logs \
  kafka-wait kafka-init-from-env kafka-list kafka-tail-topic kafka-event-topic kafka-delete-topic \
  producer-build producer-run producer-logs \
  consumer-build consumer-run \
  app-build app-up app-logs app-stop \
  spark-build spark-up spark-logs spark-down \
  demo

# ======================================================
# Environment loader (per-user)
# ======================================================

# Load envs/.env.<USR> into .env for all services
env-user:
	@if [ -z "$(USR)" ]; then echo "Missing USR (e.g. USR=avd)"; exit 1; fi
	@if [ ! -f envs/.env.$(USR) ]; then echo "Missing envs/.env.$(USR)"; exit 1; fi
	@cp envs/.env.$(USR) .env
	@echo "Loaded envs/.env.$(USR) -> .env"

show-env:
	@echo "Active .env (key vars):"
	@grep -E '^(APP_PREFIX|USR|PRODUCER_ENTRY|KAFKA_BOOTSTRAP|MONGO_URL|KAFKA_TOPICS|SPARK_MODE|SPARK_PACKAGES|PORT)=' .env || true

# ======================================================
# Docker stack (infra)
# ======================================================

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

# ======================================================
# Kafka utilities
# ======================================================

# Wait until Kafka accepts commands
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
# Producer / Consumer (containers)
# ======================================================

producer-build:
	docker compose build producer

producer-run: up
	docker compose run --rm producer

producer-logs:
	docker compose logs -f producer || true

consumer-build:
	docker compose build consumer

consumer-run: up
	docker compose run --rm consumer

# ======================================================
# Streamlit App (container)
# ======================================================

app-build:
	docker compose build app

app-up: app-build up
	docker compose up -d app

app-stop:
	docker compose stop app

app-logs:
	docker compose logs -f app || docker compose logs -f streamlit-app || true

# ======================================================
# Spark (Structured Streaming)
# ======================================================

spark-build:
	docker compose build spark-app

spark-up:
	docker compose up -d spark-app

spark-logs:
	docker compose logs -f spark-app

spark-down:
	docker compose rm -sf spark-app

# ======================================================
# Build helpers (all images)
# ======================================================

# Build all first-party images (doesnt build basis iamges)
build: producer-build consumer-build app-build spark-build
	@echo "[BUILD] All service images built."

# Rebuild complet
rebuild:
	docker compose build --no-cache --pull
	@echo "[BUILD] Rebuilt all images with --no-cache --pull."

# only images
images:
	docker compose build

#stop and clean containers, volumes and orphans
clean:
	docker compose down -v --remove-orphans
	@echo "[CLEAN] Containers & volumes removed."

# ======================================================
# USER ENTRY POINTS (each teammate has their own .env.<USR>)
# ======================================================

.PHONY: avd-env alex-env gilian-env vadim-env

# --- 1️⃣ Setup environment (copy personal .env) ---
avd-env:
	@cp envs/.env.avd .env
	@echo "[ENV] Loaded .env.avd for Dorin (AVD)"

alex-env:
	@cp envs/.env.alex .env
	@echo "[ENV] Loaded .env.alex for Alex"

gilian-env:
	@cp envs/.env.gilian .env
	@echo "[ENV] Loaded .env.gilian for Gilian"

vadim-env:
	@cp envs/.env.vadim .env
	@echo "[ENV] Loaded .env.vadim for Vadim"


# --- 2️⃣ Quick run (env + infra + topics + producer) ---
avd-demo: avd-env
	docker compose up -d zookeeper kafka mongo
	make kafka-init-from-env
	docker compose run --rm -e PRODUCER_ENTRY=avd_producer -e PYTHONPATH=/app/src producer
	docker compose up -d spark-app app
	@echo "[INFO] Demo up and running for AVD!"

alex-demo: alex-env
	docker compose up -d zookeeper kafka mongo
	make kafka-init-from-env
	docker compose run --rm -e PRODUCER_ENTRY=alex_producer -e PYTHONPATH=/app/src producer
	docker compose up -d spark-app app
	@echo "[INFO] Demo up and running for Alex!"

gilian-demo: gilian-env
	docker compose up -d zookeeper kafka mongo
	make kafka-init-from-env
	docker compose run --rm -e PRODUCER_ENTRY=gilian_producer -e PYTHONPATH=/app/src producer
	docker compose up -d spark-app app
	@echo "[INFO] Demo up and running for Gilian!"

vadim-demo: vadim-env
	docker compose up -d zookeeper kafka mongo
	make kafka-init-from-env
	docker compose run --rm -e PRODUCER_ENTRY=vadim_producer -e PYTHONPATH=/app/src producer
	docker compose up -d spark-app app
	@echo "[INFO] Demo up and running for Vadim!"

# ======================================================
# One-shot demo (after env-user)
# ======================================================

demo:
	@if [ ! -f .env ]; then echo ".env not found. Run '<user>-env' first (e.g. 'make avd-env')."; exit 1; fi
	@$(MAKE) up
	@$(MAKE) kafka-init-from-env
	@$(MAKE) producer-build
	@$(MAKE) spark-build
	@$(MAKE) app-build
	@$(MAKE) producer-run
	@$(MAKE) spark-up
	@$(MAKE) app-up

