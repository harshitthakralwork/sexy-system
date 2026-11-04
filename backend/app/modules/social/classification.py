"""Social & Demand Intelligence Engine — deterministic classification and potential-client scoring (Phase 3 & 4).

A keyword that merely appears is not a buying signal. This engine only raises
confidence when a phrase expressing *intent* is present, keeps every contributing
signal visible as evidence, and lowers confidence when a negative/context signal
(a tutorial, a news article, a job seeker, an advertisement) appears.

Every classification and score is 100% deterministic, explainable, and transparent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

CLASSIFICATION_VERSION = 2
CLASSIFICATION_METHOD = "rule"

DETERMINISTIC_CATEGORIES = (
    "Service needed",
    "Freelancer hiring",
    "Vendor search",
    "Recommendation request",
    "Project help",
    "Job hiring",
    "General discussion",
    "Not relevant",
)

# Intent phrases expressing buying or hiring intent
DEMAND_INTENT_PHRASES = (
    "looking for",
    "need a",
    "need an",
    "need someone",
    "need help",
    "seeking",
    "recommend",
    "any agency",
    "anyone know",
    "can anyone",
    "in the market for",
    "want to hire",
    "hiring a",
    "open to hiring",
    "project requirement",
    "looking to hire",
    "need someone to",
    "searching for",
    "budget for",
    "quote for",
    "looking for a quote",
    "rfp",
    "looking to outsource",
    "who can build",
    "can someone help me build",
    "willing to pay",
)

DEMAND_NEGATIVE_PHRASES = (
    "tutorial",
    "how to",
    "guide to",
    "i built",
    "we built",
    "just launched my",
    "for sale",
    "hiring? i am a",
    "job seeker",
    "my resume",
    "looking for a job",
    "opinion",
    "article:",
    "press release",
    "hire me",
    "open to work",
    "open for work",
    "available for hire",
    "my portfolio",
    "discount code",
    "coupon",
    "promotional",
)

# Category-specific keywords
CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Freelancer hiring",
        (
            "freelancer",
            "freelance",
            "contract developer",
            "contractor",
            "hire a freelancer",
            "upwork",
            "fiverr",
            "contract gig",
        ),
    ),
    (
        "Vendor search",
        (
            "vendor",
            "supplier",
            "reseller",
            "provider",
            "b2b provider",
            "saas vendor",
            "software vendor",
            "agency partner",
            "agency search",
        ),
    ),
    (
        "Recommendation request",
        (
            "recommend",
            "recommendation",
            "suggestions for",
            "anyone know a good",
            "who do you use for",
            "what tool do you recommend",
            "best agency for",
            "good experiences with",
        ),
    ),
    (
        "Job hiring",
        (
            "we are hiring",
            "job opening",
            "full-time role",
            "full time position",
            "salary range",
            "join our team",
            "apply here",
            "recruiting for",
        ),
    ),
    (
        "Project help",
        (
            "help with my project",
            "stuck on",
            "need help building",
            "project requirements",
            "consultant needed",
            "technical help",
            "code review",
        ),
    ),
    (
        "Service needed",
        (
            "website",
            "web site",
            "web development",
            "developer",
            "ecommerce",
            "e-commerce",
            "automation",
            "seo",
            "marketing",
            "app",
            "application",
            "design",
            "crm",
            "database",
            "plumbing",
            "electrician",
            "legal services",
            "accounting",
        ),
    ),
)

SERVICE_TAXONOMY: dict[str, tuple[str, ...]] = {
    "web-development": (
        "website",
        "web app",
        "frontend",
        "backend",
        "fullstack",
        "react",
        "nextjs",
        "wordpress",
        "shopify",
        "landing page",
        "web design",
        "html",
        "css",
    ),
    "mobile-app": ("mobile app", "ios app", "android app", "flutter", "react native", "swift", "kotlin"),
    "ai-automation": (
        "automation",
        "workflow",
        "make.com",
        "zapier",
        "n8n",
        "ai agent",
        "llm",
        "chatbot",
        "scraping",
        "scraper",
        "python script",
    ),
    "seo-marketing": (
        "seo",
        "lead gen",
        "leads",
        "ppc",
        "ad campaigns",
        "google ads",
        "facebook ads",
        "copywriting",
        "content marketing",
        "growth marketing",
    ),
    "ui-ux-design": ("ui/ux", "graphic design", "logo design", "branding", "figma", "redesign", "ui design"),
    "local-services": ("plumber", "electrician", "contractor", "roofing", "hvac", "cleaning service", "landscaping"),
}


@dataclass(frozen=True)
class ClassificationOutcome:
    category: str
    confidence: float
    score: int
    method: str = CLASSIFICATION_METHOD
    version: int = CLASSIFICATION_VERSION
    matched_terms: tuple[str, ...] = ()
    matched_positive_phrases: tuple[str, ...] = ()
    matched_negative_phrases: tuple[str, ...] = ()
    service_mapping: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    positive_signals: dict[str, Any] = field(default_factory=dict)
    negative_signals: dict[str, Any] = field(default_factory=dict)

    @property
    def service_tags(self) -> tuple[str, ...]:
        return self.service_mapping

    @property
    def matched_phrases(self) -> tuple[str, ...]:
        return self.matched_terms

    @property
    def negative_phrases(self) -> tuple[str, ...]:
        return self.matched_negative_phrases


def _found(phrases: tuple[str, ...], text: str) -> tuple[str, ...]:
    return tuple(p for p in phrases if p in text)


def _map_services(text: str) -> tuple[str, ...]:
    tags: list[str] = []
    for service, keywords in SERVICE_TAXONOMY.items():
        if any(k in text for k in keywords):
            tags.append(service)
    return tuple(tags)


def _pick_category(
    category_rules: tuple[tuple[str, tuple[str, ...]], ...], text: str
) -> tuple[str, tuple[str, ...]]:
    for category, keywords in category_rules:
        hits = tuple(k for k in keywords if k in text)
        if hits:
            return category, hits
    return "", ()


def classify(
    text: str,
    track_type: str = "demand",
    metadata: dict[str, Any] | None = None,
) -> ClassificationOutcome:
    """Deterministic, transparent classification for collected text with explainable scoring."""
    lowered = (text or "").lower()
    intent = _found(DEMAND_INTENT_PHRASES, lowered)
    negatives = _found(DEMAND_NEGATIVE_PHRASES, lowered)
    category, keyword_hits = _pick_category(CATEGORY_RULES, lowered)
    services = _map_services(lowered)

    evidence: list[dict[str, Any]] = []
    confidence_val = 0.0
    client_score = 0

    if intent:
        confidence_val += 45.0
        client_score += 25
        evidence.append({"rule": "explicit buying intent", "matched": list(intent), "contribution": 25})

    if "hire" in lowered or "hiring" in lowered or "contractor" in lowered:
        client_score += 25
        evidence.append({"rule": "asks to hire someone", "contribution": 25})

    if category:
        confidence_val += 25.0
        evidence.append(
            {"rule": "category keyword match", "matched": list(keyword_hits), "contribution": 25}
        )

    if services:
        client_score += 10
        evidence.append({"rule": "relevant service category", "services": list(services), "contribution": 10})

    # Contact info heuristics in text or metadata
    has_contact = bool(
        re.search(r"\(?\b\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b", lowered)
        or re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", lowered)
        or (metadata and (metadata.get("phone") or metadata.get("email")))
    )
    if has_contact:
        client_score += 15
        evidence.append({"rule": "phone/email available", "contribution": 15})

    # Metadata checks (e.g. no website found or active reviews from Google Maps)
    if metadata:
        if metadata.get("website_status") == "missing" or not metadata.get("website_url"):
            client_score += 10
            evidence.append({"rule": "no official website found", "contribution": 10})
        if metadata.get("review_count") and metadata["review_count"] > 3:
            client_score += 10
            evidence.append({"rule": "active business with real reviews", "contribution": 10})

        published_at = metadata.get("published_at")
        if isinstance(published_at, datetime):
            age_days = (datetime.now(timezone.utc) - published_at).days
            if age_days <= 7:
                client_score += 10
                evidence.append({"rule": "recent post within 7 days", "contribution": 10})

    # Penalties for negative phrases
    for neg in negatives:
        confidence_val -= 20.0
        if any(term in neg for term in ("job seeker", "hire me", "my resume", "looking for a job", "open to work")):
            client_score -= 40
            evidence.append({"rule": "job seeker penalty", "matched": neg, "contribution": -40})
        elif any(term in neg for term in ("i built", "we built", "just launched", "discount", "coupon")):
            client_score -= 30
            evidence.append({"rule": "self-promotion penalty", "matched": neg, "contribution": -30})
        else:
            client_score -= 20
            evidence.append({"rule": "negative context penalty", "matched": neg, "contribution": -20})

    # Determine final deterministic category
    if negatives and not intent:
        final_category = "Not relevant"
    elif not intent and keyword_hits:
        final_category = "General discussion"
        confidence_val = max(10.0, confidence_val - 20.0)
    elif not intent and not keyword_hits:
        final_category = "Not relevant"
        confidence_val = 0.0
    else:
        final_category = category if category else "Service needed"

    # Normalize bounds
    final_confidence = round(max(0.0, min(100.0, confidence_val)), 2)
    final_score = max(0, min(100, client_score))
    all_matched = tuple(dict.fromkeys((*intent, *keyword_hits, *negatives)))

    return ClassificationOutcome(
        category=final_category,
        confidence=final_confidence,
        score=final_score,
        matched_terms=all_matched,
        matched_positive_phrases=tuple(dict.fromkeys((*intent, *keyword_hits))),
        matched_negative_phrases=negatives,
        service_mapping=services,
        evidence=tuple(evidence),
        positive_signals={"intent": list(intent), "keywords": list(keyword_hits), "services": list(services)},
        negative_signals=dict.fromkeys(negatives, 1),
    )
