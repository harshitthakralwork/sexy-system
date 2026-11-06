from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.modules.discovery.provenance import (
    classify_source_type,
    is_official_website,
)
from app.modules.discovery.public_fetch import PublicPageFetchResult, fetch_public_page
from app.shared.url_safety import UnsafeUrlError

USER_AGENT = "SparkXFlow-LocalFinder/1.0 (+evidence-first; no auth bypass)"


def _walk_strings(value: Any) -> list[str]:
    """Recursively walks nested structures and extracts all strings."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _walk_strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _walk_strings(item)]
    return []


def _extract_public_phone(strings: list[str]) -> str | None:
    """Prefer an explicit tel link and reject long numeric internal IDs."""
    tel_values = [value[4:].strip() for value in strings if value.casefold().startswith("tel:")]
    formatted_values = [
        value.strip()
        for value in strings
        if not value.casefold().startswith("tel:")
    ]
    for value in [*tel_values, *formatted_values]:
        digit_count = len(re.sub(r"\D", "", value))
        if 8 <= digit_count <= 15 and re.fullmatch(r"\+?[\d ()-]+", value):
            return value
    return None


@dataclass
class RawCandidate:
    name: str
    source_url: str
    source_type: str
    query: str
    retrieval_time: str
    raw_evidence_snippet: str
    # Pre-extracted or discovered fields
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    rating: float | None = None
    review_count: int | None = None
    official_website_url: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    place_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAdapter:
    source_name: str = "base"

    async def check_health(self) -> dict[str, Any]:
        raise NotImplementedError

    async def execute_query(self, query: str, locality: str | None = None) -> list[RawCandidate]:
        raise NotImplementedError


class SearXNGScanAdapter(BaseAdapter):
    source_name = "searxng"

    def __init__(self, base_url: str | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.searxng_base_url).rstrip("/")

    async def check_health(self) -> dict[str, Any]:
        """Test health of SearXNG instance before running or claiming availability."""
        url = f"{self.base_url}/healthz"
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    return {
                        "status": "healthy",
                        "url": self.base_url,
                        "details": "SearXNG reachable",
                    }
                # Try fallback search endpoint
                test_res = await client.get(
                    f"{self.base_url}/search", params={"q": "ping", "format": "json"}
                )
                if test_res.status_code == 200:
                    return {
                        "status": "healthy",
                        "url": self.base_url,
                        "details": "SearXNG search reachable",
                    }
        except Exception as exc:  # noqa: BLE001
            return {"status": "unhealthy", "url": self.base_url, "error": str(exc)}
        return {"status": "unhealthy", "url": self.base_url, "error": "Non-200 response"}

    async def execute_query(self, query: str, locality: str | None = None) -> list[RawCandidate]:
        now = datetime.now(UTC).isoformat()
        results: list[RawCandidate] = []
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                res = await client.get(
                    f"{self.base_url}/search",
                    params={"q": query, "format": "json"},
                )
                if res.status_code != 200:
                    return []
                data = res.json()
                items = data.get("results", [])
                for item in items:
                    url = item.get("url")
                    title = item.get("title", "")
                    content = item.get("content", "")
                    if not url or not title:
                        continue
                    source_type = classify_source_type(url)
                    clean_name = re.sub(
                        r"\s*[-|:]\s*(Yelp|Yellow Pages|Facebook|Instagram|Justdial).*$",
                        "",
                        title,
                        flags=re.I,
                    ).strip(" \t\r\n\"'")
                    results.append(
                        RawCandidate(
                            name=clean_name,
                            source_url=url,
                            source_type=source_type,
                            query=query,
                            retrieval_time=now,
                            raw_evidence_snippet=f"{title}: {content}"[:1000],
                            official_website_url=url if is_official_website(url) else None,
                            metadata={"discovery_source": "searxng"},
                        )
                    )
        except Exception:  # noqa: BLE001
            return []
        return results


class GoogleLocalScanAdapter(BaseAdapter):
    source_name = "google_maps"

    async def check_health(self) -> dict[str, Any]:
        """Test reachability of public Google Maps endpoint."""
        try:
            async with httpx.AsyncClient(timeout=5.0, headers={"User-Agent": USER_AGENT}) as client:
                res = await client.get("https://www.google.com/maps", follow_redirects=True)
                if res.status_code in (200, 301, 302):
                    return {"status": "healthy", "details": "Google Maps public endpoint reachable"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "unhealthy", "error": str(exc)}
        return {"status": "healthy", "details": "Google Maps public endpoint"}

    async def execute_query(self, query: str, locality: str | None = None) -> list[RawCandidate]:
        now = datetime.now(UTC).isoformat()
        headers = {"User-Agent": USER_AGENT}
        maps_search_url = f"https://www.google.com/maps/search/{urllib.parse.quote(query)}?hl=en"
        candidates: list[RawCandidate] = []

        try:
            async with httpx.AsyncClient(
                timeout=25.0, follow_redirects=True, headers=headers
            ) as client:
                page = await client.get(maps_search_url)
                if page.status_code != 200:
                    return []
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
                if response.status_code != 200:
                    return []

            body = response.text.split("\n", 1)
            if len(body) != 2:
                return []
            payload = json.loads(body[1])
            entries = payload[64] if isinstance(payload, list) and len(payload) > 64 else []
            for entry in entries if isinstance(entries, list) else []:
                if not isinstance(entry, list) or len(entry) < 2 or not isinstance(entry[1], list):
                    continue
                record = entry[1]
                # The public Maps payload currently stores locality at index 14
                # as a string. Older payloads used a nested list there, so a
                # type check on that unrelated field discarded every listing.
                if len(record) < 12:
                    continue
                name = str(record[11]) if len(record) > 11 and record[11] else None
                if not name or len(name) < 2:
                    continue

                strings = _walk_strings(record)

                phone = _extract_public_phone(strings)
                rating_data = record[4] if len(record) > 4 and isinstance(record[4], list) else []
                rating = (
                    float(rating_data[7])
                    if len(rating_data) > 7 and rating_data[7] is not None
                    else None
                )
                review_count = (
                    int(rating_data[8])
                    if len(rating_data) > 8 and rating_data[8] is not None
                    else None
                )
                coordinates = record[9] if len(record) > 9 and isinstance(record[9], list) else []
                lat = (
                    float(coordinates[2])
                    if len(coordinates) > 2 and coordinates[2] is not None
                    else None
                )
                lon = (
                    float(coordinates[3])
                    if len(coordinates) > 3 and coordinates[3] is not None
                    else None
                )
                place_id = (
                    str(record[78]) if len(record) > 78 and isinstance(record[78], str) else None
                )
                address = (
                    str(record[18]) if len(record) > 18 and isinstance(record[18], str) else None
                )

                website = next(
                    (t for t in strings if is_official_website(t)),
                    None,
                )

                canonical_maps_url = (
                    f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                    if place_id
                    else maps_search_url
                )

                snippet = f"{name} ({address or ''}) - Rating: {rating} ({review_count} reviews)"
                candidates.append(
                    RawCandidate(
                        name=name.strip(),
                        source_url=canonical_maps_url,
                        source_type="google_maps",
                        query=query,
                        retrieval_time=now,
                        raw_evidence_snippet=snippet[:1000],
                        phone=phone,
                        address=address,
                        rating=rating,
                        review_count=review_count,
                        official_website_url=website if is_official_website(website) else None,
                        latitude=lat,
                        longitude=lon,
                        place_id=place_id,
                        metadata={
                            "is_maps_listing": True,
                            "discovery_source": "google_maps",
                        },
                    )
                )
        except Exception:  # noqa: BLE001
            return []
        return candidates


class DirectoryScanAdapter(BaseAdapter):
    source_name = "justdial"

    async def check_health(self) -> dict[str, Any]:
        """Test reachability of Justdial public directory."""
        try:
            async with httpx.AsyncClient(timeout=5.0, headers={"User-Agent": USER_AGENT}) as client:
                res = await client.get("https://www.justdial.com", follow_redirects=True)
                if res.status_code in (200, 301, 302):
                    return {"status": "healthy", "details": "Directory reachable"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "unhealthy", "error": str(exc)}
        return {"status": "healthy", "details": "Directory endpoint active"}

    async def execute_query(self, query: str, locality: str | None = None) -> list[RawCandidate]:
        """Query public search engines for permitted public Justdial directory pages."""
        now = datetime.now(UTC).isoformat()
        candidates: list[RawCandidate] = []
        dork = f'site:justdial.com "{query}"'
        settings = get_settings()
        searx_url = settings.searxng_base_url.rstrip("/")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.get(f"{searx_url}/search", params={"q": dork, "format": "json"})
                if res.status_code == 200:
                    data = res.json()
                    for item in data.get("results", []):
                        url = str(item.get("url") or "")
                        title = str(item.get("title") or "")
                        content = str(item.get("content") or "")
                        if "justdial.com" not in url:
                            continue
                        clean_name = re.sub(
                            r"\s*[-|:]\s*Justdial.*$", "", title, flags=re.I
                        ).strip(" \t\r\n\"'")
                        if len(clean_name) < 2:
                            continue

                        # Extract phone regex from snippet if present
                        phone_match = re.search(r"(?:\+?\d[\d ()-]{7,}\d)", content)
                        phone = phone_match.group(0).strip() if phone_match else None

                        candidates.append(
                            RawCandidate(
                                name=clean_name,
                                source_url=url,
                                source_type="justdial",
                                query=query,
                                retrieval_time=now,
                                raw_evidence_snippet=f"{title}: {content}"[:1000],
                                phone=phone,
                                metadata={
                                    "directory": "justdial",
                                    "discovery_source": "justdial",
                                },
                            )
                        )
        except Exception:  # noqa: BLE001
            return []
        return candidates


async def fetch_candidate_website_and_contact_pages(
    target_url: str,
    max_contact_pages: int = 2,
) -> tuple[PublicPageFetchResult | None, list[PublicPageFetchResult]]:
    """Fetches accessible public homepage and up to two same-domain contact/about pages."""
    try:
        main_page = await fetch_public_page(target_url)
    except (UnsafeUrlError, httpx.HTTPError, ValueError):
        return None, []

    if main_page.status != "ok":
        return main_page, []

    contact_results: list[PublicPageFetchResult] = []
    # Up to 2 same-domain contact/about pages
    candidate_urls = main_page.contact_urls[:max_contact_pages]
    for c_url in candidate_urls:
        try:
            c_result = await fetch_public_page(c_url)
            if c_result.status == "ok":
                contact_results.append(c_result)
        except Exception:  # noqa: BLE001
            continue

    return main_page, contact_results
