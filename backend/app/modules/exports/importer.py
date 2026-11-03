"""Bulk import: a file of leads becomes records, with the mapping stated.

The file is the operator's own data, so it is not evidence about the world and
it is never dressed up as something a public source said. It is still *a*
source, and it is registered as one so an imported lead carries provenance that
points at the file it came from rather than an empty column.

Duplicate detection is by domain and by phone. Never by name: two different
businesses called "Spark Coffee" are a real thing.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import session_scope
from app.core.exceptions import NotFoundError, ValidationFailedError
from app.core.logging import get_logger
from app.integrations.storage import StorageError, get_storage
from app.modules.businesses.models import Business, BusinessContact
from app.modules.discovery.models import SourceRecord, SourceRecordLink
from app.modules.discovery.store_sql import bound_payload
from app.modules.exports.formats import read_header, read_tabular
from app.modules.exports.models import ImportJob
from app.modules.sources.models import Source
from app.shared.base import utcnow
from app.shared.normalization import (
    canonical_hash,
    normalize_domain,
    normalize_email,
    normalize_name,
    normalize_phone,
    sanitize_text,
)
from app.workers.dispatcher import SynchronousDispatcher, get_dispatcher
from app.workers.tasks import register_task

logger = get_logger(__name__)

IMPORT_TASK_NAME = "sparkxflow.exports.run_import"

IMPORT_SOURCE_SLUG = "file_import"

# The fields an import may fill, and what each one means. This is the whole
# vocabulary: a column mapped to anything else is refused rather than ignored.
IMPORT_FIELDS: dict[str, str] = {
    "name": "Business name",
    "website": "Website URL",
    "phone": "Phone number",
    "email": "Email address",
    "category": "Category",
    "description": "Description",
    "address": "Street address",
    "city": "City",
    "state": "State or region",
    "country": "Country",
    "postal_code": "Postal code",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "rating": "Rating (0-5)",
    "review_count": "Review count",
}

# What to do with a row that matches a record the account already has.
DUPLICATE_STRATEGIES: tuple[str, ...] = ("skip", "merge", "create")

# Errors are reported per row, but a file with ten thousand broken rows must
# not produce a megabyte of JSON.
MAX_REPORTED_ERRORS = 100


@dataclass
class ImportCounts:
    """What the run actually did, counted as it happened."""

    total: int = 0
    created: int = 0
    merged: int = 0
    duplicates_skipped: int = 0
    failed: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def fail(self, row_number: int, reason: str) -> None:
        """A row that produced no record at all."""
        self.failed += 1
        if len(self.errors) < MAX_REPORTED_ERRORS:
            self.errors.append({"row": row_number, "reason": reason})

    def warn(self, row_number: int, reason: str) -> None:
        """A row that imported, but with a field that could not be read.

        Counted separately from failures: the record exists, and saying it
        failed would understate what the import produced.
        """
        if len(self.warnings) < MAX_REPORTED_ERRORS:
            self.warnings.append({"row": row_number, "reason": reason})

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total,
            "created": self.created,
            "merged": self.merged,
            "duplicates_skipped": self.duplicates_skipped,
            "failed": self.failed,
            "errors": self.errors,
            "warnings": self.warnings,
        }


async def ensure_import_source(session: AsyncSession) -> uuid.UUID:
    """Register the source an import came from.

    An uploaded file is not a web provider, but it is still where the data came
    from. Registering it means an imported lead can be traced back to the file
    that produced it, instead of carrying an empty provenance column.
    """
    existing = await session.scalar(select(Source.id).where(Source.slug == IMPORT_SOURCE_SLUG))
    if existing is not None:
        return existing
    source = Source(
        slug=IMPORT_SOURCE_SLUG,
        name="File import",
        category="import",
        adapter_key=IMPORT_SOURCE_SLUG,
        description="Records imported from a file uploaded by the account holder.",
        capabilities={"available_fields": list(IMPORT_FIELDS)},
        limitations={
            "rate_limit_notes": "Not applicable — the data is supplied locally.",
            "terms_notes": (
                "The operator is responsible for holding the rights to the imported data."
            ),
            "access_requirements": [],
            "max_results_per_query": None,
        },
        coverage={"geographic_coverage": "Whatever the uploaded file contains."},
        rate_limit_config={"notes": "Not applicable"},
    )
    session.add(source)
    await session.flush()
    return source.id


def suggest_mapping(header: Sequence[str]) -> dict[str, str]:
    """Guess which column carries which field, from the header names.

    A guess, and labelled as one: the operator confirms it before the import
    runs, and nothing is written on the strength of a guess alone.
    """
    normalized = {column.strip().lower().replace(" ", "_"): column for column in header}
    mapping: dict[str, str] = {}
    for field_name in IMPORT_FIELDS:
        if field_name in normalized:
            mapping[normalized[field_name]] = field_name
            continue
        for alias, column in normalized.items():
            if alias in _FIELD_ALIASES.get(field_name, ()):
                mapping[column] = field_name
                break
    return mapping


_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("business_name", "company", "company_name", "title", "business"),
    "website": ("url", "website_url", "site", "web", "domain"),
    "phone": ("phone_number", "mobile", "telephone", "contact_number", "contact"),
    "email": ("email_address", "e_mail", "mail"),
    "category": ("type", "business_category", "primary_category", "industry"),
    "description": ("about", "details", "notes", "summary"),
    "address": ("street", "street_address", "full_address"),
    "city": ("town", "locality"),
    "state": ("region", "province", "state_region"),
    "country": ("country_code", "nation"),
    "postal_code": ("zip", "zipcode", "postcode", "pin", "pin_code"),
    "latitude": ("lat", "y"),
    "longitude": ("lon", "lng", "long", "x"),
    "rating": ("stars", "star_rating", "google_rating"),
    "review_count": ("reviews", "no_of_reviews", "number_of_reviews"),
}


def read_mapping_config(config: Mapping[str, Any] | None) -> tuple[dict[str, str], str]:
    """The column mapping and the duplicate strategy stored on the job.

    The stored shape is `{"columns": {...}, "duplicate_strategy": "skip"}`. A
    flat mapping is still accepted, because that is the shape the UI sends.
    """
    if not config:
        return {}, "skip"
    columns = config.get("columns")
    if not isinstance(columns, dict):
        columns = {
            key: value for key, value in config.items() if key != "duplicate_strategy"
        }
    strategy = str(config.get("duplicate_strategy") or "skip")
    return {str(key): str(value) for key, value in columns.items()}, strategy


def validate_mapping(
    mapping: Mapping[str, str], header: Sequence[str]
) -> dict[str, str]:
    """Check the mapping against the file's own header.

    A column the file does not have, or a field the importer does not know, is
    refused: both would otherwise become a row that is silently half-imported.
    """
    if not mapping:
        raise ValidationFailedError(
            "A field mapping is required", details={"fields": list(IMPORT_FIELDS)}
        )
    clean: dict[str, str] = {}
    for column, field_name in mapping.items():
        if field_name not in IMPORT_FIELDS:
            raise ValidationFailedError(
                f"Unknown import field '{field_name}'", details={"fields": list(IMPORT_FIELDS)}
            )
        if column not in header:
            raise ValidationFailedError(
                f"The file has no column named '{column}'",
                details={"columns": list(header)},
            )
        clean[column] = field_name
    mapped_fields = set(clean.values())
    if not mapped_fields & {"name", "website"}:
        raise ValidationFailedError(
            "An import needs at least a name or a website column",
            details={"mapped": sorted(mapped_fields)},
        )
    return clean


def validate_mapping_for_job(
    job: ImportJob, mapping: Mapping[str, str], *, settings: Settings | None = None
) -> dict[str, str]:
    """Check a proposed mapping against the uploaded file, before the run starts.

    A mapping that names a column the file does not have, or a field the
    importer does not know, is refused here rather than inside the background
    run. Queuing work that is certain to fail would report the import as
    started when nothing can be imported from it.
    """
    active = settings or get_settings()
    if not job.storage_key:
        raise NotFoundError("This import's file is no longer available")
    try:
        data = get_storage(active).read(job.storage_key)
    except StorageError as exc:
        raise NotFoundError("This import's file is no longer available") from exc
    header = read_header(data, job.file_format)
    if not header:
        raise ValidationFailedError("That file has no header row")
    return validate_mapping(mapping, header)


@dataclass
class RowPayload:
    """One file row, normalised into values a business record can hold."""

    name: str | None = None
    website_url: str | None = None
    normalized_domain: str | None = None
    phone: str | None = None
    normalized_phone: str | None = None
    email: str | None = None
    normalized_email: str | None = None
    primary_category: str | None = None
    description: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    rating: float | None = None
    review_count: int | None = None
    problems: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """A row is usable when it can be told apart from nothing else.

        Same rule the discovery pipeline applies: a record with neither a name
        nor a domain cannot be identified later.
        """
        return bool(self.name or self.normalized_domain)

    @property
    def identity_keys(self) -> tuple[str, ...]:
        return tuple(
            key
            for key in (self.normalized_domain, self.normalized_phone)
            if key
        )


def _parse_float(value: str, label: str, problems: list[str]) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        problems.append(f"{label} '{value}' is not a number")
        return None


def normalize_row(raw: Mapping[str, str], region: str) -> RowPayload:
    """Turn one file row into the values a business record can hold.

    A value that cannot be read is dropped with a reason, not stored as it was
    typed. A phone number that is not a phone number is not a phone number.
    """
    problems: list[str] = []
    payload = RowPayload(problems=problems)

    payload.name = sanitize_text(raw.get("name"), max_length=255)

    website_raw = (raw.get("website") or "").strip()
    if website_raw:
        domain = normalize_domain(website_raw)
        if domain:
            payload.normalized_domain = domain
            payload.website_url = (
                website_raw if website_raw.lower().startswith(("http://", "https://")) else f"https://{domain}"
            )
        else:
            problems.append(f"website '{website_raw}' is not a usable domain")

    phone_raw = (raw.get("phone") or "").strip()
    if phone_raw:
        phone = normalize_phone(phone_raw, region)
        if phone:
            payload.normalized_phone = phone
            payload.phone = phone_raw
        else:
            problems.append(f"phone '{phone_raw}' is not a valid number")

    email_raw = (raw.get("email") or "").strip()
    if email_raw:
        email = normalize_email(email_raw)
        if email:
            payload.normalized_email = email
            payload.email = email_raw
        else:
            problems.append(f"email '{email_raw}' is not a valid address")

    payload.primary_category = sanitize_text(raw.get("category"), max_length=150)
    payload.description = sanitize_text(raw.get("description"), max_length=4000)
    payload.address = sanitize_text(raw.get("address"), max_length=2000)
    payload.city = sanitize_text(raw.get("city"), max_length=150)
    payload.state = sanitize_text(raw.get("state"), max_length=100)
    payload.country = sanitize_text(raw.get("country"), max_length=100)
    payload.postal_code = sanitize_text(raw.get("postal_code"), max_length=30)

    latitude_raw = (raw.get("latitude") or "").strip()
    if latitude_raw:
        payload.latitude = _parse_float(latitude_raw, "latitude", problems)
    longitude_raw = (raw.get("longitude") or "").strip()
    if longitude_raw:
        payload.longitude = _parse_float(longitude_raw, "longitude", problems)

    rating_raw = (raw.get("rating") or "").strip()
    if rating_raw:
        rating = _parse_float(rating_raw, "rating", problems)
        if rating is not None:
            if 0 <= rating <= 5:
                payload.rating = rating
            else:
                problems.append(f"rating '{rating_raw}' is outside 0-5")
    reviews_raw = (raw.get("review_count") or "").strip()
    if reviews_raw:
        try:
            reviews = int(float(reviews_raw))
        except (TypeError, ValueError):
            problems.append(f"review_count '{reviews_raw}' is not a number")
        else:
            if reviews >= 0:
                payload.review_count = reviews
            else:
                problems.append(f"review_count '{reviews_raw}' is negative")

    return payload


async def find_existing(
    session: AsyncSession, owner_user_id: uuid.UUID, payload: RowPayload
) -> Business | None:
    """Match a row against records the account already has.

    Domain first, then phone. Deliberately not name: two different cafes called
    "Spark Coffee" are a real thing, and merging them on a name would destroy
    two leads and their evidence.
    """
    if payload.normalized_domain:
        found = await session.scalar(
            select(Business).where(
                Business.owner_user_id == owner_user_id,
                Business.normalized_domain == payload.normalized_domain,
                Business.deleted_at.is_(None),
            )
        )
        if found is not None:
            return found
    if payload.normalized_phone:
        return await session.scalar(
            select(Business).where(
                Business.owner_user_id == owner_user_id,
                Business.normalized_phone == payload.normalized_phone,
                Business.deleted_at.is_(None),
            )
        )
    return None


_FILL_IF_MISSING = (
    "name",
    "normalized_name",
    "description",
    "primary_category",
    "website_url",
    "normalized_domain",
    "phone",
    "normalized_phone",
    "email",
    "normalized_email",
    "city",
    "state",
    "country",
    "postal_code",
    "address",
    "latitude",
    "longitude",
    "rating",
    "review_count",
)


def _values_for(payload: RowPayload) -> dict[str, Any]:
    return {
        "name": payload.name,
        "normalized_name": normalize_name(payload.name) if payload.name else None,
        "description": payload.description,
        "primary_category": payload.primary_category,
        "website_url": payload.website_url,
        "normalized_domain": payload.normalized_domain,
        "phone": payload.phone,
        "normalized_phone": payload.normalized_phone,
        "email": payload.email,
        "normalized_email": payload.normalized_email,
        "city": payload.city,
        "state": payload.state,
        "country": payload.country,
        "postal_code": payload.postal_code,
        "address": payload.address,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "rating": payload.rating,
        "review_count": payload.review_count,
    }


def _merge_into(existing: Business, values: dict[str, Any]) -> None:
    """Fill the gaps in an existing record. Never overwrite what is already there.

    An import is a partial view of a business. Overwriting a field the account
    already holds would destroy work that was done to a higher standard.
    """
    for field_name in _FILL_IF_MISSING:
        value = values.get(field_name)
        if value is not None and getattr(existing, field_name) in (None, ""):
            setattr(existing, field_name, value)


async def _write_contacts(
    session: AsyncSession, business: Business, payload: RowPayload, source_id: uuid.UUID
) -> None:
    """Store imported contacts as unverified.

    Extraction is not verification (PRD section 7.3). A file the operator
    uploaded says nothing about whether the address still works.
    """
    wanted = {
        "email": (payload.email, payload.normalized_email),
        "phone": (payload.phone, payload.normalized_phone),
    }
    for contact_type, (raw_value, normalised) in wanted.items():
        if not normalised:
            continue
        already = await session.scalar(
            select(BusinessContact).where(
                BusinessContact.business_id == business.id,
                BusinessContact.contact_type == contact_type,
                BusinessContact.normalized_email == normalised
                if contact_type == "email"
                else BusinessContact.normalized_phone == normalised,
            )
        )
        if already is not None:
            continue
        session.add(
            BusinessContact(
                business_id=business.id,
                email=raw_value if contact_type == "email" else None,
                normalized_email=normalised if contact_type == "email" else None,
                phone=raw_value if contact_type == "phone" else None,
                normalized_phone=normalised if contact_type == "phone" else None,
                contact_type=contact_type,
                verification_status="unverified",
                source_id=source_id,
                confidence=0,
            )
        )


async def _write_provenance(
    session: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    source_id: uuid.UUID,
    business_id: uuid.UUID,
    job_id: uuid.UUID,
    row_number: int,
    file_name: str,
    raw_row: Mapping[str, str],
    fingerprint: str,
    collected_at: datetime,
    retention_days: int,
) -> None:
    """One raw row per imported record, linked back to it."""
    record = SourceRecord(
        source_id=source_id,
        owner_user_id=owner_user_id,
        module="import",
        external_id=f"{job_id}:{row_number}",
        source_url=file_name,
        raw_data=bound_payload({"imported": dict(raw_row)}),
        record_hash=fingerprint,
        processing_status="processed",
        collected_at=collected_at,
        expires_at=collected_at + timedelta(days=retention_days),
    )
    session.add(record)
    await session.flush()
    session.add(
        SourceRecordLink(
            source_record_id=record.id,
            entity_type="business",
            entity_id=business_id,
            linked_at=collected_at,
        )
    )


async def execute_import(job_id: uuid.UUID, *, settings: Settings | None = None) -> str:
    """Read the file, write the records, and report exactly what happened."""
    active = settings or get_settings()

    async with session_scope() as session:
        job = await session.get(ImportJob, job_id)
        if job is None:
            logger.warning("import_job_missing", job_id=str(job_id))
            return "missing"
        if job.status != "queued":
            return job.status
        job.status = "running"
        await session.commit()

    counts = ImportCounts()
    try:
        async with session_scope() as session:
            job = await session.get(ImportJob, job_id)
            if job is None:
                return "missing"

            storage = get_storage(active)
            if not storage.exists(job.storage_key):
                raise FileNotFoundError("The uploaded file is no longer available")
            data = storage.read(job.storage_key)
            header, records = read_tabular(data, job.file_format)

            if len(records) > active.max_import_rows:
                raise ValueError(
                    f"The file has {len(records)} rows; the limit is {active.max_import_rows}"
                )

            mapping, duplicate_strategy = read_mapping_config(job.mapping_config)
            mapping = validate_mapping(mapping, header)
            if duplicate_strategy not in DUPLICATE_STRATEGIES:
                raise ValueError(f"Unknown duplicate strategy '{duplicate_strategy}'")

            counts.total = len(records)
            source_id = await ensure_import_source(session)
            seen_keys: set[str] = set()

            for index, record in enumerate(records, start=2):
                row_number = index
                # Two views of the same row: the values keyed by the field they
                # were mapped to, which is what the record is built from, and the
                # values keyed by the column they came from, which is what
                # provenance has to preserve.
                by_field = {
                    field_name: (record.get(column) or "").strip()
                    for column, field_name in mapping.items()
                }
                raw = {
                    column: (record.get(column) or "").strip() for column in mapping
                }
                payload = normalize_row(by_field, active.default_region)
                if not payload.usable:
                    counts.fail(
                        row_number,
                        "; ".join(payload.problems)
                        or "the row has neither a name nor a website",
                    )
                    continue
                if payload.problems:
                    # A partly readable row still imports: the unreadable field
                    # is dropped and the reason is reported.
                    counts.warn(row_number, "; ".join(payload.problems))

                existing = await find_existing(session, job.owner_user_id, payload)
                repeated_in_file = existing is None and any(
                    key in seen_keys for key in payload.identity_keys
                )

                if existing is not None or repeated_in_file:
                    if duplicate_strategy == "skip":
                        counts.duplicates_skipped += 1
                        continue
                    if duplicate_strategy == "merge":
                        if existing is None:
                            counts.duplicates_skipped += 1
                            continue
                        values = _values_for(payload)
                        _merge_into(existing, values)
                        await session.flush()
                        await _write_contacts(session, existing, payload, source_id)
                        await _write_provenance(
                            session,
                            owner_user_id=job.owner_user_id,
                            source_id=source_id,
                            business_id=existing.id,
                            job_id=job.id,
                            row_number=row_number,
                            file_name=job.file_name,
                            raw_row=raw,
                            fingerprint=canonical_hash(
                                payload.normalized_domain, payload.normalized_phone
                            ),
                            collected_at=utcnow(),
                            retention_days=active.retention_raw_days,
                        )
                        counts.merged += 1
                        continue

                values = _values_for(payload)
                business = Business(
                    owner_user_id=job.owner_user_id,
                    name=values["name"] or values["normalized_domain"] or "Unnamed business",
                    normalized_name=values["normalized_name"],
                    description=values["description"],
                    primary_category=values["primary_category"],
                    website_url=values["website_url"],
                    normalized_domain=values["normalized_domain"],
                    website_status="unknown",
                    phone=values["phone"],
                    normalized_phone=values["normalized_phone"],
                    email=values["email"],
                    normalized_email=values["normalized_email"],
                    rating=values["rating"],
                    review_count=values["review_count"],
                    country=values["country"],
                    state=values["state"],
                    city=values["city"],
                    postal_code=values["postal_code"],
                    address=values["address"],
                    latitude=values["latitude"],
                    longitude=values["longitude"],
                    lifecycle_status="active",
                    enrichment={"signals": {}, "field_provenance": {}},
                    first_discovered_at=utcnow(),
                )
                session.add(business)
                await session.flush()
                await _write_contacts(session, business, payload, source_id)
                await _write_provenance(
                    session,
                    owner_user_id=job.owner_user_id,
                    source_id=source_id,
                    business_id=business.id,
                    job_id=job.id,
                    row_number=row_number,
                    file_name=job.file_name,
                    raw_row=raw,
                    fingerprint=canonical_hash(payload.normalized_domain, payload.normalized_phone),
                    collected_at=utcnow(),
                    retention_days=active.retention_raw_days,
                )
                for key in payload.identity_keys:
                    seen_keys.add(key)
                counts.created += 1

            job.status = "completed"
            job.total_rows = counts.total
            job.processed_rows = counts.created + counts.merged
            job.failed_rows = counts.failed
            job.error_details = counts.as_dict()
            job.completed_at = utcnow()
            await session.commit()
        logger.info(
            "import_job_completed",
            job_id=str(job_id),
            created=counts.created,
            merged=counts.merged,
            failed=counts.failed,
        )
        return "completed"
    except Exception as exc:  # noqa: BLE001 - a crashed import must be reported
        async with session_scope() as session:
            job = await session.get(ImportJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error_details = {
                    **(job.error_details or {}),
                    "reason": f"{type(exc).__name__}: {exc}"[:500],
                }
                job.completed_at = utcnow()
                await session.commit()
        logger.error("import_job_failed", job_id=str(job_id), error_type=type(exc).__name__)
        return "failed"


@register_task(IMPORT_TASK_NAME)
async def run_import_task(*, job_id: str) -> str:
    """Inline/synchronous entry point under the same name the worker uses."""
    try:
        return await execute_import(uuid.UUID(str(job_id)))
    except ValueError:
        logger.warning("import_job_id_invalid", job_id=job_id)
        return "missing"


async def dispatch_import(
    session: AsyncSession, job: ImportJob, background_tasks: BackgroundTasks
) -> str:
    """Hand the import to the configured runner and report how it was handed.

    Inline execution is scheduled as a background task, after the response, so
    the job row is committed and visible before anything tries to read it.
    """
    dispatcher = get_dispatcher()
    if isinstance(dispatcher, SynchronousDispatcher):
        await session.commit()
        background_tasks.add_task(run_import_task, job_id=str(job.id))
        return "inline"

    try:
        dispatcher.submit(IMPORT_TASK_NAME, {"job_id": str(job.id)})
    except Exception as exc:  # noqa: BLE001 - no broker is a reportable state
        job.status = "blocked"
        job.error_details = {
            "reason": f"No worker could accept this import ({type(exc).__name__}). "
            "Set SPARKX_RUN_JOBS_SYNCHRONOUSLY=true to run jobs inline in development."
        }
        await session.commit()
        return "blocked"
    return "queued"


async def list_import_jobs(
    session: AsyncSession, owner_user_id: uuid.UUID, *, limit: int = 50
) -> list[ImportJob]:
    rows = await session.scalars(
        select(ImportJob)
        .where(ImportJob.owner_user_id == owner_user_id)
        .order_by(ImportJob.created_at.desc())
        .limit(limit)
    )
    return list(rows)


async def get_import_job(
    session: AsyncSession, owner_user_id: uuid.UUID, job_id: uuid.UUID
) -> ImportJob:
    job = await session.scalar(
        select(ImportJob).where(
            ImportJob.id == job_id, ImportJob.owner_user_id == owner_user_id
        )
    )
    if job is None:
        raise NotFoundError("Import job not found")
    return job


def import_storage_key(owner_user_id: uuid.UUID, job_id: uuid.UUID, extension: str) -> str:
    """Where an uploaded file lives. Owner-scoped, like every other key."""
    return f"imports/{owner_user_id}/{job_id}.{extension}"


def delete_import_file(job: ImportJob, *, settings: Settings | None = None) -> None:
    """Remove the uploaded file. The job row keeps the history."""
    active = settings or get_settings()
    storage = get_storage(active)
    try:
        storage.delete(job.storage_key)
    except Exception as exc:  # noqa: BLE001 - a missing file is not a failure
        logger.warning(
            "import_file_delete_failed", job_id=str(job.id), error_type=type(exc).__name__
        )


__all__ = [
    "DUPLICATE_STRATEGIES",
    "IMPORT_FIELDS",
    "IMPORT_SOURCE_SLUG",
    "IMPORT_TASK_NAME",
    "ImportCounts",
    "delete_import_file",
    "ensure_import_source",
    "execute_import",
    "find_existing",
    "get_import_job",
    "import_storage_key",
    "list_import_jobs",
    "normalize_row",
    "read_mapping_config",
    "run_import_task",
    "suggest_mapping",
    "validate_mapping",
]
