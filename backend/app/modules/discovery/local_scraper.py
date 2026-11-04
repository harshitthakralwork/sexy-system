from __future__ import annotations

import json
import re
import urllib.parse
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import SourceUnavailableError
from app.modules.businesses.models import Business
from app.modules.discovery.public_fetch import fetch_public_page
from app.shared.normalization import normalize_domain, normalize_email, normalize_phone

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


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


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
) -> LocalScrapeResponse:
    """Search public web indexes for local-business evidence without inventing fields."""
    clean_niche = niche.strip()
    clean_city = city.strip()
    settings = get_settings()
    queries = (
        f'"{clean_niche}" "{clean_city}" business phone',
        f'site:google.com/maps "{clean_niche}" "{clean_city}"',
        f'site:justdial.com "{clean_niche}" "{clean_city}"',
        f'"{clean_niche}" "{clean_city}" reviews address',
    )
    try:
        raw_results: list[dict[str, Any]] = await _google_maps_browser_results(
            clean_niche, clean_city
        )
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        raw_results = []
    async with httpx.AsyncClient(timeout=settings.searxng_timeout_seconds) as client:
        for query in queries:
            try:
                response = await client.get(
                    f"{settings.searxng_base_url.rstrip('/')}/search",
                    params={"q": query, "format": "json"},
                )
                response.raise_for_status()
                payload = response.json()
                raw_results.extend(payload.get("results", []))
            except (httpx.HTTPError, ValueError) as exc:
                if not raw_results:
                    raise SourceUnavailableError("searxng", type(exc).__name__) from exc
                break

    if not raw_results:
        try:
            raw_results = await _bing_html_results(f"{clean_niche} in {clean_city}")
        except httpx.HTTPError as exc:
            raise SourceUnavailableError("public_web_search", str(exc)) from exc

    seen: set[str] = set()
    output: list[LocalBusinessItem] = []
    stored_new = 0
    pages_fetched = 0
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
        domain = _domain(url)
        if (
            pages_fetched < 15
            and url.startswith(("http://", "https://"))
            and "google.com/maps" not in url
        ):
            try:
                fetched = await fetch_public_page(url)
            except (httpx.HTTPError, ValueError):
                fetched = None
            if fetched is not None and fetched.status == "ok":
                pages_fetched += 1
                content = " ".join(
                    part for part in (content, fetched.description, fetched.address) if part
                )
                result["phone"] = result.get("phone") or fetched.phone
                result["email"] = result.get("email") or fetched.email
                result["address"] = result.get("address") or fetched.address
                result["rating"] = result.get("rating") or fetched.rating
                result["review_count"] = result.get("review_count") or fetched.review_count
                result["public_page_method"] = fetched.extraction_method
        is_directory = any(
            domain == item or domain.endswith(f".{item}") for item in DIRECTORY_DOMAINS
        )
        website_url = None if is_directory else url
        extracted_phone, extracted_email, extracted_rating, extracted_reviews = _extract(content)
        phone = result.get("phone") or extracted_phone
        email = result.get("email") or extracted_email
        rating = result.get("rating") if result.get("rating") is not None else extracted_rating
        review_count = (
            result.get("review_count")
            if result.get("review_count") is not None
            else extracted_reviews
        )
        address = str(result.get("address") or clean_city)
        latitude = result.get("latitude")
        longitude = result.get("longitude")
        place_id = result.get("place_id")
        profile_url = (
            "https://www.google.com/maps/search/?api=1&"
            f"query={urllib.parse.quote(name + ' ' + address)}&"
            f"query_place_id={urllib.parse.quote(str(place_id))}"
            if place_id
            else None
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
                    "google_maps_url": profile_url,
                    "google_place_id": place_id,
                    "public_page_url": url,
                    "public_page_method": result.get("public_page_method"),
                },
                first_discovered_at=now,
            )
            session.add(existing)
            await session.flush()
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
            if profile_url:
                existing.enrichment = {
                    **(existing.enrichment or {}),
                    "google_maps_url": profile_url,
                    "google_place_id": place_id,
                }
            if result.get("public_page_method"):
                existing.enrichment = {
                    **(existing.enrichment or {}),
                    "public_page_url": url,
                    "public_page_method": result["public_page_method"],
                }
            await session.flush()
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
                maps_url=f"https://www.google.com/maps/search/?api=1&query={maps_query}",
            )
        )
        if len(output) >= 100:
            break
    return LocalScrapeResponse(
        niche=clean_niche,
        city=clean_city,
        total_found=len(output),
        stored_new=stored_new,
        items=output,
    )
