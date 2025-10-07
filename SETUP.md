# Project Setup Guide (Generic • Multi‑User)

This repo is now **env‑driven and prefix‑agnostic**. Every teammate can run their own pipeline (own topics, own Mongo collections, optional own Streamlit tab) **without code changes**—just by providing a personal `.env` and, optionally, a small tab module.

---

## 1) Prerequisites

- Docker & Docker Compose
- Python 3.11+ (local dev; the infra runs in Docker)
- (Optional) Spotify Developer credentials for producers that query Spotify
- A **personal** `src/.env` (never commit secrets)

### Repository layout (relevant)
```
/src
  app/                     # Streamlit UI (orchestrator + teammate tabs)
    streamlit_app.py
    tabs/
      avd.py               # Dorin's tab (example)
  consumers/               # Kafka → Mongo consumer(s)
    kafka_consumer.py
  lib/                     # shared utils
    kafka_producer.py
    spotify_payloads.py
  producers/               # producers (one per teammate or per use case)
    avd_producer.py
    example_producer.py
  docker-compose.yml       # infra (ZK, Kafka, Mongo, Mongo-Express)
  makefile                 # common tasks
.env.example               # document all env vars
envs/                      # per-user .env templates (NOT secrets)
```
> Tip: put your templates in `src/envs/.env.<prefix>` and **never** commit a real `src/.env`.

---

## 2) Your `.env` (one per teammate)

Copy `src/.env.example` to `src/.env` (or use a template in `src/envs/`). Fill only what you need.

```ini
# Identity
APP_PREFIX=alex

# Kafka (host broker)
KAFKA_BOOTSTRAP=localhost:9092

# The topics you will use (comma separated)
KAFKA_TOPICS=alex_events,alex_metrics

# Optional: route a topic to a semantic handler
# Recognized handlers in consumer: events | top10
# Unmapped topics are written RAW under GENERIC_COLL_NAMESPACE
KAFKA_TOPIC_ROUTES=alex_events:events

# Mongo
MONGO_URL=mongodb://root:example@localhost:27017/?authSource=admin
MONGO_DB=spotify_db

# Collections for classic Spotify views (optional)
# Leave empty if you don't have these; Streamlit hides sections automatically.
MONGO_COLL_EVENTS=
MONGO_COLL_TOP10=

# Namespace for RAW topics → Mongo collections (required for generic flow)
# e.g., topic "alex_events" → collection "alex__topic__alex_events"
GENERIC_COLL_NAMESPACE=alex__topic__

# (Optional) Spotify credentials if your producer hits Spotify
CLIENT_ID=<...>
CLIENT_SECRET=<...>
USERNAME=<...>
SPOTIPY_CLIENT_ID=<...>
SPOTIPY_CLIENT_SECRET=<...>
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback

# Which producer file to run on `make run-<prefix>`
PRODUCER_ENTRY=src/producers/alex_producer.py

# Misc
DEBUG=true
KAFKA_ENABLED=true
```

**Rules of thumb**
- Always set `APP_PREFIX`, `KAFKA_TOPICS`, `GENERIC_COLL_NAMESPACE`, and `PRODUCER_ENTRY`.
- Only set `MONGO_COLL_EVENTS` / `MONGO_COLL_TOP10` if you actually produce that schema.
- Use `KAFKA_TOPIC_ROUTES` only when a topic must be parsed with a specific handler (`events`, `top10`). Everything else is stored RAW safely.

---

## 3) Start infrastructure

From `src/`:
```bash
make up                 # docker compose up -d (Kafka, ZK, Mongo, Mongo-Express)
make kafka-init-from-env  # create topics found in KAFKA_TOPICS from current .env
make kafka-list         # sanity-check topics
```

Useful debugging:
```bash
make kafka-tail-topic TOPIC=alex_events
make kafka-event-topic TOPIC=alex_events   # paste one JSON line, Ctrl+D
make kafka-delete-topic TOPIC=alex_events  # careful
```

---

## 4) Run consumer & your producer

Open two terminals in `src/`.

**A) Consumer (Kafka → Mongo)**
```bash
make consume           # runs: python -m consumers.kafka_consumer
```

**B) Your producer**

- If you have a template `.env` at `src/envs/.env.alex`:
```bash
make run-alex          # copies envs/.env.alex → .env, creates topics, runs PRODUCER_ENTRY
```
- Or with the current `.env` already in place:
```bash
python -m producers.alex_producer
# or: make run-avd   (Dorin's example producer)
```

**What the consumer does**
- Subscribes to **all topics listed in `KAFKA_TOPICS`** (so add yours there).
- For topics mapped in `KAFKA_TOPIC_ROUTES`:
  - `*:events` → normalized plays written to `MONGO_COLL_EVENTS` (or inferred)
  - `*:top10`  → snapshot docs written to `MONGO_COLL_TOP10` (or inferred)
- For everything else:
  - Writes RAW documents to **`<GENERIC_COLL_NAMESPACE><topic>`**, e.g. `alex__topic__alex_metrics`.

---

## 5) Streamlit UI

From `src/`:
```bash
make app
# or: python -m streamlit run app/streamlit_app.py
```

There are **two ways** to show data:

1) **Classic AVD tab** (`app/tabs/avd.py`)  
   - Set `MONGO_COLL_EVENTS` / `MONGO_COLL_TOP10` in `.env`.  
   - Displays Recent plays, Top artists/tracks, Daily plays, Plays per market, Top‑10 snapshots, and extra insights.

2) **Orchestrator with team tabs** (if you use it)  
   - `app/streamlit_app.py` loads tabs dynamically from `app/tabs/<prefix>.py`.  
   - Each tab module must expose `render(db, cfg, prefix)` and can read from collections derived from that prefix.

If you only push RAW topics under `GENERIC_COLL_NAMESPACE`, you can build a simple explorer tab that lists collections starting with your prefix and renders them (examples exist in `avd.py`).

---

## 6) Add your own producer (quick path)

1. Copy `src/producers/example_producer.py` → `src/producers/<prefix>_producer.py` and implement your logic.
2. Edit your `.env`:
   - `APP_PREFIX=<prefix>`
   - `KAFKA_TOPICS=<your_topic1>,<your_topic2>`
   - `PRODUCER_ENTRY=src/producers/<prefix>_producer.py`
   - `GENERIC_COLL_NAMESPACE=<prefix>__topic__`
3. Create topics and run:
```bash
make run-<prefix>      # example: make run-alex
make consume
make app
```

---

## 7) Troubleshooting

- **Topic keeps reappearing:** A producer can auto‑create topics if `allow.auto.create.topics=true`. Remove that in producer config or keep the topic.
- **UI section hidden:** It becomes visible only when the corresponding `MONGO_COLL_*` env var is set (and collection has documents).
- **Nothing is inserted:** Check `KAFKA_TOPICS`, `KAFKA_BOOTSTRAP`, and consumer logs; tail your topic with `make kafka-tail-topic`.
- **Auth errors in Spotify:** match `SPOTIPY_*` with `CLIENT_ID/SECRET`, and keep the same `REDIRECT_URI` in the Spotify app settings.
- **Do not commit secrets:** only commit `.env.example` and `envs/.env.<prefix>.example` templates.

---


