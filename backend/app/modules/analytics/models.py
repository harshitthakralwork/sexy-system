"""Saved report snapshots for the Analytics & Reports feature (master plan #27).

A report is a point-in-time capture of the analytics summary the operator chose to
keep, with the filters that produced it. The snapshot is computed at creation from
real queries and stored alongside the moment it was taken, so re-opening an old
report shows the numbers as of then rather than silently drifting — the same honesty
rule that keeps discovered/stored/classified counts distinct elsewhere in the app.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import (
    JSONType,
    OwnedMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
)


class SavedReport(Base, OwnedMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "saved_reports"
    __table_args__ = (
        CheckConstraint(
            "report_type IN ('analytics','leads','social','startups')",
            name="ck_saved_report_type",
        ),
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="analytics", server_default=text("'analytics'")
    )
    # The analytics payload captured when the report was created, plus its timestamp.
    snapshot: Mapped[dict] = mapped_column(
        JSONType, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    captured_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
