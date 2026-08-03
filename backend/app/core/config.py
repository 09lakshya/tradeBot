"""Application configuration — all values sourced from environment (never hardcoded)."""
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    # Application
    app_env: Literal["local", "staging", "production"] = "local"
    app_debug: bool = False
    secret_key: str = Field(min_length=16)
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Database. Parts build the URL for the local docker-compose stack; a full
    # DATABASE_URL wins when set, so a managed cloud connection string (with TLS
    # and a URL-encoded password) can be used verbatim without decomposing it.
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    database_url_override: str | None = Field(
        default=None, validation_alias=AliasChoices("DATABASE_URL")
    )

    # Redis. Same override story: a cloud broker needs auth and TLS (rediss://),
    # which the host/port parts can't express — a full REDIS_URL wins when set.
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_url_override: str | None = Field(
        default=None, validation_alias=AliasChoices("REDIS_URL")
    )

    # Market data
    market_data_provider: str = "yahoo"
    # Comma-separated failover chain tried in order after the primary.
    market_data_fallbacks: str = ""
    market_data_rate_per_sec: float = 5.0
    market_data_burst: int = 10
    market_data_max_retries: int = 3
    market_data_timeout: float = 15.0
    alpha_vantage_api_key: str = ""
    twelve_data_api_key: str = ""
    finnhub_api_key: str = ""

    @property
    def market_data_fallback_list(self) -> list[str]:
        return [p.strip() for p in self.market_data_fallbacks.split(",") if p.strip()]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self._normalize_pg_url(self.database_url_override)
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @staticmethod
    def _normalize_pg_url(url: str) -> str:
        """Force the psycopg3 driver onto a bare Postgres URL.

        Cloud providers hand out ``postgres://`` / ``postgresql://`` strings, which
        SQLAlchemy would route to psycopg2. Rewriting the scheme (query string and
        credentials untouched, so ``?sslmode=require`` survives) keeps a single
        driver across the app, Alembic, and the integration tests.
        """
        for prefix in ("postgresql+psycopg://", "postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix):]
        return url

    @computed_field  # type: ignore[prop-decorator]
    @property
    def redis_url(self) -> str:
        if self.redis_url_override:
            return self.redis_url_override
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    # Values come from the environment / .env, not constructor arguments.
    return Settings()


settings = get_settings()
