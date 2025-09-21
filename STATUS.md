# Project Status – Data Engineering Spotify

## ✅ Current Progress

### Data Ingestion
- Data is successfully ingested from the **Spotify API**:
  - Retrieve **tracklist of an album** (title + duration).
  - Retrieve **top tracks of an artist**.
  - Retrieve **recently played tracks** and push events into **Kafka**.
- **Infrastructure (Kafka/Zookeeper/MongoDB)**:
  - `docker-compose.yml` spins up Kafka, Zookeeper, and MongoDB.
  - `makefile` initializes and lists topics (`spotify_recent_events`, `spotify_recent_snapshot`) and provides `consume` target.
  - Kafka ingestion tested: events visible via `kcat`.
  - MongoDB consumer added: events/snapshots are persisted into MongoDB (`kafka_consumer.py`).
- **Documentation**:
  - `run-and-start.md` explains setup for `.env`, Docker, and Makefile usage.
  - `STATUS.md` updated with today’s progress.

## Implemented User Stories (so far, from Dorin)

1. **As a user, I want to see the tracklist of an album with titles and duration, so I can decide which songs to listen to first.**  
   - Implemented by fetching full album tracklists from the Spotify API.  
   - The system prints **each song title and its duration** for the albums detected in the user’s listening history.  
   - Albums are identified automatically from the **last 50 tracks played**.  
   - Each album is displayed with:  
     - Album title and release date.  
     - Complete list of songs (title + duration).  
     - Total runtime of the album.  

2. **As a music fan, I want to fetch the top tracks of an artist, so I can quickly get an overview of their most popular songs.**  
   - Implemented via the Spotify API endpoint for an artist’s top tracks.  
   - The system automatically selects the **dominant artist** (most frequently played) from the user’s recent history.  
   - Then it retrieves and prints the **Top 10 tracks** of that artist, including title and duration.  
   - The **market parameter** ensures the list is relevant for the user’s country.  

3. **As a data engineer, I want to persist streaming data into MongoDB, so I can query and analyze later.**  
   - Implemented by adding `kafka_consumer.py`, which consumes from Kafka and inserts into MongoDB.  
   - Each insert is logged with a **UTC timestamp** using `datetime.now(timezone.utc)`.  
   - Verified end-to-end: Spotify API → Kafka → MongoDB.

---

⚠️ **Note:** At this point, only Dorin’s user stories have been implemented. Other team members will add their own stories in the next iteration.

---

## 🔄 Next Steps
- **Real-time Processing (Spark Structured Streaming)**:
  - Consume events from Kafka (`spotify_recent_events`).
  - Compute aggregates such as top artists, top tracks, and time distribution of plays.
  - Persist results into storage.

- **Storage & Persistence**:
  - Explore queries over MongoDB data.
  - Decide on additional storage format: Parquet files, or SQL/NoSQL DB.

- **Visualization (Streamlit)**:
  - Build a dashboard to display top artists and tracks.
  - Use simple charts (bar charts, timelines).

- **Documentation (Jupyter Notebook)**:
  - Create an end-to-end pipeline notebook: API → Kafka → MongoDB/Spark → Storage → Visualization.
  - Include screenshots, code snippets, and explanations.

- **Optional Enhancements**:
  - Extend `docker-compose.yml` with Spark and Streamlit services.
  - Automate the entire pipeline for one-command startup.

---

## 📌 Conclusion
- Current stage: **Data ingestion + Kafka + MongoDB working** ✅  
- Next stage: **Spark Streaming for real-time processing and storage**.  
- Final stage: **Visualization and documentation** to deliver a complete project that satisfies the professor’s requirements.

