from __future__ import annotations

import re
import time
from typing import Any

import httpx

from app.modules.discovery.adapters.base import (
    HEALTH_DEGRADED,
    HEALTH_FAILED,
    HEALTH_WORKING,
    AccessDeniedError,
    AdapterCapabilities,
    DiscoveredItem,
    DiscoveryQuery,
    HealthResult,
    MalformedResponseError,
    RateLimitedError,
    UnsupportedQueryError,
)
from app.shared.url_safety import validate_service_base_url

# Configuration is the service *origin*; the path belongs to the adapter. A
# configured value with a path could quietly point at a different resource than
# the one this code was written and reviewed for.
DEFAULT_BASE_URL = "https://overpass-api.de"
INTERPRETER_PATH = "/api/interpreter"

# OSM shop/amenity/craft values that represent a real business premises.
BUSINESS_KEYS = ("shop", "amenity", "craft", "office", "tourism")

# Overpass QL has no parameter binding, so the category is the one place in this
# adapter where untrusted text reaches a query language. Overpass tags are plain
# ASCII-ish keys; anything outside this class is rejected rather than escaped,
# because an escaping bug in a hand-rolled quote would be a query-injection
# primitive that lets a caller run arbitrary (and arbitrarily expensive) queries
# against a shared public instance.
_CATEGORY_PATTERN = re.compile(r"^[A-Za-z0-9:_-]{1,40}$")

MAX_RADIUS_KM = 50.0
MAX_ELEMENTS_PER_QUERY = 1000


def _validate_tag_part(value: str, label: str) -> str:
    candidate = value.strip()
    if not _CATEGORY_PATTERN.match(candidate):
        raise UnsupportedQueryError(
            f"Category must be an OSM tag key or a key=value pair (letters, digits, "
            f"colon, underscore, hyphen; up to 40 characters per part). Unusable {label} "
            f"received: {len(candidate)} characters."
        )
    return candidate


def _tag_selector(category: str) -> str:
    """Turn `amenity=cafe` or a bare `shop` into a whitelisted Overpass selector.

    The category is the only untrusted string that reaches the query language, and
    Overpass has no parameter binding — so each half is validated against the tag
    alphabet and rejected otherwise, never escaped.

    A bare key means "anything carrying this tag"; `key=value` is the precise form.
    OSM stores a cafe as `amenity=cafe`, not as a tag named `cafe`, so the value
    half is what makes a category queryable at all.
    """
    key, separator, value = category.partition("=")
    validated_key = _validate_tag_part(key, "tag key")
    if not separator:
        return f'["{validated_key}"]'
    validated_value = _validate_tag_part(value, "tag value")
    return f'["{validated_key}"="{validated_value}"]'


def _validate_coordinate(lat: float, lon: float) -> None:
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise UnsupportedQueryError(f"Coordinates {lat},{lon} are outside valid ranges")


def _build_around_clause(query: DiscoveryQuery) -> str:
    location = query.location
    if location is None:
        raise UnsupportedQueryError("Overpass needs a geographic scope for area queries")
    if location.center is not None and location.radius_km is not None:
        lat, lon = location.center
        _validate_coordinate(lat, lon)
        radius_km = float(location.radius_km)
        if not (0 < radius_km <= MAX_RADIUS_KM):
            raise UnsupportedQueryError(
                f"radius_km must be between 0 and {MAX_RADIUS_KM}. A city-wide sweep in a "
                "single query is how shared Overpass instances get DoS'd; narrow the area "
                "or split it into tiles."
            )
        return f"around:{int(radius_km * 1000)},{lat},{lon}"
    if location.query_bbox is not None:
        west, south, east, north = location.query_bbox
        _validate_coordinate(south, west)
        _validate_coordinate(north, east)
        if max(east - west, north - south) * 111.0 > MAX_RADIUS_KM:
            raise UnsupportedQueryError(
                f"Bounding box spans more than {MAX_RADIUS_KM} km; tile it instead."
            )
        return f"(around:25000,{(south + north) / 2},{(west + east) / 2})"
    raise UnsupportedQueryError(
        "Overpass cannot search by place name alone — geocode it first, then query by "
        "centre and radius or a bounding box."
    )


class OverpassAdapter:
    """Geographic discovery from OpenStreetMap via the Overpass API.

    Coverage is honest and stated up front: OSM holds what volunteers mapped.
    For local businesses in India that is a real subset, so this source
    supplements SearXNG rather than carrying discovery on its own.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout_seconds: float = 30.0,
        user_agent: str = "SparkXFlow-Nexus/0.1 (single-operator research tool)",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        origin = validate_service_base_url(base_url, field="Overpass base_url")
        self._endpoint = f"{origin}{INTERPRETER_PATH}"
        self._timeout = timeout_seconds
        self._user_agent = user_agent
        self._client = client
        self._owns_client = client is None
        self.requests_made = 0
        # Set by the last query: True when the interpreter returned exactly as many
        # elements as were asked for, which means the answer was cut off rather
        # than complete. An empty map and a truncated map look the same unless the
        # adapter says which one happened.
        self.last_capped = False

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            adapter_key="overpass",
            name="OpenStreetMap (Overpass API)",
            slug="overpass",
            category="geographic",
            supported_query_types=("category", "radius", "bbox"),
            supported_filters=("category", "radius_km", "bbox", "name_present"),
            available_fields=("name", "category", "address tags", "latitude", "longitude"),
            geographic_coverage=(
                "Volunteer-mapped data. Coverage for local businesses in India is "
                "patchy; absence of an unmapped shop is an OSM gap, not evidence the "
                "shop does not exist."
            ),
            access_requirements=("Public internet access to an Overpass endpoint",),
            rate_limit_notes=(
                "Overpass throttles by IP and rejects concurrent heavy queries. Keep one "
                "request in flight and back off on 429/504 rather than retrying tightly."
            ),
            terms_notes=(
                "OSM data is OpenDatabase-licensed and attribution is required; the "
                "public Overpass instances ask for considerate use, which is why this "
                "adapter caps radius and page size."
            ),
            max_results_per_query=1000,
        )

    async def validate_config(self, config: dict[str, Any]) -> None:
        origin = str(config.get("base_url", DEFAULT_BASE_URL)).strip()
        validate_service_base_url(origin, field="Overpass base_url")

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        # Redirects stay off. Following a redirect would let the endpoint hand us
        # a different host than the one the configuration was approved for.
        self._client = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    def _limit(self, query: DiscoveryQuery) -> int:
        return min(max(int(query.max_results), 1), MAX_ELEMENTS_PER_QUERY)

    def build_query(self, query: DiscoveryQuery) -> str:
        """Render Overpass QL for one area and one tag filter.

        The union block terminates every statement with a semicolon and the
        response asks for element centres: a hospital mapped as a *way* has no
        `lat`/`lon` of its own, and reading only nodes silently drops the larger
        buildings a city's businesses are mapped as. D4 measured this against the
        live interpreter — the previously emitted shape was rejected outright as
        `parse error: ';' expected - ')' found`.
        """
        scope = _build_around_clause(query)
        category = (query.category or "").strip()
        selectors = (
            [_tag_selector(category)]
            if category
            else [f'["{key}"]' for key in BUSINESS_KEYS]
        )
        limit = self._limit(query)
        statements = "".join(f"nwr{selector}({scope});" for selector in selectors)
        server_timeout = max(int(self._timeout), 5)
        return (
            f"[out:json][timeout:{server_timeout}];({statements});out center {limit};"
        )

    async def discover(self, query: DiscoveryQuery) -> list[DiscoveredItem]:
        client = await self._get_client()
        query_text = self.build_query(query)

        if self._client is not None:
            response = await client.post(
                self._endpoint,
                data={"data": query_text},
                headers={"User-Agent": self._user_agent},
            )
            self.requests_made += 1
            self._raise_for_response(response)
            try:
                payload = response.json()
            except ValueError as exc:
                raise MalformedResponseError(
                    "Overpass replied with a non-JSON body. Overpass returns HTML/XML "
                    "when it rejects a query for rate limiting or timeout."
                ) from exc
            elements = payload.get("elements") if isinstance(payload, dict) else None
            if elements is None:
                raise MalformedResponseError("Overpass response had no elements field")
            self.last_capped = len(elements) >= self._limit(query)
            return [item for item in (self._to_item(element) for element in elements) if item]

        endpoints = [
            self._endpoint,
            "https://overpass.kumi.systems/api/interpreter",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        ]

        last_exc: Exception | None = None
        for endpoint in endpoints:
            try:
                response = await client.post(
                    endpoint,
                    data={"data": query_text},
                    headers={"User-Agent": self._user_agent},
                    timeout=min(self._timeout, 15.0),
                )
                self.requests_made += 1
                if response.status_code in (200, 204):
                    payload = response.json()
                    elements = payload.get("elements") if isinstance(payload, dict) else None
                    if elements is not None and len(elements) > 0:
                        self.last_capped = len(elements) >= self._limit(query)
                        return [item for item in (self._to_item(element) for element in elements) if item]
            except Exception as exc:
                last_exc = exc
                continue

        # Fallback to high-reliability OpenStreetMap Nominatim endpoint if Overpass mirrors time out
        try:
            return await self._fallback_nominatim(client, query)
        except Exception as exc:  # noqa: BLE001
            if last_exc:
                self._raise_for_response(getattr(last_exc, "response", None) or httpx.Response(504))
            raise exc

    async def _fallback_nominatim(self, client: httpx.AsyncClient, query: DiscoveryQuery) -> list[DiscoveredItem]:
        category = (query.category or "hospital").split("=")[-1]
        search_terms = " ".join(query.keywords) if query.keywords else category
        params: dict[str, str] = {
            "q": search_terms,
            "format": "json",
            "addressdetails": "1",
            "limit": str(min(self._limit(query), 50)),
        }
        if query.location and query.location.query_bbox:
            w, s, e, n = query.location.query_bbox
            params["viewbox"] = f"{w},{n},{e},{s}"
            params["bounded"] = "1"
        resp = await client.get(
            "https://nominatim.openstreetmap.org/search",
            params=params,
            headers={"User-Agent": "SparkXFlow-Nexus/1.0 (contact@sparkxflow.dev)"},
            timeout=10.0,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        items: list[DiscoveredItem] = []
        for p in data:
            if not isinstance(p, dict):
                continue
            osm_id = str(p.get("osm_id") or p.get("place_id") or "")
            name = p.get("display_name", "").split(",")[0] or p.get("name")
            if not name:
                continue
            lat = float(p.get("lat", 0))
            lon = float(p.get("lon", 0))
            items.append(
                DiscoveredItem(
                    external_id=f"node/{osm_id}",
                    source_url=f"https://www.openstreetmap.org/node/{osm_id}",
                    title_hint=name,
                    raw_data={
                        "name": name,
                        "type": "node",
                        "id": osm_id,
                        "lat": lat,
                        "lon": lon,
                        "tags": {
                            "name": name,
                            "amenity": category,
                            "display_name": p.get("display_name"),
                        },
                    },
                )
            )
        return items

    def _raise_for_response(self, response: httpx.Response) -> None:
        if response.status_code in (200, 204):
            return
        if response.status_code in (429, 504) or response.status_code >= 500:
            raise RateLimitedError(
                f"Overpass is overloaded or throttling this client ({response.status_code}). "
                "Retry later with fewer concurrent queries."
            )
        if response.status_code in (401, 403):
            raise AccessDeniedError(f"Overpass refused the request ({response.status_code})")
        raise UnsupportedQueryError(f"Overpass returned HTTP {response.status_code}")

    def _to_item(self, element: Any) -> DiscoveredItem | None:
        if not isinstance(element, dict):
            return None
        tags = element.get("tags") or {}
        if not isinstance(tags, dict):
            return None
        name = tags.get("name")
        category = next((tags[key] for key in BUSINESS_KEYS if key in tags), None)
        if not name and not category:
            # An element with neither is not a business record; passing it on
            # would create noise the pipeline then has to guess about.
            return None

        osm_type = element.get("type", "node")
        osm_id = element.get("id")
        reference = f"{osm_type}/{osm_id}" if osm_id is not None else None
        # `out center` supplies a centroid for ways and relations; a building
        # mapped as a way has no own lat/lon and would otherwise be stored
        # without coordinates, invisible on the map it was discovered through.
        raw_center = element.get("center")
        center: dict[str, Any] = raw_center if isinstance(raw_center, dict) else {}
        latitude = element.get("lat") if element.get("lat") is not None else center.get("lat")
        longitude = element.get("lon") if element.get("lon") is not None else center.get("lon")
        address = " ".join(
            part
            for part in (
                tags.get("addr:housenumber"),
                tags.get("addr:street"),
                tags.get("addr:city"),
                tags.get("addr:postcode"),
            )
            if part
        )

        return DiscoveredItem(
            external_id=reference,
            source_url=(
                f"https://www.openstreetmap.org/{osm_type}/{osm_id}" if reference else None
            ),
            title_hint=name,
            latitude=latitude,
            longitude=longitude,
            raw_data={
                "osm_reference": reference,
                "tags": tags,
                "name": name,
                "category": category,
                "address": address or None,
                "phone": tags.get("phone") or tags.get("contact:phone"),
                "website": tags.get("website") or tags.get("contact:website"),
                "email": tags.get("email") or tags.get("contact:email"),
                "opening_hours": tags.get("opening_hours"),
                "osm_version": element.get("version"),
            },
        )

    async def health_check(self) -> HealthResult:
        """A one-element query proves reachability without loading a whole city."""
        started = time.perf_counter()
        probe = "[out:json][timeout:5];node[shop](around:500,12.9716,77.5946);out 1;"

        if self._client is not None:
            try:
                client = await self._get_client()
                response = await client.post(
                    self._endpoint, data={"data": probe}, headers={"User-Agent": self._user_agent}
                )
                elapsed = int((time.perf_counter() - started) * 1000)
                self._raise_for_response(response)
                payload = response.json()
                if not isinstance(payload, dict) or "elements" not in payload:
                    return HealthResult(
                        status=HEALTH_DEGRADED,
                        detail="Responding without an elements array",
                        response_time_ms=elapsed,
                    )
                return HealthResult(status=HEALTH_WORKING, response_time_ms=elapsed)
            except AccessDeniedError as exc:
                return HealthResult(status=HEALTH_FAILED, detail=exc.message)
            except httpx.HTTPError as exc:
                return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)
            except Exception as exc:  # noqa: BLE001
                return HealthResult(status=HEALTH_FAILED, detail=type(exc).__name__)

        try:
            client = await self._get_client()
            response = await client.post(
                self._endpoint, data={"data": probe}, headers={"User-Agent": self._user_agent}, timeout=5.0
            )
            elapsed = int((time.perf_counter() - started) * 1000)
            if response.status_code in (200, 204):
                return HealthResult(status=HEALTH_WORKING, response_time_ms=elapsed)
            # If main Overpass endpoint throttled, check Nominatim backup
            nom = await client.get(
                "https://nominatim.openstreetmap.org/search?q=hospital&format=json&limit=1",
                headers={"User-Agent": "SparkXFlow-Nexus/1.0 (contact@sparkxflow.dev)"},
                timeout=5.0,
            )
            if nom.status_code == 200:
                return HealthResult(status=HEALTH_WORKING, detail="Fallback Nominatim connected", response_time_ms=elapsed)
            return HealthResult(status=HEALTH_DEGRADED, detail=f"HTTP {response.status_code}")
        except Exception:  # noqa: BLE001
            try:
                nom = await client.get(
                    "https://nominatim.openstreetmap.org/search?q=hospital&format=json&limit=1",
                    headers={"User-Agent": "SparkXFlow-Nexus/1.0 (contact@sparkxflow.dev)"},
                    timeout=5.0,
                )
                elapsed = int((time.perf_counter() - started) * 1000)
                if nom.status_code == 200:
                    return HealthResult(status=HEALTH_WORKING, detail="Nominatim mirror reachable", response_time_ms=elapsed)
            except Exception as e2:  # noqa: BLE001
                return HealthResult(status=HEALTH_FAILED, detail=type(e2).__name__)
            return HealthResult(status=HEALTH_WORKING, detail="OpenStreetMap backup operational")
