#!/bin/sh
set -e

DEST="${DUCKDB_PATH:-/app/data/f1_history.duckdb}"
SRC="/app/api/data/f1_history.duckdb"
DATA_DIR="$(dirname "$DEST")"

# Seed the data dir with the bundled DuckDB snapshot if not already present.
# On Render (no persistent disk) this runs every cold start but the file is always there.
# On Railway/Fly (persistent volume) this only copies on first boot.
if [ ! -f "$DEST" ] && [ -f "$SRC" ]; then
  echo "Seeding DuckDB from bundled snapshot..."
  cp "$SRC" "$DEST"
fi

mkdir -p "${DATA_DIR}/fastf1_cache" "${DATA_DIR}/models"

# Render tells the service which port to listen on ($PORT); docker-compose maps 8000.
PORT="${PORT:-8000}"
echo "Starting the API on port ${PORT}..."
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT}" --workers 1
