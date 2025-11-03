#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Musikfan tab wrapper:
- Keeps your existing Streamlit dashboard 100% intact (from avd_classic.py)
- Adds a second sub-tab that shows Spark results (auto-discovered <prefix>_spark_* collections)
- Orchestrator imports app.tabs.musikfan:render(db, cfg, prefix)
"""

import streamlit as st

# Import your current dashboard as "classic"
try:
	from tabs import avd_classic as classic_tab
except Exception:
	classic_tab = None

# Generic Spark renderer (shows all <prefix>_spark_* collections)
try:
	from tabs import spark_generic as spark_tab
except Exception:
	spark_tab = None


def render(db, cfg, prefix: str = "avd"):
	"""
	Entry point used by the orchestrator.
	Builds two sub-tabs:
	- Insights (Classic): original AVD dashboard (from avd_classic.py)
	- Spark (Aggregates): generic Spark collections for <prefix>_spark_*
	"""
	# Expose Mongo DB in session for legacy helpers (backward compatibility)
	st.session_state._orchestrator_mongo_db = db

	st.title("🎧 Musikfan's Dashboard")

	# Two focused sub-tabs
	tab_classic, tab_spark = st.tabs(["Insights (Classic)", "Spark (Aggregates)"])

	with tab_classic:
		if classic_tab and hasattr(classic_tab, "render"):
			classic_tab.render(db=db, cfg=cfg, prefix=prefix)
		else:
			st.error("Could not load avd_classic.render().")

	with tab_spark:
		if spark_tab and hasattr(spark_tab, "render"):
			# Friendly heading + context (no changes to generic renderer required)
			st.markdown("### Spark Aggregates — Top Tracks & Top Artists")
			st.caption(
				"Aggregated views computed by Spark jobs (Top Tracks / Top Artists, plain & grouped). "
				"Use the date-range, cumulative toggle, Top-N slider, and optional group selector where applicable."
			)

			# Hide raw collection headers and use friendly labels when supported
			try:
				spark_tab.render(
					db=db,
					cfg=cfg,
					prefix=prefix,
					show_collection_headers=False,
					pretty_titles={
						f"{prefix}_spark_top_tracks_grouped": "Top Tracks (Spark grouped)",
						f"{prefix}_spark_top_artists_grouped": "Top Artists (Spark grouped)",
						f"{prefix}_spark_top_tracks": "Top Tracks",
						f"{prefix}_spark_top_artists": "Top Artists",
						f"{prefix}_spark_feature_avg": "Feature Averages",
					},
				)
			except TypeError:
				# Fallback if spark_generic does not accept the new parameters
				spark_tab.render(db=db, cfg=cfg, prefix=prefix)
		else:
			st.info("spark_generic tab not found.")

