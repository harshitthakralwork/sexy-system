"""Phase 9: import and export.

The export side and the import side are tested against the real API and the real
database, because both are claims about data the account holds: an export that
returns a file with the wrong rows, or an import that reports "12 imported" when
it wrote three, is worse than no feature at all.

Nothing here mocks storage or the ORM. The one thing that is faked is the
network, because there is none.
"""

from __future__ import annotations

import asyncio
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.core.database import session_scope
from app.integrations.storage import StorageError
from app.integrations.storage.local import LocalFileStorage
from app.modules.businesses.models import Business, BusinessContact
from app.modules.discovery.models import SourceRecord, SourceRecordLink
from app.modules.exports import importer, service
from app.modules.exports.formats import render_export
from app.modules.exports.models import ExportJob
from app.modules.sources.models import Source
from tests.conftest import Session


def _insert_business(
    owner_id: str,
    *,
    name: str = "Spark Cafe",
    domain: str | None = "sparkcafe.co.in",
    city: str | None = "Bengaluru",
    phone: str | None = None,
) -> str:
    async def run() -> str:
        async with session_scope() as db:
            business = Business(
                owner_user_id=uuid.UUID(owner_id),
                name=name,
                normalized_name=name.lower(),
                normalized_domain=domain,
                normalized_phone=phone,
                phone=phone,
                city=city,
                country="IN",
                website_url=f"https://{domain}" if domain else None,
                website_status="unknown",
                enrichment={"signals": {}},
                first_discovered_at=datetime.now(UTC),
            )
            db.add(business)
            await db.flush()
            return str(business.id)

    return asyncio.run(run())


def _csv_bytes(rows: list[dict[str, str]]) -> bytes:
    import csv

    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def _upload(account: Session, data: bytes, filename: str = "leads.csv") -> dict[str, Any]:
    response = account.api.post(
        "/api/v1/imports",
        files={"file": (filename, data, "text/csv")},
        headers=account.csrf_headers(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _run_import(account: Session, job_id: str, mapping: dict[str, str], strategy: str = "skip"):
    response = account.api.post(
        f"/api/v1/imports/{job_id}/run",
        json={"mapping": mapping, "duplicate_strategy": strategy},
        headers=account.csrf_headers(),
    )
    assert response.status_code == 200, response.text
    # The run response says `queued`; the counts are on the row the run wrote.
    return _await_import(account, job_id)


def _businesses(owner_id: str) -> list[Business]:
    async def load() -> list[Business]:
        async with session_scope() as db:
            rows = await db.scalars(
                select(Business)
                .where(Business.owner_user_id == uuid.UUID(owner_id))
                .order_by(Business.created_at)
            )
            return list(rows)

    return asyncio.run(load())


def _await_export(account: Session, job_id: str) -> dict[str, Any]:
    """Read an export job back after its background run finished.

    The response that queued the job says `queued`, because that is the truth at
    the moment it was sent: the file is produced afterwards. Re-reading the row
    is how the operator sees the finished state too.
    """
    detail = account.api.get(f"/api/v1/exports/{job_id}")
    assert detail.status_code == 200, detail.text
    return detail.json()


def _await_import(account: Session, job_id: str) -> dict[str, Any]:
    detail = account.api.get(f"/api/v1/imports/{job_id}")
    assert detail.status_code == 200, detail.text
    return detail.json()


# --- Export catalogue --------------------------------------------------------


def test_the_catalogue_lists_every_module_and_format(session_account: Session) -> None:
    body = session_account.api.get("/api/v1/exports/catalogue").json()
    keys = {module["key"] for module in body["modules"]}
    assert keys == {"leads", "social_content", "social_intelligence", "startups"}
    assert body["formats"] == ["csv", "json", "xlsx"]


def test_the_catalogue_states_the_filters_and_columns_each_module_understands(
    session_account: Session,
) -> None:
    body = session_account.api.get("/api/v1/exports/catalogue").json()
    leads = next(module for module in body["modules"] if module["key"] == "leads")
    assert "source_slugs" in leads["columns"]
    assert "shortlisted_only" in leads["filters"]


# --- Export lifecycle --------------------------------------------------------


def test_an_export_produces_a_file_that_can_be_downloaded(session_account: Session) -> None:
    _insert_business(session_account.user_id, name="Spark Cafe")

    created = session_account.api.post(
        "/api/v1/exports",
        json={"module": "leads", "format": "csv"},
        headers=session_account.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    # The response says `queued`: the file is produced afterwards, and claiming
    # otherwise would tell the operator a download exists before it does.
    assert created.json()["status"] == "queued"

    job = _await_export(session_account, created.json()["id"])
    assert job["status"] == "completed"
    assert job["total_records"] == 1
    assert job["downloadable"] is True

    downloaded = session_account.api.get(f"/api/v1/exports/{job['id']}/download")
    assert downloaded.status_code == 200
    assert "text/csv" in downloaded.headers["content-type"]
    assert "sparkxflow-leads-" in downloaded.headers["content-disposition"]
    text = downloaded.content.decode("utf-8-sig")
    assert "Spark Cafe" in text


def test_an_export_of_an_empty_account_still_returns_a_header_only_file(
    session_account: Session,
) -> None:
    created = session_account.api.post(
        "/api/v1/exports",
        json={"module": "leads", "format": "csv"},
        headers=session_account.csrf_headers(),
    )
    job = _await_export(session_account, created.json()["id"])
    assert job["total_records"] == 0
    downloaded = session_account.api.get(f"/api/v1/exports/{job['id']}/download")
    assert downloaded.status_code == 200
    assert downloaded.content.decode("utf-8-sig").strip().count(",") > 5


def test_an_export_honours_the_filter_it_was_given(session_account: Session) -> None:
    _insert_business(session_account.user_id, name="Bengaluru Cafe", city="Bengaluru")
    _insert_business(session_account.user_id, name="Pune Cafe", city="Pune")

    created = session_account.api.post(
        "/api/v1/exports",
        json={"module": "leads", "format": "csv", "filters": {"city": "Pune"}},
        headers=session_account.csrf_headers(),
    )
    job = _await_export(session_account, created.json()["id"])
    assert job["total_records"] == 1
    text = session_account.api.get(f"/api/v1/exports/{job['id']}/download").content.decode(
        "utf-8-sig"
    )
    assert "Pune Cafe" in text
    assert "Bengaluru Cafe" not in text


def test_an_unknown_filter_is_dropped_rather_than_reaching_the_query(
    session_account: Session,
) -> None:
    _insert_business(session_account.user_id, name="Spark Cafe")

    created = session_account.api.post(
        "/api/v1/exports",
        json={
            "module": "leads",
            "format": "csv",
            "filters": {"city": "Bengaluru", "owner_user_id": "someone-else"},
        },
        headers=session_account.csrf_headers(),
    )
    assert created.status_code == 201, created.text
    job = _await_export(session_account, created.json()["id"])
    assert "owner_user_id" not in job["filters"]
    assert job["total_records"] == 1


def test_an_unknown_module_is_refused(session_account: Session) -> None:
    response = session_account.api.post(
        "/api/v1/exports",
        json={"module": "passwords", "format": "csv"},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text
    assert "passwords" in response.text


def test_an_unknown_column_is_refused_rather_than_silently_dropped(
    session_account: Session,
) -> None:
    response = session_account.api.post(
        "/api/v1/exports",
        json={"module": "leads", "format": "csv", "selected_fields": ["name", "salary"]},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text
    assert "salary" in response.text


def test_an_unknown_format_is_refused(session_account: Session) -> None:
    response = session_account.api.post(
        "/api/v1/exports",
        json={"module": "leads", "format": "pdf"},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text


def test_an_export_can_be_produced_in_each_supported_format(session_account: Session) -> None:
    _insert_business(session_account.user_id, name="Spark Cafe")

    for export_format in ("csv", "json", "xlsx"):
        created = session_account.api.post(
            "/api/v1/exports",
            json={"module": "leads", "format": export_format},
            headers=session_account.csrf_headers(),
        )
        assert created.status_code == 201, created.text
        job = _await_export(session_account, created.json()["id"])
        assert job["status"] == "completed", job
        downloaded = session_account.api.get(f"/api/v1/exports/{job['id']}/download")
        assert downloaded.status_code == 200
        assert downloaded.content
        if export_format == "xlsx":
            # A workbook is a zip archive; the name is inside it, not in the bytes.
            assert downloaded.content[:2] == b"PK"
            from openpyxl import load_workbook

            workbook = load_workbook(io.BytesIO(downloaded.content))
            assert workbook.active["A1"].value == "name"
            assert workbook.active["A2"].value == "Spark Cafe"
            workbook.close()
        else:
            assert "Spark Cafe" in downloaded.content.decode("utf-8-sig", errors="replace")


def test_deleting_an_export_removes_the_file_but_keeps_the_history(
    session_account: Session,
) -> None:
    _insert_business(session_account.user_id, name="Spark Cafe")
    created = session_account.api.post(
        "/api/v1/exports",
        json={"module": "leads", "format": "csv"},
        headers=session_account.csrf_headers(),
    )
    job = created.json()

    deleted = session_account.api.delete(
        f"/api/v1/exports/{job['id']}", headers=session_account.csrf_headers()
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["downloadable"] is False

    detail = session_account.api.get(f"/api/v1/exports/{job['id']}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"

    again = session_account.api.get(f"/api/v1/exports/{job['id']}/download")
    assert again.status_code == 404


def test_another_account_cannot_read_or_delete_an_export(make_account) -> None:
    owner = make_account()
    _insert_business(owner.user_id, name="Spark Cafe")
    created = owner.api.post(
        "/api/v1/exports",
        json={"module": "leads", "format": "csv"},
        headers=owner.csrf_headers(),
    )
    job_id = created.json()["id"]

    stranger = make_account()
    assert stranger.api.get(f"/api/v1/exports/{job_id}").status_code == 404
    assert stranger.api.get(f"/api/v1/exports/{job_id}/download").status_code == 404
    assert (
        stranger.api.delete(
            f"/api/v1/exports/{job_id}", headers=stranger.csrf_headers()
        ).status_code
        == 404
    )


def test_creating_an_export_requires_a_csrf_token(session_account: Session) -> None:
    response = session_account.api.post(
        "/api/v1/exports", json={"module": "leads", "format": "csv"}
    )
    assert response.status_code == 403, response.text


# --- Import lifecycle --------------------------------------------------------


def test_an_upload_reports_the_columns_and_a_suggested_mapping_without_writing(
    session_account: Session,
) -> None:
    data = _csv_bytes(
        [
            {"Business Name": "Spark Cafe", "Website": "https://sparkcafe.co.in", "City": "Pune"},
            {"Business Name": "Second Cafe", "Website": "https://second.co.in", "City": "Delhi"},
        ]
    )
    body = _upload(session_account, data)

    assert body["columns"] == ["Business Name", "Website", "City"]
    assert body["suggested_mapping"]["Business Name"] == "name"
    assert body["suggested_mapping"]["Website"] == "website"
    assert body["total_rows"] == 2
    assert _businesses(session_account.user_id) == []


def test_a_confirmed_mapping_imports_the_rows_as_businesses(session_account: Session) -> None:
    data = _csv_bytes(
        [
            {
                "Business Name": "Spark Cafe",
                "Website": "https://sparkcafe.co.in",
                "City": "Pune",
                "Phone": "+91 98765 43210",
                "Email": "hello@sparkcafe.co.in",
            }
        ]
    )
    uploaded = _upload(session_account, data)
    job = _run_import(
        session_account,
        uploaded["id"],
        {
            "Business Name": "name",
            "Website": "website",
            "City": "city",
            "Phone": "phone",
            "Email": "email",
        },
    )
    assert job["status"] == "completed", job
    assert job["processed_rows"] == 1
    assert job["failed_rows"] == 0

    businesses = _businesses(session_account.user_id)
    assert len(businesses) == 1
    assert businesses[0].name == "Spark Cafe"
    assert businesses[0].city == "Pune"
    assert businesses[0].normalized_domain == "sparkcafe.co.in"
    assert businesses[0].normalized_phone == "+919876543210"


def test_an_imported_row_carries_provenance_pointing_at_the_file(
    session_account: Session,
) -> None:
    data = _csv_bytes(
        [{"Business Name": "Spark Cafe", "Website": "https://sparkcafe.co.in"}]
    )
    uploaded = _upload(session_account, data, filename="my-leads.csv")
    _run_import(
        session_account, uploaded["id"], {"Business Name": "name", "Website": "website"}
    )

    async def load() -> tuple[list[SourceRecord], list[SourceRecordLink]]:
        async with session_scope() as db:
            records = list(
                await db.scalars(
                    select(SourceRecord).where(
                        SourceRecord.owner_user_id == uuid.UUID(session_account.user_id)
                    )
                )
            )
            links = list(
                await db.scalars(
                    select(SourceRecordLink).where(
                        SourceRecordLink.source_record_id.in_([row.id for row in records])
                    )
                )
            )
            return records, links

    records, links = asyncio.run(load())
    assert len(records) == 1
    assert records[0].module == "import"
    assert records[0].source_url == "my-leads.csv"
    assert records[0].owner_user_id == uuid.UUID(session_account.user_id)
    assert len(links) == 1
    assert links[0].entity_type == "business"


def test_the_import_source_is_registered_as_a_source(session_account: Session) -> None:
    data = _csv_bytes(
        [{"Business Name": "Spark Cafe", "Website": "https://sparkcafe.co.in"}]
    )
    uploaded = _upload(session_account, data)
    _run_import(
        session_account, uploaded["id"], {"Business Name": "name", "Website": "website"}
    )

    async def load() -> Source | None:
        async with session_scope() as db:
            return await db.scalar(select(Source).where(Source.slug == importer.IMPORT_SOURCE_SLUG))

    source = asyncio.run(load())
    assert source is not None
    assert source.category == "import"


def test_imported_contacts_are_unverified(session_account: Session) -> None:
    data = _csv_bytes(
        [
            {
                "Business Name": "Spark Cafe",
                "Website": "https://sparkcafe.co.in",
                "Email": "hello@sparkcafe.co.in",
            }
        ]
    )
    uploaded = _upload(session_account, data)
    _run_import(
        session_account,
        uploaded["id"],
        {"Business Name": "name", "Website": "website", "Email": "email"},
    )

    async def load() -> list[BusinessContact]:
        async with session_scope() as db:
            return list(
                await db.scalars(
                    select(BusinessContact)
                    .join(Business, Business.id == BusinessContact.business_id)
                    .where(Business.owner_user_id == uuid.UUID(session_account.user_id))
                )
            )

    contacts = asyncio.run(load())
    assert len(contacts) == 1
    assert contacts[0].verification_status == "unverified"


def test_a_row_with_neither_a_name_nor_a_website_is_reported_as_a_failure(
    session_account: Session,
) -> None:
    """A row with content but no name and no website cannot become a business.

    The trailing blank line a spreadsheet leaves behind is not data and is
    skipped before it reaches the counter; a row that carries other values but
    nothing the importer can identify is a real failure and is reported.
    """
    data = _csv_bytes(
        [
            {"Business Name": "Spark Cafe", "Website": "https://sparkcafe.co.in"},
            {"Business Name": "", "Website": "", "Notes": "no identifier here"},
        ]
    )
    uploaded = _upload(session_account, data)
    job = _run_import(
        session_account, uploaded["id"], {"Business Name": "name", "Website": "website"}
    )

    assert job["status"] == "completed"
    assert job["processed_rows"] == 1
    assert job["failed_rows"] == 1
    details = job["error_details"]
    assert details["failed"] == 1
    assert details["errors"][0]["row"] == 3
    assert len(_businesses(session_account.user_id)) == 1


def test_a_partly_readable_row_imports_with_a_warning_rather_than_failing(
    session_account: Session,
) -> None:
    """A bad phone number does not make the whole row worthless."""
    data = _csv_bytes(
        [
            {
                "Business Name": "Spark Cafe",
                "Website": "https://sparkcafe.co.in",
                "Phone": "not-a-number",
            }
        ]
    )
    uploaded = _upload(session_account, data)
    job = _run_import(
        session_account,
        uploaded["id"],
        {"Business Name": "name", "Website": "website", "Phone": "phone"},
    )

    assert job["failed_rows"] == 0
    assert job["processed_rows"] == 1
    details = job["error_details"]
    assert details["warnings"], "the dropped field was not reported"
    assert details["warnings"][0]["row"] == 2
    assert len(_businesses(session_account.user_id)) == 1


def test_an_unreadable_rating_is_dropped_and_the_record_still_imports(
    session_account: Session,
) -> None:
    data = _csv_bytes(
        [
            {
                "Business Name": "Spark Cafe",
                "Website": "https://sparkcafe.co.in",
                "Rating": "not-a-number",
            }
        ]
    )
    uploaded = _upload(session_account, data)
    job = _run_import(
        session_account,
        uploaded["id"],
        {"Business Name": "name", "Website": "website", "Rating": "rating"},
    )
    assert job["failed_rows"] == 0
    businesses = _businesses(session_account.user_id)
    assert len(businesses) == 1
    assert businesses[0].rating is None


def test_a_duplicate_row_is_skipped_by_default(session_account: Session) -> None:
    data = _csv_bytes(
        [
            {"Business Name": "Spark Cafe", "Website": "https://sparkcafe.co.in"},
            {"Business Name": "Spark Cafe Again", "Website": "https://sparkcafe.co.in"},
        ]
    )
    uploaded = _upload(session_account, data)
    job = _run_import(
        session_account, uploaded["id"], {"Business Name": "name", "Website": "website"}
    )

    assert job["processed_rows"] == 1
    assert job["error_details"]["duplicates_skipped"] == 1
    assert len(_businesses(session_account.user_id)) == 1


def test_the_merge_strategy_fills_the_gaps_of_an_existing_record(
    session_account: Session,
) -> None:
    _insert_business(
        session_account.user_id, name="Spark Cafe", domain="sparkcafe.co.in", city=None
    )

    data = _csv_bytes(
        [
            {
                "Business Name": "Spark Cafe",
                "Website": "https://sparkcafe.co.in",
                "City": "Pune",
                "Phone": "+91 98765 43210",
            }
        ]
    )
    uploaded = _upload(session_account, data)
    job = _run_import(
        session_account,
        uploaded["id"],
        {"Business Name": "name", "Website": "website", "City": "city", "Phone": "phone"},
        strategy="merge",
    )

    assert job["error_details"]["merged"] == 1
    businesses = _businesses(session_account.user_id)
    assert len(businesses) == 1
    assert businesses[0].city == "Pune"
    assert businesses[0].normalized_phone == "+919876543210"


def test_the_merge_strategy_never_overwrites_a_field_that_already_has_a_value(
    session_account: Session,
) -> None:
    _insert_business(
        session_account.user_id, name="Spark Cafe", domain="sparkcafe.co.in", city="Mumbai"
    )

    data = _csv_bytes(
        [
            {
                "Business Name": "Spark Cafe Renamed",
                "Website": "https://sparkcafe.co.in",
                "City": "Pune",
            }
        ]
    )
    uploaded = _upload(session_account, data)
    _run_import(
        session_account,
        uploaded["id"],
        {"Business Name": "name", "Website": "website", "City": "city"},
        strategy="merge",
    )

    businesses = _businesses(session_account.user_id)
    assert len(businesses) == 1
    assert businesses[0].name == "Spark Cafe"
    assert businesses[0].city == "Mumbai"


def test_the_create_strategy_writes_the_duplicate_as_a_second_record(
    session_account: Session,
) -> None:
    _insert_business(session_account.user_id, name="Spark Cafe", domain="sparkcafe.co.in")

    data = _csv_bytes(
        [{"Business Name": "Spark Cafe", "Website": "https://sparkcafe.co.in"}]
    )
    uploaded = _upload(session_account, data)
    job = _run_import(
        session_account,
        uploaded["id"],
        {"Business Name": "name", "Website": "website"},
        strategy="create",
    )
    assert job["error_details"]["created"] == 1
    assert len(_businesses(session_account.user_id)) == 2


def test_two_businesses_with_the_same_name_are_not_treated_as_duplicates(
    session_account: Session,
) -> None:
    """Two different cafes called "Spark Coffee" are a real thing."""
    data = _csv_bytes(
        [
            {"Business Name": "Spark Coffee", "Website": "https://one.co.in"},
            {"Business Name": "Spark Coffee", "Website": "https://two.co.in"},
        ]
    )
    uploaded = _upload(session_account, data)
    job = _run_import(
        session_account, uploaded["id"], {"Business Name": "name", "Website": "website"}
    )
    assert job["error_details"]["created"] == 2
    assert len(_businesses(session_account.user_id)) == 2


def test_a_mapping_naming_a_field_the_importer_does_not_know_is_refused(
    session_account: Session,
) -> None:
    data = _csv_bytes([{"Business Name": "Spark Cafe"}])
    uploaded = _upload(session_account, data)
    response = session_account.api.post(
        f"/api/v1/imports/{uploaded['id']}/run",
        json={"mapping": {"Business Name": "salary"}, "duplicate_strategy": "skip"},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text
    assert "salary" in response.text


def test_a_mapping_naming_a_column_the_file_does_not_have_is_refused(
    session_account: Session,
) -> None:
    data = _csv_bytes([{"Business Name": "Spark Cafe"}])
    uploaded = _upload(session_account, data)
    response = session_account.api.post(
        f"/api/v1/imports/{uploaded['id']}/run",
        json={"mapping": {"Nonexistent": "name"}, "duplicate_strategy": "skip"},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text


def test_a_mapping_with_neither_a_name_nor_a_website_is_refused(
    session_account: Session,
) -> None:
    data = _csv_bytes([{"City": "Pune"}])
    uploaded = _upload(session_account, data)
    response = session_account.api.post(
        f"/api/v1/imports/{uploaded['id']}/run",
        json={"mapping": {"City": "city"}, "duplicate_strategy": "skip"},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text


def test_a_file_that_is_not_a_csv_or_an_excel_file_is_refused(
    session_account: Session,
) -> None:
    response = session_account.api.post(
        "/api/v1/imports",
        files={"file": ("leads.txt", b"name\nSpark", "text/plain")},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text


def test_an_empty_file_is_refused(session_account: Session) -> None:
    response = session_account.api.post(
        "/api/v1/imports",
        files={"file": ("leads.csv", b"", "text/csv")},
        headers=session_account.csrf_headers(),
    )
    assert response.status_code == 422, response.text


def test_another_account_cannot_read_or_run_someone_elses_import(make_account) -> None:
    owner = make_account()
    data = _csv_bytes([{"Business Name": "Spark Cafe", "Website": "https://sparkcafe.co.in"}])
    uploaded = _upload(owner, data)

    stranger = make_account()
    assert stranger.api.get(f"/api/v1/imports/{uploaded['id']}").status_code == 404
    response = stranger.api.post(
        f"/api/v1/imports/{uploaded['id']}/run",
        json={"mapping": {"Business Name": "name"}, "duplicate_strategy": "skip"},
        headers=stranger.csrf_headers(),
    )
    assert response.status_code == 404, response.text


def test_uploading_an_import_requires_a_csrf_token(session_account: Session) -> None:
    data = _csv_bytes([{"Business Name": "Spark Cafe"}])
    response = session_account.api.post(
        "/api/v1/imports", files={"file": ("leads.csv", data, "text/csv")}
    )
    assert response.status_code == 403, response.text


def test_deleting_an_import_removes_the_uploaded_file(session_account: Session) -> None:
    data = _csv_bytes([{"Business Name": "Spark Cafe", "Website": "https://sparkcafe.co.in"}])
    uploaded = _upload(session_account, data)

    deleted = session_account.api.delete(
        f"/api/v1/imports/{uploaded['id']}", headers=session_account.csrf_headers()
    )
    assert deleted.status_code == 200, deleted.text

    detail = session_account.api.get(f"/api/v1/imports/{uploaded['id']}")
    assert detail.status_code == 200
    assert detail.json()["total_rows"] == 1


def test_the_import_vocabulary_lists_the_fields_and_the_duplicate_strategies(
    session_account: Session,
) -> None:
    body = session_account.api.get("/api/v1/imports/vocabulary").json()
    keys = {field["key"] for field in body["fields"]}
    assert {"name", "website", "phone", "email", "city"} <= keys
    assert body["duplicate_strategies"] == ["skip", "merge", "create"]
    assert set(body["formats"]) == {"csv", "xlsx"}


# --- Storage -----------------------------------------------------------------


def test_the_storage_adapter_refuses_a_key_that_would_escape_its_root(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path)
    for key in ("../escape.txt", "a/../../escape.txt", "/absolute.txt", "a\\b.txt"):
        with pytest.raises(StorageError):
            storage.save(key, b"data")


def test_the_storage_adapter_purges_only_the_files_under_the_prefix(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path)
    storage.save("exports/one.csv", b"a")
    storage.save("imports/two.csv", b"b")

    removed = storage.purge_older_than(
        datetime.now(UTC) + timedelta(hours=1), prefix="exports"
    )
    assert removed == 1
    assert storage.exists("imports/two.csv")
    assert not storage.exists("exports/one.csv")


def test_the_expired_export_files_are_swept_and_the_rows_keep_their_history(
    session_account: Session,
) -> None:
    _insert_business(session_account.user_id, name="Spark Cafe")
    created = session_account.api.post(
        "/api/v1/exports",
        json={"module": "leads", "format": "csv"},
        headers=session_account.csrf_headers(),
    )
    job_id = created.json()["id"]

    async def expire() -> None:
        async with session_scope() as db:
            job = await db.get(ExportJob, uuid.UUID(job_id))
            assert job is not None
            job.expires_at = datetime.now(UTC) - timedelta(hours=1)
            await db.commit()

    asyncio.run(expire())
    removed = asyncio.run(service.purge_expired_files())
    assert removed >= 1

    detail = session_account.api.get(f"/api/v1/exports/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["downloadable"] is False
    assert detail.json()["total_records"] == 1


# --- Formats -----------------------------------------------------------------


def test_a_formula_shaped_value_is_not_executed_when_the_excel_file_is_opened() -> None:
    from openpyxl import load_workbook

    data = render_export([{"name": "=cmd|'/C calc'!A0"}], ["name"], "xlsx")
    workbook = load_workbook(io.BytesIO(data))
    cell = workbook.active["A2"]
    assert cell.data_type == "s"
    assert cell.value == "=cmd|'/C calc'!A0"
    workbook.close()


def test_a_phone_number_keeps_its_leading_zero_in_an_excel_file() -> None:
    from openpyxl import load_workbook

    data = render_export([{"phone": "09876543210"}], ["phone"], "xlsx")
    workbook = load_workbook(io.BytesIO(data))
    cell = workbook.active["A2"]
    assert cell.value == "09876543210"
    assert cell.data_type == "s"
    workbook.close()


def test_a_csv_export_carries_a_byte_order_mark_so_excel_reads_it_as_text() -> None:
    data = render_export([{"name": "Café"}], ["name"], "csv")
    assert data.startswith(b"\xef\xbb\xbf")


def test_the_export_module_catalogue_refuses_an_unknown_module() -> None:
    from app.core.exceptions import ValidationFailedError

    with pytest.raises(ValidationFailedError):
        service.columns_for("passwords")
