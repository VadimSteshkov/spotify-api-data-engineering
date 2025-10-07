# Base image: Use a lightweight Python version (same as producer)
FROM python:3.11-slim

# Set environment variables for better performance in Python
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Install dependencies required by the Kafka consumer (Kafka, Mongo client, env parser)
# This step is cached, making subsequent runs fast.
RUN pip install --no-cache-dir pymongo confluent-kafka python-dotenv

# Copy the entire project source code into the container
# This step should be placed last to leverage Docker's build cache effectively.
COPY . /app

# Default command to run the consumer module
# This command is executed when the container starts via `docker compose up` or `docker compose run`.
CMD ["python", "-u", "-m", "consumers.kafka_consumer"]
