from __future__ import annotations

import math
import re

from app.modules.businesses.models import Business
from app.modules.discovery.provenance import (
    SOURCE_TYPE_LABELS,
    FieldEvidence,
    determine_website_status,
    is_official_website,
    sanitize_address,
    should_update_field,
)
from app.shared.normalization import (
    normalize_domain,
    normalize_email,
    normalize_phone,
)


def clean_name_key(name: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", name.casefold())
    return re.sub(r"\s+", " ", cleaned).strip()


def coordinates_close(
    lat1: float | None,
    lon1: float | None,
    lat2: float | None,
    lon2: float | None,
    max_meters: float = 200.0,
) -> bool:
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return False
    # Simple equirectangular approximation for close distances
    dlat = (lat2 - lat1) * 111_000
    dlon = (lon2 - lon1) * 111_000 * math.cos(math.radians(lat1))
    dist = math.sqrt(dlat * dlat + dlon * dlon)
    return dist <= max_meters


def matches_existing_business(
    candidate_name: str,
    candidate_phone: str | None,
    candidate_website: str | None,
    candidate_address: str | None,
    candidate_lat: float | None,
    candidate_lon: float | None,
    existing: Business,
) -> bool:
    """Matches ONLY if normalized name matches AND at least one strong identifier
    (phone, domain, full address, or coordinates) matches.
    Never merges on name similarity alone.
    """
    cand_name_norm = clean_name_key(candidate_name)
    exist_name_norm = clean_name_key(existing.name)
    if not cand_name_norm or not exist_name_norm or cand_name_norm != exist_name_norm:
        return False

    # Check strong secondary identifiers
    # 1. Phone match
    if candidate_phone and existing.normalized_phone:
        norm_phone = normalize_phone(candidate_phone)
        if norm_phone and norm_phone == existing.normalized_phone:
            return True

    # 2. Domain match
    if candidate_website and existing.normalized_domain:
        norm_dom = normalize_domain(candidate_website)
        if norm_dom and norm_dom == existing.normalized_domain:
            return True

    # 3. Coordinates match within 200m
    has_coords = (
        candidate_lat is not None
        and candidate_lon is not None
        and existing.latitude is not None
        and existing.longitude is not None
    )
    if has_coords and coordinates_close(
        float(candidate_lat),
        float(candidate_lon),
        float(existing.latitude),
        float(existing.longitude),
    ):
        return True

    # 4. Detailed address match (at least 10 chars, not just city)
    if candidate_address and existing.address:
        cand_addr = clean_name_key(candidate_address)
        exist_addr = clean_name_key(existing.address)
        if (
            len(cand_addr) >= 10
            and len(exist_addr) >= 10
            and (cand_addr in exist_addr or exist_addr in cand_addr)
        ):
            return True

    return False


def merge_candidate_into_business(
    business: Business,
    *,
    candidate_name: str,
    candidate_phone: str | None,
    candidate_email: str | None,
    candidate_website: str | None,
    candidate_address: str | None,
    candidate_city: str,
    candidate_rating: float | None,
    candidate_review_count: int | None,
    candidate_lat: float | None,
    candidate_lon: float | None,
    source_url: str,
    source_type: str,
    field_evidence_map: dict[str, FieldEvidence],
    is_new: bool,
) -> bool:
    """Merges field data and field-level provenance safely into a Business model.
    Attaches all source listing URLs. Weaker confidence values never overwrite stronger ones.
    """
    enrichment = dict(business.enrichment or {})
    listing_urls = list(enrichment.get("source_listing_urls", []))
    field_provenance = dict(enrichment.get("field_provenance", {}))

    # 1. Track Source Listing URLs
    label = SOURCE_TYPE_LABELS.get(source_type, "Web source")
    new_listing = {"kind": source_type, "label": label, "url": source_url}
    if not any(item.get("url") == source_url for item in listing_urls):
        listing_urls.append(new_listing)

    # Specific convenience links
    if source_type == "justdial":
        enrichment["justdial_url"] = source_url
    elif source_type == "google_maps":
        enrichment["google_maps_url"] = source_url

    # 2. Merge Field Values and Provenance
    # Phone
    if candidate_phone and "phone" in field_evidence_map:
        ev = field_evidence_map["phone"]
        if should_update_field(field_provenance.get("phone"), ev):
            business.phone = candidate_phone
            business.normalized_phone = normalize_phone(candidate_phone)
            field_provenance["phone"] = ev.to_dict()

    # Email
    if candidate_email and "email" in field_evidence_map:
        ev = field_evidence_map["email"]
        if should_update_field(field_provenance.get("email"), ev):
            business.email = candidate_email
            business.normalized_email = normalize_email(candidate_email)
            field_provenance["email"] = ev.to_dict()

    # Address (never use city text)
    clean_addr = sanitize_address(candidate_address, candidate_city)
    if clean_addr and "address" in field_evidence_map:
        ev = field_evidence_map["address"]
        if should_update_field(field_provenance.get("address"), ev):
            business.address = clean_addr
            field_provenance["address"] = ev.to_dict()

    # Website
    has_valid_website = bool(
        candidate_website
        and is_official_website(candidate_website)
        and "website" in field_evidence_map
    )
    if has_valid_website:
        ev = field_evidence_map["website"]
        if should_update_field(field_provenance.get("website"), ev):
            business.website_url = candidate_website
            business.normalized_domain = normalize_domain(candidate_website)
            business.website_status = "available"
            field_provenance["website"] = ev.to_dict()
    elif not business.website_url:
        business.website_status = determine_website_status(
            official_website_url=business.website_url,
            sources_checked=True,
        )

    # Rating & Reviews
    if candidate_rating is not None and "rating" in field_evidence_map:
        ev = field_evidence_map["rating"]
        if should_update_field(field_provenance.get("rating"), ev):
            business.rating = candidate_rating
            field_provenance["rating"] = ev.to_dict()

    if candidate_review_count is not None and "review_count" in field_evidence_map:
        ev = field_evidence_map["review_count"]
        if should_update_field(field_provenance.get("review_count"), ev):
            business.review_count = candidate_review_count
            field_provenance["review_count"] = ev.to_dict()

    # Coordinates
    if business.latitude is None and candidate_lat is not None:
        business.latitude = candidate_lat
    if business.longitude is None and candidate_lon is not None:
        business.longitude = candidate_lon

    # Social links
    if "social_links" in field_evidence_map:
        ev = field_evidence_map["social_links"]
        if should_update_field(field_provenance.get("social_links"), ev):
            enrichment["social_urls"] = ev.value
            field_provenance["social_links"] = ev.to_dict()

    # Update completeness status
    has_contact = bool(business.phone or business.email)
    has_website_state = business.website_status in ("available", "missing", "unknown")
    is_complete = bool(business.name and business.address and has_contact and has_website_state)

    enrichment["source_listing_urls"] = listing_urls
    enrichment["field_provenance"] = field_provenance
    enrichment["completeness_status"] = "complete" if is_complete else "partial"
    business.enrichment = enrichment

    return True
