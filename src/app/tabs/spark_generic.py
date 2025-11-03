# tabs
# -*- coding: utf-8 -*-
"""
Generic Spark results tab for a teammate's prefix.

Discovers Mongo collections named: <prefix>_spark_*
Renders:
- top_artists / top_tracks as charts + tables
- top_tracks_grouped / top_artists_grouped with group selection + cumulative aggregation
- feature_avg as weighted-avg grouped tables

Supports BSON datetime or string for batch_ts.
Adds date-range filter, cumulative toggle, and Top-N for cumulative.

This version adds:
- show_collection_headers (bool): hide/show raw collection-name headers
- pretty_titles (dict): optional mapping {collection_name -> pretty label}
"""

import re
from datetime import datetime, time, timezone
import pandas as pd
import streamlit as st
from pymongo.errors import PyMongoError


# ---------- helpers ----------

def _to_utc_dt(v) -> datetime | None:
	"""
	Normalize a Mongo value to UTC datetime.
	Accepts: datetime (naive or tz), ISO string, else None.
	"""
	if v is None:
		return None
	if isinstance(v, datetime):
		return (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc))
	if isinstance(v, str):
		try:
			dt = datetime.fromisoformat(v)
			return (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc))
		except Exception:
			return None
	return None


def _list_collections(db, prefix: str):
	pat = re.compile(rf"^{re.escape(prefix)}_spark_")
	try:
		return [c for c in db.list_collection_names() if pat.match(c)]
	except PyMongoError as e:
		st.error(f"Mongo error while listing collections: {e}")
		return []


def _time_bounds(db, coll: str) -> tuple[datetime | None, datetime | None]:
	"""Find min/max batch_ts as UTC datetimes (works for datetime or string)."""
	try:
		first = db[coll].find({}, {"_id": 0, "batch_ts": 1}).sort("batch_ts", 1).limit(1)
		last = db[coll].find({}, {"_id": 0, "batch_ts": 1}).sort("batch_ts", -1).limit(1)
		fd = next(iter(first), None)
		ld = next(iter(last), None)
		if not fd or not ld:
			return None, None
		return _to_utc_dt(fd.get("batch_ts")), _to_utc_dt(ld.get("batch_ts"))
	except Exception:
		return None, None


def _range_query(start_dt: datetime | None, end_dt: datetime | None) -> dict:
	"""
	Build Mongo range query for batch_ts using Python datetimes in UTC.
	Works whether stored as BSON datetime or ISO string.
	"""
	if not start_dt or not end_dt:
		return {}
	return {"batch_ts": {"$gte": start_dt, "$lte": end_dt}}


def _load_per_batch(
	db, coll: str, start_dt: datetime | None, end_dt: datetime | None,
	limit: int = 2000, group_val: str | None = None
) -> pd.DataFrame:
	"""Load documents for a given date range (and optional group), sorted by batch_ts desc."""
	q = _range_query(start_dt, end_dt)
	if group_val:
		q["group"] = group_val
	try:
		cur = db[coll].find(q, {"_id": 0}).sort("batch_ts", -1).limit(limit)
		return pd.DataFrame(list(cur))
	except PyMongoError as e:
		st.error(f"Mongo error while loading {coll}: {e}")
		return pd.DataFrame()


# ---------- cumulative aggregations ----------

def _agg_artists_over_range(db, coll: str, start_dt: datetime, end_dt: datetime, topn: int) -> pd.DataFrame:
	pipeline = [
		{"$match": _range_query(start_dt, end_dt)},
		{"$group": {"_id": "$artist_name", "plays": {"$sum": "$plays"}}},
		{"$sort": {"plays": -1}},
		{"$limit": int(topn)},
	]
	try:
		rows = list(db[coll].aggregate(pipeline))
		return pd.DataFrame([{"artist_name": r["_id"], "plays": r["plays"]} for r in rows])
	except PyMongoError as e:
		st.error(f"Mongo error while aggregating {coll}: {e}")
		return pd.DataFrame()


def _agg_artists_by_group_over_range(
	db, coll: str, start_dt: datetime, end_dt: datetime, topn: int, group_value: str
) -> pd.DataFrame:
	"""
	Aggregate top artists for a specific group (e.g., country) over the selected date range.
	"""
	pipeline = [
		{"$match": {**_range_query(start_dt, end_dt), "group": group_value}},
		{"$group": {"_id": "$artist_name", "plays": {"$sum": "$plays"}}},
		{"$sort": {"plays": -1}},
		{"$limit": int(topn)},
	]
	try:
		rows = list(db[coll].aggregate(pipeline))
		return pd.DataFrame([{"artist_name": r["_id"], "plays": r["plays"]} for r in rows])
	except PyMongoError as e:
		st.error(f"Mongo error while aggregating {coll}: {e}")
		return pd.DataFrame()


def _agg_tracks_over_range(db, coll: str, start_dt: datetime, end_dt: datetime, topn: int) -> pd.DataFrame:
	pipeline = [
		{"$match": _range_query(start_dt, end_dt)},
		{"$group": {
			"_id": {"track_id": "$track_id", "track_name": "$track_name"},
			"plays": {"$sum": "$plays"}
		}},
		{"$sort": {"plays": -1}},
		{"$limit": int(topn)},
	]
	try:
		rows = list(db[coll].aggregate(pipeline))
		out = []
		for r in rows:
			k = r.get("_id") or {}
			out.append({"track_id": k.get("track_id"), "track_name": k.get("track_name"), "plays": r["plays"]})
		return pd.DataFrame(out)
	except PyMongoError as e:
		st.error(f"Mongo error while aggregating {coll}: {e}")
		return pd.DataFrame()


def _agg_tracks_by_group_over_range(
	db, coll: str, start_dt: datetime, end_dt: datetime, topn: int, group_value: str
) -> pd.DataFrame:
	"""
	Aggregate top tracks for a specific group (e.g., country) over the selected date range.
	"""
	pipeline = [
		{"$match": {**_range_query(start_dt, end_dt), "group": group_value}},
		{"$group": {
			"_id": {"track_id": "$track_id", "track_name": "$track_name"},
			"plays": {"$sum": "$plays"}
		}},
		{"$sort": {"plays": -1}},
		{"$limit": int(topn)},
	]
	try:
		rows = list(db[coll].aggregate(pipeline))
		out = []
		for r in rows:
			k = r.get("_id") or {}
			out.append({
				"track_id": k.get("track_id"),
				"track_name": k.get("track_name"),
				"plays": r["plays"]
			})
		return pd.DataFrame(out)
	except PyMongoError as e:
		st.error(f"Mongo error while aggregating {coll}: {e}")
		return pd.DataFrame()


def _agg_feature_avg_over_range(db, coll: str, start_dt: datetime, end_dt: datetime, topn: int) -> pd.DataFrame:
	"""
	Weighted average over batches:
	avg = sum(avg_value * rows) / sum(rows), grouped by 'group'.
	"""
	pipeline = [
		{"$match": _range_query(start_dt, end_dt)},
		{"$group": {
			"_id": "$group",
			"w_sum": {"$sum": {"$multiply": ["$avg_value", "$rows"]}},
			"rows_sum": {"$sum": "$rows"}
		}},
		{"$project": {
			"_id": 0,
			"group": "$_id",
			"rows": "$rows_sum",
			"avg_value": {"$cond": [{"$gt": ["$rows_sum", 0]}, {"$divide": ["$w_sum", "$rows_sum"]}, None]}
		}},
		{"$sort": {"avg_value": -1}},
		{"$limit": int(topn)},
	]
	try:
		return pd.DataFrame(list(db[coll].aggregate(pipeline)))
	except PyMongoError as e:
		st.error(f"Mongo error while aggregating {coll}: {e}")
		return pd.DataFrame()


# ---------- renderers ----------

def _render_top_artists(df: pd.DataFrame):
	if df.empty:
		st.info("No data.")
		return
	if {"artist_name", "plays"}.issubset(df.columns):
		st.bar_chart(df.set_index("artist_name")["plays"])
	st.dataframe(df, use_container_width=True)


def _render_top_tracks(df: pd.DataFrame):
	if df.empty:
		st.info("No data.")
		return
	cols = [c for c in ["track_name", "track_id", "plays", "batch_ts"] if c in df.columns]
	if "track_name" in cols and "plays" in cols:
		st.bar_chart(df.set_index("track_name")["plays"])
	st.dataframe(df[cols] if cols else df, use_container_width=True)


def _render_feature_avg(df: pd.DataFrame):
	if df.empty:
		st.info("No data.")
		return
	metric_cols = [c for c in ["avg_value", "rows"] if c in df.columns]
	st.dataframe(df, use_container_width=True)
	group_cols = [c for c in df.columns if c not in metric_cols + ["batch_ts", "mode", "feature", "group", "prefix", "batch_id"]]
	if "avg_value" in df.columns and len(group_cols) == 1:
		st.bar_chart(df.set_index(group_cols[0])["avg_value"])


# ---------- main entry ----------

def render(
	db,
	cfg,
	prefix: str,
	show_collection_headers: bool = True,
	pretty_titles: dict | None = None
) -> None:
	"""
	Render Spark dashboards for collections like '<prefix>_spark_*'.

	Args:
	- show_collection_headers: hide/show raw collection-name headers
	- pretty_titles: optional mapping {collection_name -> pretty label}
	"""
	try:
		colls = [c for c in db.list_collection_names() if re.match(rf"^{re.escape(prefix)}_spark_", c)]
	except PyMongoError as e:
		st.error(f"Mongo error while listing collections: {e}")
		return

	if not colls:
		st.info(f"No collections found like '{prefix}_spark_*'.")
		return

	# Human-friendly labels when needed (without breaking legacy)
	mode_labels = {
		"top_artists": "Top Artists",
		"top_tracks": "Top Tracks",
		"top_artists_grouped": "Top Artists by Group",
		"top_tracks_grouped": "Top Tracks by Group",
		"feature_avg": "Feature Averages",
		"unknown": "Spark Results",
	}

	for coll in sorted(colls):
		# Determine mode (used for fallback label)
		mode = "unknown"
		try:
			sdoc = db[coll].find_one({}, {"_id": 0, "mode": 1})
			if sdoc and sdoc.get("mode"):
				mode = sdoc["mode"]
		except Exception:
			pass

		# Resolve label: pretty_titles > mode label > raw name
		friendly = (
			pretty_titles.get(coll)
			if (pretty_titles and coll in pretty_titles)
			else mode_labels.get(mode, coll)
		)

		# Legacy-preserving header behavior
		if show_collection_headers:
			# If caller did NOT pass pretty_titles → show RAW collection name (legacy UI)
			if not pretty_titles:
				st.subheader(coll)
			else:
				st.subheader(friendly)
		else:
			# Headers hidden → still provide a friendly inline title
			st.markdown(f"### {friendly}")

		# Controls
		min_dt, max_dt = _time_bounds(db, coll)
		col_a, col_b, col_c = st.columns([2, 2, 2])
		with col_a:
			start_date = st.date_input("From", value=(min_dt.date() if min_dt else None), key=f"{coll}_from")
		with col_b:
			end_date = st.date_input("To", value=(max_dt.date() if max_dt else None), key=f"{coll}_to")
		with col_c:
			cumulative = st.checkbox("Cumulative over range", value=True, key=f"{coll}_cum")

		# Convert to full-day UTC bounds
		start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc) if start_date else None
		end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc) if end_date else None

		top_k = st.slider("Top N (for cumulative)", min_value=5, max_value=100, value=10, step=5, key=f"{coll}_topn")

		# Group dropdown for grouped modes (with fallback to all groups if range has none)
		selected_group = None
		if mode in ("top_tracks_grouped", "top_artists_grouped"):
			try:
				groups_in_range = sorted(db[coll].distinct("group", _range_query(start_dt, end_dt)))
			except Exception:
				groups_in_range = []
			if not groups_in_range:
				try:
					groups_in_range = sorted(db[coll].distinct("group"))
				except Exception:
					groups_in_range = []
			if groups_in_range:
				selected_group = st.selectbox("Group", groups_in_range, key=f"{coll}_group")
			else:
				st.info("No groups available.")

		# Context subtitle
		range_txt = f"{start_date or '—'} → {end_date or '—'}"
		group_txt = f" • Group: {selected_group}" if selected_group else ""
		cum_txt = f" • Cumulative (Top {top_k})" if cumulative else " • Per-batch view"
		st.caption(f"{range_txt}{group_txt}{cum_txt}")

		# Render by mode
		if cumulative and start_dt and end_dt:
			if mode == "top_artists" and selected_group is None:
				_render_top_artists(_agg_artists_over_range(db, coll, start_dt, end_dt, top_k))
			elif mode == "top_tracks" and selected_group is None:
				_render_top_tracks(_agg_tracks_over_range(db, coll, start_dt, end_dt, top_k))
			elif mode == "top_tracks_grouped" and selected_group:
				_render_top_tracks(_agg_tracks_by_group_over_range(db, coll, start_dt, end_dt, top_k, selected_group))
			elif mode == "top_artists_grouped" and selected_group:
				_render_top_artists(_agg_artists_by_group_over_range(db, coll, start_dt, end_dt, top_k, selected_group))
			elif mode == "feature_avg":
				_render_feature_avg(_agg_feature_avg_over_range(db, coll, start_dt, end_dt, top_k))
			else:
				st.dataframe(_load_per_batch(db, coll, start_dt, end_dt, 2000, selected_group), use_container_width=True)
		else:
			df = _load_per_batch(db, coll, start_dt, end_dt, 2000, selected_group)
			if mode == "top_artists" and selected_group is None:
				_render_top_artists(df)
			elif mode == "top_tracks" and selected_group is None:
				_render_top_tracks(df)
			elif mode == "top_tracks_grouped":
				_render_top_tracks(df if selected_group is None else df[df.get("group") == selected_group])
			elif mode == "top_artists_grouped":
				_render_top_artists(df if selected_group is None else df[df.get("group") == selected_group])
			elif mode == "feature_avg":
				_render_feature_avg(df)
			else:
				st.dataframe(df, use_container_width=True)

