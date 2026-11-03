"""Deleting an account's rows, in an order the database allows.

The tables to clear and the order to clear them in are read from the database's
own foreign key graph rather than from a list written by hand. A hand-written
list was correct only until a table was added to the schema and forgotten:
`notifications`, `search_areas`, `search_presets` and `retention_policies`
were never cleared, so every account that created a search area left a row
behind pointing at an account that no longer existed.

Two callers use this:

* the test harness, which deletes the rows each test account created, and
* the integrity repair, which deletes rows whose owner no longer exists.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_FK_GRAPH = """
select con.conrelid::regclass::text as child,
       child_col.attname as child_column,
       con.confrelid::regclass::text as parent,
       parent_col.attname as parent_column
from pg_constraint con
join pg_class child_class on child_class.oid = con.conrelid
join pg_namespace ns on ns.oid = child_class.relnamespace
join lateral unnest(con.conkey) with ordinality as ck(attnum, ord) on true
join lateral unnest(con.confkey) with ordinality as pk(attnum, ord) on pk.ord = ck.ord
join pg_attribute child_col
  on child_col.attrelid = con.conrelid and child_col.attnum = ck.attnum
join pg_attribute parent_col
  on parent_col.attrelid = con.confrelid and parent_col.attnum = pk.attnum
where con.contype = 'f' and ns.nspname = 'public'
"""

_COLUMNS = """
select table_name, column_name
from information_schema.columns
where table_schema = 'public'
"""

# Tables that record something an account did but cannot be reached from
# `users` through a foreign key, so the graph walk never reaches them.
_UNLINKED_BY_JOB = ("source_usage_records",)


@dataclass(frozen=True)
class ForeignKey:
    """One foreign key: `child.child_column` points at `parent.parent_column`."""

    child_table: str
    child_column: str
    parent_table: str
    parent_column: str


@dataclass(frozen=True)
class Schema:
    """The parts of the live schema the purge needs to know."""

    columns: dict[str, set[str]] = field(default_factory=dict)
    parents: dict[str, list[ForeignKey]] = field(default_factory=dict)
    children: dict[str, list[ForeignKey]] = field(default_factory=dict)

    def owner_predicate(self, table: str, seen: frozenset[str] = frozenset()) -> str | None:
        """A WHERE clause selecting the rows of `table` that belong to one account.

        Every leaf is the same `:owner` parameter — the account id — so a
        predicate can be nested inside a subquery without renumbering.
        """
        if table == "users":
            return "id = :owner"
        available = self.columns.get(table, set())
        if "owner_user_id" in available:
            return "owner_user_id = :owner"
        if "user_id" in available:
            return "user_id = :owner"
        if table in seen:
            return None

        clauses: list[str] = []
        for fk in self.parents.get(table, []):
            parent_predicate = self.owner_predicate(fk.parent_table, seen | {table})
            if parent_predicate is None:
                continue
            clauses.append(
                f'"{fk.child_column}" in (select "{fk.parent_column}"'
                f' from "{fk.parent_table}" where {parent_predicate})'
            )
        if not clauses:
            return None
        return " or ".join(f"({clause})" for clause in clauses)

    def deletion_order(self) -> list[str]:
        """Tables that must be emptied, children before the rows they point at.

        A depth-first walk from `users` yields exactly that: a table is listed
        after everything that references it.
        """
        order: list[str] = []
        seen: set[str] = set()

        def visit(table: str) -> None:
            if table in seen:
                return
            seen.add(table)
            for fk in sorted(self.children.get(table, []), key=lambda f: f.child_table):
                visit(fk.child_table)
            order.append(table)

        visit("users")
        return order


async def read_schema(connection: AsyncConnection) -> Schema:
    columns: dict[str, set[str]] = {}
    for row in (await connection.execute(text(_COLUMNS))).mappings():
        columns.setdefault(row["table_name"], set()).add(row["column_name"])

    parents: dict[str, list[ForeignKey]] = {}
    children: dict[str, list[ForeignKey]] = {}
    for row in (await connection.execute(text(_FK_GRAPH))).mappings():
        fk = ForeignKey(
            child_table=row["child"],
            child_column=row["child_column"],
            parent_table=row["parent"],
            parent_column=row["parent_column"],
        )
        parents.setdefault(fk.child_table, []).append(fk)
        children.setdefault(fk.parent_table, []).append(fk)
    return Schema(columns=columns, parents=parents, children=children)


async def delete_account_rows(
    connection: AsyncConnection, user_id: uuid.UUID
) -> dict[str, int]:
    """Remove every row that belongs to `user_id`. Returns rows removed per table."""
    schema = await read_schema(connection)
    removed: dict[str, int] = {}

    for table in schema.deletion_order():
        predicate = schema.owner_predicate(table)
        if predicate is None:
            continue
        count = await _delete(
            connection, f'delete from "{table}" where {predicate}', {"owner": user_id}
        )
        if count:
            removed[table] = count

    # `source_usage_records` has no path to `users`: it records that a source was
    # used and names the job that used it without a foreign key. The rows an
    # account's own jobs produced are still that account's history.
    for table in _UNLINKED_BY_JOB:
        if table not in schema.columns:
            continue
        count = await _delete(
            connection,
            f'delete from "{table}" where job_id in'
            " (select id from discovery_jobs where owner_user_id = :owner)",
            {"owner": user_id},
        )
        if count:
            removed[table] = count

    return removed


async def delete_orphan_rows(connection: AsyncConnection) -> dict[str, int]:
    """Remove rows whose owner no longer exists.

    These rows are unreachable. No account can list them, and with the foreign
    key in place nothing can attach them to an account again — they are the
    legacy of the window before the constraint existed.
    """
    schema = await read_schema(connection)
    removed: dict[str, int] = {}

    for table in schema.deletion_order():
        if table == "users" or "owner_user_id" not in schema.columns.get(table, set()):
            continue
        count = await _delete(
            connection,
            f'delete from "{table}" where owner_user_id is not null'
            " and not exists (select 1 from users u"
            f' where u.id = "{table}".owner_user_id)',
        )
        if count:
            removed[table] = count

    return removed


async def _delete(
    connection: AsyncConnection, statement: str, params: dict[str, object] | None = None
) -> int:
    result = await connection.execute(text(statement), params or {})
    return int(result.rowcount or 0)
