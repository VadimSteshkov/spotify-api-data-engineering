# -*- coding: utf-8 -*-
"""
Generic RAW viewer tab for orchestrator.
Shows documents stored by the Spark RAW fallback (<prefix>_raw_stream).
"""

import os
import json
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

@st.cache_data(show_spinner=False, ttl=30)
def _load_raw(coll_name: str, limit: int = 500) -> pd.DataFrame:
	db = st.session_state._orchestrator_mongo_db
	cur = db[coll_name].find({}, {"_id": 0}).sort("ingest_ts", -1).limit(int(limit))
	df = pd.DataFrame(list(cur))
	if not df.empty and "raw_json" in df.columns:
		# Try to pretty-print a preview column
		df["raw_preview"] = df["raw_json"].apply(lambda s: s[:200] + "..." if isinstance(s, str) and len(s) > 200 else s)
	return df

def render(db, cfg, prefix: str) -> None:
	st.session_state._orchestrator_mongo_db = db

	raw_coll = os.getenv("SPARK_COLL_RAW", f"{prefix}_raw_stream")
	st.caption(f"RAW collection: `{raw_coll}`")

	df = _load_raw(raw_coll, limit=1000)
	if df.empty:
		st.info("No RAW documents yet.")
		return

	if "ingest_ts" in df.columns:
		st.dataframe(df.sort_values("ingest_ts", ascending=False), use_container_width=True)
	else:
		st.dataframe(df, use_container_width=True)

