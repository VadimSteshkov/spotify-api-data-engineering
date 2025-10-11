#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tiny utility to print the current Spotify profile (for demo).
- Reads SPOTIPY_* vars from environment (use a .env loader or export them)
- Uses Spotipy OAuth, but NEVER writes a .cache file (in-memory only)
- If SPOTIPY_REFRESH_TOKEN is present -> fully automatic, no browser/paste
- Otherwise -> interactive paste flow (prints URL and asks for the redirected URL)
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
from spotipy.cache_handler import MemoryCacheHandler  # type: ignore


def _env_or_die(name: str) -> str:
	"""Fetch an env var or exit with a helpful message."""
	val = os.getenv(name)
	if not val:
		print(f"[ERROR] Missing env var: {name}")
		print("Required: SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, SPOTIPY_REDIRECT_URI")
		sys.exit(1)
	return val


def _cache_hint() -> Optional[str]:
	"""Return .cache file names if present (for display only)."""
	cwd = Path.cwd()
	candidates = sorted([p.name for p in cwd.glob(".cache*")])
	return ", ".join(candidates) if candidates else None


def _build_auth(scope: str) -> tuple[SpotifyOAuth, MemoryCacheHandler]:
	"""Create a SpotifyOAuth that never writes to disk (memory cache only)."""
	cache_handler = MemoryCacheHandler()  # in-memory only, no files
	auth = SpotifyOAuth(
		client_id=_env_or_die("SPOTIPY_CLIENT_ID"),
		client_secret=_env_or_die("SPOTIPY_CLIENT_SECRET"),
		redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI", "http://127.0.0.1:8888/callback"),
		scope=scope,
		cache_handler=cache_handler,
		open_browser=False  # important for headless Docker
	)
	return auth, cache_handler


def main() -> None:
	"""Authenticate and print profile fields (no disk cache)."""
	scope = "user-read-email user-read-private"
	auth, cache_handler = _build_auth(scope)

	# DEBUG (you can remove after testing)
	print("DEBUG: RT present =", bool(os.getenv("SPOTIPY_REFRESH_TOKEN")))
	print("DEBUG: CLIENT_ID present =", bool(os.getenv("SPOTIPY_CLIENT_ID")))

	token_info = None
	rt = os.getenv("SPOTIPY_REFRESH_TOKEN")

	if rt:
		# Refresh immediately to obtain a COMPLETE token_info dict (with expires_at)
		# Then place it into the in-memory cache so Spotipy client can use it.
		try:
			token_info = auth.refresh_access_token(rt)
			cache_handler.save_token_to_cache(token_info)
		except Exception as e:
			print(f"[WARN] refresh_access_token failed: {e}")
			token_info = None

	# Fallback to interactive paste-based flow if no RT provided (or refresh failed)
	if not token_info:
		auth_url = auth.get_authorize_url()
		print("[ACTION] Open this URL in a browser, approve access, then copy the FULL redirected URL:")
		print(auth_url)
		redirected = input("\nPaste the FULL redirected URL here: ").strip()
		code = auth.parse_response_code(redirected)
		if not code:
			print("[ERROR] Could not extract 'code' from the provided URL.")
			sys.exit(2)
		token_info = auth.get_access_token(code=code, as_dict=True)
		cache_handler.save_token_to_cache(token_info)

	# Build the client with a valid auth manager
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

