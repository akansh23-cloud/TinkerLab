from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol


class CandidateGenerator(Protocol):
    """Phase-3 deterministic candidate-generation boundary.

    Concrete strategies may retrieve known materials or emit hypothesis proposal payloads,
    but must operate only on an explicitly validated/versioned search-space context.
    """
    key: str
    version: str
    supported_material_families: set[str]
    required_inputs: set[str]
    creates_hypotheses: bool
    deterministic: bool
    maximum_safe_candidate_count: int

    def validate_search_space(self, context: dict[str, Any]) -> list[dict[str, Any]]: ...
    def generate(self, context: dict[str, Any]) -> Iterable[dict[str, Any]]: ...


class PropertyPredictor(Protocol):
    """Future Phase-4 boundary. Phase 3 has no implementation."""
    def predict(self, material: dict[str, Any], property_key: str) -> dict[str, Any]: ...


class SimulationAdapter(Protocol):
    """Phase-6 physics/simulation provider contract.

    Adapters are explicitly code-registered. No import path, executable path, container image,
    script or plugin may ever be supplied through an API payload. Every adapter must be able to
    refuse cleanly: an unavailable runtime or a missing registered artifact returns a typed
    refusal rather than a fabricated number.
    """

    @property
    def key(self) -> str: ...

    @property
    def contract_version(self) -> str: ...

    def capabilities(self) -> "SimulationCapabilities": ...
    def check_availability(self) -> "ProviderAvailability": ...
    def validate_target(self, context: dict[str, Any]) -> "ApplicabilityDecision": ...
    def build_inputs(self, context: dict[str, Any]) -> "InputBundle": ...
    def command_descriptor(self, context: dict[str, Any]) -> "SafeCommandDescriptor | None": ...
    def execute(self, context: dict[str, Any]) -> dict[str, Any]: ...
    def parse_outputs(self, context: dict[str, Any]) -> dict[str, Any]: ...
    def assess_convergence(self, context: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class SimulationCapabilities:
    method_family: str
    supported_method_keys: tuple[str, ...]
    supported_representation_types: tuple[str, ...]
    supported_representation_formats: tuple[str, ...]
    supported_material_families: tuple[str, ...]
    supported_property_keys: tuple[str, ...]
    required_artifact_types: tuple[str, ...]
    fidelity: str
    deterministic: bool
    execution_supported: bool
    maximum_target_size: int
    maximum_wall_time_seconds: int
    resource_class: str
    known_limitations: tuple[str, ...]


@dataclass(frozen=True)
class ProviderAvailability:
    available: bool
    reason_code: str
    detail: str
    executable_name: str | None = None
    executable_version: str | None = None
    executable_path_recorded: bool = False


@dataclass(frozen=True)
class ApplicabilityDecision:
    status: str
    reasons: tuple[dict[str, Any], ...]
    missing_representation_types: tuple[str, ...] = ()
    missing_artifact_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class InputBundle:
    builder_key: str
    builder_version: str
    normalized_parameters: dict[str, Any]
    files: dict[str, str]
    artifact_references: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class SafeCommandDescriptor:
    """Executable is an allowlist *key*, never a caller-supplied path, and argv is never a shell string."""
    executable_key: str
    argv: tuple[str, ...]
    stdin_file: str | None
    timeout_seconds: int
    environment_allowlist: tuple[str, ...]


class ComputeBackend(Protocol):
    """Future extraction seam for HPC/queue execution. Phase 6 implements bounded local execution only."""

    @property
    def key(self) -> str: ...

    def submit(self, descriptor: SafeCommandDescriptor, workdir: str) -> dict[str, Any]: ...


class MaterialDataProvider(Protocol):
    key: str
    version: str
    def capabilities(self) -> set[str]: ...
    def normalize(self, raw_record: dict[str, Any]) -> dict[str, Any]: ...


class ExperimentOptimizer(Protocol):
    """Future optimization boundary. Phase 3 has no implementation."""
    def recommend_next(self, experiment_state: dict[str, Any]) -> list[dict[str, Any]]: ...


class NoveltyProvider(Protocol):
    """Future novelty/IP boundary. Phase 3 has no implementation."""
    def assess(self, candidate: dict[str, Any]) -> dict[str, Any]: ...
