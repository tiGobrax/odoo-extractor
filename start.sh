#!/usr/bin/env bash
set -euo pipefail

MODE=${MODE:-service}
PORT=${PORT:-8000}

echo "Starting application in MODE=${MODE}"

if [ "$MODE" = "service" ]; then
  echo "Running HTTP API (uvicorn)"
  exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"

elif [ "$MODE" = "job" ]; then
  echo "Running batch job (full extract)"
  exec python -m src.full_extract

else
  echo "ERROR: Invalid MODE='${MODE}'. Allowed values are 'service' or 'job'."
  exit 1
fi
