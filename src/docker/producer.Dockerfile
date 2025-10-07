# Minimal Python base
FROM python:3.11-slim

# Avoid prompts and cache bloat
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install only what the producer needs (no apt-get, keep it lightweight)
# If your corporate mirror is needed, you can add: --index-url=https://<mirror>/simple
RUN pip install --no-cache-dir spotipy pymongo confluent-kafka python-dotenv

# Copy sources last to leverage Docker layer cache
COPY . /app

# Default command (overridable by `docker compose run`)
CMD ["python", "-u", "-m", "producers.avd_producer"]

