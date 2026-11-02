from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from app.modules.deduplication.service import (
    Candidate,
    DedupKey,
    DuplicatePair,
    find_duplicates,
    partition,
)
from app.modules.discovery.adapters.base import (
    AdapterError,
    DiscoveredItem,
    DiscoveryAdapter,
    DiscoveryQuery,
)
from app.shared import signals as S
from app.shared.normalization import (
    MAX_ADDRESS_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_EMAIL_LENGTH,
    MAX_NAME_LENGTH,
    MAX_PHONE_INPUT_LENGTH,
    MAX_PHONE_LENGTH,
    MAX_URL_LENGTH,
    canonical_hash,
    normalize_domain,
    normalize_email,
    normalize_name,
    normalize_phone,
    sanitize_text,
)
from app.shared.scoring import ScoreResult, ScoringRule, evaluate

PIPELINE_STAGES = (
    "discover",
    "normalize",
    "validate",
    "deduplicate",
    "enrich",
    "score",
    "store",
    "report",
)


@dataclass(frozen=True)
class Attribution:
    """Where a record came from. Required on every stored field group."""

    source_slug: str
    source_url: str | None
    retrieved_at: datetime
    external_id: str | None = None
    note: str | None = None


@dataclass
class NormalizedBusiness:
    name: str | None = None
    normalized_name: str | None = None
    website_url: str | None = None
    normalized_domain: str | None = None
    phone: str | None = None
    normalized_phone: str | None = None
    email: str | None = None
    normalized_email: str | None = None
    primary_category: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = None
    website_status: str = "unknown"
    signals: dict[str, S.SignalValue] = field(default_factory=dict)
    field_provenance: dict[str, str] = field(default_factory=dict)
    attributions: list[Attribution] = field(default_factory=list)
    fingerprint: str = ""

    def __post_init__(self) -> None:
        self.signals[S.NAME_PRESENT] = bool(self.name)
        self.signals[S.DOMAIN_PRESENT] = bool(self.normalized_domain)
        self.signals[S.PHONE_PRESENT] = bool(self.normalized_phone)
        self.signals[S.EMAIL_PRESENT] = bool(self.normalized_email)
        self.signals[S.ADDRESS_PRESENT] = bool(self.address)
        self.signals[S.GEO_PRESENT] = self.latitude is not None and self.longitude is not None
        self.signals[S.CATEGORY_MATCHED] = bool(self.primary_category)
        self.signals.setdefault(S.WEBSITE_CLAIMED, bool(self.website_url))
        self.signals.setdefault(S.WEBSITE_CHECKED, False)
        self.website_status = S.derive_website_status(self.signals)
        if not self.fingerprint:
            self.fingerprint = canonical_hash(
                self.normalized_domain,
                self.normalized_phone,
                self.normalized_email,
                self.normalized_name,
            )

    def dedup_key(self) -> DedupKey:
        profile = next((a.source_url for a in self.attributions if a.note == "profile_url"), None)
        return DedupKey(
            name=self.normalized_name,
            domain=self.normalized_domain,
            phone=self.normalized_phone,
            email=self.normalized_email,
            profile_url=profile,
            city=self.city,
            address=self.address,
        )


def normalize_item(
    item: DiscoveredItem,
    *,
    source_slug: str,
    retrieved_at: datetime,
    default_region: str = "IN",
) -> NormalizedBusiness:
    """Turn one raw hit into a business candidate, recording how each field arose.

    For a search hit the URL is where we *found* the business, not proof of its
    website, so it is stored as a claimed website with that caveat in provenance.
    Names are never invented from a URL slug.
    """
    raw: dict[str, Any] = dict(item.raw_data or {})
    name = sanitize_text(raw.get("name") or item.title_hint, max_length=MAX_NAME_LENGTH)
    website = raw.get("website")
    website_origin = "source_record"
    if not website and item.source_url:
        website = item.source_url
        website_origin = "search_result_url"

    website = sanitize_text(website, max_length=MAX_URL_LENGTH)
    normalized_domain = normalize_domain(website) if website else None
    email = normalize_email(sanitize_text(raw.get("email"), max_length=MAX_EMAIL_LENGTH))
    phone = normalize_phone(
        sanitize_text(raw.get("phone"), max_length=MAX_PHONE_INPUT_LENGTH), default_region
    )

    business = NormalizedBusiness(
        name=name,
        normalized_name=normalize_name(name) if name else None,
        website_url=website,
        normalized_domain=normalized_domain,
        phone=sanitize_text(raw.get("phone"), max_length=MAX_PHONE_LENGTH),
        normalized_phone=phone,
        email=sanitize_text(raw.get("email"), max_length=MAX_EMAIL_LENGTH),
        normalized_email=email,
        primary_category=sanitize_text(raw.get("category"), max_length=150),
        city=sanitize_text(raw.get("city"), max_length=150),
        address=sanitize_text(raw.get("address"), max_length=MAX_ADDRESS_LENGTH),
        latitude=item.latitude,
        longitude=item.longitude,
        description=sanitize_text(
            raw.get("description") or raw.get("content"), max_length=MAX_DESCRIPTION_LENGTH
        ),
        field_provenance={
            "name": f"{source_slug}:{'osm_tags' if raw.get('name') else 'page_title'}",
            "website": f"{source_slug}:{website_origin}",
            "email": f"{source_slug}:source_record" if email else "not_observed",
            "phone": f"{source_slug}:source_record" if phone else "not_observed",
        },
        attributions=[
            Attribution(
                source_slug=source_slug,
                source_url=item.source_url,
                retrieved_at=retrieved_at,
                external_id=item.external_id,
                note="profile_url" if raw.get("profile_url") else None,
            )
        ],
    )
    return business


@dataclass(frozen=True)
class ValidationOutcome:
    accepted: bool
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def validate(business: NormalizedBusiness) -> ValidationOutcome:
    """Reject records that identify nothing; warn about the rest.

    A row with no name, no domain and no contact point is noise: storing it
    inflates "businesses discovered" while being unusable, which is exactly the
    metric PRD section 22 warns against.

    Warnings are separate because a named business with an odd URL is still a
    lead. Folding warnings into rejections would silently discard usable
    records — the failure mode this function exists to prevent.
    """
    reasons: list[str] = []
    warnings: list[str] = []

    if not business.normalized_name and not business.normalized_domain:
        reasons.append("no_name_and_no_domain")
    if business.normalized_domain is None and business.website_url:
        warnings.append("website_url_unparseable")
    if business.normalized_name and business.normalized_name == business.normalized_domain:
        warnings.append("name_is_only_a_domain")

    return ValidationOutcome(accepted=not reasons, reasons=tuple(reasons), warnings=tuple(warnings))


class BusinessStore(Protocol):
    """Persistence seam. In-memory today, SQLAlchemy-backed in Phase 1."""

    async def upsert(self, business: NormalizedBusiness) -> bool: ...

    async def all(self) -> list[NormalizedBusiness]: ...


class InMemoryBusinessStore:
    def __init__(self) -> None:
        self._by_fingerprint: dict[str, NormalizedBusiness] = {}
        self.upserts = 0
        self.merges = 0

    async def upsert(self, business: NormalizedBusiness) -> bool:
        existing = self._by_fingerprint.get(business.fingerprint)
        if existing is None:
            self._by_fingerprint[business.fingerprint] = business
            self.upserts += 1
            return True
        # Never discard the earlier record's provenance when a second source
        # confirms the same business.
        existing.attributions.extend(business.attributions)
        for key, value in business.signals.items():
            if value is not None and existing.signals.get(key) is None:
                existing.signals[key] = value
        self.merges += 1
        return False

    async def all(self) -> list[NormalizedBusiness]:
        return list(self._by_fingerprint.values())


@dataclass(frozen=True)
class EnrichmentOutcome:
    ran: bool
    detail: str


class NoEnrichment:
    """Explicit placeholder until the website crawler lands.

    Returning "we did not enrich" is the point: pipeline reports can then state
    that website status is unverified rather than implying a check happened.
    """

    async def enrich(self, businesses: Sequence[NormalizedBusiness]) -> EnrichmentOutcome:
        del businesses
        return EnrichmentOutcome(
            ran=False, detail="Website crawler not implemented; website_status left unknown"
        )


@dataclass
class SourceOutcome:
    slug: str
    items_returned: int = 0
    requests_made: int = 0
    failed: bool = False
    failure_classification: str | None = None
    failure_reason: str | None = None


@dataclass
class StageCounters:
    discovered: int = 0
    normalized: int = 0
    rejected: int = 0
    warning_flagged: int = 0
    duplicates_merged: int = 0
    provenances_merged: int = 0
    review_pairs: int = 0
    stored_new: int = 0


@dataclass
class PipelineReport:
    stages: tuple[str, ...] = PIPELINE_STAGES
    counters: StageCounters = field(default_factory=StageCounters)
    sources: list[SourceOutcome] = field(default_factory=list)
    review_pairs: list[DuplicatePair] = field(default_factory=list)
    scores: list[ScoreResult] = field(default_factory=list)
    enrichment: EnrichmentOutcome | None = None

    @property
    def any_source_failed(self) -> bool:
        return any(source.failed for source in self.sources)

    def failure_summary(self) -> str:
        failed = [
            f"{source.slug}: {source.failure_classification} — {source.failure_reason}"
            for source in self.sources
            if source.failed
        ]
        return "; ".join(failed) if failed else "All sources completed"


async def run_pipeline(
    adapters: Iterable[tuple[str, DiscoveryAdapter]],
    queries: Sequence[DiscoveryQuery],
    *,
    store: BusinessStore,
    default_region: str = "IN",
    enricher: NoEnrichment | Any = None,
    scoring_rules: Sequence[ScoringRule] | None = None,
    qualification_threshold: float = 60.0,
    retrieved_at: datetime | None = None,
) -> PipelineReport:
    """Discover → Normalize → Validate → Deduplicate → Enrich → Score → Store → Report.

    A source that fails is recorded and the rest continue. One dead provider must
    not make the whole discovery platform unusable (PRD section 19).
    """
    when = retrieved_at or datetime.now(UTC)
    report = PipelineReport()
    adapter_list = list(adapters)
    collected: list[NormalizedBusiness] = []

    for slug, adapter in adapter_list:
        outcome = SourceOutcome(slug=slug)
        report.sources.append(outcome)
        for query in queries:
            try:
                items = await adapter.discover(query)
            except AdapterError as exc:
                outcome.failed = True
                outcome.failure_classification = exc.classification
                outcome.failure_reason = exc.message
                break
            except Exception as exc:  # noqa: BLE001 - never let one source kill the run
                outcome.failed = True
                outcome.failure_classification = "unexpected"
                outcome.failure_reason = type(exc).__name__
                break

            outcome.items_returned += len(items)
            outcome.requests_made = getattr(adapter, "requests_made", outcome.requests_made)
            report.counters.discovered += len(items)

            for item in items:
                business = normalize_item(
                    item, source_slug=slug, retrieved_at=when, default_region=default_region
                )
                verdict = validate(business)
                if not verdict.accepted:
                    report.counters.rejected += 1
                    continue
                if verdict.warnings:
                    report.counters.warning_flagged += 1
                collected.append(business)

    report.counters.normalized = len(collected)

    candidates = [
        Candidate(ref=business.fingerprint, key=business.dedup_key()) for business in collected
    ]
    pairs = find_duplicates(candidates)
    dedup = partition(candidates, pairs)
    report.counters.duplicates_merged = len(dedup.merged_away)
    report.counters.review_pairs = dedup.review_count
    report.review_pairs = dedup.needs_review

    # A confirmed merge must not cost us the loser's evidence. database-schema.md
    # section 12.2 requires provenance to survive merges; dropping the discarded
    # record's attributions would erase the second source that corroborated it.
    by_ref = {business.fingerprint: business for business in collected}
    for loser_ref, survivor_ref in dedup.merged_away.items():
        loser = by_ref.get(loser_ref)
        survivor = by_ref.get(survivor_ref)
        if loser is None or survivor is None or loser is survivor:
            continue
        survivor.attributions.extend(loser.attributions)
        for key, value in loser.signals.items():
            if value is not None and survivor.signals.get(key) is None:
                survivor.signals[key] = value
        report.counters.provenances_merged += 1

    survivors = [
        business for business in collected if business.fingerprint in set(dedup.unique_refs)
    ]

    enricher = enricher or NoEnrichment()
    report.enrichment = await enricher.enrich(survivors)

    if scoring_rules:
        for business in survivors:
            report.scores.append(
                evaluate(
                    dict(business.signals),
                    list(scoring_rules),
                    qualification_threshold=qualification_threshold,
                )
            )

    for business in survivors:
        if await store.upsert(business):
            report.counters.stored_new += 1

    return report
