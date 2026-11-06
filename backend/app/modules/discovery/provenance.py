from __future__ import annotations

import urllib.parse
from dataclasses import asdict, dataclass
from typing import Any

# Provenance and classification rules for local business discovery

DIRECTORY_DOMAINS = {
    "google.com",
    "maps.google.com",
    "facebook.com",
    "instagram.com",
    "justdial.com",
    "jdmagicbox.com",
    "linkedin.com",
    "mapquest.com",
    "tripadvisor.com",
    "yellowpages.com",
    "yelp.com",
    "sulekha.com",
    "indiamart.com",
    "tradeindia.com",
    "bing.com",
    "apple.com",
}

# Hosts that commonly appear in search/listing payloads but are never a
# business's own website. In particular, Google Maps exposes Street View
# thumbnails from googleapis.com; those URLs must not become "Visit" links.
NON_BUSINESS_ASSET_HOSTS = {
    "googleapis.com",
    "googleusercontent.com",
    "gstatic.com",
}
IMAGE_PATH_MARKERS = ("/thumbnail", "/image", "/photo", "/streetview")
IMAGE_EXTENSIONS = (".avif", ".bmp", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".webp")

SOURCE_TYPE_LABELS = {
    "justdial": "Justdial",
    "google_maps": "Google Maps",
    "directory": "Directory Listing",
    "website": "Official Website",
    "searxng": "Indexed Web",
}

EXTRACTION_CONFIDENCE: dict[str, float] = {
    "schema.org": 1.0,
    "official_contact_page": 0.95,
    "official_website_link": 0.85,
    "structured_directory": 0.75,
    "visible_text_official": 0.65,
    "search_snippet": 0.50,
}


@dataclass
class FieldEvidence:
    value: Any
    source_url: str
    source_type: str
    extraction_method: str
    checked_at: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_domain(url: str | None) -> str:
    if not url:
        return ""
    try:
        netloc = urllib.parse.urlparse(url).netloc.lower()
        return netloc.removeprefix("www.")
    except (ValueError, TypeError):
        return ""


def classify_source_type(url: str) -> str:
    """Classifies a URL into its true source type: justdial, google_maps, directory, or website."""
    domain = get_domain(url)
    if "justdial.com" in domain or "jdmagicbox.com" in domain:
        return "justdial"
    if "google.com" in domain and ("/maps" in url or "tbm=map" in url or "place" in url):
        return "google_maps"
    if any(domain == d or domain.endswith(f".{d}") for d in DIRECTORY_DOMAINS):
        return "directory"
    return "website"


def is_directory_url(url: str | None) -> bool:
    if not url:
        return False
    domain = get_domain(url)
    return any(domain == d or domain.endswith(f".{d}") for d in DIRECTORY_DOMAINS)


def is_official_website(url: str | None) -> bool:
    """An official business website must be an external HTTP(S) URL and NOT a directory."""
    if not url:
        return False
    clean = url.strip()
    if not clean.startswith(("http://", "https://")):
        return False
    parsed = urllib.parse.urlparse(clean)
    domain = get_domain(clean)
    if is_directory_url(clean):
        return False
    if any(domain == host or domain.endswith(f".{host}") for host in NON_BUSINESS_ASSET_HOSTS):
        return False
    path = parsed.path.casefold()
    return not (
        any(marker in path for marker in IMAGE_PATH_MARKERS) or path.endswith(IMAGE_EXTENSIONS)
    )


def determine_website_status(
    *,
    official_website_url: str | None,
    explicit_missing_confirmed: bool = False,
    page_fetch_failed: bool = False,
    sources_checked: bool = False,
) -> str:
    """Strict website rules:
    - available: verified official external business domain found.
    - missing: only after an explicit, trustworthy source confirms no website.
    - inaccessible: public page could not be checked.
    - unknown: sources checked but no authoritative conclusion.
    """
    if is_official_website(official_website_url):
        return "available"
    if explicit_missing_confirmed:
        return "missing"
    if page_fetch_failed:
        return "inaccessible"
    if sources_checked:
        return "unknown"
    return "unknown"


def sanitize_address(address: str | None, city: str | None) -> str | None:
    """Never use city text as an address fallback. If address is identical to city, it is empty."""
    if not address:
        return None
    cleaned = address.strip()
    if not cleaned:
        return None
    if city:
        city_clean = city.strip().casefold()
        city_prefix = city_clean.split(",")[0].strip()
        if cleaned.casefold() in (city_clean, city_prefix):
            return None
    # Reject generic placeholders
    placeholders = {"india", "usa", "united states", "n/a", "na", "none", "not available"}
    if cleaned.casefold() in placeholders:
        return None
    return cleaned[:500]


def should_update_field(
    existing_evidence: dict[str, Any] | None, new_evidence: FieldEvidence
) -> bool:
    """Never overwrite an existing verified value with weaker evidence.

    Returns True if new_evidence has strictly higher confidence than existing_evidence,
    or if existing_evidence is missing/empty.
    """
    if not existing_evidence or existing_evidence.get("value") in (None, "", [], {}):
        return True
    existing_conf = float(existing_evidence.get("confidence", 0.0))
    return new_evidence.confidence > existing_conf
