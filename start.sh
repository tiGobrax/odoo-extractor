#!/usr/bin/env bash
set -euo pipefail

echo "Starting Odoo Extractor API on port ${PORT:-8080}"

exec uvicorn app.api.app:app \
  --host 0.0.0.0 \
  --port "${PORT:-8080}"
