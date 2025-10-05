# Project Status — Generic, Multi‑User Spotify Data Engineering

_Last updated: today_

---

## Current pipeline (Dorin / `avd`)

**Producer**: `src/producers/avd_producer.py`  
- Pulls last 50 recent plays from Spotify and computes a "dominant artist Top‑10" for a market.  
- Publishes to Kafka topics listed in `.env`:
  - `avd_spotify_recent_events` (events)
  - `avd_artist_market_top_tracks` (top10 snapshot)

**Consumer**: `src/consumers/kafka_consumer.py`  
- Subscribes to **all** topics from `KAFKA_TOPICS` (env).  
- Routing:
  - Topics mapped in `KAFKA_TOPIC_ROUTES`:
    - `*:events`  → normalized plays → **`MONGO_COLL_EVENTS`** (or inferred)
    - `*:top10`   → snapshot docs → **`MONGO_COLL_TOP10`** (or inferred)
  - Others → RAW docs under **`<GENERIC_COLL_NAMESPACE><topic>`**.

**Mongo**
- Classic collections used by AVD tab:
  - `avd_recent_events` (historical) or `avd_spotify_recent_events` (new) — pick via `.env`
  - `avd_artist_market_top_tracks`
- Generic collections (examples): `avd__topic__alex_events`, etc.

**Streamlit**
- Orchestrator: `app/streamlit_app.py` (loads tab modules under `app/tabs/`).  
- Dorin’s tab: `app/tabs/avd.py` (robust schema handling; daily plays, per‑market, top artists/tracks, extra insights).

**Makefile highlights**
- `make up / down / logs`
- `make kafka-init-from-env` — create topics from `KAFKA_TOPICS`
- `make kafka-list` / `kafka-tail-topic TOPIC=...` / `kafka-event-topic TOPIC=...` / `kafka-delete-topic TOPIC=...`
- `make consume` — start Kafka→Mongo writer
- `make run-avd` — run Dorin’s producer
- `make run-<prefix>` — run teammate (uses `envs/.env.<prefix>` → `.env` then runs `PRODUCER_ENTRY`)

---

## How teammates add their pipeline

1) Create `src/envs/.env.<prefix>` with:
- `APP_PREFIX=<prefix>`
- `KAFKA_TOPICS=<topic_a>,<topic_b>`
- `GENERIC_COLL_NAMESPACE=<prefix>__topic__`
- `PRODUCER_ENTRY=src/producers/<prefix>_producer.py`
- (optional) `MONGO_COLL_EVENTS` / `MONGO_COLL_TOP10`

2) Write producer at `src/producers/<prefix>_producer.py` and publish to your topics.

3) Run:
```bash
make run-<prefix>    # copies envs/.env.<prefix> → .env, creates topics, runs producer
make consume
make app
```

4) (Optional) Add a Streamlit tab under `src/app/tabs/<prefix>.py` exposing `render(db, cfg, prefix)`.

---

## Open items / next steps

- Add a minimal **Generic Collections Explorer** tab that lists collections by `GENERIC_COLL_NAMESPACE` and shows last N docs.
- Optional Spark Structured Streaming job for real‑time aggregates per user/topic.
- CI guardrails: detect committed `.env` accidentally; run `flake8` / `ruff` on PRs.

---

## Changelog (most recent first)

- **Generic multi‑user refactor**
  - New env schema in `src/.env.example` with detailed comments.
  - `make run-%` / `kafka-init-from-env` / generic tail/produce/delete targets.
  - `app/tabs/avd.py` hardened (normalization, daily/market charts, extra insights, better caching).
  - Backward compatibility for AVD topics kept.
- Previous: initial single‑user pipeline (Spotify→Kafka→Mongo) + simple Streamlit dashboard.