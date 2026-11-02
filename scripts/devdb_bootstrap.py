"""Ensure the development database exists and has the required extensions.

Called by scripts/devdb.ps1 after the cluster is started.

Deliberately uses asyncpg rather than psql: the CLI inherits the console's
stdin, and when it decides it wants a password or a confirmation it blocks
forever inside a non-interactive shell. That is what made devdb.ps1 hang after
a reboot, with the server already running fine.
"""

from __future__ import annotations

import asyncio
import sys

import asyncpg

HOST = "127.0.0.1"
PORT = 5432
USER = "sparkx"
DATABASE = "sparkxflow"
EXTENSIONS = ("pgcrypto", "pg_trgm")


async def ensure_database() -> None:
    connection = await asyncpg.connect(host=HOST, port=PORT, user=USER, database="postgres")
    try:
        exists = await connection.fetchval("select 1 from pg_database where datname = $1", DATABASE)
        if exists:
            print(f"database {DATABASE} already present")
            return
        # CREATE DATABASE cannot run inside a transaction, and asyncpg prepares
        # simple queries by default; fetchval with an explicit execute avoids that.
        await connection.execute(f'CREATE DATABASE "{DATABASE}" OWNER "{USER}"')
        print(f"created database {DATABASE}")
    finally:
        await connection.close()


async def report() -> None:
    connection = await asyncpg.connect(host=HOST, port=PORT, user=USER, database=DATABASE)
    try:
        for extension in EXTENSIONS:
            await connection.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension}"')
        installed = sorted(
            row["extname"] for row in await connection.fetch("select extname from pg_extension")
        )
        tables = await connection.fetchval(
            "select count(*) from information_schema.tables"
            " where table_schema = 'public' and table_type = 'BASE TABLE'"
        )
        revision = await connection.fetchval("select version_num from alembic_version limit 1")
        print(f"extensions: {', '.join(installed)}")
        print(f"base tables: {tables}")
        print(f"alembic revision: {revision or 'none (run db-migrate)'}")
        print(f"ready: {await connection.fetchval('select version()')}")
    finally:
        await connection.close()


async def main() -> None:
    await ensure_database()
    await report()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a failure
        print(f"devdb bootstrap failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
