"""A report on what the database actually contains.

Every other surface in this platform reports what it did. This one reports
what is there, including the parts that should not be: rows owned by an
account that does not exist, counters that went negative, jobs still
claiming to be running long after their worker died, and files a job row
points at after the file itself is gone.

It is a diagnostic, not a gate. It repairs nothing and hides nothing: a
count of zero is reported as zero, and a count of four hundred is reported
as four hundred with the table it came from.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.integrations.storage import StorageError, get_storage
from app.modules.exports.models import ExportJob, ImportJob

logger = get_logger(__name__)

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"

# Table and column names come from the database's own catalogue, never from a
# request, but they are interpolated into SQL. This is the check that keeps
# them from being anything else.
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")

# Counters that can only ever increase from zero. A negative one means a row
# was written by arithmetic that went wrong, and no consumer of that row can
# make sense of it.
_COUNTERS: tuple[tuple[str, str], ...] = (
    ("discovery_jobs", "total_records"),
    ("discovery_jobs", "processed_records"),
    ("discovery_jobs", "failed_records"),
    ("discovery_jobs", "retry_count"),
    ("job_batches", "records_expected"),
    ("job_batches", "records_processed"),
    ("job_batches", "retry_count"),
    ("import_jobs", "total_rows"),
    ("import_jobs", "processed_rows"),
    ("import_jobs", "failed_rows"),
    ("export_jobs", "total_records"),
)

# A row that says "processed more than there were" is a broken count, unless
# the total was never known, in which case the comparison is meaningless.
_PROCESSED_VS_TOTAL: tuple[tuple[str, str, str], ...] = (
    ("discovery_jobs", "processed_records", "total_records"),
    ("job_batches", "records_processed", "records_expected"),
    ("import_jobs", "processed_rows", "total_rows"),
)


@dataclass(frozen=True)
class Finding:
    """One thing that is wrong, and how many times."""

    code: str
    severity: str
    count: int
    description: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "count": self.count,
            "description": self.description,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class IntegrityReport:
    """The audit's answer. ``ok`` means nothing was found at error severity."""

    checked_at: datetime
    findings: list[Finding] = field(default_factory=list)
    scope: str = "global"

    @property
    def ok(self) -> bool:
        return not any(finding.severity == SEVERITY_ERROR for finding in self.findings)

    def as_dict(self) -> dict[str, Any]:
        return {
            "checked_at": self.checked_at.isoformat(),
            "scope": self.scope,
            "ok": self.ok,
            "findings": [finding.as_dict() for finding in self.findings],
        }


def _safe(identifier: str) -> str:
    if not _IDENTIFIER.fullmatch(identifier):
        raise ValueError(f"refusing to use {identifier!r} as an identifier")
    return f'"{identifier}"'


async def _owned_tables(connection: AsyncSession) -> list[str]:
    rows = await connection.execute(
        text(
            """
            select table_name
            from information_schema.columns
            where table_schema = 'public'
              and column_name = 'owner_user_id'
              and table_name <> 'alembic_version'
            order by table_name
            """
        )
    )
    return [row[0] for row in rows]


async def _orphan_owner_rows(
    connection: AsyncSession, owner_user_id: uuid.UUID | None
) -> dict[str, int]:
    """Rows that name an owner who does not exist.

    `database-schema.md` §4.3 says an owned table references `users(id)`. That
    constraint is not in the database, so this count is the only thing standing
    between a mistyped owner id and a silent, invisible leak.
    """
    orphans: dict[str, int] = {}
    for table in await _owned_tables(connection):
        scope = ""
        params: dict[str, Any] = {}
        if owner_user_id is not None:
            scope = " and o.owner_user_id = :owner"
            params["owner"] = owner_user_id
        count = await connection.scalar(
            text(
                f"""
                select count(*)
                from {_safe(table)} o
                left join users u on u.id = o.owner_user_id
                where o.owner_user_id is not null
                  and u.id is null{scope}
                """
            ),
            params,
        )
        if count:
            orphans[table] = int(count)
    return orphans


async def _count(
    connection: AsyncSession, statement: str, owner_user_id: uuid.UUID | None
) -> int:
    scope = ""
    params: dict[str, Any] = {}
    if owner_user_id is not None:
        scope = " and owner_user_id = :owner"
        params["owner"] = owner_user_id
    value = await connection.scalar(
        text(f"select count(*) from {statement}{scope}"), params
    )
    return int(value or 0)


async def _structural_findings(
    connection: AsyncSession, owner_user_id: uuid.UUID | None
) -> list[Finding]:
    findings: list[Finding] = []

    orphans = await _orphan_owner_rows(connection, owner_user_id)
    if orphans:
        findings.append(
            Finding(
                code="orphan_owner_reference",
                severity=SEVERITY_ERROR,
                count=sum(orphans.values()),
                description=(
                    "Rows whose owner_user_id does not exist in users. Foreign key "
                    "constraints enforce new writes (NOT VALID), but historical rows "
                    "remain unvalidated."
                ),
                detail={"tables": orphans},
            )
        )

    negative: dict[str, int] = {}
    for table, column in _COUNTERS:
        count = await _count(
            connection,
            f'{_safe(table)} where "{column}" < 0',
            owner_user_id,
        )
        if count:
            negative[f"{table}.{column}"] = count
    if negative:
        findings.append(
            Finding(
                code="negative_counter",
                severity=SEVERITY_ERROR,
                count=sum(negative.values()),
                description="Counters that went below zero.",
                detail={"counters": negative},
            )
        )

    over_processed: dict[str, int] = {}
    for table, processed, total in _PROCESSED_VS_TOTAL:
        count = await _count(
            connection,
            f'{_safe(table)} where "{processed}" > "{total}" and "{total}" > 0',
            owner_user_id,
        )
        if count:
            over_processed[f"{table}.{processed}>{total}"] = count
    if over_processed:
        findings.append(
            Finding(
                code="processed_exceeds_total",
                severity=SEVERITY_ERROR,
                count=sum(over_processed.values()),
                description="Rows that processed more records than the total they started with.",
                detail={"counters": over_processed},
            )
        )

    out_of_range = await _count(
        connection,
        '"discovery_jobs" where "progress_percent" < 0 or "progress_percent" > 100',
        owner_user_id,
    )
    if out_of_range:
        findings.append(
            Finding(
                code="progress_out_of_range",
                severity=SEVERITY_ERROR,
                count=out_of_range,
                description="Discovery jobs whose progress is outside 0-100.",
            )
        )

    completed_without_file = await _count(
        connection,
        '"export_jobs" where status = \'completed\' and storage_key is null',
        owner_user_id,
    )
    if completed_without_file:
        findings.append(
            Finding(
                code="completed_export_without_file",
                severity=SEVERITY_ERROR,
                count=completed_without_file,
                description=(
                    "Exports reported as completed that name no file. The row says "
                    "the work succeeded, and there is nothing to download."
                ),
            )
        )

    return findings


async def _stuck_jobs(
    connection: AsyncSession, owner_user_id: uuid.UUID | None, stale_after: int
) -> list[Finding]:
    findings: list[Finding] = []
    cutoff = datetime.now(UTC) - timedelta(seconds=stale_after)
    for table in ("discovery_jobs", "job_batches"):
        scope = ""
        params: dict[str, Any] = {"cutoff": cutoff}
        if owner_user_id is not None:
            scope = " and owner_user_id = :owner"
            params["owner"] = owner_user_id
        count = await connection.scalar(
            text(
                f"""
                select count(*) from {_safe(table)}
                where status = 'running' and "started_at" is not null
                  and "started_at" < :cutoff{scope}
                """
            ),
            params,
        )
        if count:
            findings.append(
                Finding(
                    code=f"stuck_{table}",
                    severity=SEVERITY_WARNING,
                    count=int(count),
                    description=(
                        f"Rows in {table} still marked running long after their "
                        "worker would have died. They need a decision, not a wait."
                    ),
                )
            )
    return findings


async def _missing_files(
    connection: AsyncSession, owner_user_id: uuid.UUID | None, settings: Settings
) -> list[Finding]:
    """Rows that point at a file which is no longer there.

    The file store is local, so this happens when a directory is cleaned by
    hand, when a machine changes, or when a row was written and the file was
    never written. Either way the operator is told a download exists.
    """
    storage = get_storage(settings)
    counts: dict[str, int] = {}
    for model in (ExportJob, ImportJob):
        statement = select(model.storage_key).where(model.storage_key != "")
        if owner_user_id is not None:
            statement = statement.where(model.owner_user_id == owner_user_id)
        rows = await connection.execute(statement)
        missing = 0
        for (key,) in rows:
            if not key:
                continue
            try:
                present = storage.exists(key)
            except StorageError:
                present = False
            if not present:
                missing += 1
        counts[model.__tablename__] = missing

    findings: list[Finding] = []
    if counts["export_jobs"]:
        findings.append(
            Finding(
                code="missing_export_file",
                severity=SEVERITY_ERROR,
                count=counts["export_jobs"],
                description="Export rows that point at a file which is not there.",
            )
        )
    if counts["import_jobs"]:
        findings.append(
            Finding(
                code="missing_import_file",
                severity=SEVERITY_WARNING,
                count=counts["import_jobs"],
                description="Import rows that point at an uploaded file which is not there.",
            )
        )
    return findings


async def audit_database(
    *,
    settings: Settings | None = None,
    owner_user_id: uuid.UUID | None = None,
) -> IntegrityReport:
    """Read the database and report what is wrong with it.

    With no `owner_user_id` the audit is global — every row, every table. With
    one, it is scoped to that account, which is what the HTTP surface uses so
    that one account's report cannot describe another account's data.
    """
    active = settings or get_settings()
    findings: list[Finding] = []
    async with session_scope() as session:
        findings.extend(await _structural_findings(session, owner_user_id))
        findings.extend(
            await _stuck_jobs(session, owner_user_id, active.stale_job_after_seconds)
        )
        findings.extend(await _missing_files(session, owner_user_id, active))

    report = IntegrityReport(
        checked_at=datetime.now(UTC),
        findings=findings,
        scope="owner" if owner_user_id is not None else "global",
    )
    if findings:
        logger.warning(
            "integrity_findings",
            count=len(findings),
            codes=[finding.code for finding in findings],
        )
    return report


def main() -> int:
    """Print the global report. Used by the operator, not by the API.

    The audit is a diagnostic for the person who owns the installation, so it
    runs from the command line where it can see every table.
    """
    import asyncio
    import json

    report = asyncio.run(audit_database())
    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.ok else 1


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
