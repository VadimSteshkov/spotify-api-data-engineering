
# Project Status — Spotify Data Engineering


---

## End-to-end pipeline (prefix `avd_`)

### 1) Spotify → Kafka (producer)
- Module: **`src/producers/avd_producer.py`** (invoked via `python -m producers.avd_producer`).
- Pulls last 50 recently played tracks; builds one event per play.
- Publishes per-play events to Kafka topic: **`avd_spotify_recent_events`**.

**Event schema (simplified):**
```json
{
  "event_version": "1.0",
  "event_type": "recent_play",
  "generated_at": "...",
  "user_id": "...",
  "country": "AT",
  "market_used": "DE",
  "played_at": "...",
  "track_id": "...",
  "track_name": "...",
  "album_id": "...",
  "album_name": "...",
  "album_release_date": "...",
  "artist_ids": ["..."],
  "artist_names": ["..."]
}
```

### 2) Kafka → MongoDB (consumer)
- Module: **`src/consumers/kafka_consumer.py`** (invoked via `python -m consumers.kafka_consumer`).
- Subscribes to:
  - `avd_spotify_recent_events`
  - `avd_artist_market_top_tracks`
- Writes to MongoDB:
  - **`avd_recent_events`** (append-only). Indexes:
    - Query index: `(user_id ASC, played_at DESC)`
    - Unique: `(user_id, track_id, played_at)`
  - **`avd_artist_market_top_tracks`** (snapshot per user/artist/market). Indexes:
    - Unique: `(user_id, artist_id, market)`
    - Sort index: `(generated_at DESC)`

### 3) Dominant artist & Top-10 snapshot
- Producer computes the dominant artist from the last 50 tracks, fetches Top-10 tracks for the market.
- Publishes snapshot to `avd_artist_market_top_tracks`.

### 4) Streamlit dashboard
- Module: **`src/app/streamlit_app.py`**.
- Pages: Recent plays, Top artists, Top tracks, latest Top-10 docs.

---

## Key files

- `src/producers/avd_producer.py` — Spotify producer
- `src/consumers/kafka_consumer.py` — Kafka → Mongo consumer
- `src/lib/spotify_payloads.py` — Payload dataclasses & builders
- `src/lib/kafka_producer.py` — Kafka helper
- `src/app/streamlit_app.py` — Streamlit dashboard
- `src/makefile` — Makefile (run & infra targets)
- `src/docker-compose.yml` — Infrastructure (ZK, Kafka, Mongo, Mongo-Express)

---

## Topics & collections

| Layer  | Name                               | Purpose                                    |
|--------|------------------------------------|--------------------------------------------|
| Kafka  | `avd_spotify_recent_events`        | Per-play events                             |
| Kafka  | `avd_artist_market_top_tracks`     | Top-10 snapshot (dominant artist / market) |
| Mongo  | `avd_recent_events`                | Append-only (unique `(user, track, played)`) |
| Mongo  | `avd_artist_market_top_tracks`     | One doc per `(user, artist, market)`       |

---

## Recent changes

- Refactored to package structure: producer in `producers/`, consumer in `consumers/`, helpers in `lib/`.
- Module entry points: run with `python -m producers.avd_producer` / `python -m consumers.kafka_consumer`.
- Makefile simplified: only core targets (`run`, `consume`, `app`, `up`, `down`, `kafka-init`, `kafka-list`).
- Documentation updated to match paths and defaults. Topic and collection names unchanged.

---

## Next steps

- Extend Streamlit with filters (market, date range) and separate tabs per teammate.
- Allow additional producers under `src/producers/` with personal prefixes.
- Optional: add Spark Structured Streaming for real-time aggregates.
