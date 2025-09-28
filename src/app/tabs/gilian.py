# -*- coding: utf-8 -*-
"""
Rich teammate tab for prefix 'gil'.
Keeps the same sections as Dorin's tab: filters, recent plays, top artists, top tracks, latest Top-10.

"""

import pandas as pd
import streamlit as st
from datetime import datetime, timezone, date, time
from typing import Tuple
from pymongo.errors import PyMongoError

def _utc_range(d_from: date, d_to: date) -> Tuple[datetime, datetime]:
	"""Convert two date objects to full-day UTC datetime interval."""
	start = datetime.combine(d_from, time.min, tzinfo=timezone.utc)
	end = datetime.combine(d_to, time.max, tzinfo=timezone.utc)
	return start, end

def render(db, cfg, prefix: str):
	"""Render a tab for prefix 'gil' with filters and analytics."""
	st.session_state._orchestrator_mongo_db = db
	coll_events = f"{prefix}_recent_events"
	coll_top10 = f"{prefix}_artist_market_top_tracks"

	# Filters
	utc_now = datetime.now(timezone.utc)
	default_from = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)

	col_f1, col_f2, col_f3 = st.columns([1, 1, 1])
	with col_f1:
		date_from = st.date_input("From (UTC date)", default_from.date(), key=f"{prefix}_from")
	with col_f2:
		date_to = st.date_input("To (UTC date)", utc_now.date(), key=f"{prefix}_to")
	with col_f3:
		top_k = st.slider("Top N items", min_value=5, max_value=50, value=10, step=5, key=f"{prefix}_topn")
	show_limit = st.selectbox("Recent plays limit", options=[100, 250, 500, 1000, 5000], index=2, key=f"{prefix}_limit")

	start_dt, end_dt = _utc_range(date_from, date_to)
	start_iso, end_iso = start_dt.isoformat(), end_dt.isoformat()

	# Section placeholders
	st.subheader("Recent plays")
	st.info(f"Implement logic to load data from collection {coll_events} between {start_iso} and {end_iso}")

	st.subheader("Top artists (by plays)")
	st.info("Implement aggregation for top artists.")

	st.subheader("Top tracks (by plays)")
	st.info("Implement aggregation for top tracks.")

	st.subheader("Latest Top-10 docs")
	st.info(f"Implement loader for collection {coll_top10}")

