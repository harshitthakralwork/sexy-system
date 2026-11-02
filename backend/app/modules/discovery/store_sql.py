from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.businesses.models import Business, BusinessContact
from app.modules.discovery.models import SourceRecord, SourceRecordLink
from app.modules.discovery.pipeline import NormalizedBusiness
from app.modules.sources.models import Source

# A raw record is evidence, not an archive of the web. One pathological response
# must not be able to grow the database without limit — the remaining risk the
# security review flagged against `source_records.raw_data`.
MAX_RAW_PAYLOAD_BYTES = 64_000


def bound_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Keep the payload, but never an unbounded one."""
    try:
        encoded = json.dumps(raw, default=str)
    except (TypeError, ValueError):
        return {"_unserializable": True}
    if len(encoded) <= MAX_RAW_PAYLOAD_BYTES:
        return raw
    return {
        "_truncated": True,
        "_original_bytes": len(encoded),
        "preview": encoded[:MAX_RAW_PAYLOAD_BYTES],
    }


class SqlBusinessStore:
    """Persists normalised businesses and their provenance to PostgreSQL.

    Ownership is fixed at construction rather than passed per write. A store that
    took an owner id on each call is one forgotten argument away from filing
    another user's records, and the database would not complain.
    """

    def __init__(self, session: AsyncSession, *, owner_user_id: uuid.UUID) -> None:
        self._session = session
        self._owner = owner_user_id
        self._source_ids: dict[str, uuid.UUID | None] = {}
        self.created = 0
        self.merged = 0
        self.skipped_provenance = 0

    async def _source_id(self, slug: str) -> uuid.UUID | None:
        if slug not in self._source_ids:
            self._source_ids[slug] = await self._session.scalar(
                select(Source.id).where(Source.slug == slug)
            )
        return self._source_ids[slug]

    async def upsert(self, business: NormalizedBusiness) -> bool:
        """Insert a business, or merge provenance into the one we already have.

        True when a row was created. An existing record is never overwritten
        wholesale: gaps are filled, existing values survive, and every source
        that saw the business keeps its own attribution row.
        """
        existing = await self._find_existing(business)

        if existing is None:
            model = self._to_model(business)
            await self._session.flush()
            await self._write_contacts(model, business)
            await self._write_provenance(model.id, business)
            self.created += 1
            return True

        self._merge_into(existing, business)
        await self._session.flush()
        await self._write_contacts(existing, business)
        await self._write_provenance(existing.id, business)
        self.merged += 1
        return False

    async def _find_existing(self, business: NormalizedBusiness) -> Business | None:
        """Match on domain first, then phone — the two strongest identifiers.

        Deliberately *not* name matching. Two different cafes called "Spark
        Coffee" are a real thing, and merging them on a name would destroy two
        leads and their evidence.
        """
        if business.normalized_domain:
            found = await self._session.scalar(
                select(Business).where(
                    Business.owner_user_id == self._owner,
                    Business.normalized_domain == business.normalized_domain,
                    Business.deleted_at.is_(None),
                )
            )
            if found is not None:
                return found
        if business.normalized_phone:
            return await self._session.scalar(
                select(Business).where(
                    Business.owner_user_id == self._owner,
                    Business.normalized_phone == business.normalized_phone,
                    Business.deleted_at.is_(None),
                )
            )
        return None

    def _to_model(self, business: NormalizedBusiness) -> Business:
        model = Business(
            owner_user_id=self._owner,
            name=business.name or business.normalized_domain or "Unnamed business",
            normalized_name=business.normalized_name,
            description=business.description,
            primary_category=business.primary_category,
            website_url=business.website_url,
            normalized_domain=business.normalized_domain,
            website_status=business.website_status,
            phone=business.phone,
            normalized_phone=business.normalized_phone,
            email=business.email,
            normalized_email=business.normalized_email,
            country=business.country,
            state=business.state,
            city=business.city,
            address=business.address,
            latitude=business.latitude,
            longitude=business.longitude,
            lifecycle_status="active",
            enrichment=self._enrichment_payload(business),
            first_discovered_at=self._first_seen(business),
        )
        self._session.add(model)
        return model

    @staticmethod
    def _first_seen(business: NormalizedBusiness) -> datetime:
        stamps = [attribution.retrieved_at for attribution in business.attributions]
        return min(stamps) if stamps else datetime.now(UTC)

    @staticmethod
    def _enrichment_payload(business: NormalizedBusiness) -> dict[str, Any]:
        return {
            "signals": {key: value for key, value in business.signals.items() if value is not None},
            "field_provenance": dict(business.field_provenance),
        }

    def _merge_into(self, existing: Business, business: NormalizedBusiness) -> None:
        fill_if_missing: dict[str, Any] = {
            "name": business.name,
            "normalized_name": business.normalized_name,
            "description": business.description,
            "primary_category": business.primary_category,
            "website_url": business.website_url,
            "normalized_domain": business.normalized_domain,
            "phone": business.phone,
            "normalized_phone": business.normalized_phone,
            "email": business.email,
            "normalized_email": business.normalized_email,
            "city": business.city,
            "state": business.state,
            "country": business.country,
            "address": business.address,
            "latitude": business.latitude,
            "longitude": business.longitude,
        }
        for field, value in fill_if_missing.items():
            if value is not None and getattr(existing, field) in (None, ""):
                setattr(existing, field, value)

        # A website nobody fetched stays unknown regardless of what a later
        # source implies. Only a real check may change it.
        if existing.website_status == "unknown" and business.website_status != "unknown":
            existing.website_status = business.website_status

        signals = dict(existing.enrichment or {}).get("signals", {})
        for key, value in business.signals.items():
            if value is not None and key not in signals:
                signals[key] = value
        provenance = dict(existing.enrichment or {}).get("field_provenance", {})
        provenance.update(business.field_provenance)
        existing.enrichment = {"signals": signals, "field_provenance": provenance}
        stamps = [attribution.retrieved_at for attribution in business.attributions]
        if stamps and existing.first_discovered_at:
            existing.first_discovered_at = min(existing.first_discovered_at, min(stamps))

    async def _write_contacts(self, model: Business, business: NormalizedBusiness) -> None:
        """Store extracted contacts as unverified until something checks them.

        Extraction is not verification (PRD §7.3). A scraped address that lands
        as "verified" is how a lead list becomes a liability.
        """
        wanted = {
            "email": (business.email, business.normalized_email),
            "phone": (business.phone, business.normalized_phone),
        }
        for contact_type, (raw_value, normalised) in wanted.items():
            if not normalised:
                continue
            already = await self._session.scalar(
                select(BusinessContact).where(
                    BusinessContact.business_id == model.id,
                    BusinessContact.contact_type == contact_type,
                    BusinessContact.normalized_email == normalised
                    if contact_type == "email"
                    else BusinessContact.normalized_phone == normalised,
                )
            )
            if already is not None:
                continue
            source = business.attributions[0] if business.attributions else None
            self._session.add(
                BusinessContact(
                    business_id=model.id,
                    email=raw_value if contact_type == "email" else None,
                    normalized_email=normalised if contact_type == "email" else None,
                    phone=raw_value if contact_type == "phone" else None,
                    normalized_phone=normalised if contact_type == "phone" else None,
                    contact_type=contact_type,
                    verification_status="unverified",
                    source_url=source.source_url if source else None,
                    confidence=0,
                )
            )

    async def _write_provenance(self, business_id: uuid.UUID, business: NormalizedBusiness) -> None:
        """One raw row per source that produced this entity, linked back to it."""
        settings = get_settings()
        for attribution in business.attributions:
            source_id = await self._source_id(attribution.source_slug)
            if source_id is None:
                # An unregistered source must not be faked with a surrogate id:
                # the column references `sources`, and inventing a value there
                # either violates the key or silently points at the wrong row.
                # Counted so the job report can say provenance was incomplete.
                self.skipped_provenance += 1
                continue
            collected_at = attribution.retrieved_at
            record = SourceRecord(
                source_id=source_id,
                job_id=None,
                owner_user_id=self._owner,
                module="leads",
                external_id=attribution.external_id,
                source_url=attribution.source_url,
                raw_data=bound_payload(
                    {
                        "name": business.name,
                        "domain": business.normalized_domain,
                        "attribution_note": attribution.note,
                        "source_slug": attribution.source_slug,
                    }
                ),
                record_hash=business.fingerprint,
                processing_status="processed",
                collected_at=collected_at,
                expires_at=collected_at + timedelta(days=settings.retention_raw_days),
            )
            self._session.add(record)
            await self._session.flush()
            self._session.add(
                SourceRecordLink(
                    source_record_id=record.id,
                    entity_type="business",
                    entity_id=business_id,
                    linked_at=collected_at,
                )
            )

    async def all(self) -> list[NormalizedBusiness]:
        """Read the owner's businesses back as pipeline objects.

        Used by tests and by re-scoring passes. Ownership is in the query, so
        there is no version of this call that returns someone else's rows.
        """
        rows = (
            await self._session.scalars(
                select(Business)
                .where(Business.owner_user_id == self._owner, Business.deleted_at.is_(None))
                .order_by(Business.created_at)
            )
        ).all()
        return [self._from_model(row) for row in rows]

    @staticmethod
    def _from_model(row: Business) -> NormalizedBusiness:
        enrichment = dict(row.enrichment or {})
        return NormalizedBusiness(
            name=row.name,
            normalized_name=row.normalized_name,
            website_url=row.website_url,
            normalized_domain=row.normalized_domain,
            phone=row.phone,
            normalized_phone=row.normalized_phone,
            email=row.email,
            normalized_email=row.normalized_email,
            primary_category=row.primary_category,
            country=row.country,
            state=row.state,
            city=row.city,
            address=row.address,
            latitude=float(row.latitude) if row.latitude is not None else None,
            longitude=float(row.longitude) if row.longitude is not None else None,
            description=row.description,
            website_status=row.website_status,
            signals=dict(enrichment.get("signals", {})),
            field_provenance=dict(enrichment.get("field_provenance", {})),
            fingerprint=row.id.hex,
        )
