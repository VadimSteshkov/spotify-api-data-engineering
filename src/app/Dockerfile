# Streamlit UI
FROM python:3.11-slim
WORKDIR /app

COPY ../requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

EXPOSE 8501
CMD ["bash", "-lc", "python -m streamlit run app/streamlit_app.py --server.address=0.0.0.0 --server.port=${PORT:-8501}"]

