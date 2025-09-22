# Project Setup Guide

This document explains how the current project works (mine = Dorin’s part), and how each teammate can add their own user stories without interfering with others.

---

## 0) Current State (mine)

The project already implements ingestion for my two user stories:

- **US1 (Leaderboard / Recent Plays):**
  - `avd_recent_events` in Kafka → `avd_recent_events` collection in Mongo
  - Each play (user_id + track_id + played_at) is stored as an event.
  - Deduplicated by index `(user_id, track_id, played_at)`

- **US2 (Top 10 Tracks for Dominant Artist in Market):**
  - `avd_artist_market_top_tracks` in Kafka → `avd_artist_market_top_tracks` in Mongo
  - One document per run with **Top 10 tracks** for the most played artist in the last 50 plays.
  - Upsert key: `(user_id, artist_id, market)` → always keeps the latest snapshot.

---

## 1) Repository Structure (important files)

- `src/DE-Spotify.py` → Producer (Spotify → Kafka)  
- `src/kafka_consumer.py` → Consumer (Kafka → Mongo)  
- `src/spotify_payloads.py` → Payload schemas/builders  
- `src/kafka_producer.py` → Utility for publishing to Kafka  
- `src/makefile` → Defines targets (`make run`, `make consume`, etc.)  
- `docker-compose.yml` → Runs Kafka, Zookeeper, and Mongo  

---

## 2) Environment Variables (`.env`)

Each member needs their own `.env` file:

```ini
CLIENT_ID=...
CLIENT_SECRET=...
USERNAME=...
REDIRECT_URI=...

MARKET_OVERRIDE=AT   # Optional; defaults to Spotify profile country

KAFKA_ENABLED=true
KAFKA_BOOTSTRAP=localhost:9092

MONGO_URL=mongodb://root:example@localhost:27017/?authSource=admin
MONGO_DB=spotify_db
GROUP_ID=spotify-consumer

DEBUG=true
```

---

## 3) Infrastructure Setup

1. Start Kafka, Zookeeper, and Mongo:
   ```bash
   docker compose up -d
   ```

2. Create Kafka topics via `make run`.

3. Start the consumer:
   ```bash
   make consume
   ```

4. Run the producer:
   ```bash
   make run
   ```

---

## 4) Naming Convention (critical)

To avoid mixing data:  
- **My data (Dorin) is always prefixed with `avd_`**:
  - Topics: `avd_recent_events`, `avd_artist_market_top_tracks`
  - Mongo collections: `avd_recent_events`, `avd_artist_market_top_tracks`

Each teammate must use their **own prefix** (e.g., `ap_`, `vs_`, etc.).

Example for Alex Popescu (`ap`):
- Topic: `ap_playlist_quality`
- Collection: `ap_playlist_quality`

---

## 5) Adding Your Own User Story

Each teammate must:

### A) Define a New Kafka Topic
- In the `makefile`, add a line in the Kafka topic creation section:
  ```make
  docker exec -it kafka kafka-topics --create --if-not-exists     --topic ap_playlist_quality --bootstrap-server localhost:9092     --partitions 1 --replication-factor 1
  ```

### B) Add a Payload Schema
- In `src/spotify_payloads.py`, add a **new dataclass** for your payload.
- Use the same style as `SpotifyPlayEvent` but with fields relevant to your user story.
- Add a builder function for creating your payload from Spotify API data.

### C) Extend the Producer
- In `src/DE-Spotify.py`, after my code finishes producing, add your own logic:
  - Fetch from Spotify API (or reuse my access tokens).
  - Build your payload with your builder function.
  - Send to your topic with `KafkaJsonProducer`.

### D) Extend the Consumer
1. In `_build_mongo()` (inside `kafka_consumer.py`):
   - Add a handle for your collection:
     ```python
     c_ap = db["ap_playlist_quality"]
     ```
   - Add indexes:
     - For events: unique key like `(user_id, played_at, track_id)`
     - For snapshots: upsert key like `(user_id, playlist_id)`

2. In `consumer.subscribe([...])`:
   - Add your topic to the list.

3. In the main loop (router by `topic`):
   - Add a branch:
     ```python
     elif topic == "ap_playlist_quality":
         _upsert_ap_playlist_quality(c_ap, payload)
     ```

4. Write `_upsert_ap_playlist_quality()` function to insert/upsert.

### E) Document Your Story
- Copy the template from `docs/_template_user_story.md`.
- Fill in your details and save as `docs/<prefix>_user_story.md`.

---

## 6) How to Verify Your Data

Check that your producer and consumer work:

1. Run producer (`make run`) and consumer (`make consume`).
2. Verify Kafka logs:
   - Should show `[KAFKA] Sent ... to <topic>`
3. Verify Mongo logs:
   - Should show `[MONGO] Inserted from <topic> ...`
4. Check MongoDB:
   ```bash
   docker exec -it mongo mongosh "mongodb://root:example@mongo:27017/spotify_db?authSource=admin"      --eval 'db.ap_playlist_quality.findOne()'
   ```

---

## 7) Summary

- **My topics/collections**: `avd_recent_events`, `avd_artist_market_top_tracks`  
- **Your topics/collections**: must use your own prefix (`ap_`, `vs_`, etc.)  
- Each user story = new topic + new collection + payload schema + producer logic + consumer handler.  
- Never modify mine — only add your own sections.
