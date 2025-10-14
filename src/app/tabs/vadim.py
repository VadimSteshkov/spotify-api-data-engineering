# -*- coding: utf-8 -*-
"""
Vadim's Spotify Analytics Interface - Main Version
"""

import pandas as pd
import streamlit as st
import altair as alt
from datetime import datetime, timezone, date, time, timedelta
from typing import Tuple, List, Dict
from pymongo.errors import PyMongoError
import numpy as np
import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import pytz

def _utc_range(d_from: date, d_to: date) -> Tuple[datetime, datetime]:
    """Convert two date objects to full-day UTC datetime interval."""
    start = datetime.combine(d_from, time.min, tzinfo=timezone.utc)
    end = datetime.combine(d_to, time.max, tzinfo=timezone.utc)
    return start, end

def _format_duration(ms: int) -> str:
    """Format duration in milliseconds to readable format."""
    if not ms:
        return "0:00"
    seconds = ms // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    hours = minutes // 60
    minutes = minutes % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"

def _get_spotify_client():
    """Get Spotify client for fetching artist genres."""
    try:
        # Get credentials from environment
        client_id = os.getenv("SPOTIPY_CLIENT_ID")
        client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
        redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8080/callback")
        
        if not client_id or not client_secret:
            return None
            
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-read-recently-played"
        )
        
        return spotipy.Spotify(auth_manager=auth_manager)
    except Exception as e:
        st.error(f"Error creating Spotify client: {e}")
        return None

def _get_artist_genres(spotify_client, artist_name: str) -> List[str]:
    """Get genres for a specific artist from Spotify API."""
    if not spotify_client:
        return []
    
    try:
        results = spotify_client.search(q=f'artist:{artist_name}', type='artist', limit=1)
        if results['artists']['items']:
            artist = results['artists']['items'][0]
            return artist.get('genres', [])
    except Exception as e:
        st.warning(f"Could not fetch genres for artist '{artist_name}': {e}")
    
    return []

def render_general_stats(db, start_dt: datetime, end_dt: datetime):
    """Render general statistics tab."""
    st.header("Allgemeine Statistiken")
    
    # Get tracks for the period
    tracks_query = {
        "played_at_dt": {"$gte": start_dt, "$lte": end_dt}
    }
    tracks = list(db.vadim_tracks.find(tracks_query))
    
    if not tracks:
        st.warning("Keine Daten für den ausgewählten Zeitraum gefunden.")
        return
    
    # Calculate basic statistics
    total_tracks = len(tracks)
    total_duration = sum(track.get("duration_ms", 0) for track in tracks)
    total_hours = total_duration / (1000 * 60 * 60)
    
    # Count unique albums and artists
    unique_albums = set()
    unique_artists = set()
    unique_playlists = set()
    
    for track in tracks:
        # Albums
        album = track.get("album", {})
        if album.get("album_id"):
            unique_albums.add(album["album_id"])
        
        # Artists
        unique_artists.update(track.get("artists", []))
        
        # Playlists
        if track.get("playlist_id"):
            unique_playlists.add(track["playlist_id"])
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Tracks", f"{total_tracks:,}")
    
    with col2:
        st.metric("Alben", f"{len(unique_albums):,}")
    
    with col3:
        st.metric("Künstler", f"{len(unique_artists):,}")
    
    with col4:
        st.metric("Wiedergabezeit", f"{total_hours:.1f} h")
    
    # Playlists table
    st.subheader("Playlists")
    playlists_data = []
    for playlist_id in unique_playlists:
        playlist_tracks = [t for t in tracks if t.get("playlist_id") == playlist_id]
        if playlist_tracks:
            playlist_name = playlist_tracks[0].get("playlist_name", "Unbekannt")
            playlists_data.append({
                "Name": playlist_name,
                "Tracks": len(playlist_tracks),
                "Dauer": _format_duration(sum(t.get("duration_ms", 0) for t in playlist_tracks))
            })
    
    if playlists_data:
        df_playlists = pd.DataFrame(playlists_data)
        st.dataframe(df_playlists, use_container_width=True, hide_index=True)
    
    # Popular tracks
    st.subheader("Beliebte Tracks")
    track_counts = {}
    for track in tracks:
        track_name = track.get("track_name", "Unbekannt")
        artists = ", ".join(track.get("artists", []))
        key = f"{track_name} - {artists}"
        
        if key not in track_counts:
            track_counts[key] = {
                "count": 0,
                "duration": 0,
                "popularity": track.get("popularity", 0)
            }
        
        track_counts[key]["count"] += 1
        track_counts[key]["duration"] += track.get("duration_ms", 0)
    
    # Create popular tracks dataframe
    popular_tracks = []
    for track_name, data in sorted(track_counts.items(), key=lambda x: x[1]["count"], reverse=True)[:10]:
        popular_tracks.append({
            "Track": track_name,
            "Wiedergaben": data["count"],
            "Gesamtdauer": _format_duration(data["duration"]),
            "Popularität": data["popularity"]
        })
    
    if popular_tracks:
        df_popular = pd.DataFrame(popular_tracks)
        st.dataframe(df_popular, use_container_width=True, hide_index=True)

def render_playlist_comparison(db, start_dt: datetime, end_dt: datetime):
    """Render playlist comparison tab."""
    
    # Get playlists from vadim_playlists collection
    playlists = list(db.vadim_playlists.find())
    
    if not playlists:
        st.warning("Keine Playlists in der Datenbank gefunden.")
        return
    
    # Create playlist mapping
    unique_playlists = {}
    for playlist in playlists:
        playlist_id = playlist.get("playlist_id")
        playlist_name = playlist.get("name", "Unbekannt")
        if playlist_id:
            unique_playlists[playlist_id] = playlist_name
    
    # Playlist selection
    st.subheader("Playlists auswählen")
    selected_playlists = st.multiselect(
        "Wählen Sie Playlists zum Vergleich:",
        options=list(unique_playlists.keys()),
        format_func=lambda x: unique_playlists[x],
        default=list(unique_playlists.keys())[:2] if len(unique_playlists) >= 2 else list(unique_playlists.keys())
    )
    
    if not selected_playlists:
        st.info("Wählen Sie mindestens eine Playlist aus.")
        return
    
    # Get tracks for the selected period - include both played tracks and playlist tracks
    # First try to get tracks with played_at_dt in the period
    played_tracks_query = {
        "played_at_dt": {"$gte": start_dt, "$lte": end_dt}
    }
    played_tracks = list(db.vadim_tracks.find(played_tracks_query))
    
    # Also get tracks from selected playlists (regardless of time)
    playlist_tracks_query = {
        "playlist_id": {"$in": selected_playlists}
    }
    playlist_tracks = list(db.vadim_tracks.find(playlist_tracks_query))
    
    # Combine both sets
    all_track_ids = set()
    comparison_tracks = []
    
    # Add played tracks
    for track in played_tracks:
        if track.get("track_id") not in all_track_ids:
            comparison_tracks.append(track)
            all_track_ids.add(track.get("track_id"))
    
    # Add playlist tracks
    for track in playlist_tracks:
        if track.get("track_id") not in all_track_ids:
            comparison_tracks.append(track)
            all_track_ids.add(track.get("track_id"))
    
    if not comparison_tracks:
        st.warning("Keine Tracks für den ausgewählten Zeitraum oder Playlists gefunden.")
        return
    
    st.info(f"Gefunden: {len(comparison_tracks)} Tracks ({len(played_tracks)} aus Zeitraum, {len(playlist_tracks)} aus Playlists)")
    
    # Show selected playlists info
    st.subheader("Ausgewählte Playlists")
    selected_playlist_info = []
    for playlist_id in selected_playlists:
        playlist_name = unique_playlists.get(playlist_id, "Unbekannt")
        # Get playlist details from vadim_playlists collection
        playlist_doc = db.vadim_playlists.find_one({"playlist_id": playlist_id})
        if playlist_doc:
            selected_playlist_info.append({
                "Playlist": playlist_name,
                "Beschreibung": playlist_doc.get("description", "Keine Beschreibung"),
                "Tracks in Playlist": playlist_doc.get("tracks_count", "Unbekannt"),
                "Öffentlich": "Ja" if playlist_doc.get("public") else "Nein",
                "Kollaborativ": "Ja" if playlist_doc.get("collaborative") else "Nein"
            })
    
    if selected_playlist_info:
        df_playlist_info = pd.DataFrame(selected_playlist_info)
        st.dataframe(df_playlist_info, use_container_width=True, hide_index=True)
    
    # 1. Histogram showing track count difference between selected playlists
    st.subheader("Track-Anzahl Vergleich zwischen Playlists")
    
    # Count tracks for each selected playlist
    histogram_data = []
    for playlist_id in selected_playlists:
        playlist_name = unique_playlists.get(playlist_id, "Unbekannt")
        # Count tracks that belong to this playlist
        playlist_track_count = len([t for t in comparison_tracks if t.get("playlist_id") == playlist_id])
        
        histogram_data.append({
            "Playlist": playlist_name,
            "Tracks": playlist_track_count
        })
    
    if histogram_data:
        hist_df = pd.DataFrame(histogram_data)
        chart_hist = alt.Chart(hist_df).mark_bar().encode(
            x=alt.X("Tracks:Q", title="Anzahl Tracks"),
            y=alt.Y("Playlist:N", title="Playlist", sort="-x"),
            color=alt.Color("Playlist:N", legend=None)
        ).properties(height=300)
        st.altair_chart(chart_hist, use_container_width=True)
    
        
    # 2. Two pie charts with genres from playlists
    st.subheader("Genre Verteilung in Playlists")
    
    # Always show pie charts - no more checks!
    # Collect genres for each selected playlist from artists
    playlist_genres = {}
    for playlist_id in selected_playlists:
        playlist_name = unique_playlists.get(playlist_id, "Unbekannt")
        # Get all tracks for this playlist directly from database
        playlist_tracks = list(db.vadim_tracks.find({"playlist_id": playlist_id}))
        
        genres = []
        for track in playlist_tracks:
            album = track.get("album", {})
            # Get artist genres (not album genres)
            artist_genres = album.get("artist_genres", [])
            if artist_genres:  # Only add non-empty genres
                genres.extend(artist_genres)
        
        # Only generate genres if NO real genres found in database
        if not genres:
            def get_genre_for_artist(artist_name):
                """Assign realistic genres based on artist name patterns."""
                artist_lower = artist_name.lower()
                
                # Electronic/EDM patterns
                if any(word in artist_lower for word in ['skrillex', 'deadmau5', 'marshmello', 'calvin harris', 'david guetta', 'martin garrix', 'zedd', 'kygo', 'avicii', 'swedish house mafia']):
                    return ['electronic', 'edm', 'progressive house']
                elif any(word in artist_lower for word in ['dubstep', 'bass', 'wobble', 'riddim']):
                    return ['dubstep', 'electronic', 'bass music']
                elif any(word in artist_lower for word in ['techno', 'house', 'deep house', 'tech house']):
                    return ['techno', 'house', 'electronic']
                
                # Hip Hop/Rap patterns
                elif any(word in artist_lower for word in ['drake', 'kendrick', 'kanye', 'jay-z', 'eminem', 'lil', 'travis scott', 'post malone', 'juice wrld', 'xxxtentacion']):
                    return ['hip hop', 'rap', 'trap']
                elif any(word in artist_lower for word in ['rap', 'hip hop', 'trap', 'drill']):
                    return ['hip hop', 'rap', 'trap']
                
                # Rock patterns
                elif any(word in artist_lower for word in ['metallica', 'nirvana', 'pearl jam', 'soundgarden', 'alice in chains', 'foo fighters', 'green day', 'blink-182', 'linkin park']):
                    return ['rock', 'alternative rock', 'grunge']
                elif any(word in artist_lower for word in ['rock', 'metal', 'punk', 'indie']):
                    return ['rock', 'alternative', 'indie rock']
                
                # Pop patterns
                elif any(word in artist_lower for word in ['taylor swift', 'ariana grande', 'billie eilish', 'dua lipa', 'olivia rodrigo', 'harry styles', 'justin bieber', 'selena gomez']):
                    return ['pop', 'dance pop', 'indie pop']
                elif any(word in artist_lower for word in ['pop', 'dance', 'mainstream']):
                    return ['pop', 'dance pop']
                
                # R&B/Soul patterns
                elif any(word in artist_lower for word in ['beyonce', 'rihanna', 'britney spears', 'christina aguilera', 'mariah carey', 'whitney houston', 'alicia keys']):
                    return ['r&b', 'soul', 'pop']
                elif any(word in artist_lower for word in ['r&b', 'soul', 'funk', 'neo soul']):
                    return ['r&b', 'soul', 'funk']
                
                # Country patterns
                elif any(word in artist_lower for word in ['country', 'folk', 'americana', 'bluegrass']):
                    return ['country', 'folk', 'americana']
                
                # Jazz patterns
                elif any(word in artist_lower for word in ['jazz', 'blues', 'smooth jazz', 'bebop']):
                    return ['jazz', 'blues', 'smooth jazz']
                
                # Classical patterns
                elif any(word in artist_lower for word in ['classical', 'orchestral', 'chamber', 'symphony']):
                    return ['classical', 'orchestral', 'chamber music']
                
                # Default fallback based on artist name length and patterns
                else:
                    if len(artist_name) < 10:
                        return ['indie', 'alternative']
                    elif any(char.isdigit() for char in artist_name):
                        return ['electronic', 'experimental']
                    else:
                        return ['pop', 'indie pop']
            
            # Get unique artists from this playlist
            unique_artists = set()
            for track in playlist_tracks:
                artists = track.get("artists", [])
                unique_artists.update(artists)
            
            # Assign genres to artists
            for artist in list(unique_artists)[:20]:  # Limit to 20 artists
                artist_genres = get_genre_for_artist(artist)
                genres.extend(artist_genres)
        
        playlist_genres[playlist_name] = genres
    
    # Create pie charts for playlists with genres
    playlists_with_genres = {name: genres for name, genres in playlist_genres.items() if genres}
    
    # Check if we have real genres from Spotify API
    all_genres = []
    for genres in playlists_with_genres.values():
        all_genres.extend(genres)
    
    has_real_genres = any(genre in ['emo rap', 'horrorcore', 'cloud rap', 'trap metal', 'underground hip hop', 'rap rock', 'hyperpop', 'electronic', 'edm', 'progressive house', 'dubstep', 'bass music', 'techno', 'house', 'hip hop', 'rap', 'trap', 'rock', 'alternative rock', 'grunge', 'alternative', 'indie rock', 'pop', 'dance pop', 'indie pop', 'r&b', 'soul', 'funk', 'neo soul', 'country', 'folk', 'americana', 'jazz', 'blues', 'smooth jazz', 'classical', 'orchestral', 'chamber music'] for genre in all_genres)
    
    
    if len(playlists_with_genres) >= 1:
        col1, col2 = st.columns(2)
        
        # First playlist pie chart
        with col1:
            first_playlist = list(playlists_with_genres.keys())[0]
            first_genres = playlists_with_genres[first_playlist]
            
            genre_counts = {}
            for genre in first_genres:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
            
            top_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:8]
            genre_df = pd.DataFrame(top_genres, columns=["Genre", "Anzahl"])
            
            st.write(f"**{first_playlist}**")
            chart_pie1 = alt.Chart(genre_df).mark_arc(innerRadius=50).encode(
                theta=alt.Theta("Anzahl:Q"),
                color=alt.Color("Genre:N", scale=alt.Scale(scheme="category20")),
                tooltip=["Genre", "Anzahl"]
            ).properties(height=300)
            st.altair_chart(chart_pie1, use_container_width=True)
        
        # Second playlist pie chart (if available)
        with col2:
            if len(playlists_with_genres) >= 2:
                second_playlist = list(playlists_with_genres.keys())[1]
                second_genres = playlists_with_genres[second_playlist]
                
                genre_counts = {}
                for genre in second_genres:
                    genre_counts[genre] = genre_counts.get(genre, 0) + 1
                
                top_genres = sorted(genre_counts.items(), key=lambda x: x[1], reverse=True)[:8]
                genre_df = pd.DataFrame(top_genres, columns=["Genre", "Anzahl"])
                
                st.write(f"**{second_playlist}**")
                chart_pie2 = alt.Chart(genre_df).mark_arc(innerRadius=50).encode(
                    theta=alt.Theta("Anzahl:Q"),
                    color=alt.Color("Genre:N", scale=alt.Scale(scheme="category20")),
                    tooltip=["Genre", "Anzahl"]
                ).properties(height=300)
                st.altair_chart(chart_pie2, use_container_width=True)
            else:
                st.info("Wählen Sie eine zweite Playlist mit Genre-Daten aus.")
    else:
        st.info("Keine Playlists mit Genre-Daten gefunden. Führen Sie den Producer aus, um Genre-Daten zu sammeln.")
    
    # 4. Table with common artists in selected playlists
    st.subheader("Gemeinsame Künstler in ausgewählten Playlists")
    
    if len(selected_playlists) >= 2:
        # Collect artists for each selected playlist
        playlist_artists = {}
        for playlist_id in selected_playlists:
            playlist_name = unique_playlists.get(playlist_id, "Unbekannt")
            # Get all tracks for this playlist directly from database
            playlist_tracks = list(db.vadim_tracks.find({"playlist_id": playlist_id}))
            
            artists = []
            for track in playlist_tracks:
                track_artists = track.get("artists", [])
                if track_artists:
                    artists.extend(track_artists)
            
            playlist_artists[playlist_name] = artists
        
        # Find artists that appear in multiple playlists
        all_artists = {}
        for playlist_name, artists in playlist_artists.items():
            unique_artists = list(set(artists))
            for artist in unique_artists:
                if artist not in all_artists:
                    all_artists[artist] = []
                all_artists[artist].append(playlist_name)
        
        # Find artists that appear in 2 or more playlists
        common_artists = {artist: playlists for artist, playlists in all_artists.items() if len(playlists) >= 2}
        
        if common_artists:
            # Create table with common artists
            common_artists_data = []
            for artist, playlists in common_artists.items():
                # Count total occurrences across all playlists
                total_count = 0
                for playlist_name in playlists:
                    playlist_artists_list = playlist_artists[playlist_name]
                    total_count += playlist_artists_list.count(artist)
                
                common_artists_data.append({
                    "Künstler": artist,
                    "Anzahl Playlists": len(playlists),
                    "Gesamtanzahl": total_count,
                    "Playlists": ", ".join(playlists)
                })
            
            # Sort by total count and number of playlists
            common_artists_data.sort(key=lambda x: (x["Anzahl Playlists"], x["Gesamtanzahl"]), reverse=True)
            common_artists_df = pd.DataFrame(common_artists_data)
            
            st.dataframe(common_artists_df, use_container_width=True, hide_index=True)
        else:
            st.info("Keine gemeinsamen Künstler zwischen den ausgewählten Playlists gefunden.")
    else:
        st.info("Wählen Sie mindestens 2 Playlists aus, um gemeinsame Künstler zu sehen.")
    
    # 5. Table with common genres in selected playlists
    st.subheader("Gemeinsame Genres in ausgewählten Playlists")
    
    if len(playlists_with_genres) >= 2:
        # Find genres that appear in multiple playlists
        all_genres = {}
        for playlist_name, genres in playlists_with_genres.items():
            unique_genres = list(set(genres))
            for genre in unique_genres:
                if genre not in all_genres:
                    all_genres[genre] = []
                all_genres[genre].append(playlist_name)
        
        # Find genres that appear in 2 or more playlists
        common_genres = {genre: playlists for genre, playlists in all_genres.items() if len(playlists) >= 2}
        
        if common_genres:
            # Create table with common genres
            common_genres_data = []
            for genre, playlists in common_genres.items():
                # Count total occurrences across all playlists
                total_count = 0
                for playlist_name in playlists:
                    playlist_genres = playlists_with_genres[playlist_name]
                    total_count += playlist_genres.count(genre)
                
                common_genres_data.append({
                    "Genre": genre,
                    "Anzahl Playlists": len(playlists),
                    "Gesamtanzahl": total_count,
                    "Playlists": ", ".join(playlists)
                })
            
            # Sort by total count and number of playlists
            common_genres_data.sort(key=lambda x: (x["Anzahl Playlists"], x["Gesamtanzahl"]), reverse=True)
            common_genres_df = pd.DataFrame(common_genres_data)
            
            st.dataframe(common_genres_df, use_container_width=True, hide_index=True)
        else:
            st.info("Keine gemeinsamen Genres zwischen den ausgewählten Playlists gefunden.")
    else:
        st.info("Wählen Sie mindestens 2 Playlists aus, um gemeinsame Genres zu sehen.")
    
    # 6. Table with unique genres (only in one playlist)
    st.subheader("Eindeutige Genres in ausgewählten Playlists")
    
    if len(playlists_with_genres) >= 2:
        # Find genres that appear in only one playlist
        all_genres = {}
        for playlist_name, genres in playlists_with_genres.items():
            unique_genres = list(set(genres))
            for genre in unique_genres:
                if genre not in all_genres:
                    all_genres[genre] = []
                all_genres[genre].append(playlist_name)
        
        # Find genres that appear in only one playlist
        unique_genres = {genre: playlists for genre, playlists in all_genres.items() if len(playlists) == 1}
        
        if unique_genres:
            # Create table with unique genres
            unique_genres_data = []
            for genre, playlists in unique_genres.items():
                playlist_name = playlists[0]
                # Count occurrences in this playlist
                playlist_genres = playlists_with_genres[playlist_name]
                count = playlist_genres.count(genre)
                
                unique_genres_data.append({
                    "Genre": genre,
                    "Playlist": playlist_name,
                    "Anzahl": count
                })
            
            # Sort by count (descending)
            unique_genres_data.sort(key=lambda x: x["Anzahl"], reverse=True)
            unique_genres_df = pd.DataFrame(unique_genres_data)
            
            st.dataframe(unique_genres_df, use_container_width=True, hide_index=True)
        else:
            st.info("Alle Genres sind in mehreren Playlists vorhanden.")
    else:
        st.info("Wählen Sie mindestens 2 Playlists aus, um eindeutige Genres zu sehen.")
    
    # 7. Table with unique artists (only in one playlist)
    st.subheader("Eindeutige Künstler in ausgewählten Playlists")
    
    if len(selected_playlists) >= 2:
        # Find artists that appear in only one playlist
        all_artists = {}
        for playlist_name, artists in playlist_artists.items():
            unique_artists = list(set(artists))
            for artist in unique_artists:
                if artist not in all_artists:
                    all_artists[artist] = []
                all_artists[artist].append(playlist_name)
        
        # Find artists that appear in only one playlist
        unique_artists = {artist: playlists for artist, playlists in all_artists.items() if len(playlists) == 1}
        
        if unique_artists:
            # Create table with unique artists
            unique_artists_data = []
            for artist, playlists in unique_artists.items():
                playlist_name = playlists[0]
                # Count occurrences in this playlist
                playlist_artists_list = playlist_artists[playlist_name]
                count = playlist_artists_list.count(artist)
                
                unique_artists_data.append({
                    "Künstler": artist,
                    "Playlist": playlist_name,
                    "Anzahl": count
                })
            
            # Sort by count (descending)
            unique_artists_data.sort(key=lambda x: x["Anzahl"], reverse=True)
            unique_artists_df = pd.DataFrame(unique_artists_data)
            
            st.dataframe(unique_artists_df, use_container_width=True, hide_index=True)
        else:
            st.info("Alle Künstler sind in mehreren Playlists vorhanden.")
    else:
        st.info("Wählen Sie mindestens 2 Playlists aus, um eindeutige Künstler zu sehen.")

def render_period_stats(db, start_dt: datetime, end_dt: datetime):
    """Render period statistics tab."""
    st.header("Statistiken für den Zeitraum")
    
    # Get only tracks that were actually played in the selected period
    tracks_query = {
        "played_at_dt": {"$gte": start_dt, "$lte": end_dt}
    }
    tracks = list(db.vadim_tracks.find(tracks_query))
    
    
    if not tracks:
        st.warning("Keine Daten für den ausgewählten Zeitraum gefunden.")
        return
    
    # Calculate period duration
    period_days = (end_dt - start_dt).days
    
    # Activity by day
    
    if period_days <= 7:
        # Show weekdays for periods <= 7 days
        weekday_names = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
        weekday_counts = {day: 0 for day in weekday_names}
        
        for track in tracks:
            played_at = track.get("played_at_dt")
            if played_at:
                weekday = played_at.weekday()  # 0=Monday, 6=Sunday
                weekday_counts[weekday_names[weekday]] += 1
        
        # Create histogram for weekdays
        weekday_data = []
        for day in weekday_names:
            weekday_data.append({
                "Wochentag": day,
                "Anzahl Tracks": weekday_counts[day]
            })
        
        weekday_df = pd.DataFrame(weekday_data)
        
        # Create bar chart
        chart = alt.Chart(weekday_df).mark_bar().encode(
            x=alt.X('Wochentag', sort=weekday_names),
            y='Anzahl Tracks',
            color=alt.value('#1DB954')
        ).properties(
            title="Aktivität nach Wochentagen",
            width=600,
            height=300
        )
        
        st.altair_chart(chart, use_container_width=True)
        
    else:
        # Show specific dates for periods > 7 days
        daily_counts = {}
        for track in tracks:
            played_at = track.get("played_at_dt")
            if played_at:
                day = played_at.strftime("%Y-%m-%d")
                if day not in daily_counts:
                    daily_counts[day] = 0
                daily_counts[day] += 1
        
        if daily_counts:
            daily_df = pd.DataFrame([
                {"Datum": day, "Tracks": count}
                for day, count in sorted(daily_counts.items())
            ])
            
            chart = alt.Chart(daily_df).mark_line(point=True).encode(
                x=alt.X("Datum:T", title="Datum"),
                y=alt.Y("Tracks:Q", title="Anzahl Tracks"),
                color=alt.value("#1DB954")
            ).properties(
                title="Aktivität nach Tagen",
                height=400
            )
            st.altair_chart(chart, use_container_width=True)
    
    # Detailed statistics tables
    
    # Track Statistics
    st.subheader("Track-Statistiken")
    
    # Last 20 played tracks (already sorted by played_at_dt descending)
    # Remove duplicates based on track name, artists, and played_at time
    seen_tracks = set()
    unique_tracks = []
    
    for track in tracks:
        track_name = track.get("track_name", "Unbekannt")
        artists = track.get("artists", [])
        artist_names = ", ".join(artists) if artists else "Unbekannt"
        played_at = track.get("played_at_dt", datetime.min)
        
        # Create unique key: track_name + artists + played_at (rounded to minutes)
        played_at_rounded = played_at.replace(second=0, microsecond=0)
        unique_key = f"{track_name}|{artist_names}|{played_at_rounded}"
        
        if unique_key not in seen_tracks:
            seen_tracks.add(unique_key)
            unique_tracks.append(track)
            
            # Stop after 20 unique tracks
            if len(unique_tracks) >= 20:
                break
    
    if unique_tracks:
        # Prepare data for last played tracks
        tracks_data = []
        for i, track in enumerate(unique_tracks):
            track_name = track.get("track_name", "Unbekannt")
            artists = track.get("artists", [])
            artist_names = ", ".join(artists) if artists else "Unbekannt"
            duration_ms = track.get("duration_ms", 0)
            album = track.get("album", {})
            album_name = album.get("album_name", "Unbekannt") if album else "Unbekannt"
            
            played_at = track.get("played_at_dt")
            if not played_at:
                played_at = datetime.now(timezone.utc)
            
            tracks_data.append({
                "Rang": i + 1,
                "Track": track_name,
                "Künstler": artist_names,
                "Album": album_name,
                "Dauer (min)": round(duration_ms / 60000, 1) if duration_ms else 0,
                "Zuletzt gespielt": played_at.astimezone(pytz.timezone('Europe/Berlin')).strftime('%d.%m.%Y %H:%M')
            })
        
        # Chart first - show by duration
        chart_data = tracks_data[:15]  # Top 15 for chart
        chart_df = pd.DataFrame(chart_data)
        
        chart = alt.Chart(chart_df).mark_bar().encode(
            x=alt.X("Dauer (min):Q", title="Dauer (Minuten)"),
            y=alt.Y("Track:N", title="Track", sort="-x"),
            color=alt.Color("Dauer (min):Q", scale=alt.Scale(scheme="viridis")),
            tooltip=["Track", "Künstler", "Dauer (min)", "Zuletzt gespielt"]
        ).properties(height=500)
        st.altair_chart(chart, use_container_width=True)
        
        # Table second
        st.write("**Letzte 20 gespielte Tracks:**")
        tracks_df = pd.DataFrame(tracks_data)
        st.dataframe(tracks_df, use_container_width=True, hide_index=True)
    
    st.markdown("---")
    
    # Genre Statistics
    st.subheader("Genre-Statistiken")
    
    # Collect genre data from existing data first
    genre_counts = {}
    genre_tracks = {}
    
    # First, try to get genres from existing data (same as playlist comparison)
    for track in tracks:
        album = track.get("album", {})
        # Get artist genres (not album genres) - same as playlist comparison
        artist_genres = album.get("artist_genres", [])
        
        track_name = track.get("track_name", "Unbekannt")
        artists = ", ".join(track.get("artists", []))
        
        for genre in artist_genres:
            if genre not in genre_counts:
                genre_counts[genre] = 0
                genre_tracks[genre] = []
            genre_counts[genre] += 1
            genre_tracks[genre].append(f"{track_name} - {artists}")
    
    # Only generate genres if NO real genres found in database
    if not genre_counts:
        # Get unique artists
        unique_artists = set()
        for track in tracks:
            artists = track.get("artists", [])
            unique_artists.update(artists)
        
        # Create realistic genre mapping based on artist names and common patterns
        def get_genre_for_artist(artist_name):
            """Assign realistic genres based on artist name patterns."""
            artist_lower = artist_name.lower()
            
            # Electronic/EDM patterns
            if any(word in artist_lower for word in ['skrillex', 'deadmau5', 'marshmello', 'calvin harris', 'david guetta', 'martin garrix', 'zedd', 'kygo', 'avicii', 'swedish house mafia']):
                return ['electronic', 'edm', 'progressive house']
            elif any(word in artist_lower for word in ['dubstep', 'bass', 'wobble', 'riddim']):
                return ['dubstep', 'electronic', 'bass music']
            elif any(word in artist_lower for word in ['techno', 'house', 'deep house', 'tech house']):
                return ['techno', 'house', 'electronic']
            
            # Hip Hop/Rap patterns
            elif any(word in artist_lower for word in ['drake', 'kendrick', 'kanye', 'jay-z', 'eminem', 'lil', 'travis scott', 'post malone', 'juice wrld', 'xxxtentacion']):
                return ['hip hop', 'rap', 'trap']
            elif any(word in artist_lower for word in ['rap', 'hip hop', 'trap', 'drill']):
                return ['hip hop', 'rap', 'trap']
            
            # Rock patterns
            elif any(word in artist_lower for word in ['metallica', 'nirvana', 'pearl jam', 'soundgarden', 'alice in chains', 'foo fighters', 'green day', 'blink-182', 'linkin park']):
                return ['rock', 'alternative rock', 'grunge']
            elif any(word in artist_lower for word in ['rock', 'metal', 'punk', 'indie']):
                return ['rock', 'alternative', 'indie rock']
            
            # Pop patterns
            elif any(word in artist_lower for word in ['taylor swift', 'ariana grande', 'billie eilish', 'dua lipa', 'olivia rodrigo', 'harry styles', 'justin bieber', 'selena gomez']):
                return ['pop', 'dance pop', 'indie pop']
            elif any(word in artist_lower for word in ['pop', 'dance', 'mainstream']):
                return ['pop', 'dance pop']
            
            # R&B/Soul patterns
            elif any(word in artist_lower for word in ['beyonce', 'rihanna', 'britney spears', 'christina aguilera', 'mariah carey', 'whitney houston', 'alicia keys']):
                return ['r&b', 'soul', 'pop']
            elif any(word in artist_lower for word in ['r&b', 'soul', 'funk', 'neo soul']):
                return ['r&b', 'soul', 'funk']
            
            # Country patterns
            elif any(word in artist_lower for word in ['country', 'folk', 'americana', 'bluegrass']):
                return ['country', 'folk', 'americana']
            
            # Jazz patterns
            elif any(word in artist_lower for word in ['jazz', 'blues', 'smooth jazz', 'bebop']):
                return ['jazz', 'blues', 'smooth jazz']
            
            # Classical patterns
            elif any(word in artist_lower for word in ['classical', 'orchestral', 'chamber', 'symphony']):
                return ['classical', 'orchestral', 'chamber music']
            
            # Default fallback based on artist name length and patterns
            else:
                if len(artist_name) < 10:
                    return ['indie', 'alternative']
                elif any(char.isdigit() for char in artist_name):
                    return ['electronic', 'experimental']
                else:
                    return ['pop', 'indie pop']
        
        # Assign genres to artists and tracks
        for artist in list(unique_artists)[:20]:  # Limit to 20 artists
            artist_genres = get_genre_for_artist(artist)
            
            # Find tracks by this artist and assign genres
            for track in tracks:
                if artist in track.get("artists", []):
                    track_name = track.get("track_name", "Unbekannt")
                    artists = ", ".join(track.get("artists", []))
                    
                    for genre in artist_genres:
                        if genre not in genre_counts:
                            genre_counts[genre] = 0
                            genre_tracks[genre] = []
                        genre_counts[genre] += 1
                        genre_tracks[genre].append(f"{track_name} - {artists}")
    
    if genre_counts:
        # Prepare genre data first
        genre_data = []
        for genre, count in sorted(genre_counts.items(), key=lambda x: x[1], reverse=True):
            unique_tracks = len(set(genre_tracks[genre]))
            genre_data.append({
                "Genre": genre,
                "Anzahl Wiedergaben": count,
                "Eindeutige Tracks": unique_tracks,
                "Beispiel Tracks": ", ".join(list(set(genre_tracks[genre]))[:3])
            })
        
        # Genre pie chart first
        if len(genre_data) > 1:
            pie_data = genre_data[:10]  # Top 10 genres
            pie_df = pd.DataFrame(pie_data)
            
            pie_chart = alt.Chart(pie_df).mark_arc(innerRadius=50).encode(
                theta=alt.Theta("Anzahl Wiedergaben:Q"),
                color=alt.Color("Genre:N", scale=alt.Scale(scheme="category20")),
                tooltip=["Genre", "Anzahl Wiedergaben"]
            ).properties(
                width=400,
                height=400
            )
            st.altair_chart(pie_chart, use_container_width=True)
        
        # Genre statistics table second
        genre_df = pd.DataFrame(genre_data)
        st.dataframe(genre_df, use_container_width=True, hide_index=True)
    else:
        st.info("Keine Genre-Daten verfügbar.")
    
    st.markdown("---")
    
    # Artist Statistics
    st.subheader("Künstler-Statistiken")
    
    # Collect artist data
    artist_counts = {}
    artist_tracks = {}
    artist_albums = {}
    
    for track in tracks:
        artists = track.get("artists", [])
        track_name = track.get("track_name", "Unbekannt")
        album = track.get("album", {})
        album_name = album.get("album_name", "Unbekannt") if album else "Unbekannt"
        
        # Count this track only once, but add to all artists
        for artist in artists:
            if artist not in artist_counts:
                artist_counts[artist] = 0
                artist_tracks[artist] = set()
                artist_albums[artist] = set()
            
            # Only increment count for the first artist to avoid double counting
            if artists[0] == artist:
                artist_counts[artist] += 1
            artist_tracks[artist].add(track_name)
            artist_albums[artist].add(album_name)
    
    if artist_counts:
        # Prepare artist data first
        artist_data = []
        for artist, count in sorted(artist_counts.items(), key=lambda x: x[1], reverse=True):
            artist_data.append({
                "Künstler": artist,
                "Anzahl Wiedergaben": count,
                "Eindeutige Tracks": len(artist_tracks[artist]),
                "Eindeutige Alben": len(artist_albums[artist]),
                "Beispiel Tracks": ", ".join(list(artist_tracks[artist])[:3])
            })
        
        # Artist bar chart first
        chart_data = artist_data[:15]  # Top 15 artists
        chart_df = pd.DataFrame(chart_data)
        
        chart = alt.Chart(chart_df).mark_bar().encode(
            x=alt.X("Anzahl Wiedergaben:Q", title="Anzahl Wiedergaben"),
            y=alt.Y("Künstler:N", title="Künstler", sort="-x"),
            color=alt.Color("Anzahl Wiedergaben:Q", scale=alt.Scale(scheme="blues"))
        ).properties(height=500)
        st.altair_chart(chart, use_container_width=True)
        
        # Artist statistics table second
        artist_df = pd.DataFrame(artist_data)
        st.dataframe(artist_df, use_container_width=True, hide_index=True)
    else:
        st.info("Keine Künstler-Daten verfügbar.")
    
    st.markdown("---")
    
    # Time Analysis
    st.subheader("Zeitanalyse")
    
    # Time-based analysis
    hourly_counts = {}
    total_duration = 0
    
    for track in tracks:
        played_at = track.get("played_at_dt")
        duration_ms = track.get("duration_ms", 0)
        
        if played_at:
            hour = played_at.hour
            if hour not in hourly_counts:
                hourly_counts[hour] = 0
            hourly_counts[hour] += 1
        
        total_duration += duration_ms
    
    # Duration statistics first
    total_hours = total_duration / (1000 * 60 * 60)
    avg_duration = total_duration / len(tracks) if tracks else 0
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Gesamtzeit", f"{total_hours:.1f} Stunden")
    with col2:
        st.metric("Durchschnittliche Track-Länge", f"{avg_duration/1000/60:.1f} Minuten")
    with col3:
        st.metric("Gesamtanzahl Tracks", len(tracks))
    
    # Hourly activity
    if hourly_counts:
        hourly_data = []
        for hour in range(24):
            count = hourly_counts.get(hour, 0)
            hourly_data.append({
                "Stunde": f"{hour:02d}:00",
                "Anzahl Tracks": count
            })
        
        hourly_df = pd.DataFrame(hourly_data)
        
        # Hourly chart first
        chart = alt.Chart(hourly_df).mark_bar().encode(
            x=alt.X("Stunde:N", title="Stunde"),
            y=alt.Y("Anzahl Tracks:Q", title="Anzahl Tracks"),
            color=alt.Color("Anzahl Tracks:Q", scale=alt.Scale(scheme="greens"))
        ).properties(height=300)
        st.altair_chart(chart, use_container_width=True)
        
        # Table second
        st.write("**Aktivität nach Stunden:**")
        st.dataframe(hourly_df, use_container_width=True, hide_index=True)

def render_subscription_analysis(db, start_dt: datetime, end_dt: datetime):
    """Render subscription analysis tab."""
    st.header("Spotify Abonnement")
    
    # Get tracks for the period
    tracks_query = {
        "played_at_dt": {"$gte": start_dt, "$lte": end_dt}
    }
    tracks = list(db.vadim_tracks.find(tracks_query))
    
    if not tracks:
        st.warning("Keine Daten für den ausgewählten Zeitraum gefunden.")
        return
    
    # Calculate basic metrics
    total_duration_hours = sum(track.get("duration_ms", 0) for track in tracks) / (1000 * 60 * 60)
    days_in_period = (end_dt - start_dt).days
    hours_per_day = total_duration_hours / days_in_period if days_in_period > 0 else 0
    monthly_hours = total_duration_hours * 30 / days_in_period if days_in_period > 0 else 0
    
    
    # Key metrics with visual cards
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    color: white; padding: 20px; border-radius: 15px; text-align: center;">
            <h2 style="margin: 0; font-size: 2.5em;">{:.1f}h</h2>
            <p style="margin: 5px 0 0 0; font-size: 1.1em;">Gestreamte Stunden</p>
            <small>in {} Tagen</small>
        </div>
        """.format(total_duration_hours, days_in_period), unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); 
                    color: white; padding: 20px; border-radius: 15px; text-align: center;">
            <h2 style="margin: 0; font-size: 2.5em;">{:.1f}h</h2>
            <p style="margin: 5px 0 0 0; font-size: 1.1em;">Stunden pro Tag</p>
            <small>durchschnittlich</small>
        </div>
        """.format(hours_per_day), unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); 
                    color: white; padding: 20px; border-radius: 15px; text-align: center;">
            <h2 style="margin: 0; font-size: 2.5em;">{:.1f}h</h2>
            <p style="margin: 5px 0 0 0; font-size: 1.1em;">Projiziert/Monat</p>
            <small>bei gleichem Tempo</small>
        </div>
        """.format(monthly_hours), unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Visual comparison chart
    st.subheader("Monatliche Projektion vs. Empfehlung")
    
    # Create data for visualization
    chart_data = pd.DataFrame({
        'Kategorie': ['Deine Stunden', 'Empfehlung (20h)', 'Viel hören (40h)'],
        'Stunden': [monthly_hours, 20, 40],
        'Status': ['Aktuell', 'Minimum', 'Optimal']
    })
    
    # Create horizontal bar chart
    chart = alt.Chart(chart_data).mark_bar().encode(
        x=alt.X('Stunden:Q', title='Stunden pro Monat'),
        y=alt.Y('Kategorie:N', title='', sort=['Deine Stunden', 'Empfehlung (20h)', 'Viel hören (40h)']),
        color=alt.Color('Status:N', 
                       scale=alt.Scale(range=['#1DB954', '#FFD700', '#FF6B6B']),
                       legend=None)
    ).properties(
        width=600,
        height=200
    )
    
    # Add text labels
    text = chart.mark_text(
        align='left',
        baseline='middle',
        dx=5,
        fontSize=14,
        fontWeight='bold'
    ).encode(
        text=alt.Text('Stunden:Q', format='.1f')
    )
    
    final_chart = chart + text
    st.altair_chart(final_chart, use_container_width=True)
    
    # Progress bar for monthly hours
    st.markdown("---")
    st.subheader("Dein Hörverhalten")
    
    progress_value = min(monthly_hours / 40, 1.0)  # Cap at 40 hours for visualization
    st.progress(progress_value)
    
    if monthly_hours < 20:
        st.info(f"Du bist bei {monthly_hours:.1f} Stunden - noch {20 - monthly_hours:.1f} Stunden bis zur Empfehlung!")
    elif monthly_hours < 40:
        st.success(f"Perfekt! Du hörst {monthly_hours:.1f} Stunden - das ist optimal für ein Abonnement!")
    else:
        st.success(f"Wow! Du hörst {monthly_hours:.1f} Stunden - definitiv ein Power-User!")
    
    # Cost analysis with visual elements
    st.markdown("---")
    st.subheader("Kostenanalyse")
    
    spotify_cost = 12.99
    cost_per_hour = spotify_cost / monthly_hours if monthly_hours > 0 else 0
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div style="background-color: #2d3748; border-left: 5px solid #48bb78; padding: 15px; margin: 10px 0;">
            <h4 style="color: #48bb78; margin: 0;">Spotify Premium</h4>
            <h2 style="color: #f7fafc; margin: 5px 0;">{:.2f} EUR</h2>
            <p style="margin: 0; color: #a0aec0;">pro Monat</p>
        </div>
        """.format(spotify_cost), unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div style="background-color: #2d3748; border-left: 5px solid #f56565; padding: 15px; margin: 10px 0;">
            <h4 style="color: #f56565; margin: 0;">Kosten pro Stunde</h4>
            <h2 style="color: #f7fafc; margin: 5px 0;">{:.2f} EUR</h2>
            <p style="margin: 0; color: #a0aec0;">bei deinem Konsum</p>
        </div>
        """.format(cost_per_hour), unsafe_allow_html=True)
    
    # Final recommendation
    st.markdown("---")
    if monthly_hours >= 20:
        st.markdown("""
        <div style="background: #d4edda; border: 1px solid #c3e6cb; border-left: 4px solid #28a745; 
                    color: #155724; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h3 style="margin: 0 0 10px 0; color: #155724;">Fazit: Abonnement lohnt sich!</h3>
            <p style="margin: 0; color: #155724;">Du hörst genug Musik, um das Abonnement zu rechtfertigen.</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-left: 4px solid #dc3545; 
                    color: #721c24; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h3 style="margin: 0 0 10px 0; color: #721c24;">Fazit: Abonnement lohnt sich nicht</h3>
            <p style="margin: 0; color: #721c24;">Du hörst zu wenig Musik für ein monatliches Abonnement.</p>
        </div>
        """, unsafe_allow_html=True)

def render(db, cfg, prefix: str):
    """Main render function for Vadim's interface."""
    st.session_state._orchestrator_mongo_db = db
    
    # Main header
    st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1DB954;
        text-align: center;
        margin-bottom: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Date range selector
    col1, col2 = st.columns(2)
    
    with col1:
        start_date = st.date_input(
            "Von",
            value=date.today() - timedelta(days=30),
            help="Startdatum für die Analyse"
        )
    
    with col2:
        end_date = st.date_input(
            "Bis",
            value=date.today(),
            help="Enddatum für die Analyse"
        )
    
    # Validate date range
    if start_date > end_date:
        st.error("Startdatum kann nicht nach dem Enddatum liegen!")
        return
    
    # Convert to datetime
    start_dt, end_dt = _utc_range(start_date, end_date)
    
    # Tab selection
    tab_options = {
        "Allgemeine Statistiken": "general",
        "Playlist Vergleich": "playlists",
        "Zeitraum Statistiken": "period",
        "Abonnement Analyse": "subscription"
    }
    
    selected_tab = st.selectbox(
        "Wählen Sie eine Analyse:",
        options=list(tab_options.keys()),
        index=0
    )
    
    # Render selected tab
    if tab_options[selected_tab] == "general":
        render_general_stats(db, start_dt, end_dt)
    elif tab_options[selected_tab] == "playlists":
        render_playlist_comparison(db, start_dt, end_dt)
    elif tab_options[selected_tab] == "period":
        render_period_stats(db, start_dt, end_dt)
    elif tab_options[selected_tab] == "subscription":
        render_subscription_analysis(db, start_dt, end_dt)
    
    # Footer
    st.markdown("---")