
# Project Setup Guide


---

## 1) Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for running producer/consumer locally outside containers)
- Spotify Developer credentials (per teammate): `CLIENT_ID`, `CLIENT_SECRET`, `REDIRECT_URI`
- A personal `.env` file in `src/` (keep it local, do not commit)

### Repository layout (relevant parts)
```
/src
  /app/                    # Streamlit UI
  /consumers/              # Kafka → Mongo consumer(s)
    kafka_consumer.py
  /lib/                    # shared helpers & dataclasses
    kafka_producer.py
    spotify_payloads.py
  /producers/              # Spotify → Kafka producer(s)
    avd_producer.py
    example_producer.py
  docker-compose.yml       # infra: Zookeeper, Kafka, Mongo, Mongo-Express
  makefile                 # run targets
```

---

## 2) Environment

Place your runtime variables in `src/.env` or export them in your shell. Typical keys:

```ini
# Spotify
CLIENT_ID=...
CLIENT_SECRET=...
USERNAME=...
REDIRECT_URI=http://localhost:8080/callback

# Market/country
MARKET_OVERRIDE=AT  # optional; defaults to Spotify profile country

# Kafka & Mongo
KAFKA_BOOTSTRAP=localhost:9092
GROUP_ID=spotify-consumer
MONGO_URL=mongodb://root:example@localhost:27017/?authSource=admin
MONGO_DB=spotify_db

# Optional overrides (defaults exist in code)
TOPIC_EVENTS=avd_spotify_recent_events
TOPIC_TOP10=avd_artist_market_top_tracks
COLL_EVENTS=avd_recent_events
COLL_TOP10=avd_artist_market_top_tracks
DEBUG=true
```

---

## 3) Start infrastructure

From `src/`:

```bash
make up           # docker compose up -d (ZK, Kafka, Mongo, Mongo-Express)
make kafka-init   # create topics if missing
make kafka-list   # list topics
```

Docker Compose file: `src/docker-compose.yml`

Default topics created:
- `avd_spotify_recent_events`
- `avd_artist_market_top_tracks`

---

## 4) Run the pipeline

Open two terminals in `src/`:

**Terminal A — Consumer → Mongo**
```bash
make consume        # runs: python -m consumers.kafka_consumer
```

**Terminal B — Producer → Kafka**
```bash
make run            # runs: python -m producers.avd_producer
```

What happens:
- Producer publishes per-play events to **Kafka topic** `avd_spotify_recent_events`.
- Producer also publishes the **Top-10 snapshot for the dominant artist/market** to **Kafka topic** `avd_artist_market_top_tracks`.
- Consumer writes to MongoDB:
  - **Collection `avd_recent_events`** (append-only, unique on `(user_id, track_id, played_at)`).
  - **Collection `avd_artist_market_top_tracks`** (upsert on `(user_id, artist_id, market)`, plus index on `generated_at` DESC).

---

## 5) Streamlit dashboards (team tabs)

### 5.1 Run the dashboard
From `src/`:
```bash
.venv/bin/streamlit run app/streamlit_app.py
# or: make app

### 5.2 Configure teammates and tab labels

Example configuration (src/app/team_config.yaml):


### 5.3 Add a new tab

Each teammate has a Python file under src/app/tabs/.

Example (src/app/tabs/avd.py)

---

## 6) Add your own producer

1. Create a producer under `src/producers/<prefix>_producer.py`.
2. Publish to your own topic(s) (use a personal prefix to avoid collisions).
3. Extend the consumer in `src/consumers/kafka_consumer.py` (subscribe to your topic; route messages to a collection with your prefix; add indexes).
4. Optionally add a Streamlit tab or a separate app file.

Example Makefile snippet:
```make
run-alex:
	$(PY) -m producers.alex_producer
```

---


## 7) Team demo plan

Each teammate runs their own producer against their own Spotify account (with their personal `.env`).  
For a single-laptop demo, you can import Mongo backups from everyone into one Mongo instance. **Prefixes** avoid collisions.  

- Use Makefile run targets (e.g. `make run-avd`, `make run-alex`) to switch identities quickly.  
- Streamlit can either show one user’s data only (default `streamlit_app.py`) or be extended with tabs per prefix.  

---

## 8) Security

- Never commit any `.env` file or tokens.  
- If you back up Mongo, do not share raw dumps publicly — keep them within the team or anonymize them.  

---

## 9) How to add your own producer

Each team member can implement their own Kafka producer without interfering with others.  
The convention is to use your own prefix (e.g., `avd_`, `alex_`, etc.) for both Kafka topics and MongoDB collections.

### Steps

**1. Create your producer file**  
- Copy `src/producers/example_producer.py` as a template.  
- Save it as `src/producers/<yourname>_producer.py`.  
- Adjust the code to produce your own events, using your prefix.

**2. Define your Kafka topic(s)**  
- Choose a topic name with your prefix, e.g. `alex_recent_events`.  
- In the Makefile, add a run target, for example:  
```make
run-alex:  # run producer with Alex's env
	$(PY) -m producers.alex_producer
```

**3. Configure MongoDB collection**  
- Make sure the consumer writes to a collection with your prefix (e.g., `alex_recent_events`).  
- This avoids collisions between users.

**4. Add your Streamlit dashboard (optional)**  
- Create `src/app/streamlit_app_<yourname>.py`.  
- You can copy `streamlit_app.py` and adapt it to your data.

**5. Test**  
```bash
make up
make run-alex
make consume
.venv/bin/streamlit run src/app/streamlit_app_alex.py
```

Following this pattern, each teammate can work independently but still share the same infrastructure.

---


## 10) Troubleshooting

- If Kafka just started, run `make kafka-init` after a short wait.
- If offsets are stuck, change `GROUP_ID` to replay from scratch.
- If index conflicts occur, drop the dev collection once; consumer recreates indexes idempotently.
- `__consumer_offsets` is Kafka’s internal topic — ignore it.
