# Minimal Python + Java base; PySpark ships Spark itself
FROM python:3.11-slim

# Install Java (required by Spark)
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jre-headless curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Workdir inside container
WORKDIR /app

# Copy requirements first (better cache)
COPY spark/requirements.txt /app/spark/requirements.txt

# Install Python deps
RUN pip install --no-cache-dir -r /app/spark/requirements.txt

# Copy the whole src (code, including spark/streaming_job.py)
COPY . /app

# Default env (can be overridden by docker-compose or `docker run -e`)
ENV PYTHONUNBUFFERED=1

# Default command: run Spark job
# (packages are provided via env SPARK_PACKAGES if needed)
CMD [ "python", "-m", "spark.streaming_job" ]

