from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.dev",
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )

    # ── App ───────────────────────────────────────────────
    app_name: str = "URL Shortener & Analytics"
    app_version: str = "1.1.0"
    base_url: str = "http://localhost:8000"
    short_code_length: int = 7
    debug: bool = False

    # ── Postgres ──────────────────────────────────────────
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "urlshort"
    postgres_host: str = "db"
    postgres_port: int = 5432

    # ── Redis ─────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"

    # ── Celery ────────────────────────────────────────────
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"
    celery_task_always_eager: bool = False
    celery_result_expires_seconds: int = 3600

    # ── Analytics Queue ───────────────────────────────────
    analytics_queue_enabled: bool = True

    # ── Rate limiting ─────────────────────────────────────
    rate_anon_per_min: int = 100
    rate_auth_per_min: int = 1000

    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60

    rate_limit_auth_requests: int = 5
    rate_limit_api_requests: int = 100
    rate_limit_redirect_requests: int = 60

    # ── Caching ───────────────────────────────────────────
    hot_link_threshold: int = 50
    hot_link_extended_ttl: int = 86400
    default_cache_ttl: int = 3600

    # ── GeoIP / Analytics  ─────────────────────────
    geoip_db_path: str = "/data/GeoLite2-City.mmdb"
    analytics_default_days: int = 7
    analytics_max_days: int = 90
    click_counter_flush_seconds: int = 30

    # ── Webhook ─────────────────────────
    webhook_secret: str = "dev-webhook-secret-change-me"
    ebhook_timeout_seconds: float = 5.0
    webhook_max_retries: int = 5
    webhook_user_agent: str = "url-shortener-analytics-webhook/1.0"

    @property
    def database_url(self) -> str:
        """Async URL — used by SQLAlchemy asyncpg engine."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """Sync URL — used by Alembic migrations."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
