# Docker‑only Setup Guide (Multi‑User)

This project now runs **entirely in Docker**. Each teammate uses their own `.env` so you can run isolated pipelines (own Kafka topics / Mongo collections / optional Streamlit tab) without touching code.

---

## 1) Prerequisites

- Docker Engine + Docker Compose plugin
- Open host ports (or change them in `src/docker-compose.yml`):
  - Zookeeper **2181**
  - Kafka **9092**
  - MongoDB **27017**
  - Mongo‑Express **8081**
  - Streamlit **8501**

> No local Python or Java is required for running the stack — everything is containerized.

Repository layout (relevant):
```
/src
  app/                     # Streamlit UI
    streamlit_app.py
    tabs/
      avd.py               # Dorin's example tab
  consumers/               # Kafka → Mongo consumer(s)
    kafka_consumer.py
  docker/                  # Dockerfiles for app/producer/consumer
  lib/                     # shared utils
  producers/               # producers (one per teammate or per use case)
    avd_producer.py
  spark/                   # Spark Structured Streaming job + Dockerfile
  docker-compose.yml       # infra (ZK, Kafka, Mongo, Mongo-Express, Producer, Spark, App)
  makefile                 # docker-only tasks
  envs/                    # per-user .env templates (NOT secrets)
```

---

## 2) Configure your environment

Pick one of these flows.

### A) Quick: built-ins for teammates
We ship convenience targets that copy a personal env and run:
```bash
cd src
make avd-env         # or: alex-env / gilian-env / vadim-env
make show-env        # sanity-check key vars
```

### B) Generic (any teammate)
Copy your template into `.env`:
```bash
cd src
make env-user USR=<your_prefix>     # copies envs/.env.<prefix> → .env
make show-env
```

### Required/important `.env` keys
- **APP_PREFIX** — your short id (e.g. `avd`, `alex`).
- **KAFKA_TOPICS** — comma-separated list of topics you produce to.
- **KAFKA_BOOTSTRAP** — inside containers use `kafka:19092`. (From host tools use `localhost:9092`.)
- **MONGO_URL** — inside containers use `mongodb://root:example@mongo:27017/?authSource=admin`. (From host tools use `localhost`.)
- **PRODUCER_ENTRY** — python module name, e.g. `avd_producer`, `alex_producer` (resolved under `producers/`).

Optional:
- **KAFKA_TOPIC_ROUTES** — map topics to semantic handlers in the consumer (e.g. `avd_spotify_recent_events:events,avd_artist_market_top_tracks:top10`).
- **MONGO_DB**, **MONGO_COLL_EVENTS**, **MONGO_COLL_TOP10** — if you use the classic AVD dashboards.

---

## 3) Start the infrastructure

From `src/`:
```bash
make up                     # start ZK, Kafka, Mongo, Mongo-Express, plus build other images
make logs                   # follow all service logs
docker compose ps           # verify status
```

Create your topics from `.env`:
```bash
make kafka-init-from-env
make kafka-list
```

Kafka helpers:
```bash
make kafka-tail-topic TOPIC=<name>   # consume from beginning
make kafka-event-topic TOPIC=<name>  # produce one JSON line (Ctrl+D to send)
make kafka-delete-topic TOPIC=<name>
```

---

## 4) Run producer / consumer / app

Open one terminal (or run sequentially). All run **in containers**.

```bash
# Producer (honors PRODUCER_ENTRY from .env; override with -e)
make producer-build
make producer-run
# or one-shot for Dorin's producer:
docker compose run --rm -e PRODUCER_ENTRY=avd_producer -e PYTHONPATH=/app/src producer

# Consumer (Kafka → Mongo generic writer/parsers)
make consumer-build
make consumer-run

# Spark Structured Streaming (optional)
make spark-build
make spark-up
make spark-logs

# Streamlit UI
make app-build
make app-up
make app-logs
```

All services/ports (host):
- Kafka: `localhost:9092`
- MongoDB: `mongodb://root:example@localhost:27017/?authSource=admin`
- Mongo‑Express: `http://localhost:8081` (admin / secret by default)
- Streamlit: `http://localhost:8501`

---

## 5) One‑command demos

```bash
cd src
make avd-demo   # sets env, brings up infra, creates topics, runs Dorin's producer, starts Spark + App
# or, after setting your own .env:
make demo       # infra + topics + build + run producer + spark + app
```

---

## 6) Troubleshooting

### Port already in use (2181/9092/27017/8081/8501)
Find who owns the port and kill the stray `docker-proxy` if needed:
```bash
sudo ss -ltnp '( sport = :2181 or sport = :9092 or sport = :27017 or sport = :8081 or sport = :8501 )'
sudo lsof -iTCP:<PORT> -sTCP:LISTEN -n -P
sudo kill -9 $(sudo lsof -t -iTCP:<PORT> -sTCP:LISTEN) 2>/dev/null || true
sudo systemctl restart docker
```

### Kafka not ready yet
`make kafka-wait` is built into `kafka-init-from-env`. If it times out, check `docker compose logs -f kafka zookeeper`.

### Mongo‑Express won’t start
If `8081` is taken, change `ports:` in `src/docker-compose.yml`, then:
```bash
docker compose rm -sf mongo-express
docker compose up -d --no-deps --force-recreate mongo-express
```

### Reset the stack (without losing named volumes)
```bash
docker compose down
docker compose up -d
```

If you do want a clean Mongo (named volume data loss!):
```bash
docker compose down -v
```

---

## 7) Don’t commit secrets

- Real `.env` files are ignored by `.gitignore` (only commit `*.example`).
- Never commit Spotify or DB credentials.
