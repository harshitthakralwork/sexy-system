from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

DuplicateStrategy = Literal["skip", "merge", "create"]


class ExportModuleOut(BaseModel):
    """One exportable thing, with the filters and columns it understands."""

    key: str
    label: str
    filters: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    # Which filters take a yes/no and which take a number. The UI needs these
    # to offer the right control rather than guessing from the name.
    boolean_filters: list[str] = Field(default_factory=list)
    numeric_filters: list[str] = Field(default_factory=list)


class ExportCatalogueOut(BaseModel):
    modules: list[ExportModuleOut]
    formats: list[str]


class ExportRequestIn(BaseModel):
    module: str = Field(max_length=50)
    format: str = Field(default="csv", max_length=20)
    filters: dict[str, Any] = Field(default_factory=dict)
    selected_fields: list[str] | None = None


class ExportJobOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    module: str
    export_format: str
    status: str
    filters: dict[str, Any] = Field(default_factory=dict)
    selected_fields: list[str] = Field(default_factory=list)
    total_records: int | None = None
    error_details: dict[str, Any] | None = None
    created_at: datetime
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    downloadable: bool = False


class ExportJobListOut(BaseModel):
    items: list[ExportJobOut]
    total: int


class ImportFieldOut(BaseModel):
    key: str
    label: str


class ImportVocabularyOut(BaseModel):
    """Everything the operator needs to build a mapping."""

    fields: list[ImportFieldOut]
    duplicate_strategies: list[str]
    formats: list[str]


class ImportUploadOut(BaseModel):
    """What the uploaded file turned out to contain."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    file_name: str
    file_format: str
    status: str
    columns: list[str] = Field(default_factory=list)
    suggested_mapping: dict[str, str] = Field(default_factory=dict)
    total_rows: int = 0
    processed_rows: int = 0
    failed_rows: int = 0
    error_details: dict[str, Any] | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ImportRunIn(BaseModel):
    """The mapping the operator confirmed, and what to do about duplicates."""

    mapping: dict[str, str] = Field(default_factory=dict)
    duplicate_strategy: DuplicateStrategy = "skip"


class ImportJobOut(ImportUploadOut):
    mapping_config: dict[str, Any] = Field(default_factory=dict)


class ImportJobListOut(BaseModel):
    items: list[ImportJobOut]
    total: int
