"""Alembic environment — async migrations using project Settings."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.config import Settings
from src.infrastructure.database.models import Base

# Alembic Config object
config = context.config

# Python logging from the config file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use the application's metadata for autogenerate support
target_metadata = Base.metadata


def _get_database_url() -> str:
    """Build the database URL from application settings.

    Falls back to alembic.ini ``sqlalchemy.url`` when the required
    ``IMG_DB_USER`` / ``IMG_DB_PASSWORD`` env vars are not set (e.g.
    offline generation with a placeholder URL).
    """
    try:
        settings = Settings()  # type: ignore[call-arg]
        return settings.database_url
    except Exception:
        url = config.get_main_option("sqlalchemy.url")
        if not url:
            raise RuntimeError(
                "Database URL not configured. Set IMG_DB_USER and "
                "IMG_DB_PASSWORD environment variables, or provide "
                "sqlalchemy.url in alembic.ini."
            ) from None
        return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emits SQL without a live connection."""
    url = _get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations."""
    db_url = _get_database_url()
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = db_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
