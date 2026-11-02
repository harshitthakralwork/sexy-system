from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.modules.deduplication.service import Candidate, compare
from app.modules.discovery.adapters.base import (
    AdapterCapabilities,
    DiscoveredItem,
    DiscoveryQuery,
    HealthResult,
    RateLimitedError,
)
from app.modules.discovery.pipeline import (
    InMemoryBusinessStore,
    PipelineReport,
    normalize_item,
    run_pipeline,
    validate,
)
from app.shared.scoring import Operator, ScoringRule

RETRIEVED = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)


class StubAdapter:
    """A source that returns fixed items, so the pipeline is testable offline.

    Real adapters are covered against mocked HTTP in test_adapters.py; this one
    covers the stages between them and storage.
    """

    def __init__(self, items: list[DiscoveredItem], *, fail: bool = False) -> None:
        self._items = items
        self._fail = fail
        self.calls = 0
        self.requests_made = 0

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="stub",
            name="Stub",
            slug="stub",
            category="search",
            supported_query_types=("keyword",),
            supported_filters=(),
            available_fields=("title", "url"),
            geographic_coverage="test only",
        )

    async def validate_config(self, config: dict) -> None:
        return None

    async def discover(self, query: DiscoveryQuery) -> list[DiscoveredItem]:
        del query
        self.calls += 1
        self.requests_made += 1
        if self._fail:
            raise RateLimitedError("stub throttled")
        return list(self._items)

    async def health_check(self) -> HealthResult:
        return HealthResult(status="working")


def search_item(url: str, title: str, **extra: object) -> DiscoveredItem:
    """A search hit, shaped the way the SearXNG adapter shapes one: the result URL
    is both provenance and the business's claimed website."""
    return DiscoveredItem(
        external_id=None,
        source_url=url,
        title_hint=title,
        website_hint=url,
        raw_data={"content": "A cafe", **(extra if extra else {})},
    )


@pytest.mark.asyncio
async def test_two_sources_describing_one_business_store_it_once_with_both_provenances() -> None:
    """Deduplication must not cost us the second source's evidence — the point of
    multi-source discovery is corroboration."""
    searxng = StubAdapter([search_item("https://sparkcoffee.in/", "Spark Coffee")])
    overpass = StubAdapter(
        [
            DiscoveredItem(
                external_id="node/1",
                source_url="https://openstreetmap.org/node/1",
                title_hint="Spark Coffee",
                raw_data={"name": "Spark Coffee", "website": "https://sparkcoffee.in"},
            )
        ]
    )
    store = InMemoryBusinessStore()

    report = await run_pipeline(
        [("searxng", searxng), ("overpass", overpass)],
        [DiscoveryQuery(keywords=("coffee",))],
        store=store,
        retrieved_at=RETRIEVED,
    )

    stored = await store.all()
    assert len(stored) == 1
    assert report.counters.discovered == 2
    assert {attribution.source_slug for attribution in stored[0].attributions} == {
        "searxng",
        "overpass",
    }
    assert store.merges == 1


@pytest.mark.asyncio
async def test_website_status_stays_unknown_until_something_actually_fetches_it() -> None:
    """This is the difference between intelligence and guessing: a claimed URL is
    not a verified one, and the export says so."""
    store = InMemoryBusinessStore()
    adapter = StubAdapter([search_item("https://sparkcoffee.in/", "Spark Coffee")])

    report = await run_pipeline(
        [("searxng", adapter)], [DiscoveryQuery(keywords=("x",))], store=store
    )

    stored = await store.all()
    assert stored[0].website_status == "unknown"
    assert report.enrichment is not None
    assert report.enrichment.ran is False
    assert "website_status left unknown" in report.enrichment.detail


@pytest.mark.asyncio
async def test_a_failing_source_is_recorded_and_the_others_still_store() -> None:
    """PRD section 19: one dead provider must not make discovery unusable — and
    must not make it look like it found nothing."""
    broken = StubAdapter([], fail=True)
    working = StubAdapter([search_item("https://goodcafe.in/", "Good Business")])
    store = InMemoryBusinessStore()

    report = await run_pipeline(
        [("broken", broken), ("working", working)],
        [DiscoveryQuery(keywords=("coffee",))],
        store=store,
    )

    assert report.any_source_failed is True
    failure = next(source for source in report.sources if source.failed)
    assert failure.failure_classification == "rate_limited"
    assert "rate_limited" in report.failure_summary()
    assert report.counters.stored_new == 1


@pytest.mark.asyncio
async def test_records_identifying_nothing_are_rejected_not_stored() -> None:
    store = InMemoryBusinessStore()
    junk = StubAdapter([DiscoveredItem(external_id=None, source_url=None, raw_data={})])

    report = await run_pipeline([("stub", junk)], [DiscoveryQuery(keywords=("x",))], store=store)

    assert report.counters.rejected == 1
    assert report.counters.stored_new == 0
    assert await store.all() == []


@pytest.mark.asyncio
async def test_indian_phone_from_a_source_becomes_e164_with_provenance() -> None:
    store = InMemoryBusinessStore()
    item = DiscoveredItem(
        external_id="node/9",
        source_url="https://osm.test/node/9",
        title_hint="Brew Theory",
        raw_data={
            "name": "Brew Theory",
            "website": "https://brewtheory.in",
            "phone": "098765 43210",
            "email": " Hello@BrewTheory.IN ",
        },
    )

    await run_pipeline(
        [("overpass", StubAdapter([item]))], [DiscoveryQuery(keywords=("x",))], store=store
    )

    stored = (await store.all())[0]
    assert stored.normalized_phone == "+919876543210"
    assert stored.phone == "098765 43210"  # original preserved alongside
    assert stored.normalized_email == "hello@brewtheory.in"
    assert stored.field_provenance["phone"].startswith("overpass:")
    assert stored.website_status == "unknown"


@pytest.mark.asyncio
async def test_scoring_runs_over_survivors_and_returns_evidence() -> None:
    rules = [
        ScoringRule("No phone found", "phone_present", 50, Operator.EQ, False),
        ScoringRule("Name known", "name_present", 50, Operator.EQ, True),
    ]
    store = InMemoryBusinessStore()
    adapter = StubAdapter([search_item("https://onlycafe.in/", "Only Cafe")])

    report = await run_pipeline(
        [("stub", adapter)], [DiscoveryQuery(keywords=("x",))], store=store, scoring_rules=rules
    )

    assert isinstance(report, PipelineReport)
    assert len(report.scores) == 1
    result = report.scores[0]
    assert result.qualified is True
    assert {entry.rule_name for entry in result.evidence} == {"No phone found", "Name known"}


@pytest.mark.asyncio
async def test_pipeline_reports_its_stage_order() -> None:
    store = InMemoryBusinessStore()
    report = await run_pipeline(
        [("stub", StubAdapter([search_item("https://a.test/", "A")]))],
        [DiscoveryQuery(keywords=("x",))],
        store=store,
    )
    assert report.stages == (
        "discover",
        "normalize",
        "validate",
        "deduplicate",
        "enrich",
        "score",
        "store",
        "report",
    )


def test_normalize_never_invents_a_name_from_a_url() -> None:
    """A slug like "spark-coffee-bengaluru" is evidence about a page, not a
    business name. Inventing one here would create an unfalsifiable record."""
    item = DiscoveredItem(
        external_id=None,
        source_url="https://example.com/spark-coffee",
        website_hint="https://example.com/spark-coffee",
        raw_data={},
    )
    business = normalize_item(item, source_slug="searxng", retrieved_at=RETRIEVED)

    assert business.name is None
    assert business.normalized_domain == "example.com"
    assert validate(business).accepted is True


def test_where_a_record_was_found_is_never_its_website() -> None:
    """D4 regression, from a real run: 16 distinct Hisar hospitals collapsed into
    3 because the OpenStreetMap page each was found on became their shared domain,
    and a shared domain is a confirmed-duplicate identity key.

    A record with no website of its own keeps no website. That is the honest
    answer, and it is also the only one that keeps neighbouring businesses apart.
    """
    first = normalize_item(
        DiscoveredItem(
            external_id="node/1",
            source_url="https://www.openstreetmap.org/node/1",
            raw_data={"name": "Khetarpaul Hospital"},
        ),
        source_slug="overpass",
        retrieved_at=RETRIEVED,
    )
    second = normalize_item(
        DiscoveredItem(
            external_id="node/2",
            source_url="https://www.openstreetmap.org/node/2",
            raw_data={"name": "Savant Hospital"},
        ),
        source_slug="overpass",
        retrieved_at=RETRIEVED,
    )

    assert first.normalized_domain is None
    assert second.normalized_domain is None
    assert first.website_url is None
    # Not a pair at all: nothing identifies them as one business.
    assert compare(Candidate("a", first.dedup_key()), Candidate("b", second.dedup_key())) is None


def test_an_unparseable_url_warns_but_does_not_discard_the_lead() -> None:
    """Regression: treating a warning as a rejection silently throws away usable
    businesses — the opposite of what validation is for."""
    item = DiscoveredItem(
        external_id=None,
        source_url="https://localhost:8080/weird-path",
        website_hint="https://localhost:8080/weird-path",
        title_hint="Spark Coffee",
        raw_data={},
    )
    business = normalize_item(item, source_slug="searxng", retrieved_at=RETRIEVED)
    verdict = validate(business)

    assert verdict.accepted is True
    assert verdict.reasons == ()
    assert "website_url_unparseable" in verdict.warnings


@pytest.mark.asyncio
async def test_warning_flagged_records_are_counted_and_stored() -> None:
    store = InMemoryBusinessStore()
    item = DiscoveredItem(
        external_id=None,
        source_url="https://localhost:9/weird",
        website_hint="https://localhost:9/weird",
        title_hint="Weird Cafe",
        raw_data={},
    )
    report = await run_pipeline(
        [("stub", StubAdapter([item]))], [DiscoveryQuery(keywords=("x",))], store=store
    )

    assert report.counters.rejected == 0
    assert report.counters.warning_flagged == 1
    assert report.counters.stored_new == 1
