# Run and Start Guide

This document explains how to set up, run, and verify the Spotify Kafka project.

## Prerequisites

Make sure you have the following installed on your system:

- Python 3.10+ (with `venv`)
- Docker and Docker Compose
- `kcat` (Kafka CLI client, sometimes called kafkacat)

On Ubuntu/Debian you can install with:

```bash
sudo apt install python3 python3-venv python3-pip kcat
```

For Docker and Compose, follow official installation guides or use:

```bash
sudo apt install docker.io docker-compose-plugin
```

Make sure your user is in the `docker` group or run docker commands with `sudo`.

---

## Setup the Python environment

Clone the repository and create a virtual environment:

```bash
git clone <your_repo_url>
cd spotify-api-data-engineering
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Environment configuration

Copy `.env.example` to `.env` and fill in your Spotify API credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```ini
CLIENT_ID=your_spotify_client_id
CLIENT_SECRET=your_spotify_client_secret
USERNAME=your_spotify_username
REDIRECT_URI=http://localhost:8888/callback

DEBUG=true

KAFKA_ENABLED=true
KAFKA_BOOTSTRAP=localhost:9092
```

⚠️ **Do not commit your `.env` file** (it is in `.gitignore`).

---

## Start Kafka with Docker Compose

Launch Zookeeper and Kafka containers:

```bash
sudo docker compose up -d
```

Check containers:

```bash
docker ps
```

You should see `zookeeper` and `kafka` running.

---

## Initialize Kafka topics

Create required topics (only once):

```bash
make kafka-init
```

This will create:
- `spotify_recent_events`
- `spotify_recent_snapshot`

Verify:

```bash
make kafka-list
```

---

## Run the application

# in prj folder
sudo docker compose down -v
sudo docker compose up -d
sudo docker compose ps
# wait for zookeeper = Up (healthy) and kafka = Up


Start the main program:

```bash
make run
```

This will:
- fetch Spotify "recently played" tracks
- print leaderboards and album details
- send JSON events and snapshots to Kafka if enabled

If Kafka is enabled, you should see:

```
[KAFKA] Sent N events to spotify_recent_events and 1 snapshot to spotify_recent_snapshot
```

---

## Consume messages from Kafka

You can read the produced messages with `kcat`:

### Stream events
```bash
make kafka-events
```

### Snapshot (last 50 plays)
```bash
make kafka-snapshot
```

---

## Project layout

```
.
├── DE-Spotify.py          # Main application
├── schemas/
│   ├── spotify_payloads.py  # JSON schema definitions
│   └── kafka_producer.py    # Kafka producer wrapper
├── docker-compose.yml     # Kafka/Zookeeper setup
├── makefile               # Helper commands
├── requirements.txt       # Python dependencies
├── run-and-start.md       # This file
└── .env                   # Local config (ignored in git)
```

---

## Makefile targets

- `make kafka-init` — create topics
- `make kafka-list` — list topics
- `make kafka-events` — consume from `spotify_recent_events`
- `make kafka-snapshot` — consume from `spotify_recent_snapshot`
- `make run` — run the Python app

---

## Troubleshooting

- If Kafka connection fails, ensure containers are running: `docker ps`
- If `kcat` shows nothing, check that `KAFKA_ENABLED=true` in `.env`
- If Spotify auth fails, regenerate token with correct `REDIRECT_URI`

---

## Next steps

- Integrate Spark streaming to consume these topics
- Create visualizations (dashboards) of play patterns
- Extend schemas if needed (e.g., enrich with audio features)
