from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

HEALTH_WORKING = "working"
HEALTH_DEGRADED = "degraded"
HEALTH_FAILED = "failed"
HEALTH_UNKNOWN = "unknown"


class AdapterError(Exception):
    """A source could not do what was asked, for a reason we can name.

    ``classification`` is deliberately coarse and honest. There is no
    classification that means "worked around the block" — access denial is
    reported as such (PRD section 17, master prompt section 9).
    """

    def __init__(
        self, message: str, *, classification: str = "error", retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.message = message
        self.classification = classification
        self.retryable = retryable


class AccessDeniedError(AdapterError):
    """The source refused the request (bot protection, auth wall, 403/429)."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message, classification="access_denied", retryable=retryable)


class RateLimitedError(AdapterError):
    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message, classification="rate_limited", retryable=retryable)


class UnsupportedQueryError(AdapterError):
    """The caller asked for something this source cannot answer."""

    def __init__(self, message: str) -> None:
        super().__init__(message, classification="unsupported_query", retryable=False)


class MalformedResponseError(AdapterError):
    def __init__(self, message: str) -> None:
        super().__init__(message, classification="malformed_response", retryable=True)


@dataclass(frozen=True)
class AdapterCapabilities:
    """What a source can actually do, so the UI never promises more.

    `geographic_coverage` and `limitations` exist because sources are not
    interchangeable: Overpass is strong for mapped chains and weak for an
    unmapped local shop, and that must be visible to the user.
    """

    adapter_key: str
    name: str
    slug: str
    category: str
    supported_query_types: tuple[str, ...]
    supported_filters: tuple[str, ...]
    available_fields: tuple[str, ...]
    geographic_coverage: str
    access_requirements: tuple[str, ...] = ()
    rate_limit_notes: str = ""
    terms_notes: str = ""
    max_results_per_query: int | None = None


@dataclass(frozen=True)
class LocationSpec:
    """Geographic scope of a query. Radius in km; bbox for map rectangles."""

    query_bbox: tuple[float, float, float, float] | None = None
    center: tuple[float, float] | None = None
    radius_km: float | None = None
    place_name: str | None = None

    def __post_init__(self) -> None:
        if self.query_bbox is not None:
            west, south, east, north = self.query_bbox
            if not (west <= east and south <= north):
                raise ValueError("query_bbox must be ordered (west, south, east, north)")
        if self.center is not None and self.radius_km is not None and self.radius_km <= 0:
            raise ValueError("radius_km must be positive when a centre is given")


@dataclass(frozen=True)
class DiscoveryQuery:
    keywords: tuple[str, ...] = ()
    category: str | None = None
    location: LocationSpec | None = None
    country: str | None = None
    max_results: int = 50
    extra: dict[str, Any] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.keywords and self.category is None and self.location is None


@dataclass(frozen=True)
class DiscoveredItem:
    """One candidate record exactly as the source presented it.

    Nothing here is normalised or judged. Normalisation is the pipeline's job,
    and keeping it out of adapters is what lets a second source be added without
    re-deciding what a "business" is.
    """

    external_id: str | None
    source_url: str | None
    raw_data: dict[str, Any]
    title_hint: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class HealthResult:
    status: str
    detail: str | None = None
    response_time_ms: int | None = None

    @property
    def ok(self) -> bool:
        return self.status == HEALTH_WORKING


class DiscoveryAdapter(Protocol):
    """Contract every source implements (architecture.md section 9.1).

    ``discover`` must not raise for "no results" — an empty list is a valid,
    honest outcome and is distinct from a failure, which must raise AdapterError.
    """

    @property
    def capabilities(self) -> AdapterCapabilities: ...

    async def validate_config(self, config: dict[str, Any]) -> None: ...

    async def discover(self, query: DiscoveryQuery) -> list[DiscoveredItem]: ...

    async def health_check(self) -> HealthResult: ...
