"""Alembic migration environment.

Loads the sync DATABASE_URL_SYNC from app settings (Alembic does not run async),
and points autogenerate at ``Base.metadata`` so future model additions are
detected. ORM models are imported lazily — Stage 1 has no real models yet.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from src.core.config import get_settings

# Importing the models package registers every table on Base.metadata.
from src.models import Base  # noqa: F401  (re-exported)
from src.models import (  # noqa: F401
    AdminArea,
    AnalysisResult,
    Building,
    CandidateLand,
    LandTransaction,
    OfficialLandPrice,
    PopulationStat,
    Project,
    ProjectStage,
    Recommendation,
    RoadExpansionStage,
    RoadSegment,
    Store,
    StoreBrand,
    StoreFeature,
    StoreImpactAnalysis,
    TrafficVolume,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url at runtime from app settings — keeps secrets out of
# alembic.ini and lets dev/test/prod share one config file.
#
# Production hosts (Railway, Render, Fly) only inject ``DATABASE_URL`` —
# they don't know about our separate ``DATABASE_URL_SYNC``. Derive the
# sync DSN by swapping the asyncpg driver out of ``database_url`` so we
# never have two env vars to keep in sync. The explicit
# ``database_url_sync`` is honoured first when it differs from its
# default (e.g. local dev pointing Alembic at a different DB).
settings = get_settings()
_DEFAULT_SYNC_DSN = (
    "postgresql://realestate:realestate@localhost:5432/realestate"
)
if settings.database_url_sync and settings.database_url_sync != _DEFAULT_SYNC_DSN:
    sync_url = settings.database_url_sync
else:
    # ``postgresql+asyncpg://...`` → ``postgresql+psycopg2://...``. The
    # +psycopg2 marker is explicit so SQLAlchemy doesn't accidentally pick
    # asyncpg again under any URL-rewriting middleware.
    sync_url = settings.database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    ).replace(
        # Some hosts emit a bare ``postgresql://``; psycopg2 is the
        # default sync driver so we can leave it alone in that case, but
        # be explicit if it does come through.
        "postgresql://", "postgresql+psycopg2://"
    )
    # Avoid double-replacement if both prefixes matched.
    sync_url = sync_url.replace(
        "postgresql+psycopg2+psycopg2://", "postgresql+psycopg2://"
    )
config.set_main_option("sqlalchemy.url", sync_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without a live DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
            # PostGIS-managed tables are not ours to migrate.
            include_object=_skip_postgis_objects,
        )

        with context.begin_transaction():
            context.run_migrations()


def _skip_postgis_objects(obj: object, name: str | None, type_: str, *_: object) -> bool:
    """Tell autogenerate to ignore PostGIS-internal tables."""
    if type_ == "table" and name in {
        "spatial_ref_sys",
        "geography_columns",
        "geometry_columns",
        "raster_columns",
        "raster_overviews",
        "topology",
        "layer",
    }:
        return False
    return True


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
