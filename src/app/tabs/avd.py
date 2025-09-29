# -*- coding: utf-8 -*-
"""
Runs as a plugin inside the orchestrator (db handle is injected).
"""

import os
from datetime import datetime, timezone, date, time
from typing import Tuple, List

import pandas as pd
import streamlit as st
import altair as alt
from pymongo.errors import PyMongoError

# =========================
# Helpers (prefix-based collections)
# =========================
def _coll_names(prefix: str) -> Tuple[str, str]:
	"""Return (events_collection, top10_collection) for a given prefix."""
	coll_events = f"{prefix}_recent_events"
	coll_top10 = f"{prefix}_artist_market_top_tracks"
	# Allow explicit overrides via env if someone really wants custom names per tab
	coll_events = os.getenv("COLL_EVENTS", coll_events)
	coll_top10 = os.getenv("COLL_TOP10", coll_top10)
	return coll_events, coll_top10


def _utc_range(d_from: date, d_to: date) -> Tuple[datetime, datetime]:
	"""Convert two date objects to full-day UTC datetime interval."""
	start = datetime.combine(d_from, time.min, tzinfo=timezone.utc)
	end = datetime.combine(d_to, time.max, tzinfo=timezone.utc)
	return start, end


# Normalization pipe (robust to older docs)
PIPE_NORMALIZE_ARTISTS = [
	{
		"$set": {
			"artist_ids_norm": {
				"$cond": [
					{"$isArray": "$artist_ids"},
					"$artist_ids",
					{"$cond": [{"$eq": ["$artist_ids", None]}, [], ["$artist_ids"]]},
				]
			},
			"artist_names_norm": {
				"$cond": [
					{"$isArray": "$artist_names"},
					"$artist_names",
					{"$cond": [{"$eq": ["$artist_names", None]}, [], ["$artist_names"]]},
				]
			},
		}
	}
]


# =========================
# Data loaders / computations (cached)
# =========================
@st.cache_data(show_spinner=False, ttl=60)
def _load_recent_events(db_name: str, coll_name: str, d_from: str, d_to: str, limit: int) -> pd.DataFrame:
	"""Load recent events with safe projection; attach parsed datetime for UI."""
	try:
		db = st.session_state._orchestrator_mongo_db  # injected by orchestrator render()
		q = {"played_at": {"$gte": d_from, "$lte": d_to}} if (d_from and d_to) else {}
		cur = db[coll_name].find(
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
		st.error(f"Mongo error while loading events from {coll_name}: {e}")
		return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=60)
def _top_artists(db_name: str, coll_name: str, d_from: str, d_to: str, limit: int) -> pd.DataFrame:
	"""Compute top artists by play count, robust to mixed schemas."""
	try:
		db = st.session_state._orchestrator_mongo_db
		match = {"played_at": {"$gte": d_from, "$lte": d_to}} if (d_from and d_to) else {}

		pipeline: List[dict] = []
		pipeline += PIPE_NORMALIZE_ARTISTS
		pipeline.append({"$match": match} if match else {"$match": {}})
		pipeline += [
			{"$unwind": "$artist_ids_norm"},
			{"$group": {"_id": "$artist_ids_norm", "plays": {"$sum": 1}}},
			{"$sort": {"plays": -1}},
			{"$limit": int(limit)},
			{
				"$lookup": {
					"from": coll_name,
					"localField": "_id",
					"foreignField": "artist_ids",
					"as": "sample_docs",
				}
			},
			{
				"$set": {
					"artist_name": {
						"$let": {
							"vars": {"first": {"$first": "$sample_docs"}},
							"in": {
								"$cond": [
									{"$gt": [{"$size": {"$ifNull": ["$$first.artist_names", []]}}, 0]},
									{"$arrayElemAt": ["$$first.artist_names", 0]},
									"Unknown",
								]
							},
						}
					}
				}
			},
			{"$project": {"_id": 0, "artist_id": "$_id", "artist_name": 1, "plays": 1}},
		]

		rows = list(db[coll_name].aggregate(pipeline))
		return pd.DataFrame(rows)
	except PyMongoError as e:
		st.error(f"Mongo error while computing top artists from {coll_name}: {e}")
		return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=60)
def _top_tracks(db_name: str, coll_name: str, d_from: str, d_to: str, limit: int) -> pd.DataFrame:
	"""Compute top tracks by play count (groups by track_id & track_name)."""
	try:
		db = st.session_state._orchestrator_mongo_db
		match = {"played_at": {"$gte": d_from, "$lte": d_to}} if (d_from and d_to) else {}
		pipeline = [
			{"$match": match} if match else {"$match": {}},
			{
				"$group": {
					"_id": {"track_id": "$track_id", "track_name": "$track_name"},
					"plays": {"$sum": 1},
					"any_artist_names": {"$first": "$artist_names"},
				}
			},
			{"$sort": {"plays": -1}},
			{"$limit": int(limit)},
		]
		rows = list(db[coll_name].aggregate(pipeline))
		df = pd.DataFrame(rows)
		if not df.empty:
			df["track_id"] = df["_id"].apply(lambda x: (x or {}).get("track_id"))
			df["track_name"] = df["_id"].apply(lambda x: (x or {}).get("track_name"))
			df.drop(columns=["_id"], inplace=True, errors="ignore")
		return df
	except PyMongoError as e:
		st.error(f"Mongo error while computing top tracks from {coll_name}: {e}")
		return pd.DataFrame()


@st.cache_data(show_spinner=False, ttl=60)
def _latest_top10_docs(db_name: str, coll_name: str, limit: int) -> pd.DataFrame:
	"""Load the latest generated 'Top 10 for dominant artist' documents."""
	try:
		db = st.session_state._orchestrator_mongo_db
		cur = db[coll_name].find({}, {"_id": 0}).sort("generated_at", -1).limit(int(limit))
		return pd.DataFrame(list(cur))
	except PyMongoError as e:
		st.error(f"Mongo error while loading top10 docs from {coll_name}: {e}")
		return pd.DataFrame()


# =========================
# Main render (tab)
# =========================
def render(db, cfg, prefix: str):
	"""
	Render a tab for the given prefix.
	- Uses its own filters (date range, limits)
	- Shows: daily plays, plays per market, recent plays, top artists, top tracks, latest Top-10 docs
	"""
	# Expose db handle to cached functions
	st.session_state._orchestrator_mongo_db = db

	coll_events, coll_top10 = _coll_names(prefix)

	# Filters (tab-level, independent from other tabs)
	with st.sidebar:
		st.markdown(f"**[{prefix}]** Collections: `{coll_events}`, `{coll_top10}`")

	utc_now = datetime.now(timezone.utc)
	default_from = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)

	col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
	with col_f1:
		date_from = st.date_input("From (UTC date)", default_from.date(), key=f"{prefix}_from")
	with col_f2:
		date_to = st.date_input("To (UTC date)", utc_now.date(), key=f"{prefix}_to")
	with col_f3:
		top_k = st.slider("Top N items", min_value=5, max_value=50, value=10, step=5, key=f"{prefix}_topk")
	show_limit = st.selectbox(
		"Recent plays limit",
		options=[100, 250, 500, 1000, 5000],
		index=2,
		key=f"{prefix}_limit",
	)

	start_dt, end_dt = _utc_range(date_from, date_to)
	start_iso, end_iso = start_dt.isoformat(), end_dt.isoformat()

	# === Daily plays (by selected date range) ===
	st.subheader("Daily plays (selected range)")

	coll_daily = f"{prefix}_recent_events"
	pipeline_daily = [
		{"$match": {"played_at": {"$gte": start_iso, "$lte": end_iso}}},
		{
			"$group": {
				"_id": {"$substr": ["$played_at", 0, 10]},  # YYYY-MM-DD
				"plays": {"$sum": 1}
			}
		},
		{"$sort": {"_id": 1}}
	]

	try:
		rows_daily = list(st.session_state._orchestrator_mongo_db[coll_daily].aggregate(pipeline_daily))
		df_daily = pd.DataFrame(rows_daily)
		if not df_daily.empty:
			df_daily.rename(columns={"_id": "date"}, inplace=True)
			st.line_chart(df_daily.set_index("date")["plays"])
			st.dataframe(df_daily, use_container_width=True)
		else:
			st.info("No data in the selected date range.")
	except PyMongoError as e:
		st.error(f"Mongo error while computing daily plays: {e}")

	# === Plays per market (selected range) ===
	st.subheader("Plays per market")

	pipeline_market = [
		{"$match": {"played_at": {"$gte": start_iso, "$lte": end_iso}}},
		{
			"$group": {
				"_id": "$market_used",
				"plays": {"$sum": 1}
			}
		},
		{"$sort": {"plays": -1}}
	]

	try:
		rows_market = list(st.session_state._orchestrator_mongo_db[coll_events].aggregate(pipeline_market))
		df_market = pd.DataFrame(rows_market)
		if not df_market.empty:
			df_market.rename(columns={"_id": "market"}, inplace=True)
			st.bar_chart(df_market.set_index("market")["plays"])
			# Optional: pie chart with Altair
			chart = alt.Chart(df_market).mark_arc().encode(
				theta="plays",
				color="market",
				tooltip=["market", "plays"]
			)
			st.altair_chart(chart, use_container_width=True)
			st.dataframe(df_market, use_container_width=True)
		else:
			st.info("No market data in the selected range.")
	except PyMongoError as e:
		st.error(f"Mongo error while computing plays per market: {e}")

	# ============ Recent plays ============
	st.subheader("Recent plays")
	df_recent = _load_recent_events(db.name, coll_events, start_iso, end_iso, int(show_limit))
	st.caption(f"{len(df_recent)} rows")
	if df_recent.empty:
		st.info(f"No data found in {coll_events} for the selected range.")
	else:
		st.dataframe(
			df_recent[["played_at_dt", "track_name", "artist_names", "album_name", "market_used"]]
				.rename(columns={"played_at_dt": "played_at"}),
			use_container_width=True,
		)

	# ============ Side-by-side: Top artists / Top tracks ============
	col1, col2 = st.columns(2, gap="large")

	with col1:
		st.subheader("Top artists (by plays)")
		df_art = _top_artists(db.name, coll_events, start_iso, end_iso, int(top_k))
		if df_art.empty:
			st.info("No artist data found.")
		else:
			df_art["label"] = df_art["artist_name"].fillna(df_art["artist_id"])
			st.bar_chart(df_art.set_index("label")["plays"])
			st.dataframe(df_art[["artist_id", "artist_name", "plays"]], use_container_width=True)

	with col2:
		st.subheader("Top tracks (by plays)")
		df_tr = _top_tracks(db.name, coll_events, start_iso, end_iso, int(top_k))
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

	# ============ Latest Top 10 docs ============
	st.subheader("Latest ‘Top 10 for dominant artist in market’ docs")
	df_top10 = _latest_top10_docs(db.name, coll_top10, limit=10)
	if df_top10.empty:
		st.info(f"No documents in {coll_top10} yet.")
	else:
		cols = ["generated_at", "market", "artist_name", "artist_id", "user_id"]
		existing_cols = [c for c in cols if c in df_top10.columns]
		if existing_cols:
			st.dataframe(df_top10[existing_cols], use_container_width=True)
		else:
			st.dataframe(df_top10, use_container_width=True)

		for _, row in df_top10.iterrows():
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

