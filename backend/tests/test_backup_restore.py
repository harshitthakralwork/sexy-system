"""Tests for backup/restore safety, integrity diagnostics, and owner FK enforcement.

Validates that:
1. Owner foreign keys actively reject new orphan inserts.
2. The integrity audit produces accurate diagnostic findings reflecting NOT VALID FKs.
3. Backup/restore scripts enforce required safeguards and prevent accidental data loss.
"""

from __future__ import annotations

import pathlib
import uuid

import pytest

from app.core.config import get_settings
from app.modules.health.integrity import audit_database

try:
    import asyncpg
except ImportError:
    asyncpg = None


@pytest.mark.asyncio
async def test_owner_fk_rejects_new_orphan_insert() -> None:
    """The foreign keys added in c7d4e1a92b08 are NOT VALID on historical rows,

    but MUST enforce new writes. Inserting a row pointing to a nonexistent owner
    must fail with ForeignKeyViolationError.
    """
    if asyncpg is None:
        pytest.skip("asyncpg is not installed")

    dsn = get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(dsn=dsn, timeout=5)
    nonexistent_user = uuid.uuid4()
    try:
        with pytest.raises(asyncpg.ForeignKeyViolationError) as exc_info:
            await conn.execute(
                "insert into notifications (id, owner_user_id, notification_type, title, message) "
                "values ($1, $2, 'system', 'Test Alert', 'Orphan test message')",
                uuid.uuid4(),
                nonexistent_user,
            )
        assert "fk_notifications_owner_user_id_users" in str(exc_info.value)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_integrity_audit_description_accurate() -> None:
    """The integrity audit must accurately describe that foreign key constraints

    enforce new writes while historical rows remain unvalidated.
    """
    report = await audit_database()
    orphan_finding = next((f for f in report.findings if f.code == "orphan_owner_reference"), None)
    if orphan_finding is not None:
        assert "NOT VALID" in orphan_finding.description
        assert "enforce new writes" in orphan_finding.description


def test_backup_and_restore_scripts_exist() -> None:
    """The backup and restore automation scripts must exist and be executable."""
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    backup_script = root / "scripts" / "backup-db.ps1"
    restore_script = root / "scripts" / "restore-db.ps1"

    assert backup_script.is_file(), f"Missing {backup_script}"
    assert restore_script.is_file(), f"Missing {restore_script}"

    # Verify restore-db.ps1 contains safety guard preventing accidental primary DB overwrite
    restore_content = restore_script.read_text(encoding="utf-8")
    assert "AllowPrimaryDatabase" in restore_content
    assert "ConfirmOverwrite" in restore_content


def test_backup_directory_is_gitignored() -> None:
    """The backup storage path backend/var/backups must be gitignored."""
    root = pathlib.Path(__file__).resolve().parent.parent.parent
    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert "backend/var/" in gitignore or "*.dump" in gitignore
