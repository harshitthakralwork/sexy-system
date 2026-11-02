"""Security regression tests.

Each test names the finding it pins, so deleting one has to be a deliberate
decision rather than an accident.
"""

from __future__ import annotations

import csv
import io
import socket
from typing import Any

import httpx
import pytest

from app.core.config import Settings
from app.core.security import hash_password, verify_password_for_login
from app.modules.discovery.adapters.base import (
    AdapterError,
    DiscoveredItem,
    DiscoveryQuery,
    LocationSpec,
    UnsupportedQueryError,
)
from app.modules.discovery.adapters.overpass import MAX_RADIUS_KM, OverpassAdapter
from app.modules.discovery.adapters.searxng import (
    MAX_KEYWORDS_PER_QUERY,
    MAX_RESULTS_LIMIT,
    QueryTooBroadError,
    SearxngAdapter,
)
from app.modules.discovery.pipeline import InMemoryBusinessStore, normalize_item, run_pipeline
from app.modules.exports.csv_export import to_csv
from app.shared.normalization import (
    MAX_EMAIL_LENGTH,
    MAX_NAME_LENGTH,
    normalize_email,
    normalize_phone,
    sanitize_text,
)
from app.shared.scoring import Operator, ScoringRule, evaluate
from app.shared.url_safety import (
    UnsafeUrlError,
    validate_discovered_target,
    validate_service_base_url,
)
from tests.test_pipeline import RETRIEVED, StubAdapter

# Written as a code point rather than a literal so the character is visible in
# the source and cannot be silently lost by an editor.
ZERO_WIDTH = chr(0x200B)


def client_for(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def searxng_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"results": []})


# ------------------------------------------------------------------ SSRF guard


def test_service_base_url_refuses_a_smuggled_path() -> None:
    """Adapters append their own endpoint. A configured path would silently
    change which resource is requested."""
    with pytest.raises(UnsafeUrlError, match="without a path"):
        validate_service_base_url("https://searxng.internal/proxy?token=abc")


def test_service_base_url_refuses_credentials_and_bad_scheme() -> None:
    with pytest.raises(UnsafeUrlError, match="credentials"):
        validate_service_base_url("https://admin:hunter2@searxng.internal")
    with pytest.raises(UnsafeUrlError, match="http or https"):
        validate_service_base_url("file:///etc/passwd")
    with pytest.raises(UnsafeUrlError, match="http or https"):
        validate_service_base_url("gopher://127.0.0.1:11211/_stats")


def test_service_base_url_allows_local_origin_by_design() -> None:
    """Local-first means loopback SearXNG is expected. The untrusted-input rule
    lives in validate_discovered_target, not here."""
    assert validate_service_base_url("http://localhost:8080") == "http://localhost:8080"
    assert validate_service_base_url("http://searxng:8080/") == "http://searxng:8080"


HOST_TO_ADDRESS = {
    "127.0.0.1": "127.0.0.1",
    "localhost": "127.0.0.1",
    "169.254.169.254": "169.254.169.254",
    "metadata.google.internal": "169.254.169.254",
    "10.0.0.5": "10.0.0.5",
    "192.168.1.1": "192.168.1.1",
    "::1": "::1",
}


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:6379/",
        "http://localhost/admin",
        "http://169.254.169.254/latest/meta-data/iam/security-credentials/",
        "http://metadata.google.internal/",
        "http://10.0.0.5/internal-service",
        "http://192.168.1.1:8000/api/v1/businesses",
        "http://[::1]:8000/",
    ],
)
def test_discovered_target_refuses_internal_addresses(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding: a crawler that fetches URLs taken from web pages is an SSRF
    machine unless targets are approved. Redis, PostgreSQL and the cloud
    metadata service are all one scraped page away."""

    def fake_getaddrinfo(host_arg: str, port: int, *args: Any, **kwargs: Any) -> list[Any]:
        literal = HOST_TO_ADDRESS[host_arg]
        family = socket.AF_INET6 if ":" in literal else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (literal, port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrlError):
        validate_discovered_target(url)


def test_discovered_target_allows_a_public_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )
    assert validate_discovered_target("https://example.com/about") == "https://example.com/about"


def test_discovered_target_rejects_split_horizon_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checking only the first answer would let a host with one public and one
    loopback record through."""
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(UnsafeUrlError, match="non-public address"):
        validate_discovered_target("https://split-horizon.example/")


def test_private_network_opt_out_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))],
    )
    approved = validate_discovered_target("http://localhost/lab", allow_private_networks=True)
    assert approved == "http://localhost/lab"


# ---------------------------------------------------- Untrusted text hardening


def test_html_markup_is_removed_before_storage() -> None:
    """Finding: page titles and snippets were stored verbatim, carrying markup
    into exports and into any renderer that forgets to escape."""
    dirty = "<script>alert(1)</script>Spark <b>Coffee</b>"
    cleaned = sanitize_text(dirty, max_length=MAX_NAME_LENGTH)
    assert cleaned is not None
    assert "<" not in cleaned and "script" not in cleaned.lower()
    assert "Coffee" in cleaned


def test_control_and_zero_width_characters_are_removed() -> None:
    cleaned = sanitize_text("Spark\x00Coffee\x1b[31m") or ""
    assert "\x00" not in cleaned and "\x1b" not in cleaned
    assert cleaned.startswith("Spark Coffee")
    # A zero-width space made two visually identical names compare unequal.
    assert sanitize_text(f"Sp{ZERO_WIDTH}ark") == "Sp ark"


def test_overlong_scraped_text_is_clipped_not_dropped() -> None:
    assert len(sanitize_text("A" * 50_000, max_length=MAX_NAME_LENGTH)) == MAX_NAME_LENGTH


def test_oversized_contact_fields_are_rejected_not_truncated_silently() -> None:
    """A 5 MB 'email' would fail at the INSERT with an opaque database error."""
    assert normalize_email("a" * 400 + "@example.com") is None
    assert normalize_email("x@example.com") == "x@example.com"
    near_limit = normalize_email("a" * (MAX_EMAIL_LENGTH - 20) + "@example.com")
    assert near_limit is not None and len(near_limit) <= MAX_EMAIL_LENGTH
    assert normalize_phone("9" * 400, "IN") is None


def test_pipeline_sanitises_before_it_stores() -> None:
    item = DiscoveredItem(
        external_id=None,
        source_url="https://brewed.in/",
        title_hint="<img src=x onerror=alert(1)>Brewed Cafe",
        raw_data={"content": "x" * 20_000},
    )
    business = normalize_item(item, source_slug="searxng", retrieved_at=RETRIEVED)

    assert business.name is not None and "<" not in business.name
    assert business.description is not None and len(business.description) <= 4000


# --------------------------------------------------------- Query/resource bounds


@pytest.mark.parametrize(
    "category",
    [
        'cafe"]["shop',
        '"]; node["shop"]; out;',
        "cafe name]",
        "café",
        "a" * 60,
        # The value half is the same attack surface now that `key=value` is allowed.
        'amenity="cafe"]["shop',
        'amenity="cafe"; out count;',
        "amenity=",
        "=",
    ],
)
def test_overpass_refuses_category_injection(category: str) -> None:
    """Finding (High): the category string was interpolated into Overpass QL with
    no escaping. Overpass has no parameter binding, so a crafted tag broke out of
    the filter and could run arbitrary, arbitrarily expensive queries against a
    shared public instance."""
    adapter = OverpassAdapter(client=client_for(lambda request: httpx.Response(200, json={})))
    query = DiscoveryQuery(
        category=category,
        location=LocationSpec(center=(12.9, 77.5), radius_km=1),
        max_results=10,
    )
    with pytest.raises(UnsupportedQueryError, match="OSM tag"):
        adapter.build_query(query)


def test_overpass_radius_and_bounds_are_capped() -> None:
    adapter = OverpassAdapter(client=client_for(lambda request: httpx.Response(200, json={})))
    too_big = DiscoveryQuery(
        category="amenity=cafe",
        location=LocationSpec(center=(12.9, 77.5), radius_km=MAX_RADIUS_KM * 100),
    )
    with pytest.raises(UnsupportedQueryError, match="radius_km"):
        adapter.build_query(too_big)

    bad_coords = DiscoveryQuery(
        category="amenity=cafe", location=LocationSpec(center=(900.0, 77.5), radius_km=1)
    )
    with pytest.raises(UnsupportedQueryError, match="outside valid ranges"):
        adapter.build_query(bad_coords)


def test_overpass_clamps_the_element_limit() -> None:
    adapter = OverpassAdapter(client=client_for(lambda request: httpx.Response(200, json={})))
    body = adapter.build_query(
        DiscoveryQuery(
            category="amenity=cafe",
            location=LocationSpec(center=(12.9, 77.5), radius_km=1),
            max_results=999_999,
        )
    )
    assert "out center 1000;" in body


def test_overpass_configuration_must_be_an_origin() -> None:
    with pytest.raises(UnsafeUrlError):
        OverpassAdapter("https://overpass-api.de/api/interpreter?auth=token")


@pytest.mark.asyncio
async def test_searxng_keyword_fanout_is_capped() -> None:
    """Finding: one query could carry thousands of keywords, each multiplied by
    every page — a self-inflicted DoS that gets the instance blocked upstream."""
    adapter = SearxngAdapter("http://searxng.local", client=client_for(searxng_ok))
    query = DiscoveryQuery(keywords=tuple(f"term {i}" for i in range(MAX_KEYWORDS_PER_QUERY + 5)))
    with pytest.raises(QueryTooBroadError, match="keywords per query"):
        await adapter.discover(query)


@pytest.mark.asyncio
async def test_searxng_results_cap_is_configuration_proof() -> None:
    adapter = SearxngAdapter("http://searxng.local", client=client_for(searxng_ok))
    with pytest.raises(QueryTooBroadError, match="capped"):
        await adapter.discover(
            DiscoveryQuery(keywords=("coffee",), max_results=MAX_RESULTS_LIMIT + 1)
        )


@pytest.mark.asyncio
async def test_searxng_rejects_an_absurd_query_length() -> None:
    adapter = SearxngAdapter("http://searxng.local", client=client_for(searxng_ok))
    with pytest.raises(QueryTooBroadError, match="characters"):
        await adapter.discover(DiscoveryQuery(keywords=("coffee " * 200,)))


@pytest.mark.asyncio
async def test_redirects_are_not_followed() -> None:
    """A redirect would move the request to a host the configuration was never
    approved for, so 3xx must surface as a failure rather than a second hop."""
    requests_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/"})

    adapter = SearxngAdapter("http://searxng.local", client=client_for(handler))
    with pytest.raises(AdapterError):
        await adapter.discover(DiscoveryQuery(keywords=("coffee",)))

    assert len(requests_seen) == 1


def test_searxng_rejects_a_path_bearing_instance_url() -> None:
    with pytest.raises(UnsafeUrlError):
        SearxngAdapter("http://searxng.local/search?q=anything")


# ------------------------------------------------------------ Merge integrity


@pytest.mark.asyncio
async def test_a_confirmed_merge_keeps_both_sources_evidence() -> None:
    """Finding: dedup discarded the merged-away record, erasing the attribution
    that corroborated the survivor — the opposite of database-schema.md §12.2."""
    same_phone = "+91 98765 43210"
    first = StubAdapter(
        [
            DiscoveredItem(
                external_id="1",
                source_url="https://one.in/",
                title_hint="Spark Coffee",
                raw_data={"name": "Spark Coffee Roasters", "phone": same_phone},
            )
        ]
    )
    second = StubAdapter(
        [
            DiscoveredItem(
                external_id="2",
                source_url="https://two.in/listing",
                title_hint="Spark Coffee Roasters",
                raw_data={
                    "name": "Spark Coffee Roasters",
                    "phone": same_phone,
                    "website": "https://second.in",
                },
            )
        ]
    )
    store = InMemoryBusinessStore()

    report = await run_pipeline(
        [("searxng", first), ("overpass", second)],
        [DiscoveryQuery(keywords=("coffee",))],
        store=store,
    )

    assert report.counters.provenances_merged == 1
    stored = await store.all()
    assert len(stored) == 1
    slugs = {attribution.source_slug for attribution in stored[0].attributions}
    assert slugs == {"searxng", "overpass"}


# -------------------------------------------------------- Logging and config


def test_hostile_correlation_id_is_neither_echoed_nor_logged() -> None:
    """Finding: the inbound header was length-checked only. Escape sequences
    survive JSON encoding, reach a terminal log viewer, and the value is
    reflected into a response header."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    hostile = "\x1b[31mFORGED\x1b[0m|forged"
    with TestClient(create_app()) as client:
        echoed = client.get("/health/live", headers={"X-Correlation-ID": hostile}).headers[
            "X-Correlation-ID"
        ]
        assert echoed != hostile
        assert "\x1b" not in echoed and "|" not in echoed
        assert all(character.isalnum() or character in "._-" for character in echoed)

        clean = "trace-abc_123.def"
        again = client.get("/health/live", headers={"X-Correlation-ID": clean})
        assert again.headers["X-Correlation-ID"] == clean


def test_request_logging_omits_the_query_string(capsys: pytest.CaptureFixture[str]) -> None:
    """OAuth codes and tokens arrive in query strings. The access log line must
    carry the path only, or every login writes a secret to disk."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as client:
        client.get("/health/ready?access_token=SEARCRETMATERIAL&code=alsosecret")

    captured = capsys.readouterr().out
    assert "SEARCRETMATERIAL" not in captured
    assert "alsosecret" not in captured
    assert "/health/ready" in captured


def test_production_refuses_wildcard_cors_with_credentials() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        signing_secret="x" * 32,
        cookie_secure=True,
        database_url="postgresql+asyncpg://u:p@db.internal:5432/sparkxflow",
        cors_origins=["*"],
    )
    assert any("CORS" in problem for problem in settings.validate_for_startup())


@pytest.mark.parametrize(
    ("field", "value"),
    [("searxng_max_pages", 999), ("session_ttl_hours", 0), ("searxng_timeout_seconds", 3600.0)],
)
def test_runaway_configuration_is_refused_at_load_time(field: str, value: int) -> None:
    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: value})


# ----------------------------------------------------------------- Scoring


def test_negative_weight_rules_are_rejected() -> None:
    """A negative weight could push a published score below zero. The database
    forbids it; the evaluator must not be more permissive than the schema."""
    rules = [ScoringRule("Bad", "name_present", -50, Operator.EQ, True)]
    with pytest.raises(ValueError, match="invalid weight"):
        evaluate({"name_present": True}, rules)


def test_non_finite_weight_is_rejected() -> None:
    rules = [ScoringRule("NaN", "name_present", float("nan"), Operator.EQ, True)]
    with pytest.raises(ValueError, match="invalid weight"):
        evaluate({"name_present": True}, rules)


# ---------------------------------------------------------------- CSV / auth


def test_newlines_in_scraped_text_cannot_forge_extra_rows() -> None:
    text = to_csv([{"name": "Spark\r\nEvil", "city": "Bengaluru"}])
    rows = list(csv.reader(io.StringIO(text)))
    # Header plus exactly one data row: the CRLF sits inside a quoted field.
    assert len(rows) == 2
    assert rows[1][0] == "Spark\r\nEvil"


def test_login_verification_does_not_leak_account_existence() -> None:
    """A missing account must cost the same as a wrong password, or the login
    form becomes an enumeration oracle."""
    existing = hash_password("correct horse battery staple")

    assert verify_password_for_login("wrong", existing) is False
    assert verify_password_for_login("wrong", None) is False
    assert verify_password_for_login("correct horse battery staple", existing) is True
