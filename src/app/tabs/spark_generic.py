# -*- coding: utf-8 -*-
"""
Generic Spark results tab for a teammate's prefix.

This tab discovers all Mongo collections named:
	<prefix>_spark_*

…and renders each one nicely:
- top_artists / top_tracks as charts + tables
- feature_avg grouped tables (with feature name in docs)
"""

import re
import streamlit as st
import pandas as pd
from pymongo.errors import PyMongoError

def _list_collections(db, prefix: str):
	pat = re.compile(rf"^{re.escape(prefix)}_spark_")
	try:
		return [c for c in db.list_collection_names() if pat.match(c)]
	except PyMongoError as e:
		st.error(f"Mongo error while listing collections: {e}")
		return []

def _load_all(db, coll: str, limit: int = 2000) -> pd.DataFrame:
	try:
		cur = db[coll].find({}, {"_id": 0}).sort("batch_ts", -1).limit(limit)
		return pd.DataFrame(list(cur))
	except PyMongoError as e:
		st.error(f"Mongo error while loading {coll}: {e}")
		return pd.DataFrame()

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
	# Try to guess metric columns
	metric_cols = [c for c in ["avg_value", "rows"] if c in df.columns]
	# Display grouped table
	st.dataframe(df, use_container_width=True)
	# If there's a single grouping + avg_value -> draw quick bar
	group_cols = [c for c in df.columns if c not in metric_cols + ["batch_ts", "mode", "feature", "group", "prefix", "batch_id"]]
	if "avg_value" in df.columns and len(group_cols) == 1:
		st.bar_chart(df.set_index(group_cols[0])["avg_value"])

def render(db, cfg, prefix: str) -> None:
	st.caption(f"Spark collections for **{prefix}**")
	colls = _list_collections(db, prefix)
	if not colls:
		st.info(f"No collections found like '{prefix}_spark_*'.")
		return

	for coll in sorted(colls):
		st.subheader(coll)
		df = _load_all(db, coll, limit=2000)
		mode = "unknown"
		if "mode" in df.columns and df["mode"].notna().any():
			mode = df["mode"].iloc[0]

		if mode == "top_artists":
			_render_top_artists(df)
		elif mode == "top_tracks":
			_render_top_tracks(df)
		elif mode == "feature_avg":
			st.markdown(f"*Feature:* **{df.get('feature', pd.Series(['?'])).iloc[0]}**  ·  *Group:* **{df.get('group', pd.Series(['?'])).iloc[0]}**")
			_render_feature_avg(df)
		else:
			st.dataframe(df, use_container_width=True)

