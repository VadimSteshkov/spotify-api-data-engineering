# SpotifyAPI – User Stories & Umsetzung

## Nutzerstories
1. Als Musiker möchte ich wöchentlich einen klaren Bericht erhalten, wie viele Streams jeder meiner Tracks und jedes Albums erzielt hat, um schnell zu sehen, was wächst oder fällt, und meine Promo anzupassen.  
2. Als DJ will ich Brücken zwischen Subgenres: eine kurze Liste mit 5 Tracks, die zwei Stile im Set nahtlos verbinden.  
3. Friend Match & Blind Spots: Ich will meine Playlists mit denen der Freunde vergleichen, gemeinsame Genres, einen Ähnlichkeitsscore und „Blind Spots“ sehen – was mir fehlt, bei Freunden aber gut läuft.  
4. Weekly Genre Drift & Activity Digest: Ich will jeden Montag einen 7-Tage-Digest mit Hörstunden, Genre-Verschiebung (↑/↓ je Wochentag), neu entdeckten Artists/Alben, meistgespielten/neu gespeicherten Alben sowie kurzen, trendbasierten Vorschlägen.

---
## Umsetzung (theoretisch + Links)

### 1) Musiker — Wöchentlicher Streams-Report (Tracks & Alben)
- **Endpunkte:**  
  - [Get Artist](https://developer.spotify.com/documentation/web-api/reference/get-an-artist)  
  - [Get Artist’s Albums](https://developer.spotify.com/documentation/web-api/reference/get-an-artists-albums)  
  - [Get Album](https://developer.spotify.com/documentation/web-api/reference/get-an-album)  
  - [Get Album Tracks](https://developer.spotify.com/documentation/web-api/reference/get-an-albums-tracks)  
  - [Get Track](https://developer.spotify.com/documentation/web-api/reference/get-track)
- **Scopes:** keine (nur öffentliche Katalogdaten) – Übersicht: [Scopes](https://developer.spotify.com/documentation/web-api/concepts/scopes)  
- **Takt:** täglich snapshotten → wöchentlich aggregieren  
- **Daten speichern:** `artist_id`, `album_id`, `track_id`, `track.popularity`, `album.release_date`, `snapshot_date`  
- **Output:** Weekly-Report (Top ↑/↓, Δ zur Vorwoche in %/absolut, Tagesverlauf)  
- **Hinweis:** Exakte Streamzahlen liefert die Web-API nicht; bei Bedarf S4A/Streaming-Export importieren, sonst Popularity-Proxy nutzen.

---

### 2) DJ — Subgenre-Brücken (5-Track-Bridge)
- **Endpunkte:**  
  - [Search for Item](https://developer.spotify.com/documentation/web-api/reference/search) (Suche nach Playlists/Tracks mit Subgenre-Keywords)  
  - [Get Playlist Items](https://developer.spotify.com/documentation/web-api/reference/get-playlists-tracks)
- **Scopes:** keine (öffentliche Playlists); optional für private Quellen: `playlist-read-private`, `playlist-read-collaborative` – siehe [Scopes](https://developer.spotify.com/documentation/web-api/concepts/scopes) & Hinweise zu [Playlists](https://developer.spotify.com/documentation/web-api/concepts/playlists)  
- **Takt:** on-demand oder wöchentlich  
- **Daten speichern:** `playlist_id`, `track_id`, Reihenfolge im Playlist-Kontext, `artist_id` (für Genre-Tags via Artist)  
- **Output:** Liste von 5 Tracks als Bridge A→B (direkt in eigene Playlist übernehmbar)

---

### 3) User — Friend Match & Blind Spots
- **Endpunkte:**  
  - [Get Current User’s Playlists](https://developer.spotify.com/documentation/web-api/reference/get-a-list-of-current-users-playlists)  
  - [Get User’s Playlists](https://developer.spotify.com/documentation/web-api/reference/get-list-users-playlists)  
  - [Get Playlist Items](https://developer.spotify.com/documentation/web-api/reference/get-playlists-tracks)  
  - [Get Artist](https://developer.spotify.com/documentation/web-api/reference/get-an-artist) (Genres)
- **Scopes:** für eigene private/Collab: `playlist-read-private`, `playlist-read-collaborative`; öffentliche Freund-Playlists ohne Scopes – [Scopes](https://developer.spotify.com/documentation/web-api/concepts/scopes)  
- **Takt:** on-demand / wöchentlich  
- **Daten speichern:** `user_id`, `playlist_id`, `track_id`, `artist_id`, `genres[]`  
- **Output:** Ähnlichkeitsscore (z. B. Jaccard), gemeinsame Genres, „Blind Spots“ (empfohlene Tracks/Artists aus Freund-Playlists, die dir fehlen)

---

### 4) User — Weekly Genre Drift & Activity Digest (7 Tage)
- **Endpunkte:**  
  - [Get Recently Played Tracks](https://developer.spotify.com/documentation/web-api/reference/get-recently-played) (laufend loggen; Beachte: liefert jeweils max. 50 Einträge)  
  - [Get Artist](https://developer.spotify.com/documentation/web-api/reference/get-an-artist) (Genres)  
  - optional: [Get User’s Top Items](https://developer.spotify.com/documentation/web-api/reference/get-users-top-artists-and-tracks)
- **Scopes:** `user-read-recently-played`, optional `user-top-read` – [Scopes](https://developer.spotify.com/documentation/web-api/concepts/scopes)  
- **Takt:** Polling alle X Minuten/Stunden → Digest montags  
- **Daten speichern:** `played_at`, `track_id`, angenäherte `minutes_listened` (≈ `duration_ms` pro Play), `artist_id`, `genres[]`, Flags `is_new_artist/album`  
- **Output:** Hörstunden je Tag, Genre-Pfeile (↑/↓), neu entdeckte Artists/Alben, meistgespielt/neu gespeichert, 3–5 trendbasierte Vorschläge  
---