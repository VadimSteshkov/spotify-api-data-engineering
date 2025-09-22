# User Story Documentation Template

This template must be copied and filled by each teammate.  
Save your file as: `docs/<prefix>_user_story.md`  
Example: `docs/ap_user_story.md`

---

## 1) User Story (text)

_As a [type of user], I want to [goal], so that [benefit]._  

Example:  
_As a user, I want to know if my playlists are good for parties (danceability, energy) so I can pick better music._

---

## 2) Kafka Topic

- **Topic name:** `<prefix>_<your_topic>`  
- Example: `ap_playlist_quality`

---

## 3) Mongo Collection

- **Collection name:** `<prefix>_<your_collection>`  
- Example: `ap_playlist_quality`

---

## 4) Payload Schema (fields)

List all fields your payload will contain. Example:

- `event_version`
- `event_type`
- `event_time`
- `user_id`
- `playlist_id`
- `avg_danceability`
- `avg_energy`

---

## 5) Producer Logic

- Where in `src/DE-Spotify.py` you add your code.
- Which API endpoints you use.
- How you transform raw data into your payload.

---

## 6) Consumer Logic

- Where in `src/kafka_consumer.py` you add your handler.
- Which indexes you define.
- Unique key / upsert strategy.

---

## 7) Example Mongo Query

Give a simple query to test your data. Example:

```bash
docker exec -it mongo mongosh "mongodb://root:example@mongo:27017/spotify_db?authSource=admin"   --eval 'db.ap_playlist_quality.find().limit(5).pretty()'
```

---

## 8) Notes

- Anything special about your user story.
- Edge cases, debug tips, etc.
