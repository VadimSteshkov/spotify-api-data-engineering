# tabs
# !/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Team Streamlit orchestrator.

What it does:
- Loads team_config.yaml (sibling of this file)
- Creates tabs using each teammate's display_name
- Dynamically imports each tab module: tabs.<prefix>
- Opens a single MongoDB client and passes it to every tab

Notes:
- Indentation uses TAB characters (as requested).
"""

import importlib
import os

import streamlit as st
import yaml
from pymongo import MongoClient

# ---------- Config loading ----------
# Prefer a team_config.yaml placed next to this script
CFG_PATH = os.path.join(os.path.dirname(__file__), "team_config.yaml")
try:
	with open(CFG_PATH, "r", encoding="utf-8") as f:
		cfg = yaml.safe_load(f) or {}
except Exception as e:
	st.error(f"Failed to load team_config.yaml: {e}")
	cfg = {}

team = cfg.get("team", [])  # list of teammates with {prefix, display_name, ...}
mongo_dbname = cfg.get("mongo_db", "spotify_db")  # database name shared by tabs

# ---------- Mongo client ----------
# Prefer env MONGO_URL; fall back to common Docker URL, then localhost.
mongo_url = os.getenv(
	"MONGO_URL",
	os.getenv("MONGODB_URI", "mongodb://root:example@mongo:27017/?authSource=admin")
)
if "mongo:" not in mongo_url and "localhost" not in mongo_url and "127.0.0.1" not in mongo_url:
	# leave custom cloud URLs as-is
	pass

try:
	client = MongoClient(mongo_url)
	db = client[mongo_dbname]
	# ping once to surface connection errors in UI
	db.command("ping")
	mongo_ok = True
except Exception as e:
	mongo_ok = False
	db = None

# ---------- Page setup ----------
st.set_page_config(page_title="Team Dashboard", layout="wide")
st.sidebar.header("Settings")
st.sidebar.caption(f"DB: {mongo_dbname} | URL: {mongo_url}")

if not mongo_ok:
	st.sidebar.error("Mongo connection failed. Check MONGO_URL and container network.")
	st.stop()

# ---------- Build dynamic tabs ----------
tab_labels: list[str] = []
tab_modules: list[tuple[object | None, str]] = []  # (module, prefix)

for member in team:
	prefix = (member.get("prefix") or "").strip()
	display = (member.get("display_name") or prefix).strip() or prefix
	module_name = f"tabs.{(member.get('module_name') or '').strip()}"

	try:
		mod = importlib.import_module(module_name)
		tab_labels.append(display)
		tab_modules.append((mod, prefix))
	except Exception as e:
		# Keep a placeholder tab so the user sees which module is missing
		tab_labels.append(f"{display} (missing)")
		tab_modules.append((None, prefix))

# Prepend Overview tab
tabs = st.tabs(["Overview", *tab_labels])

# ---------- Overview ----------
with tabs[0]:
	st.title("Overview")
	st.write("Use the tabs above to explore each teammate’s analytics.")

	# Quick inventory: show spark collections per teammate prefix
	with st.expander("Spark collections per teammate"):
		for member in team:
			pfx = (member.get("prefix") or "").strip()
			if not pfx:
				continue
			cols = sorted([c for c in db.list_collection_names() if c.startswith(f"{pfx}_spark_")])
			if cols:
				st.markdown(f"**{pfx}** → {', '.join(f'`{c}`' for c in cols)}")
			else:
				st.markdown(f"**{pfx}** → _no avd_spark_* collections found_")

# ---------- Teammate tabs ----------
for i, ((mod, prefix), label) in enumerate(zip(tab_modules, tab_labels), start=1):
	with tabs[i]:
		st.header(label)
		if mod and hasattr(mod, "render"):
			try:
				# Contract: every tab module exposes render(db, cfg, prefix)
				mod.render(db=db, cfg=cfg, prefix=prefix)
			except Exception as e:
				st.error(f"Tab '{label}' crashed: {e}")
		else:
			if mod is None:
				st.warning(
					f"Module '{member.get('module_name')}' not found. Create tabs/{member.get('module_name')}.py with a render(db, cfg, prefix) function.")
			else:
				st.warning(f"Module 'tabs.{member.get('module_name')}' has no render(db, cfg, prefix) function.")
