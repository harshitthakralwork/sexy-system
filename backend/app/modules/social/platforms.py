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
        "slug": "hackernews",
        "name": "Hacker News",
        "adapter_key": "hackernews",
        "is_enabled": True,
        "capabilities": {
            "access_method": "Algolia public search API (no authentication, no key)",
            "searchable": ["keyword", "author", "front_page", "ask_hn", "show_hn"],
            "available_fields": [
                "title",
                "text",
                "url",
                "author",
                "created_at",
                "points",
                "num_comments",
            ],
            "content_types": ["post", "comment"],
        },
        "limitations": {
            "access": "Only Hacker News content; subject to Algolia public rate limits.",
            "coverage": "Tech/startup discussion, predominantly English. Not a general web index.",
            "filters": "Date filtering via created_at; no geographic filter.",
            "requires": "None.",
        },
    },
    {
        "slug": "rss",
        "name": "RSS / Atom feeds",
        "adapter_key": "rss",
        "is_enabled": True,
        "capabilities": {
            "access_method": "Configurable public feed URLs, parsed with the standard library",
            "searchable": ["feed_url"],
            "available_fields": ["title", "link", "description", "published"],
            "content_types": ["post"],
        },
        "limitations": {
            "access": "http(s) public feeds only; feed URLs are checked against SSRF rules.",
            "coverage": "Exactly what each configured feed publishes — snippet or full text.",
            "filters": "Dates come from the feed entry; no server-side search.",
            "requires": "A user-configured feed URL list.",
        },
    },
    {
        "slug": "searxng",
        "name": "Web index (SearXNG)",
        "adapter_key": "searxng",
        "is_enabled": True,
        "capabilities": {
            "access_method": "Self-hosted SearXNG metasearch JSON endpoint",
            "searchable": ["keyword", "site"],
            "available_fields": ["title", "url", "snippet", "publishedDate"],
            "content_types": ["other"],
        },
        "limitations": {
            "access": "Needs a reachable SearXNG instance; it aggregates upstream engines.",
            "coverage": "Indexed snippets only — never a confirmed retrieval of the source post. "
            "Coverage depends on upstream indexing and platform blocking.",
            "filters": "Language and time-range only where the instance supports them.",
            "requires": "SPARKX_SEARXNG_BASE_URL pointing at a running instance.",
        },
    },
    {
        "slug": "stackoverflow",
        "name": "Stack Overflow",
        "adapter_key": "stackoverflow",
        "is_enabled": True,
        "capabilities": {
            "access_method": "Public API (no key for low volume)",
            "searchable": ["keyword"],
            "available_fields": ["title", "link", "score", "answer_count", "creation_date", "tags"],
            "content_types": ["post"],
        },
        "limitations": {
            "access": "Anonymous access is rate-limited by Stack Exchange; a key raises the limit.",
            "coverage": "Public questions only; relevant to technical/hiring demand.",
            "filters": "Sort and tag only; no geographic filter.",
            "requires": "None for basic use.",
        },
    },
    {
        "slug": "bluesky",
        "name": "Bluesky",
        "adapter_key": "bluesky",
        "is_enabled": True,
        "capabilities": {
            "access_method": "Unauthenticated public search endpoint (app.bsky)",
            "searchable": ["keyword"],
            "available_fields": ["text", "uri", "indexedAt", "author handle"],
            "content_types": ["post"],
        },
        "limitations": {
            "access": "Public posts only; subject to Bluesky's public API limits.",
            "coverage": "Whatever Bluesky's public search indexes; not exhaustive.",
            "filters": "Sort only.",
            "requires": "None.",
        },
    },
    {
        "slug": "mastodon",
        "name": "Mastodon",
        "adapter_key": "mastodon",
        "is_enabled": True,
        "capabilities": {
            "access_method": "Configurable instance search endpoint (public toots)",
            "searchable": ["keyword"],
            "available_fields": ["content", "url", "created_at", "account"],
            "content_types": ["post"],
        },
        "limitations": {
            "access": "Unauthenticated search availability varies by instance; a "
            "refusal is reported honestly rather than faked.",
            "coverage": "Depends on the configured instance's visibility rules.",
            "filters": "Type filter (statuses) only.",
            "requires": "SPARKX_MASTODON_BASE_URL (defaults to a public instance).",
        },
    },
    {
        "slug": "linkedin",
        "name": "LinkedIn",
        "adapter_key": "linkedin",
        "is_enabled": True,
        "capabilities": {
            "access_method": "SearXNG metasearch site search",
            "searchable": ["keyword", "profile", "company"],
            "available_fields": ["title", "url", "snippet", "publishedDate"],
            "content_types": ["profile", "company", "post"],
        },
        "limitations": {
            "access": "Public profiles and company pages indexed via metasearch.",
            "coverage": "Public web-index snippets only; this is not direct LinkedIn access.",
            "filters": "Keyword, headline, role, company, language.",
            "requires": "SearXNG metasearch instance.",
        },
    },
    {
        "slug": "instagram",
        "name": "Instagram",
        "adapter_key": "instagram",
        "is_enabled": True,
        "capabilities": {
            "access_method": "SearXNG metasearch site search",
            "searchable": ["keyword", "hashtag", "handle"],
            "available_fields": ["title", "url", "snippet", "publishedDate"],
            "content_types": ["post"],
        },
        "limitations": {
            "access": "Public posts, captions, and creator profiles via metasearch.",
            "coverage": "Public web-index snippets only; this is not direct Instagram access.",
            "filters": "Keyword and hashtag search.",
            "requires": "SearXNG metasearch instance.",
        },
    },
    {
        "slug": "facebook",
        "name": "Facebook",
        "adapter_key": "facebook",
        "is_enabled": True,
        "capabilities": {
            "access_method": "SearXNG metasearch dorking",
            "searchable": ["keyword", "page", "group"],
            "available_fields": ["title", "url", "snippet", "publishedDate"],
            "content_types": ["post"],
        },
        "limitations": {
            "access": "Public posts, public business pages, and public groups.",
            "coverage": "Public search engine index snippets.",
            "filters": "Keyword search.",
            "requires": "SearXNG metasearch instance.",
        },
    },
    {
        "slug": "x",
        "name": "X (Twitter)",
        "adapter_key": "x",
        "is_enabled": True,
        "capabilities": {
            "access_method": "Public syndication feed & SearXNG metasearch dorking",
            "searchable": ["keyword", "username", "url"],
            "available_fields": ["text", "url", "author", "publishedDate"],
            "content_types": ["post"],
        },
        "limitations": {
            "access": "Public user timelines via syndication, oEmbed, and metasearch dorking.",
            "coverage": "Public syndication where available and web-index snippets; keyword "
            "results are not guaranteed real-time.",
            "filters": "Keyword, username, and post URL.",
            "requires": "SearXNG metasearch instance.",
        },
    },
    {
        "slug": "youtube",
        "name": "YouTube",
        "adapter_key": "youtube",
        "is_enabled": True,
        "capabilities": {
            "access_method": "Public channel RSS feeds, oEmbed API & SearXNG dorking",
            "searchable": ["keyword", "channel_id", "url"],
            "available_fields": ["title", "url", "snippet", "publishedDate", "author"],
            "content_types": ["video"],
        },
        "limitations": {
            "access": "Public video metadata, channel RSS atom feeds, and oEmbed summaries.",
            "coverage": "Public videos and channel feeds without API key quotas.",
            "filters": "Keyword, channel ID, video URL.",
            "requires": "SearXNG metasearch instance.",
        },
    },
    {
        "slug": "justdial",
        "name": "Justdial & Directories",
        "adapter_key": "justdial",
        "is_enabled": True,
        "capabilities": {
            "access_method": "Public directory index & schema.org JSON-LD extraction",
            "searchable": ["keyword", "business", "city"],
            "available_fields": ["name", "phone", "website", "address", "rating", "review_count"],
            "content_types": ["directory_listing"],
        },
        "limitations": {
            "access": "Public directory listings discovered via SearXNG.",
            "coverage": "Local service businesses and vendor directories.",
            "filters": "Keyword, city, business type.",
            "requires": "SearXNG metasearch instance.",
        },
    },
)

# All supported public/discovery connectors are enabled according to their honest capabilities.
# This ensures Reddit, HackerNews, RSS, SearXNG, StackOverflow, Bluesky, Mastodon, etc.,
# are operational while preserving honest rate-limit and access boundaries.
SOCIAL_MVP_PLATFORM_SLUGS = frozenset(
    entry["slug"] for entry in PLATFORM_DEFINITIONS if entry.get("is_enabled", True)
)

ENABLED_ADAPTER_KEYS = frozenset(
    entry["adapter_key"]
    for entry in PLATFORM_DEFINITIONS
    if entry.get("is_enabled", True)
)
