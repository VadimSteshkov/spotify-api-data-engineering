# Base image: Use a lightweight Python version (same as producer/consumer)
FROM python:3.11-slim

# Set environment variables to optimize Python/Pip operations
ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app

# Install all dependencies required by the Streamlit application
# This step is critical for caching and fast subsequent runs.
RUN pip install --no-cache-dir streamlit pymongo python-dotenv pyyaml

# Copy the entire project source code into the container
# This is usually the last step to ensure build cache reusability.
COPY . /app

# Expose the default Streamlit port
EXPOSE 8501

# Default command to start the Streamlit application (CMD is easier to read than ENTRYPOINT for this)
CMD [ "python", "-m", "streamlit", "run", "app/streamlit_app.py", \
      "--server.headless=true", \
      "--server.address=0.0.0.0", \
      "--server.port=8501", \
      "--browser.gatherUsageStats=false" ]
