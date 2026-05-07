"""Application settings.

Loaded once at process start from environment variables (and ``.env`` in dev).
Uses pydantic-settings v2; ``get_settings`` is cached so the parsed object is
shared across the FastAPI app, Alembic, and tests.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Environment(str, Enum):
    """Deployment environment. Drives debug toggles, log format, etc."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class LogLevel(str, Enum):
    """Allowed log levels (uppercase, matches stdlib ``logging``)."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """Strongly-typed application settings sourced from env/.env."""

    # Files later in the tuple override earlier ones — matches the Vite /
    # Next.js convention where `.env` holds shared defaults and
    # `.env.local` carries personal overrides (both git-ignored).
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── Environment ────────────────────────────────────────────────────────
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = True
    log_level: LogLevel = LogLevel.INFO
    project_name: str = "RealEstate Analyzer"
    version: str = "0.1.0"

    # ─── Server ─────────────────────────────────────────────────────────────
    api_v1_prefix: str = "/api/v1"
    # ``NoDecode`` keeps pydantic-settings from JSON-parsing the env var
    # before our validator splits it on commas.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"],
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: str | list[str]) -> list[str]:
        """Allow comma-separated env var ``CORS_ORIGINS=a,b,c``."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # ─── Database ───────────────────────────────────────────────────────────
    # Stored as plain strings — pydantic's PostgresDsn rejects the asyncpg
    # +driver suffix in v2 unless we customize the URL type, which is more
    # ceremony than this layer needs. Validation happens when SQLAlchemy
    # connects.
    database_url: str = Field(
        default="postgresql+asyncpg://realestate:realestate@localhost:5432/realestate",
        description="Async DSN used by SQLAlchemy + asyncpg.",
    )
    database_url_sync: str = Field(
        default="postgresql://realestate:realestate@localhost:5432/realestate",
        description="Sync DSN used by Alembic (asyncpg can't run migrations).",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_pre_ping: bool = True
    db_echo: bool = False

    # ─── Redis ──────────────────────────────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0")
    feature_cache_ttl_seconds: int = 86_400  # 24h

    # ─── External APIs ──────────────────────────────────────────────────────
    molit_api_key: str | None = None
    admin_population_api_key: str | None = None
    realty_price_api_key: str | None = None
    # Kakao REST is optional — only useful with a Business App registration.
    # Frontend Maps JS SDK works without it.
    kakao_api_key: str | None = None
    # Naver Open API is the recommended geocoder backend (free, no biz cert).
    naver_client_id: str | None = None
    naver_client_secret: str | None = None

    # ─── ML ─────────────────────────────────────────────────────────────────
    mlflow_tracking_uri: str = "http://localhost:5000"
    models_dir: Path = Path("./models_artifacts")

    # ─── Observability ──────────────────────────────────────────────────────
    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float = 0.1

    # ─── Auth (Phase 2) ─────────────────────────────────────────────────────
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60

    # ─── Rate limiting ──────────────────────────────────────────────────────
    rate_limit_default: str = "100/minute"

    # ─── Derived ────────────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        """True in production. Used to gate debug-only behavior."""
        return self.environment == Environment.PRODUCTION

    @property
    def is_test(self) -> bool:
        """True under pytest — disables Sentry, slowapi, model loading, etc."""
        return self.environment == Environment.TEST


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide ``Settings`` singleton.

    Cached because ``BaseSettings.__init__`` re-parses ``.env`` and env vars
    on every call, which is wasted work (and slows down every Depends()).
    """
    return Settings()
