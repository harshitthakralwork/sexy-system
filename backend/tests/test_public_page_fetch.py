from __future__ import annotations

import httpx
import pytest

from app.modules.discovery import public_fetch
from app.modules.discovery.local_scraper import _select_official_website, _source_kind


@pytest.mark.asyncio
async def test_public_page_fetch_prefers_schema_org_and_collects_public_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = """
    <html><head>
      <title>Fallback title</title>
      <meta name="description" content="Public bakery profile">
      <script type="application/ld+json">
      {
        "@context":"https://schema.org",
        "@type":"LocalBusiness",
        "name":"Honest Bakery",
        "telephone":"+91 98765 43210",
        "email":"hello@honest.example",
        "address":{"streetAddress":"1 Market Road","addressLocality":"Hisar"},
        "aggregateRating":{"ratingValue":"4.6","reviewCount":"120"}
      }
      </script>
    </head><body>
      <a href="/contact">Contact</a>
      <a href="https://www.linkedin.com/company/honest-bakery">LinkedIn</a>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    monkeypatch.setattr(public_fetch, "validate_discovered_target", lambda value: value)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await public_fetch.fetch_public_page("https://honest.example", client=client)

    assert result.status == "ok"
    assert result.business_name == "Honest Bakery"
    assert result.phone is not None
    assert result.email == "hello@honest.example"
    assert result.address == "1 Market Road, Hisar"
    assert result.rating == 4.6
    assert result.review_count == 120
    assert result.contact_urls == ["https://honest.example/contact"]
    assert result.social_urls == ["https://www.linkedin.com/company/honest-bakery"]
    assert result.extraction_method == "schema_org_json_ld"


@pytest.mark.asyncio
async def test_directory_page_keeps_listing_separate_from_official_website(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    html = """
    <html><body>
      <a href="https://www.example-bakery.in">Official website</a>
      <a href="https://www.instagram.com/examplebakery">Instagram</a>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    monkeypatch.setattr(public_fetch, "validate_discovered_target", lambda value: value)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await public_fetch.fetch_public_page(
            "https://www.justdial.com/hisar/example-bakery", client=client
        )

    assert result.website_urls == ["https://www.example-bakery.in"]
    assert _source_kind("https://www.justdial.com/hisar/example-bakery") == "justdial"
    assert (
        _select_official_website(
            source_url="https://www.justdial.com/hisar/example-bakery",
            source_kind="justdial",
            candidates=result.website_urls,
        )
        == "https://www.example-bakery.in"
    )


@pytest.mark.asyncio
async def test_public_page_fetch_refuses_non_html_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"pdf")

    monkeypatch.setattr(public_fetch, "validate_discovered_target", lambda value: value)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await public_fetch.fetch_public_page("https://honest.example/file", client=client)

    assert result.status == "unsupported"
    assert result.extraction_method == "content_type_check"
