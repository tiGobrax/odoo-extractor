#!/usr/bin/env bash
set -euo pipefail

echo "Starting Odoo Extractor (MODE=${MODE:-service})"

exec python -m app.main
