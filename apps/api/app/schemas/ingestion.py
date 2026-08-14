from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ImportRequest(BaseModel):
    organisation_id: str
    input_format: Literal["json", "csv"]
    content: str = Field(min_length=2, max_length=2_000_000)
    provider_key: str = "local_import"
    idempotency_key: str | None = Field(default=None, max_length=120)


class ImportPreviewOut(BaseModel):
    payload_checksum: str
    format: str
    valid: bool
    material_count: int
    observation_count: int
    warnings: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    normalized_preview: list[dict[str, Any]]


class ImportCommitOut(BaseModel):
    import_id: str
    status: str
    idempotent_replay: bool
    payload_checksum: str
    summary: dict[str, Any]
    errors: list[dict[str, Any]]


class ImportBatchOut(BaseModel):
    id: str
    organisation_id: str
    provider_id: str
    input_format: str
    payload_checksum: str
    idempotency_key: str | None
    status: str
    summary: dict[str, Any]
    errors: list[dict[str, Any]]
    created_at: datetime
    committed_at: datetime | None
