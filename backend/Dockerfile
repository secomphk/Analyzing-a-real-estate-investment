# syntax=docker/dockerfile:1.6
# Multi-stage build: builder installs deps with Poetry, runtime is slim.
#
# Base image is pinned to Debian Bookworm because the runtime stage
# installs distro-specific package names (``libgdal32``, ``libgeos-c1v5``,
# ``libproj25``) that don't exist verbatim on Trixie (where libgdal is now
# called ``libgdal36``, libgeos is ``libgeos-c1t64`` after the t64
# transition, etc.). Pinning the suffix keeps the apt list stable so the
# ``apt-get install`` line below doesn't drift when upstream rebases the
# Python images. Bump explicitly when we test against a newer Debian.
ARG PYTHON_VERSION=3.11

# ─── Builder ────────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.2 \
    POETRY_VIRTUALENVS_CREATE=true \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

# Build deps for geospatial / ML stack (geopandas, shapely, prophet, faiss).
# Retry apt up to 3× — Railway's build network occasionally drops packages
# mid-download which would otherwise crash a fresh build with no diagnostic.
RUN set -eux; \
    for i in 1 2 3; do \
        apt-get update && \
        apt-get install -y --no-install-recommends --fix-missing \
            build-essential \
            curl \
            git \
            libpq-dev \
            gdal-bin \
            libgdal-dev \
            libgeos-dev \
            libproj-dev \
        && break || { echo "apt retry $i"; sleep 5; rm -rf /var/lib/apt/lists/*; }; \
    done && \
    rm -rf /var/lib/apt/lists/*

RUN pip install "poetry==${POETRY_VERSION}"

WORKDIR /app

COPY pyproject.toml poetry.lock* ./

# Install only main deps; dev deps stay out of the runtime image.
RUN poetry install --only main --no-root

# ─── Runtime ────────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app

RUN set -eux; \
    for i in 1 2 3; do \
        apt-get update && \
        apt-get install -y --no-install-recommends --fix-missing \
            libpq5 \
            libgdal32 \
            libgeos-c1v5 \
            libproj25 \
            curl \
            tini \
        && break || { echo "apt retry $i"; sleep 5; rm -rf /var/lib/apt/lists/*; }; \
    done && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --system app && \
    useradd --system --gid app --home-dir /app --shell /bin/bash app

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app . /app
RUN chmod +x /app/scripts/entrypoint.sh

# Optional model / runtime arguments — overridable per environment.
ARG MODEL_VERSION=v1
ENV MODEL_VERSION=${MODEL_VERSION} \
    MODELS_DIR=/app/models_artifacts \
    UVICORN_WORKERS=2

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail http://localhost:8000/health || exit 1

# tini is PID 1 so SIGTERM propagates cleanly during rolling deploys; the
# entrypoint script handles optional S3 model sync + alembic migrations
# before exec'ing uvicorn.
ENTRYPOINT ["/usr/bin/tini", "--", "/app/scripts/entrypoint.sh"]
