"""Alembic environment — online migrations against the app database.

The DB URL and all metadata come from the application, so migrations never drift
from the ORM models and no credentials live in alembic.ini.
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import settings
from app.models import Base  # imports every model -> populates Base.metadata

config = context.config

# A caller that set ``sqlalchemy.url`` explicitly (the Postgres integration tests
# point Alembic at their own throwaway database) must win: clobbering it here
# would run their up/down migration against the app's real database instead.
_explicit_url = config.get_main_option("sqlalchemy.url", None)
db_url = _explicit_url or settings.database_url
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
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
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
