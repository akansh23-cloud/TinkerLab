from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ProviderAdapter(Protocol):
    # Read-only members so immutable (frozen dataclass) adapters satisfy the contract.
    @property
    def key(self) -> str: ...

    @property
    def version(self) -> str: ...

    def capabilities(self) -> set[str]: ...
    def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class LocalImportProvider:
    key: str = "local_import"
    version: str = "2.0"

    def capabilities(self) -> set[str]:
        return {"json_import", "csv_import", "normalize"}

    def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any]:
        # Input parser already validates the documented local schema. Copying avoids hidden mutation.
        return {k: v for k, v in raw_record.items()}


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderAdapter] = {}
        provider: ProviderAdapter = LocalImportProvider()
        self._providers[provider.key] = provider

    def get(self, key: str) -> ProviderAdapter | None:
        return self._providers.get(key)

    def list(self) -> list[ProviderAdapter]:
        return list(self._providers.values())


provider_registry = ProviderRegistry()
