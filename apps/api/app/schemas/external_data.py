from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ExternalIngestRequest(BaseModel):
    provider: Literal["materials_project", "pubchem", "epa_comptox", "optimade"]
    dataset_key: str = Field(min_length=1, max_length=160)
    query: dict[str, Any] = Field(default_factory=dict)
    commercial_context: bool = True
    requirement_temperature_k: float | None = Field(default=None, ge=0, le=10000)
    optimade_base_url: str | None = Field(default=None, max_length=500)
    optimade_provider_id: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def validate_provider_fields(self) -> "ExternalIngestRequest":
        if len(self.query) > 30:
            raise ValueError("query contains too many parameters")
        try:
            encoded_query = json.dumps(self.query, sort_keys=True, separators=(",", ":"), default=str)
        except (TypeError, ValueError) as exc:
            raise ValueError("query must be JSON-serializable") from exc
        if len(encoded_query.encode("utf-8")) > 20_000:
            raise ValueError("query payload is too large")
        if self.provider == "optimade":
            if not self.optimade_base_url or not self.optimade_provider_id:
                raise ValueError("OPTIMADE ingestion requires optimade_base_url and optimade_provider_id")
        return self
