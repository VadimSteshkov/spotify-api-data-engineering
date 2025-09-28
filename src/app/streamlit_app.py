#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Streamlit dashboard for Spotify pipeline (multi-owner friendly).

Reads from MongoDB:
- <prefix>_recent_events (append-only play events)
- <prefix>_artist_market_top_tracks (latest top10 per dominant artist & market)

ENV (optional):
	# Mongo
	MONGO_URL  = "mongodb://root:example@localhost:27017/?authSource=admin"
	MONGO_DB   = "spotify_db"

	# Owner/prefix convention so each colleague can have isolated collections
	OWNER_PREFIX = "avd"  # e.g., "alex", "bogdan", ...

	# (Advanced) Override collection names explicitly if needed
	COLL_EVENTS = "avd_recent_events"
	COLL_TOP10  = "avd_artist_market_top_tracks"

Run:
	streamlit run src/app/streamlit_app.py
"""

import os
from datetime import datetime, timezone, date, time
from typing import Optional, Tuple, List

import pandas as pd
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import streamlit as st

# -----------------------------
# Config (env with safe defaults; supports team prefixes)
# -----------------------------
MONGO_URL = os.getenv("MONGO_URL", "mongodb://root:example@localhost:27017/?authSource=admin")
DB_NAME   = os.getenv("MONGO_DB",  "spotify_db")

OWNER_PREFIX = os.getenv("OWNER_PREFIX", "avd").strip() or "avd"
DEFAULT_COLL_EVENTS = f"{OWNER_PREFIX}_recent_events"
DEFAULT_COLL_TOP10  = f"{OWNER_PREFIX}_artist_market_top_tracks"

# Allow explicit overrides via env if a colleague wants custom names
COLL_EVENTS = os.getenv("COLL_EVENTS", DEFAULT_COLL_EVENTS)
COLL_TOP10  = os.getenv("COLL_TOP10",  DEFAULT_COLL_TOP10)

# -----------------------------
# Mongo helpers (cached)
# -----------------------------
@st.cache_resource(show_spinner=False)
def _get_db():
	"""Create a single Mongo client per Streamlit session and return the DB handle."""
	client = MongoClient(MONGO_URL)
	return client[DB_NAME]

# -----------------------------
# Common pipeline piece: normalize fields to arrays
# This makes the UI robust even if some older docs stored strings/nulls.
# -----------------------------
PIPE_NORMALIZE_ARTISTS = [
	{
		"$set": {
			"artist_ids_norm": {
				"$cond": [
					{ "$isArray": "$artist_ids" },
					"$artist_ids",
					{ "$cond": [ { "$eq": [ "$artist_ids", None ] }, [], [ "$artist_ids" ] ] }
				]
			},
			"artist_names_norm": {
				"$cond": [
					{ "$isArray": "$artist_names" },
					"$artist_names",
					{ "$cond": [ { "$eq": [ "$artist_names", None ] }, [], [ "$artist_names" ] ] }
				]
			}
		}
	}
]

def _utc_range(d_from: date, d_to: date) -> Tuple[datetime, datetime]:
	"""Helper: convert two date objects to full-day UTC datetime interval."""
	start = datetime.combine(d_from, time.min, tzinfo=timezone.utc)
	end   = datetime.combine(d_to,   time.max, tzinfo=timezone.utc)
	return start, end

@st.cache_data(show_spinner=False, ttl=60)
def _load_recent_events(
	date_range: Optional[Tuple[datetime, datetime]] = None,
	limit: int = 5000
) -> pd.DataFrame:
	"""Load recent events with safe projection; attach parsed datetime for UI."""
	try:
		db = _get_db()
		q = {}
		if date_range:
			start, end = date_range
			# played_at is string in UTC → lexicographic filter works
			q["played_at"] = {"$gte": start.isoformat(), "$lte": end.isoformat()}

		cur = db[COLL_EVENTS].find(
			q,
			{
				"_id": 0,
				"user_id": 1,
				"played_at": 1,
				"track_id": 1,
				"track_name": 1,
				"artist_ids": 1,
				"artist_names": 1,
				"album_id": 1,
				"album_name": 1,
				"country": 1,
				"market_used": 1,
			},
		).sort("played_at", -1).limit(int(limit))
		df = pd.DataFrame(list(cur))
		if not df.empty:
			df["played_at_dt"] = pd.to_datetime(df["played_at"], utc=True, errors="coerce")
		return df
	except PyMongoError as e:
		st.error(f"Mongo error while loading events: {e}")
		return pd.DataFrame()

@st.cache_data(show_spinner=False, ttl=60)
def _top_artists(
	limit: int = 20,
	date_range: Optional[Tuple[datetime, datetime]] = None
) -> pd.DataFrame:
	"""Compute top artists by play count, robust to mixed schemas."""
	try:
		db = _get_db()
		match = {}
		if date_range:
			start, end = date_range
			match["played_at"] = {"$gte": start.isoformat(), "$lte": end.isoformat()}

		pipeline: List[dict] = []
		pipeline += PIPE_NORMALIZE_ARTISTS
		pipeline.append({ "$match": match } if match else { "$match": {} })
		pipeline += [
			{ "$unwind": "$artist_ids_norm" },
			{ "$group": { "_id": "$artist_ids_norm", "plays": { "$sum": 1 } } },
			{ "$sort": { "plays": -1 } },
			{ "$limit": int(limit) },

			# Best-effort to fetch a representative name without assuming aligned arrays
			{
				"$lookup": {
					"from": COLL_EVENTS,
					"localField": "_id",
					"foreignField": "artist_ids",  # matches any doc where artist_ids array contains _id
					"as": "sample_docs"
				}
			},
			{
				"$set": {
					"artist_name": {
						"$let": {
							"vars": { "first": { "$first": "$sample_docs" } },
							"in": {
								"$cond": [
									{ "$gt": [ { "$size": { "$ifNull": [ "$$first.artist_names", [] ] } }, 0 ] },
									{ "$arrayElemAt": [ "$$first.artist_names", 0 ] },
									"Unknown"
								]
							}
						}
					}
				}
			},
			{ "$project": { "_id": 0, "artist_id": "$_id", "artist_name": 1, "plays": 1 } }
		]

		rows = list(db[COLL_EVENTS].aggregate(pipeline))
		df = pd.DataFrame(rows)
		return df
	except PyMongoError as e:
		st.error(f"Mongo error while computing top artists: {e}")
		return pd.DataFrame()

@st.cache_data(show_spinner=False, ttl=60)
def _top_tracks(
	limit: int = 20,
	date_range: Optional[Tuple[datetime, datetime]] = None
) -> pd.DataFrame:
	"""Compute top tracks by play count (groups by track_id & track_name)."""
	try:
		db = _get_db()
		match = {}
		if date_range:
			start, end = date_range
			match["played_at"] = {"$gte": start.isoformat(), "$lte": end.isoformat()}

		pipeline = [
			{ "$match": match } if match else { "$match": {} },
			{
				"$group": {
					"_id": { "track_id": "$track_id", "track_name": "$track_name" },
					"plays": { "$sum": 1 },
					"any_artist_names": { "$first": "$artist_names" },
				}
			},
			{ "$sort": { "plays": -1 } },
			{ "$limit": int(limit) },
		]
		rows = list(db[COLL_EVENTS].aggregate(pipeline))
		df = pd.DataFrame(rows)
		if not df.empty:
			df["track_id"] = df["_id"].apply(lambda x: (x or {}).get("track_id"))
			df["track_name"] = df["_id"].apply(lambda x: (x or {}).get("track_name"))
			df.drop(columns=["_id"], inplace=True, errors="ignore")
		return df
	except PyMongoError as e:
		st.error(f"Mongo error while computing top tracks: {e}")
		return pd.DataFrame()

@st.cache_data(show_spinner=False, ttl=60)
def _latest_top10_docs(limit: int = 20) -> pd.DataFrame:
	"""Load the latest generated 'Top 10 for dominant artist' documents."""
	try:
		db = _get_db()
		cur = db[COLL_TOP10].find({}, {"_id": 0}).sort("generated_at", -1).limit(int(limit))
		df = pd.DataFrame(list(cur))
		return df
	except PyMongoError as e:
		st.error(f"Mongo error while loading top10 docs: {e}")
		return pd.DataFrame()

# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="Spotify Dashboard (Team-ready)", page_icon="🎧", layout="wide")
st.title("Spotify Dashboard")

with st.sidebar:
	st.header("Filters")
	st.caption(f"Mongo DB: **{DB_NAME}**, Collections: **{COLL_EVENTS}**, **{COLL_TOP10}**")

	utc_now = datetime.now(timezone.utc)
	default_from = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)

	date_from = st.date_input("From (UTC date)", default_from.date())
	date_to   = st.date_input("To (UTC date)", utc_now.date())
	top_k = st.slider("Top K", min_value=5, max_value=50, value=10, step=5)
	show_limit = st.selectbox("Recent plays limit", options=[100, 250, 500, 1000, 5000], index=2)

	date_range = _utc_range(date_from, date_to)

# -----------------------------
# Recent plays
# -----------------------------
st.subheader("Recent plays")
df_recent = _load_recent_events(date_range=date_range, limit=int(show_limit))
st.caption(f"{len(df_recent)} rows")
if df_recent.empty:
	st.info(f"No data found in {COLL_EVENTS} for the selected range.")
else:
	st.dataframe(
		df_recent[["played_at_dt", "track_name", "artist_names", "album_name", "market_used"]]
		.rename(columns={"played_at_dt": "played_at"}),
		use_container_width=True,
	)

# -----------------------------
# Side-by-side: Top artists / Top tracks
# -----------------------------
col1, col2 = st.columns(2, gap="large")

with col1:
	st.subheader("Top artists (by plays)")
	df_art = _top_artists(limit=top_k, date_range=date_range)
	if df_art.empty:
		st.info("No artist data found.")
	else:
		df_art["label"] = df_art["artist_name"].fillna(df_art["artist_id"])
		st.bar_chart(df_art.set_index("label")["plays"])
		st.dataframe(df_art[["artist_id", "artist_name", "plays"]], use_container_width=True)

with col2:
	st.subheader("Top tracks (by plays)")
	df_tr = _top_tracks(limit=top_k, date_range=date_range)
	if df_tr.empty:
		st.info("No track data found.")
	else:
		df_tr["label"] = df_tr["track_name"].fillna(df_tr["track_id"])
		st.bar_chart(df_tr.set_index("label")["plays"])
		st.dataframe(
			df_tr[["track_id", "track_name", "any_artist_names", "plays"]]
				.rename(columns={"any_artist_names": "artist_names"}),
			use_container_width=True,
		)

# -----------------------------
# Latest Top 10 docs
# -----------------------------
st.subheader("Latest ‘Top 10 for dominant artist in market’ docs")
df_top10 = _latest_top10_docs(limit=10)
if df_top10.empty:
	st.info(f"No documents in {COLL_TOP10} yet.")
else:
	cols = ["generated_at", "market", "artist_name", "artist_id", "user_id"]
	existing_cols = [c for c in cols if c in df_top10.columns]
	if existing_cols:
		st.dataframe(df_top10[existing_cols], use_container_width=True)
	else:
		st.dataframe(df_top10, use_container_width=True)

	for i, row in df_top10.iterrows():
		title = f"{row.get('artist_name','?')} · {row.get('market','?')} · {row.get('generated_at','?')}"
		with st.expander(title):
			tracks = pd.DataFrame(row.get("tracks") or [])
			if not tracks.empty:
				show_cols = [c for c in ["rank", "track_name", "duration_ms", "album_name", "artists"] if c in tracks.columns]
				if "rank" in show_cols:
					st.dataframe(tracks[show_cols].set_index("rank"), use_container_width=True)
				else:
					st.dataframe(tracks[show_cols], use_container_width=True)
			else:
				st.write("No tracks array.")

