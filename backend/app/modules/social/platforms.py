from __future__ import annotations

from typing import Any

# Honest platform catalogue. Every entry states what its *permitted* public
# access allows. Platforms without a free, permitted access method are disabled
# by default, so the UI shows "restricted" rather than implying availability
# (PRD §5.3: "The product must not promise unrestricted collection",
# architecture §15: report limitations clearly; no credential abuse).
PLATFORM_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "slug": "reddit",
        "name": "Reddit",
        "adapter_key": "reddit",
        "is_enabled": True,
        "capabilities": {
            "access_method": "Public JSON endpoints (no authentication)",
            "searchable": ["keyword", "subreddit", "username"],
            "available_fields": [
                "title",
                "selftext",
                "author",
                "score",
                "created_utc",
                "permalink",
            ],
            "content_types": ["post", "comment"],
        },
        "limitations": {
            "access": "Unauthenticated JSON is rate-limited and may be throttled or blocked.",
            "coverage": "Public posts and comments only; no private or deleted content.",
            "filters": "No geographic or user-defined date range filter; sort order only.",
            "requires": "A descriptive User-Agent identifying this application.",
        },
    },
    {
        "slug": "linkedin",
        "name": "LinkedIn",
        "adapter_key": "none",
        "is_enabled": False,
        "capabilities": {},
        "limitations": {
            "access": "No permitted public API for company or profile data without a partner key.",
            "reason": (
                "Scraping public pages violates LinkedIn's terms; this product will not do it."
            ),
        },
    },
    {
        "slug": "instagram",
        "name": "Instagram",
        "adapter_key": "none",
        "is_enabled": False,
        "capabilities": {},
        "limitations": {
            "access": "Graph API requires an approved app and access token.",
            "reason": "No key is configured; scraping violates the platform terms.",
        },
    },
    {
        "slug": "facebook",
        "name": "Facebook",
        "adapter_key": "none",
        "is_enabled": False,
        "capabilities": {},
        "limitations": {
            "access": "Graph API requires an app and access token, with review for most data.",
            "reason": "No key is configured; scraping violates the platform terms.",
        },
    },
    {
        "slug": "x",
        "name": "X (Twitter)",
        "adapter_key": "none",
        "is_enabled": False,
        "capabilities": {},
        "limitations": {
            "access": "API v2 requires a paid developer account tier.",
            "reason": "No key is configured; scraping violates the platform terms.",
        },
    },
    {
        "slug": "youtube",
        "name": "YouTube",
        "adapter_key": "none",
        "is_enabled": False,
        "capabilities": {},
        "limitations": {
            "access": "Data API requires an API key with a quota.",
            "reason": "No key is configured.",
        },
    },
)

ENABLED_ADAPTER_KEYS = frozenset(
    entry["adapter_key"] for entry in PLATFORM_DEFINITIONS if entry["is_enabled"]
)
