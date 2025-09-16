# Project Status – Data Engineering Spotify

## ✅ Current Progress

### Data Ingestion
- Data is successfully ingested from the **Spotify API**:
  - Retrieve **tracklist of an album** (title + duration).
  - Retrieve **top tracks of an artist**.
  - Retrieve **recently played tracks** and push events into **Kafka**.
- **Infrastructure (Kafka/Zookeeper)**:
  - `docker-compose.yml` available to spin up services.
  - `makefile` provided to initialize and list topics (`spotify_recent_events`, `spotify_recent_snapshot`).
  - Kafka ingestion tested: events are visible in the terminal (`kcat`).
- **Documentation**:
  - `run-and-start.md` explains how to set up the environment, `.env`, Docker, and Makefile usage.

## Implemented User Stories (so far, from Dorin)

1. **As a user, I want to see the tracklist of an album with titles and duration, so I can decide which songs to listen to first.**  
   - Implemented by fetching full album tracklists from the Spotify API.  
   - The system prints **each song title and its duration** for the albums detected in the user’s listening history.  
   - Albums are identified automatically from the **last 50 tracks played**.  
   - Each album is displayed with:  
     - Album title and release date.  
     - Complete list of songs (title + duration).  
     - Total runtime of the album.  
   - Example from output:  
     ```
     === Album #2: A Iesit Soarele Din Nori — Florin Salam (release: 2015-05-21) ===
     01. A Iesit Soarele Din Nori (03:41)
     02. Viata Mea E Si Buna Si Rea (04:27)
     ...
     --- Total album length: 60:33 ---
     ```  
   - Implemented with the **market parameter** (e.g., `AT`) to ensure that the tracklist reflects availability in the user’s country.  

2. **As a music fan, I want to fetch the top tracks of an artist, so I can quickly get an overview of their most popular songs.**  
   - Implemented via the Spotify API endpoint for an artist’s top tracks.  
   - The system automatically selects the **dominant artist** (most frequently played) from the user’s recent history.  
   - Then it retrieves and prints the **Top 10 tracks** of that artist, including title and duration.  
   - Example from output:  
     ```
     === Top 10 tracks for Tzanca Uraganu (market=AT) ===
     01. Tu blondina,eu brunet — Tzanca Uraganu (02:25)
     02. Damelo — Tzanca Uraganu, Mr. Juve (02:37)
     ...
     ```  
   - The **market parameter** ensures that the top tracks list is relevant to the user’s country (e.g., AT = Austria).  
   - This gives the user an accurate view of the artist’s popularity in their region.  

---

⚠️ **Note:** At this point, only Dorin’s user stories have been implemented. Other team members will add their own stories in the next iteration.

---

## 🔄 Next Steps
- **Real-time Processing (Spark Structured Streaming)**:
  - Consume events from Kafka (`spotify_recent_events`).
  - Compute aggregates such as top artists, top tracks, and time distribution of plays.
  - Persist results into storage.

- **Storage & Persistence**:
  - Decide on storage format: Parquet files, or a database (NoSQL/SQL).

- **Visualization (Streamlit)**:
  - Build a dashboard to display top artists and tracks.
  - Use simple charts (bar charts, timelines).

- **Documentation (Jupyter Notebook)**:
  - Create an end-to-end pipeline notebook: API → Kafka → Spark → Storage → Visualization.
  - Include screenshots, code snippets, and explanations.

- **Optional Enhancements**:
  - Extend `docker-compose.yml` with Spark, database, and Streamlit services.
  - Automate the entire pipeline for one-command startup.

---

## 📌 Conclusion
- Current stage: **Data ingestion + Kafka working** ✅  
- Next stage: **Spark Streaming for real-time processing and storage**.  
- Final stage: **Visualization and documentation** to deliver a complete project that satisfies the professor’s requirements.

