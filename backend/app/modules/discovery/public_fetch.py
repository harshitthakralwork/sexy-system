from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from app.shared.normalization import normalize_email, normalize_phone
from app.shared.url_safety import UnsafeUrlError, validate_discovered_target

MAX_RESPONSE_BYTES = 1_500_000
MAX_REDIRECTS = 4
USER_AGENT = "SparkXFlow-PublicFetcher/1.0 (+public pages only)"
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\d ()-]{7,}\d)")


class PublicPageFetchRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2_000)


class PublicPageFetchResult(BaseModel):
    requested_url: str
    final_url: str
    status: Literal["ok", "blocked", "unsupported"]
    status_code: int
    title: str | None = None
    description: str | None = None
    business_name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    rating: float | None = None
    review_count: int | None = None
    published_at: datetime | None = None
    website_url: str | None = None
    website_urls: list[str] = Field(default_factory=list)
    social_urls: list[str] = Field(default_factory=list)
    contact_urls: list[str] = Field(default_factory=list)
    extraction_method: str
    notes: list[str] = Field(default_factory=list)


def _walk_json(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        rows = [value]
        for child in value.values():
            rows.extend(_walk_json(child))
        return rows
    if isinstance(value, list):
        return [row for child in value for row in _walk_json(child)]
    return []


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())[:1_000]
    return None


def _address(value: Any) -> str | None:
    if isinstance(value, str):
        return _first_text(value)
    if not isinstance(value, dict):
        return None
    parts = [
        value.get("streetAddress"),
        value.get("addressLocality"),
        value.get("addressRegion"),
        value.get("postalCode"),
        value.get("addressCountry"),
    ]
    return _first_text(", ".join(str(part) for part in parts if part))


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_rating(value: Any, best: Any = None) -> float | None:
    num = _number(value)
    if num is None:
        return None
    best_num = _number(best)
    if best_num and best_num > 5.0:
        num = (num / best_num) * 5.0
    elif num > 10.0:
        num = (num / 100.0) * 5.0
    elif num > 5.0:
        num = (num / 10.0) * 5.0
    return max(0.0, min(5.0, round(num, 2)))


def _integer(value: Any) -> int | None:
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _external_website_links(final_url: str, links: list[str]) -> list[str]:
    """Return plausible public business-site links, never social profiles.

    A directory page can link to a business website.  Its own canonical URL is
    provenance, not the business website, so only cross-domain non-social links
    are retained for later review by the caller.
    """
    source_host = urlsplit(final_url).netloc.lower().removeprefix("www.")
    blocked_hosts = (
        "facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com",
        "youtube.com", "google.com", "googleusercontent.com",
    )
    candidates: list[str] = []
    for link in links:
        parsed = urlsplit(link)
        if parsed.scheme not in {"http", "https"}:
            continue
        host = parsed.netloc.lower().removeprefix("www.")
        is_blocked = any(host == item or host.endswith(f".{item}") for item in blocked_hosts)
        if not host or host == source_host or is_blocked:
            continue
        candidates.append(link)
    return list(dict.fromkeys(candidates))[:12]


async def _download(url: str, client: httpx.AsyncClient) -> tuple[str, int, bytes, str]:
    current = validate_discovered_target(url)
    for _ in range(MAX_REDIRECTS + 1):
        response = await client.get(current, headers={"User-Agent": USER_AGENT})
        if response.is_redirect:
            location = response.headers.get("location")
            if not location:
                response.raise_for_status()
            current = validate_discovered_target(urljoin(current, location))
            continue
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            return current, response.status_code, b"", content_type
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ValueError("public page exceeded the 1.5 MB extraction limit")
        return current, response.status_code, response.content, content_type
    raise ValueError("public page exceeded the redirect limit")


async def fetch_public_page(
    url: str, *, client: httpx.AsyncClient | None = None
) -> PublicPageFetchResult:
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=httpx.Timeout(15.0), follow_redirects=False)
    try:
        final_url, status_code, body, content_type = await _download(url, http)
    finally:
        if owns_client:
            await http.aclose()

    if not body:
        return PublicPageFetchResult(
            requested_url=url,
            final_url=final_url,
            status="unsupported",
            status_code=status_code,
            extraction_method="content_type_check",
            notes=[f"Unsupported content type: {content_type or 'unknown'}"],
        )

    soup = BeautifulSoup(body, "lxml")
    for node in soup(["script", "style", "noscript", "svg"]):
        if node.name != "script" or node.get("type") != "application/ld+json":
            node.decompose()

    json_nodes: list[dict[str, Any]] = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            json_nodes.extend(_walk_json(json.loads(script.get_text(" ", strip=True))))
        except (json.JSONDecodeError, TypeError):
            continue
    entity = next(
        (
            node
            for node in json_nodes
            if any(
                token in str(node.get("@type", "")).casefold()
                for token in ("localbusiness", "organization", "store", "professionalservice")
            )
        ),
        {},
    )
    aggregate = (
        entity.get("aggregateRating") if isinstance(entity.get("aggregateRating"), dict) else {}
    )
    text = " ".join(soup.get_text(" ", strip=True).split())[:250_000]
    emails = [normalize_email(match) for match in EMAIL_RE.findall(text)]
    phones = [normalize_phone(match) for match in PHONE_RE.findall(text)]
    emails = [value for value in emails if value]
    phones = [value for value in phones if value and 8 <= len(re.sub(r"\D", "", value)) <= 15]

    links = [urljoin(final_url, str(link.get("href"))) for link in soup.select("a[href]")]
    social_hosts = (
        "linkedin.com",
        "facebook.com",
        "instagram.com",
        "x.com",
        "twitter.com",
        "youtube.com",
    )
    social_urls = list(
        dict.fromkeys(
            link
            for link in links
            if any(host in urlsplit(link).netloc.lower() for host in social_hosts)
        )
    )[:12]
    website_urls = _external_website_links(final_url, links)
    contact_urls = list(
        dict.fromkeys(
            link
            for link in links
            if any(word in link.casefold() for word in ("contact", "about", "support"))
        )
    )[:8]
    canonical = soup.select_one('link[rel="canonical"]')
    canonical_url = (
        urljoin(final_url, str(canonical.get("href")))
        if canonical and canonical.get("href")
        else None
    )
    meta_description = soup.select_one('meta[name="description"], meta[property="og:description"]')
    published_meta = soup.select_one(
        'meta[property="article:published_time"], meta[name="datePublished"], meta[name="pubdate"]'
    )
    published_at = _date(entity.get("datePublished"))
    if published_at is None and published_meta and published_meta.get("content"):
        published_at = _date(published_meta.get("content"))
    if published_at is None:
        time_node = soup.select_one("time[datetime]")
        if time_node and time_node.get("datetime"):
            published_at = _date(time_node.get("datetime"))
    title = _first_text(entity.get("name"), soup.title.string if soup.title else None)

    return PublicPageFetchResult(
        requested_url=url,
        final_url=final_url,
        status="ok",
        status_code=status_code,
        title=title,
        description=_first_text(
            entity.get("description"), meta_description.get("content") if meta_description else None
        ),
        business_name=_first_text(entity.get("name")),
        phone=_first_text(entity.get("telephone"), phones[0] if phones else None),
        email=_first_text(entity.get("email"), emails[0] if emails else None),
        address=_address(entity.get("address")),
        rating=_clean_rating(aggregate.get("ratingValue"), aggregate.get("bestRating")),
        review_count=_integer(aggregate.get("reviewCount") or aggregate.get("ratingCount")),
        published_at=published_at,
        website_url=_first_text(entity.get("url"), canonical_url),
        website_urls=website_urls,
        social_urls=social_urls,
        contact_urls=contact_urls,
        extraction_method="schema_org_json_ld" if entity else "visible_html",
        notes=[
            "Only publicly returned HTML was read; no login, cookie or CAPTCHA bypass was used."
        ],
    )


__all__ = [
    "PublicPageFetchRequest",
    "PublicPageFetchResult",
    "UnsafeUrlError",
    "fetch_public_page",
]
