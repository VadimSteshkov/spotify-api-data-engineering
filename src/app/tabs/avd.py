#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AVD tab wrapper:
- Keeps your existing Streamlit dashboard 100% intact (moved to avd_classic.py)
- Adds a second sub-tab that shows Spark results (auto-discovered avd_spark_* collections)
- Orchestrator still imports app.tabs.avd:render(db, cfg, prefix)
"""

import streamlit as st

# Import your current dashboard as "classic"
try:
	from tabs import avd_classic as classic_tab
except Exception as e:
	classic_tab = None

# Generic Spark renderer (shows all <prefix>_spark_* collections)
try:
	from tabs import spark_generic as spark_tab
except Exception as e:
	spark_tab = None


def render(db, cfg, prefix: str = "avd"):
	"""
	Entry point used by the orchestrator.
	Builds two sub-tabs:
	- Classic: your original AVD dashboard (from avd_classic.py)
	- Spark:   generic Spark collections for <prefix>_spark_*
	"""
	st.title("🎧 Dorin's Dashboard")
	tab_classic, tab_spark = st.tabs(["Classic", "Spark"])

	# -------- Classic (your existing code) --------
	with tab_classic:
		st.caption("Your original dashboard (unchanged).")
		if classic_tab and hasattr(classic_tab, "render"):
			# Call your existing render exactly as before
			classic_tab.render(db=db, cfg=cfg, prefix=prefix)
		else:
			st.error("Could not load avd_classic.render(). Make sure src/app/tabs/avd_classic.py exists.")

	# -------- Spark (generic) --------
	with tab_spark:
		st.caption(f"Spark analytics for collections like `{prefix}_spark_*`.")
		if spark_tab and hasattr(spark_tab, "render"):
			try:
				spark_tab.render(db=db, cfg=cfg, prefix=prefix)
			except Exception as e:
				st.error(f"Spark tab failed: {e}")
		else:
			st.info("spark_generic tab not found. Add src/app/tabs/spark_generic.py to enable this view.")

