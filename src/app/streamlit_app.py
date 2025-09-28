#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Orchestrator Streamlit app (team tabs loader).

This application dynamically loads per-teammate tabs from modules under:
  src/app/tabs/<prefix>.py  (each must expose: render(db, cfg, prefix))

Configuration file:
  src/app/team_config.yaml

Environment (optional):
  MONGO_URL = "mongodb://root:example@localhost:27017/?authSource=admin"
  MONGO_DB  = "spotify_db"

Run:
  streamlit run src/app/streamlit_app.py
"""

import os
import importlib
from pathlib import Path
from typing import Dict, Any, List

import streamlit as st
import yaml
from pymongo import MongoClient
from pymongo.errors import PyMongoError


# =========================
# Config helpers
# =========================
def _load_config() -> Dict[str, Any]:
	"""Load team configuration from team_config.yaml (same folder as this file)."""
	cfg_path = Path(__file__).resolve().parent / "team_config.yaml"
	if not cfg_path.exists():
		st.error(f"Missing config file: {cfg_path}")
		return {}
	try:
		with cfg_path.open("r", encoding="utf-8") as f:
			return yaml.safe_load(f) or {}
	except Exception as e:
		st.error(f"Failed to read team_config.yaml: {e}")
		return {}


def _get_db(mongo_url: str, db_name: str):
	"""Create a single Mongo client per Streamlit session and return the DB handle."""
	try:
		client = MongoClient(mongo_url)
		return client[db_name]
	except PyMongoError as e:
		st.error(f"Mongo connection error: {e}")
		return None


# =========================
# Main UI
# =========================
st.set_page_config(page_title="Spotify Dashboard (Team Orchestrator)", layout="wide")

cfg = _load_config()
if not cfg:
	st.stop()

# Resolve defaults from config and/or env
defaults = cfg.get("defaults", {})
mongo_url = os.getenv("MONGO_URL", defaults.get("mongo_url", "mongodb://root:example@localhost:27017/?authSource=admin"))
db_name   = os.getenv("MONGO_DB",  defaults.get("db_name", "spotify_db"))
team: List[Dict[str, Any]] = cfg.get("team", [])
tabs_order: List[str] = cfg.get("ui", {}).get("tabs_order", ["Overview"] + [m.get("prefix", "") for m in team])

db = _get_db(mongo_url, db_name)
if db is None:
	st.stop()

# Sidebar info
with st.sidebar:
	st.header("Settings")
	st.caption(f"DB: **{db_name}**  |  URL: **{mongo_url}**")
	st.caption("Tabs are driven by team_config.yaml and modules in app/tabs/*.py")

# Build tabs
tabs = st.tabs(tabs_order)

# Overview tab
with tabs[0]:
	st.header("Overview")
	st.write("This is the team orchestrator dashboard. Use the tabs to view each teammate's data.")
	st.write("To add a new teammate tab:")
	st.code("""1) Add an entry in src/app/team_config.yaml under 'team:' with {prefix, display_name}
2) Create src/app/tabs/<prefix>.py exposing: render(db, cfg, prefix)
3) Restart Streamlit (or hot-reload)""", language="text")

# Per-teammate tabs
for i, member in enumerate(team, start=1):
	prefix = member.get("prefix", "").strip()
	disp = member.get("display_name", prefix or "Unknown")
	with tabs[i]:
		st.header(disp)
		if not prefix:
			st.warning("Missing 'prefix' in team_config.yaml entry.")
			continue

		module_name = f"app.tabs.{prefix}"
		try:
			mod = importlib.import_module(module_name)
		except ModuleNotFoundError:
			st.info(f"Tab module not found: {module_name}. Create src/app/tabs/{prefix}.py with a render() function.")
			continue

		if not hasattr(mod, "render"):
			st.warning(f"Module {module_name} has no 'render(db, cfg, prefix)' function.")
			continue

		try:
			mod.render(db=db, cfg=cfg, prefix=prefix)
		except Exception as e:
			st.error(f"Error while rendering tab '{prefix}': {e}")
