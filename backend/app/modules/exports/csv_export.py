from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from typing import Any

# Columns exported for a business row. Attribution and verification state are
# part of the export, not optional extras: a lead list that has lost its source
# is a list of guesses (PRD section 7.2, master prompt section 9).
BUSINESS_COLUMNS: tuple[str, ...] = (
    "name",
    "primary_category",
    "phone",
    "email",
    "email_verification_status",
    "website_url",
    "website_status",
    "address",
    "city",
    "state",
    "country",
    "latitude",
    "longitude",
    "opportunity_score",
    "opportunity_confidence",
    "qualification_status",
    "evidence_summary",
    "source_slugs",
    "source_urls",
    "first_discovered_at",
    "last_researched_at",
    "crm_stage",
)

_UNTRUSTED_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralize_formula(value: str) -> str:
    r"""Stop a scraped cell from executing when the CSV is opened in a spreadsheet.

    Business names and descriptions come from public web pages. A page that
    titles itself ``=cmd\|'...`` would otherwise become a formula the operator's
    Excel runs. Quoting alone is not enough — Excel evaluates after unquoting.
    """
    if value and value[0] in _UNTRUSTED_PREFIXES:
        return "'" + value
    return value


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ";".join(str(part) for part in value)
    if isinstance(value, Mapping):
        return ";".join(f"{key}={child}" for key, child in sorted(value.items()))
    return str(value)


def to_csv(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str] = BUSINESS_COLUMNS,
) -> str:
    """Serialise rows as CSV with a fixed, ordered header.

    Fields a row does not carry export as empty rather than shifting the columns,
    so a consumer can trust the header order.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(list(columns))

    for row in rows:
        writer.writerow([neutralize_formula(_stringify(row.get(column))) for column in columns])

    return buffer.getvalue()


def parse_selected_fields(raw: str | Sequence[str] | None) -> tuple[str, ...]:
    """Resolve a requested field list, rejecting columns that are not exported.

    Silently dropping an unknown column would hand the user a file missing the
    field they asked for and no indication of it.
    """
    if raw is None or raw == "":
        return BUSINESS_COLUMNS
    requested = [raw] if isinstance(raw, str) else list(raw)
    unknown = [name for name in requested if name not in BUSINESS_COLUMNS]
    if unknown:
        raise ValueError(f"Unknown export columns: {', '.join(unknown)}")
    return tuple(requested)
