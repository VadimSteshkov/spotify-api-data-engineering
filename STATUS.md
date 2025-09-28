# Project Status — Spotify Data Engineering (as of 28‑Sep‑2025)

This file summarizes the **current state of the repo**, what works end‑to‑end, what changed recently, and what we plan next. It reflects the code you have in `main`/`avd-branch` today (Kafka + Mongo ingestion working, plus the Streamlit dashboard).

---

## What works end‑to‑end (mine = Dorin’s part, prefix `avd_`)

### 1) Ingestion from Spotify → Kafka
- The producer pulls **recently played tracks** using the Spotify API and builds one **event per play**.
- Events are published to Kafka topic: **`avd_spotify_recent_events`**.
- Event schema (simplified):
  ```json
  {
    "event_version": "1.0",
    "event_type": "recent_play",
    "generated_at": "...",
    "user_id": "...",
    "country": "AT",
    "market_used": "DE",
    "played_at": "2025-09-22T07:58:49.561Z",
    "track_id": "...",
    "track_name": "...",
    "track_duration_ms": 123456,
    "album_id": "...",
    "album_name": "...",
    "album_release_date": "...",
    "artist_ids": ["..."],
    "artist_names": ["..."]
  }
  ```

### 2) Kafka → MongoDB consumer (idempotent writes)
- Topic **`avd_spotify_recent_events`** → collection **`avd_recent_events`** (append‑only).
- Unique index: **`(user_id, track_id, played_at)`** ensures **no duplicates** when re‑processing.
- Topic **`avd_artist_market_top_tracks`** → collection **`avd_artist_market_top_tracks`** (snapshot per `(user_id, artist_id, market)`).
- Upsert key for snapshots: **`(user_id, artist_id, market)`**, keeping only the latest document for that triplet.

### 3) Dominant artist & Top‑10 by market (my second user story)
- The producer computes the **dominant artist** from the last 50 plays, then fetches **Top‑10** tracks for a selected market and publishes a snapshot to **`avd_artist_market_top_tracks`**.
- The consumer **upserts** into Mongo (one doc per `(user, artist, market)`).

### 4) Streamlit dashboard (new)
- App file: **`src/app/streamlit_app.py`**.
- Reads directly from MongoDB (no Kafka needed to view historical data).
- Pages/sections:
  - **Recent plays** (table, with UTC time)
  - **Top artists** (bar chart by play counts)
  - **Top tracks** (bar chart by play counts)
  - **Latest Top‑10 docs** (expandable rows to see tracks inside the snapshot)
- Date range filtering (UTC) + simple caching for snappy UX.

---

## Key files in the repo

- **`src/DE-Spotify.py`** — Spotify producer (API → Kafka).
- **`src/kafka_consumer.py`** — Kafka consumer (Kafka → MongoDB).
- **`src/spotify_payloads.py`** — Payload dataclass & builders for per‑play events.
- **`src/kafka_producer.py`** — Small helper used by the producer to push JSON to Kafka.
- **`src/app/streamlit_app.py`** — Streamlit dashboard reading from Mongo.
- **`src/makefile`** — Commands for Docker, topics, produce/consume, and helpers (see Setup).
- **`docker-compose.yml`** — Zookeeper, Kafka, MongoDB, Mongo‑Express.

---

## Topics & collections (mine)

| Layer  | Mine (prefix `avd_`)                  | What it’s for                                  |
|--------|---------------------------------------|------------------------------------------------|
| Kafka  | `avd_spotify_recent_events`          | Per‑play events                                |
| Kafka  | `avd_artist_market_top_tracks`       | Top‑10 snapshot for dominant artist/market     |
| Mongo  | `avd_recent_events`                  | Append‑only, dedup by (user,track,played_at)   |
| Mongo  | `avd_artist_market_top_tracks`       | One doc per (user, artist, market), latest only|

> `__consumer_offsets` is Kafka’s internal system topic — **do not delete**.

---

## Recent changes (high‑level)

- **Makefile refactor**:  
  - Introduced `KAFKA_CONTAINER` variable (defaults to `kafka`) to avoid hardcoding the container name.
  - Grouped topic commands (`kafka-init`, `kafka-list`, `kafka-delete`).
  - Added **env helpers**: `env-avd`, `env-alex`, `env-bogdan` and **one‑shot run targets** `run-avd`, `run-alex`, `run-bogdan` (copy team‑specific `.env.*` before running).
- **Streamlit** app added under `src/app` with Mongo queries that are safe for the array fields (`artist_ids`, `artist_names`).
- **Mongo indexes** are idempotent and aligned with the payloads.

---

## How we validate

- Kafka: `make kafka-list`, `make kafka-init`, console producer/consumer smoke tests.
- Mongo: quick `mongosh` queries to inspect documents and verify indexes.
- Streamlit: run locally and filter by date; see bar charts populate.

---

## Known quirks & troubleshooting

- **Kafka "Broker may not be available"** right after `docker compose up`: wait a few seconds; if it persists → `make down && make up` then `make kafka-init`.
- **Zookeeper timeouts**: same as above; check container health with `docker ps` and `docker logs`.
- **Topic with underscore warning**: benign in our single‑broker dev setup.
- **Duplicate index names** in Mongo: the consumer already handles index creation idempotently. If you changed names manually in the past, drop the old index or drop the collection once (dev only).

---

## Next steps (proposal)

- **Team stories**: each colleague adds their **own topics & collections** using a personal prefix (see Setup Guide).
- **Streamlit**: add tabs per teammate, and market/date filters across all widgets.
- **(Optional)** Spark Structured Streaming from Kafka for near‑real‑time aggregations.
- **Notebook**: one Jupyter file documenting the pipeline with screenshots, sample queries, and references to code paths.

---

## Data & privacy notes

- OAuth tokens are per‑user; never commit your `.env`.
- Team demo can be done on one laptop by importing multiple Mongo DBs (each with separate prefixes) and switching `.env` with Make targets (`run-avd`, `run-alex`, …).
