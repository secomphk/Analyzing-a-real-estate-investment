#!/usr/bin/env bash
# Container entrypoint.
#
# Responsibilities:
#   1. (Optional) Sync model artifacts from S3 into ${MODELS_DIR}.
#   2. (Optional) Run Alembic migrations when MIGRATE_ON_BOOT=true.
#   3. exec uvicorn so signals propagate.
#
# Idempotent — safe to run on every container start.
set -euo pipefail

log() { printf '[entrypoint] %s\n' "$*"; }

: "${MODELS_DIR:=/app/models_artifacts}"
mkdir -p "${MODELS_DIR}"

if [[ -n "${MODELS_S3_URI:-}" ]]; then
    if command -v aws >/dev/null 2>&1; then
        log "syncing models from ${MODELS_S3_URI} → ${MODELS_DIR}"
        aws s3 sync --no-progress "${MODELS_S3_URI}" "${MODELS_DIR}"
    else
        log "WARN: MODELS_S3_URI is set but aws CLI is not installed in this image; skipping sync."
    fi
fi

# Diagnostic: print the DB host/user the runtime is using (mask password)
# so deploy logs reveal misconfigured DATABASE_URL without leaking secrets.
if [[ -n "${DATABASE_URL:-}" ]]; then
    masked=$(printf '%s' "${DATABASE_URL}" | sed -E 's#(://[^:]+:)[^@]+@#\1***@#')
    log "DATABASE_URL = ${masked}"
else
    log "WARN: DATABASE_URL is not set"
fi
log "REDIS_URL set: $([[ -n "${REDIS_URL:-}" ]] && echo yes || echo no)"

if [[ "${MIGRATE_ON_BOOT:-false}" == "true" ]]; then
    log "running alembic upgrade head (cold Postgres + PostGIS can take 60-120s)"
    if alembic upgrade head; then
        log "alembic migration complete"
    else
        rc=$?
        log "ERROR: alembic upgrade head failed with exit code ${rc}"
        log "starting uvicorn anyway so /health responds and we can debug"
    fi
fi

# Seed-on-boot escape hatch: in environments where Railway's "Run Command"
# UI is unreliable (or the operator just wants a one-shot seed without
# spinning a separate worker), set ``SEED_ON_BOOT=true`` and the seed
# script will run idempotently after migrations. Subsequent boots no-op
# because the seed itself uses ON CONFLICT DO NOTHING. Flip the env var
# off after first successful boot to stop the (cheap) extra step.
if [[ "${SEED_ON_BOOT:-false}" == "true" ]]; then
    log "running src.scripts.seed --scenario all (SEED_ON_BOOT=true)"
    if python -m src.scripts.seed --scenario all; then
        log "seed complete"
    else
        rc=$?
        log "WARN: seed failed with exit code ${rc} — continuing with empty DB"
    fi
fi

WORKERS="${UVICORN_WORKERS:-1}"
# Railway / Render / Fly inject ${PORT}; locally we default to 8000.
PORT_BIND="${PORT:-8000}"
log "starting uvicorn (workers=${WORKERS}, port=${PORT_BIND})"
exec uvicorn src.main:app \
    --host 0.0.0.0 \
    --port "${PORT_BIND}" \
    --workers "${WORKERS}" \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    "$@"
