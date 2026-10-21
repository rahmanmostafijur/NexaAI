#!/bin/sh
set -e

echo "Applying database migrations..."
alembic upgrade head

if [ "${SEED_ON_STARTUP:-false}" = "true" ]; then
    echo "Seeding demo data (idempotent)..."
    python -m scripts.seed
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
    --timeout-keep-alive 75
