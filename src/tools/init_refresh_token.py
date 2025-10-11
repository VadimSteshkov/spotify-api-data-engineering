#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Docker-friendly helper that obtains a long-lived SPOTIPY_REFRESH_TOKEN
for a given user env-file (e.g. envs/.env.avd).

- Reads CLIENT_ID/SECRET/REDIRECT_URI/USERNAME from the provided env file
- Memory-only OAuth cache (no .cache files on disk)
- Headless flow: prints an auth URL; you paste the redirected URL
- Prints a nice banner: "Refresh token for <USR>: <token>"
- Optional: in-place update of the env file (replace or append SPOTIPY_REFRESH_TOKEN=...)
"""

import os
import re
import sys
import argparse
from typing import Optional

try:
    from dotenv import dotenv_values
except Exception:
    print("[ERROR] python-dotenv is required inside the container.")
    sys.exit(1)

from spotipy.oauth2 import SpotifyOAuth           # type: ignore
from spotipy.cache_handler import MemoryCacheHandler  # type: ignore


def _require(d: dict, key: str) -> str:
    v = (d.get(key) or "").strip()
    if not v:
        raise SystemExit(f"[ERROR] Missing '{key}' in the provided env file.")
    return v


def _guess_usr(env_path: str, env: dict) -> str:
    # Prefer USERNAME or SPOTIFY_USERNAME; else infer from filename suffix (.env.<USR>)
    usr = (env.get("USERNAME") or env.get("SPOTIFY_USERNAME") or "").strip()
    if usr:
        return usr
    m = re.search(r"\.env\.([A-Za-z0-9_\-\.]+)$", env_path)
    return m.group(1) if m else "unknown"


def _write_refresh_token(env_path: str, token: str) -> None:
    """Replace existing SPOTIPY_REFRESH_TOKEN=... or append at the end."""
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.strip().startswith("SPOTIPY_REFRESH_TOKEN="):
            lines[i] = f"SPOTIPY_REFRESH_TOKEN={token}"
            updated = True
            break
    if not updated:
        lines.append(f"SPOTIPY_REFRESH_TOKEN={token}")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Get (and optionally write) a Spotify refresh token from Docker.")
    parser.add_argument("--env-file", required=True, help="Path to envs/.env.<USR>")
    parser.add_argument("--write", action="store_true", help="Write SPOTIPY_REFRESH_TOKEN into the env-file")
    args = parser.parse_args()

    env_path = args.env_file
    if not os.path.exists(env_path):
        raise SystemExit(f"[ERROR] Env file not found: {env_path}")

    env = dotenv_values(env_path)  # read only this file
    client_id     = _require(env, "SPOTIPY_CLIENT_ID")
    client_secret = _require(env, "SPOTIPY_CLIENT_SECRET")
    redirect_uri  = (env.get("SPOTIPY_REDIRECT_URI") or "http://127.0.0.1:8888/callback").strip()

    scope = " ".join([
        "user-read-private",
        "user-read-email",
        "user-read-recently-played",
        "user-read-currently-playing",
        "user-top-read",
    ])

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
        open_browser=False,                    # never try to open a browser in Docker
        cache_handler=MemoryCacheHandler(),    # no .cache files
    )

    auth_url = auth.get_authorize_url()
    print("\n[ ACTION ] Open this URL in your browser, approve the app,")
    print("          then paste the FULL redirected URL back here.\n")
    print(auth_url)

    redirected = input("\nPaste redirected URL: ").strip()
    code = auth.parse_response_code(redirected)
    if not code:
        raise SystemExit("[ERROR] Could not extract 'code' param from the pasted URL.")

    # Ask Spotify for access+refresh
    token_info = auth.get_access_token(code=code, as_dict=True)
    refresh_token: Optional[str] = token_info.get("refresh_token")
    if not refresh_token:
        raise SystemExit("[ERROR] No refresh_token received. Check scopes & redirect URI in your Spotify app settings.")

    usr = _guess_usr(env_path, env)
    print(f"\nRefresh token for {usr}:")
    print(f"SPOTIPY_REFRESH_TOKEN={refresh_token}")

    if args.write:
        _write_refresh_token(env_path, refresh_token)
        print(f"\n[ OK ] Wrote SPOTIPY_REFRESH_TOKEN into {env_path}")

    print("\nDone.\n")


if __name__ == "__main__":
    main()

