from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Platform --------------------------------------------------------------


class SocialPlatformOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    adapter_key: str
    capabilities: dict = Field(default_factory=dict)
    limitations: dict = Field(default_factory=dict)
    is_enabled: bool
    health_status: str
    last_run_at: datetime | None = None
    last_error: str | None = None


# --- Research queries -------------------------------------------------------


class SocialResearchQueryCreateIn(BaseModel):
    platform_slug: str = Field(min_length=1, max_length=100)
    query_config: dict = Field(default_factory=dict)


class SocialResearchQueryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform_id: uuid.UUID
    platform_slug: str
    query_config: dict
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    last_run_error: str | None = None
    created_at: datetime
    updated_at: datetime


class SocialResearchQueryListOut(BaseModel):
    items: list[SocialResearchQueryOut]
    total: int
    limit: int
    offset: int


# --- Content ---------------------------------------------------------------


class SocialContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform_id: uuid.UUID
    platform_slug: str
    research_query_id: uuid.UUID | None = None
    profile_id: uuid.UUID | None = None
    external_id: str
    content_url: str | None = None
    content_type: str
    content_text: str | None = None
    published_at: datetime | None = None
    engagement_data: dict = Field(default_factory=dict)
    author_username: str | None = None
    author_profile_url: str | None = None
    collected_at: datetime


class SocialContentListOut(BaseModel):
    items: list[SocialContentOut]
    total: int
    limit: int
    offset: int


class SocialRunOut(BaseModel):
    query_id: uuid.UUID
    platform_slug: str
    status: str
    collected: int
    stored_new: int
    duplicates: int
    error: str | None = None


class SocialLinkIn(BaseModel):
    business_id: uuid.UUID


class SocialLinkOut(BaseModel):
    business_id: uuid.UUID
    platform: str
    profile_url: str


# --- Intelligence tracks, runs, results, saved items (engine) ---------------

TRACK_TYPES = ("demand", "business")


def _validate_frequency(value: dict | None) -> dict | None:
    if value is None:
        return None
    has_interval = "interval_seconds" in value
    has_cron = "cron" in value
    if has_interval == has_cron:
        raise ValueError(
            "frequency_config must contain exactly one of 'interval_seconds' or 'cron'"
        )
    if has_interval:
        seconds = value["interval_seconds"]
        if not isinstance(seconds, int) or seconds < 60:
            raise ValueError("interval_seconds must be an integer >= 60")
    else:
        cron = value["cron"]
        if not isinstance(cron, str) or len(cron.split()) != 5:
            raise ValueError("cron must be a five-field expression")
    return value


class TrackCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    track_type: str = Field(default="demand")
    keywords: list[str] = Field(default_factory=list)
    exact_phrases: list[str] = Field(default_factory=list)
    excluded_terms: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    language: str | None = Field(default=None, max_length=50)
    geography: str | None = Field(default=None, max_length=150)
    date_from: datetime | None = None
    date_to: datetime | None = None
    source_config: dict = Field(default_factory=dict)
    frequency_config: dict | None = None
    max_results_per_run: int = Field(default=50, ge=1, le=200)
    is_enabled: bool = True

    model_config = ConfigDict()

    @staticmethod
    def _clean_list(values: list[str]) -> list[str]:
        out: list[str] = []
        for raw in values:
            item = str(raw).strip()
            if item and item not in out:
                out.append(item)
        return out

    @staticmethod
    def _validate_term_count(values: list[str], label: str) -> list[str]:
        # Bound fan-out: an unbounded term list multiplies upstream requests.
        if len(values) > 20:
            raise ValueError(f"Too many {label} (max 20)")
        for item in values:
            if len(item) > 200:
                raise ValueError(f"{label} entry too long (max 200 chars)")
        return values

    @field_validator("track_type")
    @classmethod
    def _valid_type(cls, value: str) -> str:
        if value not in TRACK_TYPES:
            raise ValueError(f"track_type must be one of {', '.join(TRACK_TYPES)}")
        return value

    @field_validator("keywords", "exact_phrases", "excluded_terms", "hashtags", "platforms")
    @classmethod
    def _clean_terms(cls, value: list[str]) -> list[str]:
        cleaned = TrackCreateIn._clean_list(value)
        return TrackCreateIn._validate_term_count(cleaned, "term")

    @field_validator("frequency_config")
    @classmethod
    def _valid_freq(cls, value: dict | None) -> dict | None:
        return _validate_frequency(value)

    def has_search_terms(self) -> bool:
        return bool(self.keywords or self.exact_phrases or self.hashtags or self.source_config)


class TrackUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    track_type: str | None = None
    keywords: list[str] | None = None
    exact_phrases: list[str] | None = None
    excluded_terms: list[str] | None = None
    hashtags: list[str] | None = None
    platforms: list[str] | None = None
    language: str | None = Field(default=None, max_length=50)
    geography: str | None = Field(default=None, max_length=150)
    date_from: datetime | None = None
    date_to: datetime | None = None
    source_config: dict | None = None
    frequency_config: dict | None = None
    max_results_per_run: int | None = Field(default=None, ge=1, le=200)
    is_enabled: bool | None = None
    is_paused: bool | None = None

    @field_validator("track_type")
    @classmethod
    def _valid_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value not in TRACK_TYPES:
            raise ValueError(f"track_type must be one of {', '.join(TRACK_TYPES)}")
        return value

    @field_validator("frequency_config")
    @classmethod
    def _valid_freq(cls, value: dict | None) -> dict | None:
        return _validate_frequency(value)


class TrackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    track_type: str
    keywords: list
    exact_phrases: list
    excluded_terms: list
    hashtags: list
    platforms: list
    language: str | None = None
    geography: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    source_config: dict = Field(default_factory=dict)
    frequency_config: dict | None = None
    max_results_per_run: int
    is_enabled: bool
    is_paused: bool
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TrackListOut(BaseModel):
    items: list[TrackOut]
    total: int
    limit: int
    offset: int


class DiscoveryRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    track_id: uuid.UUID | None = None
    status: str
    trigger_type: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    sources_attempted: list = Field(default_factory=list)
    queries_attempted: int
    results_returned: int
    stored_new: int
    duplicates: int
    review_flagged: int
    classification_counts: dict = Field(default_factory=dict)
    error_summary: str | None = None
    duration_ms: int | None = None
    created_at: datetime


class DiscoveryRunListOut(BaseModel):
    items: list[DiscoveryRunOut]
    total: int
    limit: int
    offset: int


class TrackRunOut(BaseModel):
    run_id: uuid.UUID
    status: str


class IntelligenceResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform_id: uuid.UUID
    external_id: str
    content_type: str
    title: str | None = None
    snippet: str | None = None
    content_text: str | None = None
    content_url: str | None = None
    canonical_url: str | None = None
    published_at: datetime | None = None
    discovered_at: datetime | None = None
    retrieval_status: str | None = None
    track_type: str | None = None
    classification: str | None = None
    confidence_score: float | None = None
    classification_method: str | None = None
    matched_terms: list = Field(default_factory=list)
    evidence: list = Field(default_factory=list)
    needs_review: bool
    source_attribution: list = Field(default_factory=list)
    collected_at: datetime
    author_username: str | None = None
    platform_slug: str | None = None


class IntelligenceListOut(BaseModel):
    items: list[IntelligenceResultOut]
    total: int
    limit: int
    offset: int


class SavedItemIn(BaseModel):
    note: str | None = Field(default=None, max_length=4000)
    tags: list[str] = Field(default_factory=list)


class SavedItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content_id: uuid.UUID
    note: str | None = None
    tags: list = Field(default_factory=list)
    converted_business_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class SavedItemOutWithResult(SavedItemOut):
    result: IntelligenceResultOut | None = None
