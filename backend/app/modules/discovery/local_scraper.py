from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import session_scope
from app.modules.businesses.models import Business
from app.modules.discovery import job_service
from app.modules.discovery.models import Search
from app.modules.discovery.provenance import is_official_website
from app.modules.discovery.public_fetch import fetch_public_page
from app.shared.normalization import normalize_domain, normalize_email, normalize_phone
from app.shared.url_safety import UnsafeUrlError

DIRECTORY_DOMAINS = {
    "google.com",
    "facebook.com",
    "instagram.com",
    "justdial.com",
    "linkedin.com",
    "mapquest.com",
    "tripadvisor.com",
    "yellowpages.com",
    "yelp.com",
}

SOURCE_LABELS = {
    "justdial": "Justdial",
    "google_maps": "Google Maps",
    "website": "Website",
    "directory": "Directory listing",
}

ProgressCallback = Callable[[str, int, int, int], Awaitable[bool]]


class LocalSearchCancelled(Exception):
    """Raised when the durable local-search job has been cancelled."""


@dataclass
class FetchedEvidence:
    result: Any
    checked_urls: list[str]
    field_urls: dict[str, str]


class LocalScrapeRequest(BaseModel):
    niche: str = Field(min_length=2, max_length=100)
    city: str = Field(min_length=2, max_length=150)


class LocalBusinessItem(BaseModel):
    id: str
    name: str
    phone: str | None = None
    email: str | None = None
    rating: float | None = None
    review_count: int | None = None
    address: str | None = None
    website_url: str | None = None
    website_status: str
    maps_url: str


class LocalScrapeResponse(BaseModel):
    niche: str
    city: str
    total_found: int
    stored_new: int
    items: list[LocalBusinessItem]


def _clean_name(raw: str) -> str:
    value = re.sub(r"\s*[-|:]\s*(Yelp|Yellow Pages|Facebook|Instagram).*$", "", raw, flags=re.I)
    return re.sub(r"^\d+[.)]\s*", "", value).strip(" \t\r\n\"'")[:255]


def _normalize_rating(value: Any) -> float | None:
    if value is None:
        return None
    try:
        val = float(value)
        if val > 10.0:
            val = (val / 100.0) * 5.0
        elif val > 5.0:
            val = (val / 10.0) * 5.0
        return max(0.0, min(5.0, round(val, 2)))
    except (ValueError, TypeError):
        return None


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def _source_kind(url: str) -> str:
    domain = _domain(url)
    if domain == "justdial.com" or domain.endswith(".justdial.com"):
        return "justdial"
    if domain == "google.com" or domain.endswith(".google.com"):
        return "google_maps"
    if any(domain == item or domain.endswith(f".{item}") for item in DIRECTORY_DOMAINS):
        return "directory"
    return "website"


def _is_official_website(url: str | None, source_kind: str) -> bool:
    return bool(source_kind == "website" and is_official_website(url))


def _select_official_website(
    *, source_url: str, source_kind: str, candidates: list[str]
) -> str | None:
    """Choose only an externally reported public business URL, never a listing URL."""
    if _is_official_website(source_url, source_kind):
        return source_url
    for candidate in candidates:
        if _source_kind(candidate) == "website" and is_official_website(candidate):
            return candidate
    return None


def _extract(content: str) -> tuple[str | None, str | None, float | None, int | None]:
    phone_match = re.search(r"(?:\+?\d[\d ()-]{7,}\d)", content)
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", content, re.I)
    rating_match = re.search(r"\b([0-5](?:\.\d)?)\s*(?:stars?|out of 5)\b", content, re.I)
    reviews_match = re.search(r"\b([\d,]+)\s+(?:Google\s+)?(?:reviews?|ratings?)\b", content, re.I)
    phone = phone_match.group(0).strip() if phone_match else None
    email = email_match.group(0) if email_match else None
    rating = float(rating_match.group(1)) if rating_match else None
    review_digits = re.sub(r"\D", "", reviews_match.group(1)) if reviews_match else ""
    reviews = int(review_digits) if review_digits else None
    return phone, email, rating, reviews


def _field_status(value: object, *, checked: bool, attempted: bool = False) -> str:
    """Describe what was observed without turning absent data into a claim."""
    if value not in (None, "", [], {}):
        return "available"
    if checked:
        return "not_found_after_public_page_check"
    return "inaccessible" if attempted else "not_verified"


def _completeness_status(
    *,
    name: str,
    address: str | None,
    phone: str | None,
    email: str | None,
    website_url: str | None,
    profile_url: str | None,
    field_status: dict[str, str],
) -> str:
    if any(status == "inaccessible" for status in field_status.values()):
        return "needs_review"
    # Contact can be either phone or email, but the source URL and a verified
    # website state are required before calling a record complete.
    if name and address and (phone or email) and profile_url and (
        website_url or field_status["website"] == "not_found_after_public_page_check"
    ):
        return "complete"
    return "partial"


async def _bing_html_results(query: str) -> list[dict[str, str]]:
    """Crawl Bing's public HTML results when the local metasearch returns nothing."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
        )
    }
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
        response = await client.get("https://www.bing.com/search", params={"q": query})
        response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    rows: list[dict[str, str]] = []
    for item in soup.select("li.b_algo"):
        link = item.select_one("h2 a")
        if link is None or not link.get("href"):
            continue
        snippet = item.select_one(".b_caption p")
        rows.append(
            {
                "title": link.get_text(" ", strip=True),
                "url": str(link["href"]),
                "content": snippet.get_text(" ", strip=True) if snippet else "",
            }
        )
    return rows


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _walk_strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _walk_strings(item)]
    return []


async def _google_maps_browser_results(niche: str, city: str) -> list[dict[str, Any]]:
    """Replay the public data request referenced by the Google Maps browser page."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
        )
    }
    query = f"{niche} {city}"
    maps_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}?hl=en"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=headers) as client:
        page = await client.get(maps_url)
        page.raise_for_status()
        soup = BeautifulSoup(page.text, "lxml")
        data_href = next(
            (
                str(link.get("href"))
                for link in soup.find_all("link")
                if str(link.get("href", "")).startswith("/search?tbm=map")
            ),
            None,
        )
        if not data_href:
            return []
        response = await client.get(f"https://www.google.com{data_href}")
        response.raise_for_status()
    body = response.text.split("\n", 1)
    if len(body) != 2:
        return []
    payload = json.loads(body[1])
    entries = payload[64] if isinstance(payload, list) and len(payload) > 64 else []
    rows: list[dict[str, Any]] = []
    for entry in entries if isinstance(entries, list) else []:
        record = entry[1] if isinstance(entry, list) and len(entry) > 1 else None
        if not isinstance(record, list) or len(record) < 90 or not isinstance(record[11], str):
            continue
        coordinates = record[9] if isinstance(record[9], list) else []
        rating_data = record[4] if isinstance(record[4], list) else []
        strings = _walk_strings(record)
        phone = next(
            (
                text
                for text in strings
                if re.fullmatch(r"\+?\d[\d ()-]{7,}\d", text.strip())
                and 8 <= len(re.sub(r"\D", "", text)) <= 15
            ),
            None,
        )
        email = next(
            (text for text in strings if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text)),
            None,
        )
        website = next(
            (
                text
                for text in strings
                if text.startswith("http")
                and not any(
                    host in text for host in ("google.com", "googleusercontent.com", "gstatic.com")
                )
            ),
            None,
        )
        rows.append(
            {
                "title": record[11],
                "url": website or maps_url,
                "content": record[18] if isinstance(record[18], str) else "",
                "phone": phone,
                "email": email,
                "rating": rating_data[7] if len(rating_data) > 8 else None,
                "review_count": rating_data[8] if len(rating_data) > 8 else None,
                "address": record[18] if isinstance(record[18], str) else None,
                "latitude": coordinates[2] if len(coordinates) > 3 else None,
                "longitude": coordinates[3] if len(coordinates) > 3 else None,
                "place_id": record[78] if isinstance(record[78], str) else None,
            }
        )
    return rows


async def scrape_google_local(
    session: AsyncSession,
    owner_user_id: uuid.UUID,
    niche: str,
    city: str,
    *,
    progress: ProgressCallback | None = None,
) -> LocalScrapeResponse:
    """Search public web indexes for local-business evidence without inventing fields."""
    clean_niche = niche.strip()
    clean_city = city.strip()
    settings = get_settings()

    async def report(stage: str, total: int, processed: int, failed: int = 0) -> None:
        if progress is not None and not await progress(stage, total, processed, failed):
            raise LocalSearchCancelled
    queries = (
        f'"{clean_niche}" "{clean_city}" business phone',
        f'site:google.com/maps "{clean_niche}" "{clean_city}"',
        f'site:justdial.com "{clean_niche}" "{clean_city}"',
        f'"{clean_niche}" "{clean_city}" reviews address',
    )
    await report("Starting public source check", 1, 0)
    try:
        raw_results: list[dict[str, Any]] = await _google_maps_browser_results(
            clean_niche, clean_city
        )
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        raw_results = []

    async def _fetch_searx_query(c: httpx.AsyncClient, q: str) -> list[dict[str, Any]]:
        try:
            resp = await c.get(
                f"{settings.searxng_base_url.rstrip('/')}/search",
                params={"q": q, "format": "json"},
            )
            if resp.status_code == 200:
                return resp.json().get("results", [])
        except (httpx.HTTPError, ValueError, TypeError):
            pass
        return []

    async with httpx.AsyncClient(timeout=8.0) as client:
        searx_batches = await asyncio.gather(
            *[_fetch_searx_query(client, q) for q in queries],
            return_exceptions=True,
        )
        for batch in searx_batches:
            if isinstance(batch, list):
                raw_results.extend(batch)

    if not raw_results:
        try:
            raw_results = await _bing_html_results(f"{clean_niche} in {clean_city}")
        except (httpx.HTTPError, ValueError, TypeError):
            raw_results = []

    await report("Public indexes checked", len(raw_results), 0)

    # Every returned listing gets a normal public-page check.  Directory pages
    # are evidence too: they can expose a listed phone, address, rating or the
    # business' official site. Google result pages are deliberately excluded
    # because they are not a stable public HTML source for this collector.
    enrichment_urls = {
        str(result.get("url"))
        for result in raw_results
        if str(result.get("url") or "").startswith(("http://", "https://"))
        and _source_kind(str(result.get("url"))) != "google_maps"
    }

    async def fetch_with_retry(url: str) -> tuple[str, FetchedEvidence | None]:
        checked_urls: list[str] = []
        for attempt in range(3):
            try:
                fetched = await asyncio.wait_for(fetch_public_page(url), timeout=20.0)
                checked_urls.append(url)
                if fetched.status == "ok":
                    field_urls = {
                        field: fetched.final_url
                        for field, value in {
                            "phone": fetched.phone,
                            "email": fetched.email,
                            "address": fetched.address,
                            "rating": fetched.rating,
                            "review_count": fetched.review_count,
                            "website": fetched.website_url or fetched.website_urls,
                            "social_links": fetched.social_urls,
                        }.items()
                        if value not in (None, "", [])
                    }
                    # A contact page is still a public page and often contains
                    # the number or email omitted on the listing overview.
                    if not (fetched.phone and fetched.email) and fetched.contact_urls:
                        source_host = _domain(fetched.final_url)
                        for contact_url in fetched.contact_urls[:2]:
                            if _domain(contact_url) != source_host:
                                continue
                            try:
                                contact = await asyncio.wait_for(
                                    fetch_public_page(contact_url), timeout=20.0
                                )
                            except (TimeoutError, httpx.HTTPError, UnsafeUrlError, ValueError):
                                continue
                            checked_urls.append(contact_url)
                            if contact.status != "ok":
                                continue
                            for field in ("phone", "email", "address"):
                                if getattr(fetched, field) is None and getattr(contact, field):
                                    setattr(fetched, field, getattr(contact, field))
                                    field_urls[field] = contact.final_url
                            if not fetched.social_urls and contact.social_urls:
                                fetched.social_urls = contact.social_urls
                                field_urls["social_links"] = contact.final_url
                    return url, FetchedEvidence(
                        result=fetched,
                        checked_urls=list(dict.fromkeys(checked_urls)),
                        field_urls=field_urls,
                    )
            except (TimeoutError, httpx.HTTPError, UnsafeUrlError, ValueError):
                pass
            if attempt < 2:
                await asyncio.sleep(1.0 * (attempt + 1))
        return url, None

    semaphore = asyncio.Semaphore(2)

    async def limited_fetch(url: str) -> tuple[str, FetchedEvidence | None]:
        async with semaphore:
            return await fetch_with_retry(url)

    fetch_tasks = [asyncio.create_task(limited_fetch(url)) for url in enrichment_urls]
    fetched_by_url: dict[str, FetchedEvidence | None] = {}
    for fetched_count, task in enumerate(asyncio.as_completed(fetch_tasks), start=1):
        url, evidence = await task
        fetched_by_url[url] = evidence
        await report("Checking public listing pages", len(fetch_tasks), fetched_count)

    seen: set[str] = set()
    output: list[LocalBusinessItem] = []
    stored_new = 0
    now = datetime.now(UTC)
    for result in raw_results:
        title = str(result.get("title") or "")
        content = str(result.get("content") or "")
        url = str(result.get("url") or "")
        evidence = f"{title} {content} {url}".casefold()
        niche_terms = [term for term in re.split(r"\W+", clean_niche.casefold()) if len(term) > 2]
        city_term = clean_city.split(",", 1)[0].strip().casefold()
        if not any(term in evidence for term in niche_terms) or city_term not in evidence:
            continue
        name = _clean_name(title)
        if len(name) < 2 or not url or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        source_kind = _source_kind(url)
        fetched_evidence = fetched_by_url.get(url)
        fetched = fetched_evidence.result if fetched_evidence else None
        page_attempted = url in enrichment_urls
        page_checked = fetched is not None
        if fetched is not None:
            content = " ".join(
                part for part in (content, fetched.description, fetched.address) if part
            )
            result["phone"] = result.get("phone") or fetched.phone
            result["email"] = result.get("email") or fetched.email
            result["address"] = result.get("address") or fetched.address
            result["rating"] = result.get("rating") or fetched.rating
            result["review_count"] = result.get("review_count") or fetched.review_count
            result["public_page_method"] = fetched.extraction_method

        website_candidates = []
        if fetched is not None:
            website_candidates = [
                candidate
                for candidate in [fetched.website_url, *fetched.website_urls]
                if isinstance(candidate, str)
            ]
        website_url = _select_official_website(
            source_url=url, source_kind=source_kind, candidates=website_candidates
        )
        extracted_phone, extracted_email, extracted_rating, extracted_reviews = _extract(content)
        phone = result.get("phone") or extracted_phone
        email = result.get("email") or extracted_email
        raw_rating = result.get("rating") if result.get("rating") is not None else extracted_rating
        rating = _normalize_rating(raw_rating)
        review_count = (
            result.get("review_count")
            if result.get("review_count") is not None
            else extracted_reviews
        )
        address = str(result["address"]) if result.get("address") else None
        latitude = result.get("latitude")
        longitude = result.get("longitude")
        place_id = result.get("place_id")
        google_profile_url = (
            "https://www.google.com/maps/search/?api=1&"
            f"query={urllib.parse.quote(name + ' ' + (address or clean_city))}&"
            f"query_place_id={urllib.parse.quote(str(place_id))}"
            if place_id
            else None
        )
        profile_url = google_profile_url or (
            url if source_kind in {"justdial", "directory", "google_maps"} else None
        )
        field_evidence = {
            field: {
                "source_url": (
                    fetched_evidence.field_urls.get(field) if fetched_evidence else None
                )
                or url,
                "source_kind": source_kind,
                "checked_at": now.isoformat(),
            }
            for field, value in {
                "phone": phone,
                "email": email,
                "address": address,
                "rating": rating,
                "review_count": review_count,
                "website": website_url,
                "social_links": fetched.social_urls if fetched else [],
            }.items()
            if value not in (None, "", [])
        }
        field_status = {
            "phone": _field_status(phone, checked=page_checked, attempted=page_attempted),
            "email": _field_status(email, checked=page_checked, attempted=page_attempted),
            "address": _field_status(address, checked=page_checked, attempted=page_attempted),
            "rating": _field_status(rating, checked=page_checked, attempted=page_attempted),
            "review_count": _field_status(
                review_count, checked=page_checked, attempted=page_attempted
            ),
            "website": _field_status(website_url, checked=page_checked, attempted=page_attempted),
            "social_links": _field_status(
                fetched.social_urls if fetched else [],
                checked=page_checked,
                attempted=page_attempted,
            ),
        }
        completeness = _completeness_status(
            name=name,
            address=address,
            phone=phone,
            email=email,
            website_url=website_url,
            profile_url=profile_url,
            field_status=field_status,
        )
        normalized_name = name.casefold()
        existing = await session.scalar(
            select(Business).where(
                Business.owner_user_id == owner_user_id,
                Business.normalized_name == normalized_name,
                Business.city.ilike(clean_city),
                Business.deleted_at.is_(None),
            )
        )
        if existing is None:
            existing = Business(
                owner_user_id=owner_user_id,
                name=name,
                normalized_name=normalized_name,
                primary_category=clean_niche,
                website_url=website_url,
                normalized_domain=normalize_domain(website_url) if website_url else None,
                website_status="available" if website_url else "unknown",
                phone=phone,
                normalized_phone=normalize_phone(phone) if phone else None,
                email=email,
                normalized_email=normalize_email(email) if email else None,
                rating=rating,
                review_count=review_count,
                city=clean_city,
                address=address,
                latitude=latitude,
                longitude=longitude,
                lifecycle_status="active",
                enrichment={
                    "google_maps_url": google_profile_url,
                    "google_place_id": place_id,
                    "public_page_url": url,
                    "public_page_method": result.get("public_page_method"),
                    "source_listing_urls": [
                        {"kind": source_kind, "label": SOURCE_LABELS[source_kind], "url": url}
                    ],
                    "justdial_url": url if source_kind == "justdial" else None,
                    "official_website_url": website_url,
                    "checked_urls": fetched_evidence.checked_urls if fetched_evidence else [],
                    "social_urls": fetched.social_urls if fetched else [],
                    "field_evidence": field_evidence,
                    "field_status": field_status,
                    "completeness_status": completeness,
                    "checked_at": now.isoformat(),
                },
                first_discovered_at=now,
            )
            session.add(existing)
            stored_new += 1
        else:
            if phone and not existing.phone:
                existing.phone = phone
                existing.normalized_phone = normalize_phone(phone)
            if email and not existing.email:
                existing.email = email
                existing.normalized_email = normalize_email(email)
            if rating is not None:
                existing.rating = rating
            if review_count is not None:
                existing.review_count = review_count
            if website_url and not existing.website_url:
                existing.website_url = website_url
                existing.normalized_domain = normalize_domain(website_url)
                existing.website_status = "available"
            if existing.address in (None, clean_city) and address:
                existing.address = address
            if existing.latitude is None and latitude is not None:
                existing.latitude = latitude
            if existing.longitude is None and longitude is not None:
                existing.longitude = longitude
            previous_enrichment = dict(existing.enrichment or {})
            listing_urls = previous_enrichment.get("source_listing_urls", [])
            if not isinstance(listing_urls, list):
                listing_urls = []
            source_listing = {"kind": source_kind, "label": SOURCE_LABELS[source_kind], "url": url}
            if source_listing not in listing_urls:
                listing_urls.append(source_listing)
            existing_field_status = {
                **field_status,
                "phone": _field_status(
                    existing.phone, checked=page_checked, attempted=page_attempted
                ),
                "email": _field_status(
                    existing.email, checked=page_checked, attempted=page_attempted
                ),
                "website": _field_status(
                    existing.website_url, checked=page_checked, attempted=page_attempted
                ),
            }
            previous_checked_urls = previous_enrichment.get("checked_urls", [])
            if not isinstance(previous_checked_urls, list):
                previous_checked_urls = []
            previous_field_evidence = previous_enrichment.get("field_evidence", {})
            if not isinstance(previous_field_evidence, dict):
                previous_field_evidence = {}
            existing.enrichment = {
                **(existing.enrichment or {}),
                "google_maps_url": google_profile_url or previous_enrichment.get("google_maps_url"),
                "google_place_id": place_id or previous_enrichment.get("google_place_id"),
                "justdial_url": (
                    url if source_kind == "justdial" else previous_enrichment.get("justdial_url")
                ),
                "source_listing_urls": listing_urls,
                "official_website_url": existing.website_url or website_url,
                "public_page_url": url,
                "public_page_method": (
                    result.get("public_page_method")
                    or previous_enrichment.get("public_page_method")
                ),
                "checked_urls": list(
                    dict.fromkeys(
                        [
                            *previous_checked_urls,
                            *(fetched_evidence.checked_urls if fetched_evidence else []),
                        ]
                    )
                )[:20],
                "field_evidence": {**previous_field_evidence, **field_evidence},
                "social_urls": (
                    fetched.social_urls
                    if fetched
                    else (existing.enrichment or {}).get("social_urls", [])
                ),
                "field_status": existing_field_status,
                "completeness_status": _completeness_status(
                    name=existing.name,
                    address=existing.address,
                    phone=existing.phone,
                    email=existing.email,
                    website_url=existing.website_url,
                    profile_url=(
                        profile_url
                        or previous_enrichment.get("justdial_url")
                        or previous_enrichment.get("google_maps_url")
                    ),
                    field_status=existing_field_status,
                ),
                "checked_at": now.isoformat(),
            }
        maps_query = urllib.parse.quote(f"{name} {clean_city}")
        output.append(
            LocalBusinessItem(
                id=str(existing.id),
                name=existing.name,
                phone=existing.phone,
                email=existing.email,
                rating=float(existing.rating) if existing.rating is not None else None,
                review_count=existing.review_count,
                address=existing.address,
                website_url=existing.website_url,
                website_status=existing.website_status,
                maps_url=(
                    url
                    if source_kind in {"justdial", "directory", "google_maps"}
                    else f"https://www.google.com/maps/search/?api=1&query={maps_query}"
                ),
            )
        )
        await report("Normalising and saving listings", len(raw_results), len(output))
        if len(output) >= 250:
            break

    await session.flush()
    return LocalScrapeResponse(
        niche=clean_niche,
        city=clean_city,
        total_found=len(output),
        stored_new=stored_new,
        items=output,
    )


async def run_local_search_job(*, job_id: str) -> str:
    """Run a local search outside the request that created it.

    Progress is committed between public-page checks, so a long evidence pass
    remains visible and cancellation is observed before the next listing.
    """
    try:
        parsed_job_id = uuid.UUID(job_id)
    except ValueError:
        return "failed"

    async with session_scope() as session:
        job = await job_service.claim_job(session, parsed_job_id)
        if job is None:
            return "ignored"
        search = await session.get(Search, job.search_id) if job.search_id else None
        config = dict(search.query_config) if search is not None else {}
        niche = str(config.get("niche") or "").strip()
        city = str(config.get("city") or "").strip()
        if not niche or not city:
            job.status = "failed"
            job.error_details = {"reason": "Local search job is missing its niche or city."}
            job_service.mark_finished(job)
            await job_service.add_log(
                session, job.id, "error", "Local search configuration was invalid"
            )
            return "failed"

        last_stage: str | None = None

        async def progress(stage: str, total: int, processed: int, failed: int) -> bool:
            nonlocal last_stage
            await session.refresh(job, attribute_names=["status"])
            if job.status == "cancelled":
                return False
            fraction = processed / total if total else 0
            if stage == "Starting public source check":
                stage_progress = 1
            elif stage == "Public indexes checked":
                stage_progress = 10
            elif stage == "Checking public listing pages":
                stage_progress = 10 + (fraction * 75)
            else:
                # Saving comes after evidence collection. Keep job progress
                # monotonic even when fewer candidates survive normalisation.
                stage_progress = 85 + (fraction * 14)
            job.total_records = max(job.total_records, total, 0)
            job.processed_records = max(job.processed_records, processed, 0)
            job.failed_records = max(job.failed_records, failed, 0)
            job.progress_percent = max(
                float(job.progress_percent or 0), min(99, round(stage_progress, 2))
            )
            job.report = {
                "stage": stage,
                "niche": niche,
                "city": city,
                "public_pages_checked": processed,
                "public_pages_total": total,
            }
            if stage != last_stage:
                await job_service.add_log(session, job.id, "info", stage)
                last_stage = stage
            await session.commit()
            return True

        try:
            result = await scrape_google_local(
                session, job.owner_user_id, niche, city, progress=progress
            )
        except LocalSearchCancelled:
            await session.refresh(job, attribute_names=["status"])
            if job.status != "cancelled":
                job.status = "cancelled"
                job_service.mark_finished(job)
            await job_service.add_log(session, job.id, "warning", "Local search cancelled")
            return "cancelled"
        except Exception as exc:  # noqa: BLE001 - background failures must be visible
            job.status = "failed"
            job.error_details = {"reason": f"{type(exc).__name__}: {exc}"[:500]}
            job_service.mark_finished(job)
            await job_service.add_log(session, job.id, "error", "Local search failed")
            return "failed"

        await session.refresh(job, attribute_names=["status"])
        if job.status == "cancelled":
            return "cancelled"
        job.status = "completed"
        job.progress_percent = 100
        job.total_records = max(job.total_records, result.total_found)
        job.processed_records = max(job.processed_records, result.total_found)
        job.report = {
            "stage": "Search complete",
            "niche": result.niche,
            "city": result.city,
            "total_found": result.total_found,
            "stored_new": result.stored_new,
        }
        job_service.mark_finished(job)
        await job_service.add_log(session, job.id, "info", "Local search completed", job.report)
        return "completed"
