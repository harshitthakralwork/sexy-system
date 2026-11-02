from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.exports.csv_export import (
    BUSINESS_COLUMNS,
    neutralize_formula,
    parse_selected_fields,
    to_csv,
)


def test_export_header_is_the_agreed_column_order() -> None:
    csv_text = to_csv([{"name": "Spark Coffee"}])
    assert csv_text.splitlines()[0] == ",".join(BUSINESS_COLUMNS)


def test_missing_fields_export_empty_instead_of_shifting_columns() -> None:
    row = to_csv([{"name": "Spark", "city": "Bengaluru"}]).splitlines()[1]
    values = row.split(",")
    assert values[0] == "Spark"
    assert len(values) == len(BUSINESS_COLUMNS)


def test_attribution_columns_are_part_of_the_default_export() -> None:
    """A lead list with no source is unusable for verification or opt-out."""
    assert "source_slugs" in BUSINESS_COLUMNS
    assert "source_urls" in BUSINESS_COLUMNS
    assert "email_verification_status" in BUSINESS_COLUMNS
    assert "website_status" in BUSINESS_COLUMNS


@pytest.mark.parametrize("payload", ["=cmd|'/C calc'!A0", "+SUM(1+1)", "-2+3", "@SUM(1+1)"])
def test_scraped_text_cannot_become_a_spreadsheet_formula(payload: str) -> None:
    """A page title is attacker-controlled text. Excel evaluates a leading
    = + - @ after unquoting, so the cell must be defanged, not just quoted."""
    line = to_csv([{"name": payload}]).splitlines()[1]
    assert line.startswith("'" + payload[0])


def test_neutralize_leaves_ordinary_text_alone() -> None:
    assert neutralize_formula("Spark Coffee") == "Spark Coffee"
    assert neutralize_formula("-80% of sales") == "'-80% of sales"


def test_lists_and_mappings_flatten_readably() -> None:
    csv_text = to_csv([{"source_slugs": ["searxng", "overpass"]}])
    assert "searxng;overpass" in csv_text


def test_booleans_export_as_words_not_python_repr() -> None:
    assert "true" in to_csv([{"website_status": True}])


def test_none_becomes_empty_not_the_word_none() -> None:
    line = to_csv([{"name": None}]).splitlines()[1]
    assert "None" not in line


def test_requesting_an_unknown_column_is_rejected() -> None:
    """Dropping it silently would hand back a file missing what was asked for."""
    with pytest.raises(ValueError, match="Unknown export columns"):
        parse_selected_fields(["name", "inner_thoughts"])


def test_selected_fields_are_honoured_in_requested_order() -> None:
    assert parse_selected_fields(["city", "name"]) == ("city", "name")
    csv_text = to_csv(
        [{"name": "Spark", "city": "Bengaluru"}], parse_selected_fields(["city", "name"])
    )
    assert csv_text.splitlines()[0] == "city,name"


def test_row_with_no_data_still_emits_a_header_only_file() -> None:
    assert to_csv([]).splitlines() == [",".join(BUSINESS_COLUMNS)]


def test_timestamps_survive_serialisation() -> None:
    moment = datetime(2026, 11, 2, 9, 30, tzinfo=UTC)
    csv_text = to_csv([{"first_discovered_at": moment}])
    assert "2026-11-02 09:30:00+00:00" in csv_text
