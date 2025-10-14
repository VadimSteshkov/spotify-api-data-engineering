FROM python:3.11-slim
WORKDIR /app

# (optional) toolchain minim dacă vreun wheel necesită build
# RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

# Install all Python deps from the app requirements
COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
EXPOSE 8501

# Run streamlit from /app (no "app/" prefix)
CMD ["bash","-lc","python -m streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=${PORT:-8501}"]

