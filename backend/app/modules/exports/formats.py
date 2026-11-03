"""Rendering and reading the tabular formats the platform exchanges files in.

CSV, Excel and JSON are the three formats the PRD asks for (PRD section 7.8).
They share one rule: a value that came from a public web page is never allowed
to become something the spreadsheet will execute.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from app.modules.exports.csv_export import BUSINESS_COLUMNS, neutralize_formula, to_csv

EXPORT_FORMATS: tuple[str, ...] = ("csv", "json", "xlsx")

FORMAT_EXTENSIONS: dict[str, str] = {"csv": "csv", "json": "json", "xlsx": "xlsx"}

FORMAT_MEDIA_TYPES: dict[str, str] = {
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Columns whose text must not be reinterpreted by a spreadsheet. A phone number
# written as a number loses its leading zero, and a postal code written as a
# number loses the ones Excel thinks are padding.
TEXT_ONLY_COLUMNS: frozenset[str] = frozenset({"phone", "email", "postal_code"})

# The prefixes a spreadsheet treats as the start of a formula. Excel refuses
# `=` outright; the others are interpreted by Excel and LibreOffice alike.
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _is_formula_like(value: str) -> bool:
    return value.startswith(_FORMULA_PREFIXES)


def _xlsx_cell_value(value: Any, column: str) -> Any:
    """One cell of an Excel sheet, safe to write.

    Text stays text, so a phone number keeps its leading zero and a code like
    `007` is not silently turned into 7.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and column not in TEXT_ONLY_COLUMNS:
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        return ";".join(str(part) for part in value)
    if isinstance(value, Mapping):
        return ";".join(f"{key}={child}" for key, child in sorted(value.items()))
    return str(value)


def _write_xlsx(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> bytes:
    """Render rows as an Excel workbook.

    Every cell that starts with a formula prefix is forced back to text and
    marked as quoted: openpyxl turns any string beginning with `=` into a
    formula cell, and Excel evaluates those on open. Quoting alone is not
    enough — Excel evaluates after unquoting.
    """
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Export"
    sheet.append(list(columns))

    for row in rows:
        sheet.append([_xlsx_cell_value(row.get(column), column) for column in columns])
        for cell in sheet[sheet.max_row]:
            if cell.data_type == "f" or (
                isinstance(cell.value, str) and _is_formula_like(cell.value)
            ):
                cell.data_type = "s"
                cell.quotePrefix = True

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def render_export(
    rows: Sequence[Mapping[str, Any]], columns: Sequence[str], export_format: str
) -> bytes:
    """Render rows in one of the supported formats.

    CSV is written with a byte-order mark so Excel opens a non-ASCII name as
    text rather than as mojibake.
    """
    if export_format == "csv":
        return to_csv(rows, columns=columns).encode("utf-8-sig")
    if export_format == "json":
        payload = [{column: row.get(column) for column in columns} for row in rows]
        return json.dumps(payload, indent=2, default=str, ensure_ascii=False).encode("utf-8")
    if export_format == "xlsx":
        return _write_xlsx(rows, columns)
    raise ValueError(f"Unsupported export format '{export_format}'")


def _cell_text(value: Any) -> str:
    """One uploaded cell as the text it will be interpreted as."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _read_csv(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    try:
        header_raw = next(reader)
    except StopIteration:
        return [], []
    header = [cell.strip() for cell in header_raw]
    rows: list[dict[str, str]] = []
    for raw in reader:
        if not any(cell.strip() for cell in raw):
            continue
        record: dict[str, str] = {}
        for index, column in enumerate(header):
            record[column] = raw[index].strip() if index < len(raw) else ""
        rows.append(record)
    return header, rows


def _read_xlsx(data: bytes) -> tuple[list[str], list[dict[str, str]]]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        sheet = workbook.active
        stream = sheet.iter_rows(values_only=True)
        try:
            header_raw = next(stream)
        except StopIteration:
            return [], []
        header = [("" if cell is None else str(cell).strip()) for cell in header_raw]
        rows: list[dict[str, str]] = []
        for raw in stream:
            if raw is None or all(cell is None or str(cell).strip() == "" for cell in raw):
                continue
            record: dict[str, str] = {}
            for index, column in enumerate(header):
                value = raw[index] if index < len(raw) else None
                record[column] = _cell_text(value)
            rows.append(record)
        return header, rows
    finally:
        workbook.close()


def read_header(data: bytes, file_format: str) -> list[str]:
    """The first row of a file, read without parsing the rest of it.

    The upload response needs the column names so the operator can map them,
    and a file that turns out to be the wrong shape should be refused at
    upload time rather than after a full parse.
    """
    if file_format == "csv":
        text = data.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        try:
            first = next(reader)
        except StopIteration:
            return []
        return [cell.strip() for cell in first]
    if file_format == "xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            sheet = workbook.active
            for row in sheet.iter_rows(values_only=True):
                return [("" if cell is None else str(cell).strip()) for cell in row]
            return []
        finally:
            workbook.close()
    raise ValueError(f"Unsupported import format '{file_format}'")


def count_rows(data: bytes, file_format: str) -> int:
    """How many data rows the file holds, excluding the header."""
    if file_format == "csv":
        text = data.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        total = 0
        for row in reader:
            if any(cell.strip() for cell in row):
                total += 1
        return max(total - 1, 0)
    if file_format == "xlsx":
        from openpyxl import load_workbook

        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            sheet = workbook.active
            total = 0
            seen_header = False
            for row in sheet.iter_rows(values_only=True):
                if not seen_header:
                    seen_header = True
                    continue
                if row is not None and any(
                    cell is not None and str(cell).strip() for cell in row
                ):
                    total += 1
            return total
        finally:
            workbook.close()
    raise ValueError(f"Unsupported import format '{file_format}'")


def read_tabular(data: bytes, file_format: str) -> tuple[list[str], list[dict[str, str]]]:
    """Read an uploaded file into a header row and a list of string records.

    Values come back as text because that is what the file actually said. The
    importer normalises them afterwards, and a number that was rounded by the
    exporting spreadsheet cannot be recovered here.
    """
    if file_format == "csv":
        return _read_csv(data)
    if file_format == "xlsx":
        return _read_xlsx(data)
    raise ValueError(f"Unsupported import format '{file_format}'")


def neutralize_cell(value: str) -> str:
    """Public alias of the formula guard, for callers outside this module."""
    return neutralize_formula(value)


__all__ = [
    "BUSINESS_COLUMNS",
    "EXPORT_FORMATS",
    "FORMAT_EXTENSIONS",
    "FORMAT_MEDIA_TYPES",
    "TEXT_ONLY_COLUMNS",
    "count_rows",
    "neutralize_cell",
    "read_header",
    "read_tabular",
    "render_export",
]
