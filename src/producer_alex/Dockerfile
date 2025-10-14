# Generic Kafka Producer
FROM python:3.11-slim
WORKDIR /app

# Install deps from the project-level requirements
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy source
COPY . /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

# PRODUCER_ENTRY decides module (e.g., producer_avd.avd_producer)
CMD ["python", "-u", "-m", "producer_alex.producer"]

