#!/usr/bin/env bash
# Small Docker wrapper for init_refresh_token.py
# Usage:
#   ./tools/get_refresh_token.sh avd
#   ./tools/get_refresh_token.sh avd --write

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <USR> [--write]"
  exit 1
fi

USR="$1"; shift || true
WRITE_FLAG="$*"

# Run inside the existing 'producer' image to reuse dependencies
# NOTE: the repo root is mounted by docker-compose already (volumes: - ./:/app)
docker compose run --rm \
  -e PYTHONUNBUFFERED=1 \
  producer \
  bash -lc "python -u tools/init_refresh_token.py --env-file envs/.env.${USR} ${WRITE_FLAG}"

