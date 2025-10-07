# Project Status — Docker‑only, Multi‑User Spotify Data Engineering

_Last updated: today_

---

## What’s running (Docker Compose)

- **Zookeeper** (`2181`), **Kafka** (`9092`), **MongoDB** (`27017`), **Mongo‑Express** (`8081`)
- **Producer** (module from `PRODUCER_ENTRY`), **Consumer** (Kafka → Mongo), **Spark** (optional), **Streamlit App** (`8501`)

Internal container endpoints used by app/producer/consumer/spark:
- `KAFKA_BOOTSTRAP = kafka:19092`
- `MONGO_URL = mongodb://root:example@mongo:27017/?authSource=admin`

Host endpoints for tooling:
- Kafka: `localhost:9092`
- Mongo: `localhost:27017`
- UI: `http://localhost:8081` (Mongo‑Express), `http://localhost:8501` (Streamlit)

---

## Current AVD pipeline (example reference)

**Producer**: `producers/avd_producer.py`  
- Fetches recent plays from Spotify and computes Top‑10 for the dominant recent artist (per market).  
- Publishes to topics listed in `.env` such as:
  - `avd_spotify_recent_events` (events)
  - `avd_artist_market_top_tracks` (top‑10 snapshot)

**Consumer**: `consumers/kafka_consumer.py`  
- Subscribes to **all** topics from `KAFKA_TOPICS`.  
- Routing:
  - `KAFKA_TOPIC_ROUTES`: `*:events` → normalized plays → **MONGO_COLL_EVENTS** (or inferred)
  - `KAFKA_TOPIC_ROUTES`: `*:top10`  → snapshots → **MONGO_COLL_TOP10** (or inferred)
  - Any other topic → RAW doc to **`<GENERIC_COLL_NAMESPACE><topic>`**.

**Mongo**
- Classic collections (if configured): `avd_spotify_recent_events`, `avd_artist_market_top_tracks`
- Generic RAW examples: `avd__topic__<your_topic>`

**Streamlit**
- App: `app/streamlit_app.py` (loads tabs from `app/tabs/`)
- Dorin’s tab: `app/tabs/avd.py` (shows Recent plays, Top artists/tracks, Daily, Per‑market, Top‑10 snapshots, extra insights).

---

## Makefile highlights (docker‑only)

- Infra: `make up | down | logs`
- Kafka utils: `make kafka-init-from-env`, `kafka-list`, `kafka-tail-topic TOPIC=...`, `kafka-event-topic TOPIC=...`, `kafka-delete-topic TOPIC=...`
- Producer: `make producer-build`, `make producer-run`, `make producer-logs`
- Consumer: `make consumer-build`, `make consumer-run`
- Spark: `make spark-build`, `make spark-up`, `make spark-logs`, `make spark-down`
- App: `make app-build`, `make app-up`, `make app-logs`, `make app-stop`
- Quick demos: `make avd-demo` (Dorin), `make demo` (with existing `.env`)
- Env helpers: `make avd-env | alex-env | gilian-env | vadim-env`, or `make env-user USR=<prefix>`, and `make show-env`

---

## How a teammate onboards (their own pipeline)

1. Create `src/envs/.env.<prefix>` (and **do not** commit secrets). Set at least:
   - `APP_PREFIX=<prefix>`
   - `KAFKA_TOPICS=<topic_a>,<topic_b>`
   - `GENERIC_COLL_NAMESPACE=<prefix>__topic__`
   - `PRODUCER_ENTRY=<prefix>_producer`
   - (optional) `MONGO_COLL_EVENTS` / `MONGO_COLL_TOP10`
2. Add `producers/<prefix>_producer.py` and publish to those topics.
3. Run:
```bash
cd src
make env-user USR=<prefix>
make up && make kafka-init-from-env
make producer-build && make producer-run
make consumer-build && make consumer-run
make app-build && make app-up
```
4. (Optional) Add `app/tabs/<prefix>.py` exposing `render(db, cfg, prefix)` for a custom UI.

---

## Next steps / ideas

- Document minimal examples for a generic RAW data explorer tab.
- Optional: enable schema-registry + Avro/JSON‑Schema if needed.
- Optional: CI to lint Dockerfiles and validate `envs/.env.*.example` templates.

---

## Changelog (this refactor)

- **Docker‑only migration**
  - Removed host/venv execution paths; all services run in containers.
  - New Dockerfiles for `app/`, `docker/producer.Dockerfile`, and `consumers/`.
  - Updated `spark/Dockerfile` to Java 21 JRE and PySpark pinned via `requirements.txt`.
  - Compose rewired for internal endpoints (`kafka:19092`, `mongo:27017`) and dev-friendly bind mounts.
- **Makefile overhaul**
  - Added `env-user`, per‑user shortcuts, and `*-demo` flows.
  - Centralized Kafka helpers (`kafka-init-from-env`, tail/produce/delete).
  - Clean targets for producer/consumer/app/spark.
- **.gitignore hardened**
  - Ignore real `.env` everywhere; keep only `*.example`.
  - Ignore caches, build artefacts, logs, and local Mongo bind directories.
- **Docs**
  - This `SETUP.md` & `STATUS.md` now describe the Docker-only multi‑user workflow.
