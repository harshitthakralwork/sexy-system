"""Schema integrity tests against a real PostgreSQL.

These skip when no database is reachable, so the suite still runs on a bare
machine — but they are the only tests that prove the migrations produce what the
models claim. Metadata-level unit tests cannot see that a migration silently
dropped a primary key; these can.

The file exists because `0002` created `business_tags` with a unique constraint
and no primary key, and Alembic's autogenerate reported no drift in either
direction. Each test opens and closes its own connection: a pool bound to one
event loop cannot be used from another, which is exactly how async test suites
produce mysterious cross-loop failures.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from app.core.config import get_settings

try:
    import asyncpg
except ImportError:  # pragma: no cover - asyncpg is a runtime dependency
    asyncpg = None


async def _connect() -> asyncpg.Connection:
    dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(dsn=dsn, timeout=5)


@asynccontextmanager
async def database() -> AsyncIterator[asyncpg.Connection]:
    """Skip rather than fail when there is no database.

    An absent development database is an environment fact, not a broken build;
    reporting it as a failure would train everyone to ignore red tests.
    """
    if asyncpg is None:
        pytest.skip("asyncpg is not installed")
    try:
        connection = await _connect()
    except Exception as exc:  # noqa: BLE001 - any connection failure is a skip here
        pytest.skip(f"no reachable PostgreSQL for integrity tests ({type(exc).__name__})")
    try:
        yield connection
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_every_table_has_a_primary_key() -> None:
    """The regression this file was written for.

    A table without a primary key is unreplicable, unmergeable and free to
    accumulate duplicates, and nothing else in the suite would notice.
    """
    async with database() as connection:
        rows = await connection.fetch(
            """
            select t.tablename,
                   exists (
                       select 1 from pg_constraint k
                       where k.conrelid = ('public.' || t.tablename)::regclass and k.contype = 'p'
                   ) as has_pk
            from pg_tables t
            where t.schemaname = 'public' and t.tablename <> 'alembic_version'
            order by t.tablename
            """
        )
    missing = [row["tablename"] for row in rows if not row["has_pk"]]
    assert not missing, f"tables without a primary key: {missing}"
    assert len(rows) >= 37, f"expected the full slice schema, found {len(rows)} tables"


@pytest.mark.asyncio
async def test_foreign_keys_are_enforced() -> None:
    """Provenance and ownership tables are only as good as the references between
    them; a dangling business_id would be an invisible integrity failure."""
    async with database() as connection:
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await connection.execute(
                "insert into business_tags (business_id, tag_id) values ($1, $2)",
                uuid.uuid4(),
                uuid.uuid4(),
            )


@pytest.mark.asyncio
async def test_composite_key_rejects_duplicate_tag_links() -> None:
    business_id, tag_id, owner_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with database() as connection:
        try:
            await connection.execute(
                "insert into users (id, email, password_hash, display_name)"
                " values ($1, $2, 'hash', 'Test')",
                owner_id,
                f"test-{owner_id}@example.com",
            )
            await connection.execute(
                "insert into businesses (id, owner_user_id, name, website_status, lifecycle_status,"
                " first_discovered_at) values ($1, $2, 'Integrity Test Co',"
                " 'unknown', 'active', now())",
                business_id,
                owner_id,
            )
            await connection.execute(
                "insert into tags (id, owner_user_id, name) values ($1, $2, 'integrity')",
                tag_id,
                owner_id,
            )
            await connection.execute(
                "insert into business_tags (business_id, tag_id) values ($1, $2)",
                business_id,
                tag_id,
            )
            with pytest.raises(asyncpg.UniqueViolationError):
                await connection.execute(
                    "insert into business_tags (business_id, tag_id) values ($1, $2)",
                    business_id,
                    tag_id,
                )
        finally:
            await connection.execute(
                "delete from business_tags where business_id = $1", business_id
            )
            await connection.execute("delete from tags where id = $1", tag_id)
            await connection.execute("delete from businesses where id = $1", business_id)
            await connection.execute("delete from users where id = $1", owner_id)


@pytest.mark.asyncio
async def test_check_constraints_reject_invented_states() -> None:
    """`website_status` deliberately distinguishes missing / inaccessible / unknown.
    Without the constraint the database would accept any string and the scoring
    engine would be reading fiction."""
    async with database() as connection:
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                "insert into businesses (id, owner_user_id, name, website_status, lifecycle_status,"
                " first_discovered_at) values ($1, $2, 'Check Test Co',"
                " 'definitely_has_one', 'active', now())",
                uuid.uuid4(),
                uuid.uuid4(),
            )


@pytest.mark.asyncio
async def test_job_progress_counters_are_bounded() -> None:
    """Progress must come from real processing. A 140% job is the kind of number a
    simulated percentage produces, and the schema refuses it outright."""
    async with database() as connection:
        with pytest.raises(asyncpg.CheckViolationError):
            await connection.execute(
                "insert into discovery_jobs (id, owner_user_id, job_type, status, progress_percent)"
                " values ($1, $2, 'discovery', 'running', 140)",
                uuid.uuid4(),
                uuid.uuid4(),
            )


@pytest.mark.asyncio
async def test_server_side_uuid_default_is_available() -> None:
    """gen_random_uuid() comes from the pgcrypto revision. If that extension were
    missing, inserts relying on the server default would fail at runtime instead
    of at migration time."""
    async with database() as connection:
        assert await connection.fetchval("select gen_random_uuid() is not null") is True


@pytest.mark.asyncio
async def test_jsonb_and_timestamptz_round_trip() -> None:
    """Storage is UTC and flexible metadata is JSONB, per database-schema.md §4.
    A timezone silently becoming local time would corrupt retention deadlines."""
    business_id, owner_id = uuid.uuid4(), uuid.uuid4()
    async with database() as connection:
        try:
            await connection.execute(
                "insert into users (id, email, password_hash, display_name)"
                " values ($1, $2, 'hash', 'Test')",
                owner_id,
                f"test-{owner_id}@example.com",
            )
            await connection.execute(
                "insert into businesses (id, owner_user_id, name, website_status, lifecycle_status,"
                " first_discovered_at, enrichment)"
                " values ($1, $2, 'TZ Test Co', 'unknown', 'active',"
                " '2026-11-02T00:00:00+00:00', $3)",
                business_id,
                owner_id,
                '{"source": "test"}',
            )
            row = await connection.fetchrow(
                "select first_discovered_at at time zone 'UTC' as utc_ts, enrichment"
                " from businesses where id = $1",
                business_id,
            )
            assert row["utc_ts"].hour == 0
            assert '"source": "test"' in row["enrichment"]
        finally:
            await connection.execute("delete from businesses where id = $1", business_id)
            await connection.execute("delete from users where id = $1", owner_id)
