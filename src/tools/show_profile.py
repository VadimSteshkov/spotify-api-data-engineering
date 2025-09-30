#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tiny utility to print the current Spotify profile (for demo).
- Reads SPOTIPY_* vars from environment (use a .env loader or export them)
- Uses Spotipy OAuth, reuses token cache (.cache-<username>)
- Prints key fields to stdout
"""

import os
import sys
from pathlib import Path
from typing import Optional

try:
	# Optional: load .env if python-dotenv is available
	from dotenv import load_dotenv  # type: ignore
	load_dotenv()
except Exception:
	pass

import spotipy  # type: ignore
from spotipy.oauth2 import SpotifyOAuth  # type: ignore


def _env_or_die(name: str) -> str:
	"""Fetch an env var or exit with a helpful message."""
	val = os.getenv(name)
	if not val:
		print(f"[ERROR] Missing env var: {name}")
		print("Required: SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI")
		sys.exit(1)
	return val


def _cache_hint() -> Optional[str]:
	"""Return the most likely Spotipy cache file if present, for display."""
	# Spotipy stores .cache or .cache-<username> in CWD by default
	cwd = Path.cwd()
	candidates = sorted([p.name for p in cwd.glob(".cache*")])
	return ", ".join(candidates) if candidates else None


def main() -> None:
	"""Authenticate and print profile fields."""
	# Ensure required envs exist (also helpful error if they don't)
	_env_or_die("SPOTIPY_CLIENT_ID")
	_env_or_die("SPOTIPY_CLIENT_SECRET")
	_env_or_die("SPOTIPY_REDIRECT_URI")

	scope = "user-read-email user-read-private"
	auth = SpotifyOAuth(scope=scope)
	sp = spotipy.Spotify(auth_manager=auth)

	me = sp.me()  # current user's profile JSON

	# Extract commonly useful fields (defensive .get to avoid KeyError)
	user_id = me.get("id")
	display_name = me.get("display_name")
	country = me.get("country")
	product = me.get("product")  # e.g., premium/free
	email = me.get("email")
	followers = (me.get("followers") or {}).get("total")
	uri = me.get("uri")
	profile_url = (me.get("external_urls") or {}).get("spotify")

	print("=== Spotify Profile ===")
	print(f"user_id      : {user_id}")
	print(f"display_name : {display_name}")
	print(f"country      : {country}")
	print(f"plan         : {product}")
	print(f"email        : {email}")
	print(f"followers    : {followers}")
	print(f"uri          : {uri}")
	print(f"profile_url  : {profile_url}")

	cache = _cache_hint()
	if cache:
		print(f"\nToken cache  : {cache}")
	else:
		print("\nToken cache  : (no .cache* file detected in current folder)")

if __name__ == "__main__":
	main()
