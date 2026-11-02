"""Print `serving` if PostgreSQL accepts a query, `wedged` otherwise.

A postmaster on Windows can survive an unclean client termination and come back
unable to reserve its shared-memory segment: it keeps listening on the port and
every connection then hangs or fails. `pg_ctl status` cannot see that, so this
probe asks the server a question instead of trusting the process table.

Kept as its own file because embedding multi-line Python inside a PowerShell
string is how the caller ends up waiting on a quoting accident.
"""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg

HOST = "127.0.0.1"
PORT = int(os.environ.get("SPARKX_DEVDB_PORT", "5432"))
USER = os.environ.get("SPARKX_DEVDB_USER", "sparkx")


async def main() -> None:
    try:
        conn = await asyncpg.connect(
            host=HOST, port=PORT, user=USER, database="postgres", timeout=6
        )
        try:
            await conn.fetchval("select 1")
        finally:
            await conn.close()
    except Exception:  # noqa: BLE001 - any failure means "not serving"
        print("wedged")
        sys.exit(1)
    print("serving")


if __name__ == "__main__":
    asyncio.run(main())
