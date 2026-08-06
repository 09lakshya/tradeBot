"""Connection-URL resolution: parts for local, full-URL override for cloud."""
from app.core.config import Settings

BASE = {
    "secret_key": "test-secret-key-not-for-production",
    "postgres_user": "u", "postgres_password": "p", "postgres_db": "d",
    "postgres_host": "h", "postgres_port": 6000,
}


def test_database_url_built_from_parts_by_default() -> None:
    s = Settings(_env_file=None, **BASE, database_url_override=None)
    assert s.database_url == "postgresql+psycopg://u:p@h:6000/d"


def test_full_database_url_override_wins_and_gets_psycopg_driver() -> None:
    # A cloud "postgres://" string must be rewritten to the psycopg3 driver while
    # preserving the host, credentials, and the sslmode query the provider requires.
    s = Settings(
        _env_file=None,
        **BASE,
        database_url_override="postgres://cu:cp@cloud.example:5432/cdb?sslmode=require",
    )
    assert s.database_url == "postgresql+psycopg://cu:cp@cloud.example:5432/cdb?sslmode=require"


def test_database_url_override_leaves_explicit_psycopg_scheme_untouched() -> None:
    url = "postgresql+psycopg://cu:cp@cloud.example:5432/cdb?sslmode=require"
    assert Settings(_env_file=None, **BASE, database_url_override=url).database_url == url


def test_redis_url_from_parts_by_default() -> None:
    s = Settings(_env_file=None, **BASE, redis_host="rh", redis_port=6380, redis_db=2, redis_url_override=None)
    assert s.redis_url == "redis://rh:6380/2"


def test_redis_url_override_supports_tls_and_auth() -> None:
    url = "rediss://:secret@cloud-redis.example:6379/0"
    assert Settings(_env_file=None, **BASE, redis_url_override=url).redis_url == url
