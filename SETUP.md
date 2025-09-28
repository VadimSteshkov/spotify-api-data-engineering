# Project Setup Guide (with team onboarding)

This guide explains how to **run the project**, how **my** part (Dorin, prefix `avd_`) works, and how teammates can plug in their **own user stories** without interfering. All steps are **Docker‑first**; local installs are optional.

---

## 1) Prerequisites

- Docker & Docker Compose
- Python 3.11+ (only if you want to run producer/consumer locally, outside of containers)
- Spotify Developer credentials (per teammate): `CLIENT_ID`, `CLIENT_SECRET`, `REDIRECT_URI`
- A personal `.env` with your Spotify auth settings (never commit it).

Repo layout (top‑level):
```
/docs
/notebooks
/src
  /app                 # Streamlit UI
  docker-compose.yml   # (sometimes placed at repo root; adapt paths accordingly)
  makefile
  DE-Spotify.py        # Producer
  kafka_consumer.py    # Consumer
  kafka_producer.py    # Kafka helper
  spotify_payloads.py  # Payload dataclasses
  mongo_init/          # (optional seed/init)
  envs/                # (optional) per-user env files, e.g. .env.avd, .env.alex
```
> Your actual repo may keep `docker-compose.yml` at root — both patterns work as long as Makefile paths match.

---

## 2) Environment management (per teammate)

Each teammate keeps **their own** `.env`. For team demos you can store copies in `src/envs/`:
```
src/envs/.env.avd
src/envs/.env.alex
```
**Important:** these files are **local only**; do not commit secrets.

### Example `.env` (minimal)
```ini
# Spotify
CLIENT_ID=...
CLIENT_SECRET=...
USERNAME=...
REDIRECT_URI=http://localhost:8080/callback

# Market/country
MARKET_OVERRIDE=AT

# Kafka & Mongo
KAFKA_ENABLED=true
KAFKA_BOOTSTRAP=localhost:9092
MONGO_URL=mongodb://root:example@localhost:27017/?authSource=admin
MONGO_DB=spotify_db
GROUP_ID=spotify-consumer

# Misc
DEBUG=true
```

### Makefile env helpers
The Makefile exposes convenience targets (copy your env then run):
```make
env-avd:      ## copy src/envs/.env.avd to src/.env
	cp src/envs/.env.avd src/.env

env-alex:
	cp src/envs/.env.alex src/.env


run-avd: env-avd run   ## run producer with Dorin's env
run-alex: env-alex run ## run producer with Alex's env

```
> If your Makefile doesn’t have these yet, add them (safe to include; they don’t affect others).

---

## 3) Start infrastructure

From `src/` (where the Makefile lives):
```bash
make up              # docker compose up -d (Kafka, ZK, Mongo, Mongo-Express)
make kafka-init      # creates topics if not existing
make kafka-list      # sanity check topics
```
**Defaults**
- `KAFKA_CONTAINER=kafka` (override if your container has a different name)
- Topics (mine): `avd_spotify_recent_events`, `avd_artist_market_top_tracks`

If `kafka-init` prints “Broker may not be available”, wait a few seconds. If still failing:
```bash
make down && make up && make kafka-init
```

---

## 4) Run the pipeline (mine)

Open **two terminals** in `src/`:

**Terminal A — Consumer → Mongo**
```bash
make consume   # runs kafka_consumer.py (idempotent upserts)
```

**Terminal B — Producer → Kafka**
```bash
make run       # runs DE-Spotify.py with your current src/.env
# or, if you use per-user env shortcuts:
make run-avd
# make run-alex
```

What happens:
- Producer sends **per‑play events** to `avd_spotify_recent_events`.
- Producer also sends **Top‑10 snapshot** for dominant artist to `avd_artist_market_top_tracks`.
- Consumer writes to Mongo:
  - `avd_recent_events` (unique key `(user_id, track_id, played_at)`)
  - `avd_artist_market_top_tracks` (upsert key `(user_id, artist_id, market)`)

---

## 5) Streamlit dashboard

Run locally (from repo root or `src/` — adjust path accordingly):
```bash
# inside the project venv (recommended):
.venv/bin/streamlit run src/app/streamlit_app.py
# or, if streamlit is installed globally:
streamlit run src/app/streamlit_app.py
```
What you get:
- **Recent plays** table (UTC time), **Top artists**, **Top tracks** bar charts.
- **Latest Top‑10** snapshot viewer.
- Date filters & page‑level caches.

> The app expects the collections to be named like mine. If teammates add their own collections, they can either extend the app with tabs or spin a separate app file for their prefix.

---

## 6) Add **your** user story (template & steps)

### Naming convention (critical)
Use **your own prefix** everywhere (Kafka topic name + Mongo collection name). Example for Alex (`ap_`):
- Topic: `ap_playlist_quality`
- Collection: `ap_playlist_quality`

### Files to touch
1) **`src/spotify_payloads.py`**
   - Add a **dataclass** for your event/snapshot payload(s).
   - Add **builder(s)** that turn Spotify JSON into your dataclass(es).

2) **`src/DE-Spotify.py`** (producer)
   - After/around my code paths, call your Spotify API, build your payload(s), then publish to **your** topic using the existing Kafka helper.

3) **`src/kafka_consumer.py`** (consumer)
   - In `_build_mongo()`: create **your** collection and indexes (unique key for events; upsert key for snapshots).
   - In `subscribe([...])`: add **your** topic.
   - In the message router: add a handler like `_upsert_ap_playlist_quality(...)` to insert/upsert in your collection.

4) **`docs/_template_user_story.md`** → copy to `docs/<prefix>_user_story.md` and fill it in.

> Do **not** rename or modify my topics/collections; add your own in parallel. This keeps data clean for each teammate.

---

## 7) Quick Mongo sanity checks

```bash
# One recent play
docker exec -it mongo mongosh "mongodb://root:example@mongo:27017/spotify_db?authSource=admin" \
  --eval 'db.avd_recent_events.findOne({}, {track_name:1, artist_names:1, played_at:1, _id:0})'

# Top artists by plays
docker exec -it mongo mongosh "mongodb://root:example@mongo:27017/spotify_db?authSource=admin" \
  --eval 'db.avd_recent_events.aggregate([{$unwind:"$artist_ids"},{$group:{_id:"$artist_ids",plays:{$sum:1}}},{$sort:{plays:-1}},{$limit:10}]).toArray()'

# Latest Top-10 doc
docker exec -it mongo mongosh "mongodb://root:example@mongo:27017/spotify_db?authSource=admin" \
  --eval 'db.avd_artist_market_top_tracks.find().sort({generated_at:-1}).limit(1).pretty()'
```

---

## 8) Troubleshooting

- **Kafka “Broker may not be available”**: containers might still be starting. `make down && make up`, then `make kafka-init`.
- **Consumer stuck / offsets**: stop `make consume`, start again; for full replay create a **new** consumer group (`GROUP_ID`) or reset offsets.
- **Topic cleanup** (dev only): `make kafka-delete TOPIC=name` to remove a bad topic; then `make kafka-init`.
- **Mongo index conflicts**: if you changed index names manually earlier, drop the collection in dev and let the consumer recreate clean indexes.
- **`__consumer_offsets`**: Kafka’s system topic, expected to be there.

---

## 9) Team demo plan

- Each teammate runs **their own** producer against **their own** Spotify account (with their `.env`).
- For a single‑laptop demo, you can **import Mongo backups** from everyone into one Mongo instance. Prefixes avoid collisions.
- Use the Makefile env helpers (`run-avd`, `run-alex`) to switch identities quickly.
- Streamlit can either show **Dorin’s** data only (current file) or be extended with tabs for each prefix.

---

## 10) Security

- Never commit any `.env` or tokens.
- If you back up Mongo, do not share raw dumps publicly — keep them within the team or anonymize.


## 11) How to add your own producer

Each team member can implement their own Kafka producer without interfering with others.  
The convention is to use your own prefix (e.g., `avd_`, `alex_`, etc.) for both Kafka topics and MongoDB collections.

### Steps

1. **Create your producer file**  
   - Copy the existing `src/kafka_producer.py` or `src/topic_producer/example_producer.py` as a template.  
   - Save it as `src/topic_producer/<yourname>_producer.py`.  
   - Adjust the code to produce your own events.

2. **Define your topic(s)**  
   - Choose a topic name with your prefix, e.g. `alex_recent_events`.  
   - In `makefile`, add an entry under the Kafka section:  
     ```make
     run-alex:  # run producer with Alex's env
     	.venv/bin/python3 src/topic_producer/alex_producer.py
     ```

3. **Configure MongoDB collection**  
   - Make sure your consumer writes to a collection with your prefix (e.g., `alex_recent_events`).  
   - This avoids collisions between users.

4. **Add your Streamlit dashboard (optional)**  
   - Create `src/app/streamlit_app_<yourname>.py`.  
   - You can copy `streamlit_app.py` and adapt it to your data.

5. **Test**  
   - Run `make up` to start the infra.  
   - Run your producer (`make run-alex`) to push events.  
   - Start your consumer (`make consume`) and confirm events reach MongoDB.  
   - Launch your dashboard with:  
     ```bash
     .venv/bin/streamlit run src/app/streamlit_app_alex.py
     ```

Following this pattern, each teammate can work independently but still share the same infrastructure.

