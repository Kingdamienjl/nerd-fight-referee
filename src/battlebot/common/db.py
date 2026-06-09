"""Database helpers for local tools and workers."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import asyncpg


DEFAULT_DATABASE_URL = "postgresql://battlebot:change_me@localhost:5432/battlebot"


def database_url(override: str | None = None) -> str:
    return override or os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL


def schema_sql_path() -> Path:
    return Path(__file__).resolve().parents[1] / "db" / "schema.sql"


def load_schema_sql() -> str:
    return schema_sql_path().read_text(encoding="utf-8")


@asynccontextmanager
async def connect_database(url: str | None = None) -> AsyncIterator[asyncpg.Connection]:
    connection = await asyncpg.connect(database_url(url))
    try:
        yield connection
    finally:
        await connection.close()


async def apply_schema(connection: asyncpg.Connection) -> None:
    await connection.execute(load_schema_sql())
