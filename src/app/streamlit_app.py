#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Streamlit orchestrator:
- Reads team_config.yaml
- Builds tabs with user-friendly labels (display_name)
- Imports each teammate's tab module by prefix: app.tabs.<prefix>
"""

import os
import importlib
import yaml
import streamlit as st
from pymongo import MongoClient

# ---------- Load config ----------
CFG_PATH = os.path.join(os.path.dirname(__file__), "team_config.yaml")
with open(CFG_PATH, "r", encoding="utf-8") as f:
	cfg = yaml.safe_load(f) or {}

team = cfg.get("team", [])
mongo_dbname = cfg.get("mongo_db", "spotify_db")

# ---------- Mongo client ----------
# Prefer env MONGO_URL; fall back to localhost
mongo_url = os.getenv("MONGO_URL", "mongodb://root:example@localhost:27017/?authSource=admin")
client = MongoClient(mongo_url)
db = client[mongo_dbname]

# ---------- Page setup ----------
st.set_page_config(page_title="Team Dashboard", layout="wide")
st.sidebar.header("Settings")
st.sidebar.caption(f"DB: {mongo_dbname} | URL: {mongo_url}")

# ---------- Build tab labels (display_name) and load modules ----------
tab_labels = []
tab_modules = []

for member in team:
	prefix = member.get("prefix", "").strip()
	display = member.get("display_name", prefix).strip() or prefix

	# Import module app.tabs.<prefix> but show display_name as label
	module_name = f"app.tabs.{prefix}"
	try:
		mod = importlib.import_module(module_name)
		tab_labels.append(display)
		tab_modules.append((mod, prefix))
	except Exception as e:
		tab_labels.append(f"{display} (missing)")
		tab_modules.append((None, prefix))

# Prepend Overview tab
tabs = st.tabs(["Overview", *tab_labels])

# ---------- Overview ----------
with tabs[0]:
	st.title("Overview")
	st.write("This is the team orchestrator dashboard. Use the tabs to view each teammate’s data.")

	# Show common collections for the first teammate as hint
	if team:
		pfx = team[0].get("prefix", "demo")
		#st.sidebar.subheader(f"[{pfx}] Collections")
		#st.sidebar.markdown(f"- `{pfx}_recent_events`")
		#st.sidebar.markdown(f"- `{pfx}_artist_market_top_tracks`")

# ---------- Teammate tabs ----------
for i, ((mod, prefix), label) in enumerate(zip(tab_modules, tab_labels), start=1):
	with tabs[i]:
		st.header(label)
		if mod and hasattr(mod, "render"):
			try:
				mod.render(db=db, cfg=cfg, prefix=prefix)
			except Exception as e:
				st.error(f"Tab '{label}' failed: {e}")
		else:
			st.warning(f"Module for '{label}' not found or has no render(db,cfg,prefix).")

