"""Social & Demand Intelligence Engine — deterministic classification (Phase 3).

A keyword that merely appears is not a buying signal. This engine only raises
confidence when a phrase expressing *intent* is present, keeps every contributing
signal visible as evidence, and lowers confidence when a negative/context signal
(a tutorial, a news article, a job seeker, an advertisement) appears. Rules are data
and the method/version are stamped onto every result, so a call can be explained,
re-run under a new rule set, or overridden by a human — never a black box.

Local AI is designed in as an optional enrichment (see ``method``); the
deterministic path is the only one the core flow depends on, and there is no paid
fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CLASSIFICATION_VERSION = 1
CLASSIFICATION_METHOD = "rule"

DEMAND_CATEGORIES = (
    "Service Needed",
    "Vendor Search",
    "Freelancer Hiring",
    "Agency Search",
    "Recommendation Request",
    "Project Help",
    "Hiring",
    "Partnership Opportunity",
    "General Discussion",
    "Unclassified",
)

BUSINESS_CATEGORIES = (
    "Startup",
    "Established Business",
    "New Business",
    "Company Expansion",
    "Hiring Signal",
    "Product Launch",
    "Partnership Opportunity",
    "Technology Need",
    "Market Trend",
    "Competitor Activity",
    "General Company Update",
    "Unclassified",
)

# Intent phrases say "someone wants something done". A category keyword alone does
# not; both are required for a confident demand call.
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
)

BUSINESS_INTENT_PHRASES = (
    "launches",
    "launched",
    "raising",
    "raises",
    "series a",
    "series b",
    "funding",
    "seed round",
    "expansion",
    "expanding",
    "new office",
    "opening a new",
    "hiring",
    "now hiring",
    "hiring developers",
    "new product",
    "announced",
    "acquired",
    "acquisition",
    "partnership",
    "partnered",
    "digital transformation",
    "migrating to",
    "rebrand",
    "competitor",
)

BUSINESS_NEGATIVE_PHRASES = (
    "tutorial",
    "how to",
    "opinion",
    "editorial",
    "job seeker",
    "for sale",
)

# Ordered category rules: the first category whose keywords appear in the text wins,
# but only once an intent phrase has been seen. Order encodes specificity.
DEMAND_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Agency Search", ("agency", "agencies", "development company", "software company")),
    ("Freelancer Hiring", ("freelancer", "freelance", "contract developer", "contractor")),
    ("Vendor Search", ("vendor", "supplier", "reseller", "provider")),
    ("Recommendation Request", ("recommend", "suggestion", "anyone know")),
    ("Hiring", ("full-time", "employee", "position", "role", "recruiter")),
    ("Partnership Opportunity", ("partner", "partnership", "joint venture")),
    (
        "Service Needed",
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
        ),
    ),
    ("Project Help", ("project", "help with", "build an", "build a")),
)

BUSINESS_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Hiring Signal", ("hiring", "now hiring", "recruiting", "open roles", "open position")),
    ("Product Launch", ("launches", "launched", "new product", "released", "goes live")),
    ("Company Expansion", ("expansion", "expanding", "new office", "opening a new", "scale up")),
    (
        "Startup",
        ("startup", "seed round", "series a", "series b", "funding", "raises", "raising"),
    ),
    ("Technology Need", ("digital transformation", "migrating", "replatform", "integrating")),
    ("Partnership Opportunity", ("partnership", "partnered", "integrates with", "collaboration")),
    ("Competitor Activity", ("competitor", "rival", "vs ", "alternative to")),
    ("New Business", ("founded", "new business", "just started", "we are a new")),
    ("Market Trend", ("trend", "report", "market", "industry")),
)


@dataclass(frozen=True)
class ClassificationOutcome:
    category: str
    confidence: float
    method: str = CLASSIFICATION_METHOD
    version: int = CLASSIFICATION_VERSION
    matched_terms: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    positive_signals: dict[str, Any] = field(default_factory=dict)
    negative_signals: dict[str, Any] = field(default_factory=dict)


def _found(phrases: tuple[str, ...], text: str) -> tuple[str, ...]:
    return tuple(p for p in phrases if p in text)


def _pick_category(
    category_rules: tuple[tuple[str, tuple[str, ...]], ...], text: str
) -> tuple[str, tuple[str, ...]]:
    for category, keywords in category_rules:
        hits = tuple(k for k in keywords if k in text)
        if hits:
            return category, hits
    return "", ()


def _classify(
    text: str,
    *,
    intent_phrases: tuple[str, ...],
    negative_phrases: tuple[str, ...],
    category_rules: tuple[tuple[str, tuple[str, ...]], ...],
    generic_category: str,
    discussion_category: str,
) -> ClassificationOutcome:
    lowered = (text or "").lower()
    intent = _found(intent_phrases, lowered)
    negatives = _found(negative_phrases, lowered)
    category, keyword_hits = _pick_category(category_rules, lowered)

    if not intent and not keyword_hits:
        return ClassificationOutcome(
            category="Unclassified",
            confidence=0.0,
            matched_terms=(),
            evidence=({"rule": "no intent or category keyword", "contribution": 0},),
            negative_signals=dict.fromkeys(negatives, 1),
        )

    evidence: list[dict[str, Any]] = []
    # Intent is what separates a genuine signal from a bare keyword mention.
    score = 0.0
    if intent:
        score += 45.0
        evidence.append({"rule": "intent phrase", "matched": list(intent), "contribution": 45})
    if category:
        score += 25.0
        evidence.append(
            {"rule": "category keyword", "matched": list(keyword_hits), "contribution": 25}
        )

    if not intent:
        # A category keyword with no intent phrase is at best general discussion.
        category = discussion_category
        score -= 25.0
        evidence.append({"rule": "keyword without intent → discussion", "contribution": -25})

    for negative in negatives:
        score -= 20.0
        evidence.append(
            {"rule": "negative/context signal", "matched": negative, "contribution": -20}
        )

    if not category:
        category = generic_category if intent else "Unclassified"

    confidence = max(0.0, min(100.0, score))
    matched = tuple(dict.fromkeys((*intent, *keyword_hits, *negatives)))
    return ClassificationOutcome(
        category=category,
        confidence=round(confidence, 2),
        matched_terms=matched,
        evidence=tuple(evidence),
        positive_signals={"intent": list(intent), "category_keywords": list(keyword_hits)},
        negative_signals=dict.fromkeys(negatives, 1),
    )


def classify(text: str, track_type: str) -> ClassificationOutcome:
    """Deterministic, transparent classification for a track's collected text."""
    if track_type == "business":
        return _classify(
            text,
            intent_phrases=BUSINESS_INTENT_PHRASES,
            negative_phrases=BUSINESS_NEGATIVE_PHRASES,
            category_rules=BUSINESS_CATEGORY_KEYWORDS,
            generic_category="General Company Update",
            discussion_category="General Company Update",
        )
    return _classify(
        text,
        intent_phrases=DEMAND_INTENT_PHRASES,
        negative_phrases=DEMAND_NEGATIVE_PHRASES,
        category_rules=DEMAND_CATEGORY_KEYWORDS,
        generic_category="Service Needed",
        discussion_category="General Discussion",
    )
