Stage 1 – Requirements & Use Cases (Spotify Data Engineering Project)

Objective
The project uses the Spotify REST API to collect and analyze data about artists, tracks, albums, and audio features (danceability, energy, etc.), then processes and visualizes them in a dashboard.

Functional Requirements (FR)
- FR1: Connect to Spotify API and collect data (artists, albums, tracks, audio features).
- FR2: Store raw data in MongoDB (raw.*).
- FR3: Process data with Spark → curated collections (curated.*).
- FR4: Simulate “play” events via Kafka and process them in real-time.
- FR5: Build a Streamlit dashboard with visualizations (charts, top lists, correlations).
- FR6: Document the workflow in a Jupyter Notebook.

Non-Functional Requirements (NFR)
- NFR1: Data clarity and consistency.
- NFR2: Retry logic for API rate limits.
- NFR3: Idempotent runs (no duplicate or corrupted data).
- NFR4: Simplicity and reproducibility (everyone can run the code).

Use Stories
1. Als Musikjournalist will ich Trends bei neuen Releases analysieren, um Artikel über aktuelle Musikrichtungen schreiben zu können.
2. Als Festival-Organisator will ich wissen, welche Künstler in meiner Region am meisten gestreamt werden, um ein passendes Line-up zu planen.
3. Als Werbungstreibender will ich herausfinden, zu welchen Tageszeiten am meisten Musik gehört wird, um zielgerichtete Werbung zu schalten.
4. Als Fitness-Trainer will ich Playlists mit Songs hoher Energie zusammenstellen, um meine Kunden beim Training zu motivieren.
5. Als Event-Planer will ich wissen, welche Songs in einer Stadt am beliebtesten sind, um passende Musik auf Veranstaltungen zu spielen.

Data Model (simplified)
- MongoDB (NoSQL): raw.artists, raw.albums, raw.tracks, raw.audio_features, curated.*.
- Optional SQL (star schema): dim_artists, dim_albums, dim_tracks, fact_plays.

Project Plan (6 weekly stages)
1. Requirements & Useer Stories  (now).
2. Data Ingestion (batch API → MongoDB).
3. Data Processing (Spark → curated).
4. Streaming (Kafka → Spark).
5. Visualization (Streamlit).
6. Final Demo + Notebook.

