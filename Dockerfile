FROM python:3.12-slim

WORKDIR /app

# System deps for LightGBM/XGBoost compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (layer-cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY api/                 ./api/
COPY ingest/              ./ingest/
COPY live/                ./live/
COPY start_backend.py     ./
COPY docker-entrypoint.sh ./
RUN chmod +x /app/docker-entrypoint.sh

# Base data dirs (may be overlaid by a persistent volume mount at /app/data)
RUN mkdir -p /app/data/fastf1_cache /app/data/models

ENV PYTHONPATH=/app/api
ENV DUCKDB_PATH=/app/data/f1_history.duckdb
ENV FASTF1_CACHE_DIR=/app/data/fastf1_cache
ENV MODEL_DIR=/app/data/models
ENV LOG_FORMAT=json
ENV LOG_LEVEL=INFO

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
