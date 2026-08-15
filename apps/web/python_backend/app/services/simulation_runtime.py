"""Phase-6 bounded local execution.

Safety properties this module is responsible for, all structural rather than advisory:

  * an executable is selected by an **allowlist key**, never by a caller-supplied path or name;
  * commands are argument arrays passed to ``subprocess.run``; ``shell=True`` is never used;
  * working directories are server-generated tokens under a single controlled root, and every
    path is re-checked to be inside that root before use (path-traversal protection);
  * the child environment is an allowlist, so no host secret is inherited;
  * wall-time timeout, stdout/stderr caps and artifact size caps are always applied;
  * nothing is ever downloaded during a run.

``ComputeBackend`` exists so an HPC/queue backend can be added later without changing callers.
Phase 6 implements bounded local execution only.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.contracts import SafeCommandDescriptor
from app.domain.enums import SimulationJobStatus

RUNNER_CONTRACT_VERSION = "local-runner-v1"
COMPUTE_BACKEND_KEY = "local_bounded_v1"

MAX_STDOUT_BYTES = 64_000
MAX_STDERR_BYTES = 32_000
MAX_ARTIFACT_BYTES = 256_000
MAX_TIMEOUT_SECONDS = 900
DEFAULT_TIMEOUT_SECONDS = 60

# Server-admin allowlist. An API caller can select a provider version; it can never introduce a
# new entry here, supply a path, or override the binary a key resolves to.
ALLOWED_EXECUTABLES: dict[str, tuple[str, ...]] = {
    "lammps": ("lmp", "lmp_serial", "lmp_mpi"),
    "quantum_espresso_pw": ("pw.x",),
}

# Only these variables are forwarded to a child process. Everything else (tokens, database URLs,
# cloud credentials) is dropped.
ENVIRONMENT_ALLOWLIST: tuple[str, ...] = ("PATH", "LANG", "LC_ALL", "HOME", "TMPDIR", "OMP_NUM_THREADS")

SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


class UnsafeExecutionRequest(ValueError):
    """Raised when a request would breach a structural safety rule. Never downgraded to a warning."""


@dataclass(frozen=True)
class ResourceRequest:
    cpu_count: int = 1
    memory_mb: int = 512
    wall_time_seconds: int = DEFAULT_TIMEOUT_SECONDS
    gpu_count: int = 0
    working_storage_mb: int = 64

    def as_dict(self) -> dict[str, Any]:
        return {
            "cpu_count": self.cpu_count, "memory_mb": self.memory_mb,
            "wall_time_seconds": self.wall_time_seconds, "gpu_count": self.gpu_count,
            "working_storage_mb": self.working_storage_mb,
            # Honest about what is actually enforced locally versus recorded as metadata.
            "enforced": ["wall_time_seconds", "stdout_bytes", "stderr_bytes", "artifact_bytes"],
            "metadata_only": ["cpu_count", "memory_mb", "gpu_count", "working_storage_mb"],
        }


@dataclass
class ExecutionOutcome:
    status: str
    exit_code: int | None
    failure_code: str | None
    stdout: str
    stderr: str
    stdout_truncated: bool
    stderr_truncated: bool
    elapsed_seconds: float
    output_files: dict[str, str] = field(default_factory=dict)


def workdir_token() -> str:
    return uuid.uuid4().hex


def _runtime_root() -> str:
    root = os.path.join(tempfile.gettempdir(), "tinkerlab-simulation")
    os.makedirs(root, mode=0o700, exist_ok=True)
    return os.path.realpath(root)


def safe_join(root: str, *parts: str) -> str:
    """Join and prove the result stays inside ``root``. Rejects traversal, absolute and odd names."""
    for part in parts:
        if not SAFE_FILENAME.match(part):
            raise UnsafeExecutionRequest(f"Unsafe path component rejected: {part!r}")
    candidate = os.path.realpath(os.path.join(root, *parts))
    root_real = os.path.realpath(root)
    if candidate != root_real and not candidate.startswith(root_real + os.sep):
        raise UnsafeExecutionRequest("Resolved path escapes the controlled simulation root")
    return candidate


def resolve_executable(executable_key: str) -> tuple[str | None, str | None]:
    """Resolve an allowlist key to a binary. Returns (resolved_path, binary_name)."""
    candidates = ALLOWED_EXECUTABLES.get(executable_key)
    if not candidates:
        return None, None
    for name in candidates:
        found = shutil.which(name)
        if found:
            return found, name
    return None, None


def probe_executable_version(executable_key: str, version_argv: tuple[str, ...] = ("-h",)) -> tuple[bool, str | None, str | None]:
    """Probe availability once. Callers cache per request; never probe per target."""
    resolved, name = resolve_executable(executable_key)
    if not resolved:
        return False, None, None
    try:
        completed = subprocess.run(  # noqa: S603 - argv array, allowlisted binary, no shell
            [resolved, *version_argv], capture_output=True, text=True, timeout=10,
            env=sanitized_environment(), cwd=_runtime_root(),
        )
    except (OSError, subprocess.SubprocessError):
        return True, name, None
    blob = f"{completed.stdout}\n{completed.stderr}"
    for line in blob.splitlines():
        if line.strip():
            return True, name, line.strip()[:120]
    return True, name, None


def sanitized_environment() -> dict[str, str]:
    env = {key: os.environ[key] for key in ENVIRONMENT_ALLOWLIST if key in os.environ}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    # Deterministic locale keeps solver number formatting stable across hosts.
    env.setdefault("LC_ALL", "C")
    return env


def sanitize_command_for_record(descriptor: SafeCommandDescriptor, binary_name: str | None) -> dict[str, Any]:
    """Persist an auditable command shape without leaking host paths or secrets."""
    return {
        "executable_key": descriptor.executable_key,
        "resolved_binary_name": binary_name,
        "argv": list(descriptor.argv),
        "stdin_file": descriptor.stdin_file,
        "timeout_seconds": descriptor.timeout_seconds,
        "environment_allowlist": list(descriptor.environment_allowlist),
        "shell": False,
        "runner_contract": RUNNER_CONTRACT_VERSION,
    }


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    encoded = text.encode(errors="replace")
    if len(encoded) <= limit:
        return text, False
    return encoded[:limit].decode(errors="replace") + "\n[TRUNCATED BY TINKERLAB OUTPUT CAP]", True


def content_checksum(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class LocalBoundedComputeBackend:
    """The only Phase-6 compute backend. Bounded, local, synchronous."""

    key = COMPUTE_BACKEND_KEY
    contract_version = RUNNER_CONTRACT_VERSION

    def prepare_workdir(self, token: str) -> str:
        workdir = safe_join(_runtime_root(), token)
        os.makedirs(workdir, mode=0o700, exist_ok=True)
        return workdir

    def write_inputs(self, workdir: str, files: dict[str, str]) -> dict[str, str]:
        written: dict[str, str] = {}
        for name, body in sorted(files.items()):
            path = safe_join(workdir, name)
            encoded = body.encode()
            if len(encoded) > MAX_ARTIFACT_BYTES:
                raise UnsafeExecutionRequest(f"Input artifact {name} exceeds the {MAX_ARTIFACT_BYTES}-byte bound")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(body)
            written[name] = body
        return written

    def submit(self, descriptor: SafeCommandDescriptor, workdir: str) -> dict[str, Any]:
        outcome = self.execute(descriptor, workdir)
        return {"status": outcome.status, "exit_code": outcome.exit_code, "failure_code": outcome.failure_code}

    def execute(self, descriptor: SafeCommandDescriptor, workdir: str) -> ExecutionOutcome:
        if descriptor.timeout_seconds <= 0 or descriptor.timeout_seconds > MAX_TIMEOUT_SECONDS:
            raise UnsafeExecutionRequest("Timeout must be positive and within the configured Phase-6 bound")
        resolved, binary_name = resolve_executable(descriptor.executable_key)
        if not resolved:
            return ExecutionOutcome(
                SimulationJobStatus.FAILED, None, "provider_executable_unavailable", "", "", False, False, 0.0,
            )
        # Every argument is a literal produced by a reviewed input builder; none is a shell string.
        argv = [resolved, *descriptor.argv]
        stdin_handle = None
        if descriptor.stdin_file:
            stdin_path = safe_join(workdir, descriptor.stdin_file)
            stdin_handle = open(stdin_path, encoding="utf-8")  # noqa: SIM115 - closed in finally
        started = time.monotonic()
        try:
            completed = subprocess.run(  # noqa: S603 - allowlisted binary, argv array, shell=False
                argv, cwd=workdir, env=sanitized_environment(), stdin=stdin_handle,
                capture_output=True, text=True, timeout=descriptor.timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired:
            return ExecutionOutcome(
                SimulationJobStatus.TIMED_OUT, None, "wall_time_exceeded", "", "", False, False,
                round(time.monotonic() - started, 6),
            )
        except OSError as exc:
            return ExecutionOutcome(
                SimulationJobStatus.FAILED, None, "process_launch_failed", "", str(exc)[:500], False, False,
                round(time.monotonic() - started, 6),
            )
        finally:
            if stdin_handle:
                stdin_handle.close()
        elapsed = round(time.monotonic() - started, 6)
        stdout, stdout_truncated = _truncate(completed.stdout, MAX_STDOUT_BYTES)
        stderr, stderr_truncated = _truncate(completed.stderr, MAX_STDERR_BYTES)
        status = SimulationJobStatus.COMPLETED if completed.returncode == 0 else SimulationJobStatus.FAILED
        return ExecutionOutcome(
            status, completed.returncode,
            None if completed.returncode == 0 else "non_zero_exit_code",
            stdout, stderr, stdout_truncated, stderr_truncated, elapsed,
        )

    def collect_outputs(self, workdir: str, names: tuple[str, ...]) -> dict[str, str]:
        collected: dict[str, str] = {}
        for name in names:
            try:
                path = safe_join(workdir, name)
            except UnsafeExecutionRequest:
                continue
            if not os.path.isfile(path):
                continue
            with open(path, encoding="utf-8", errors="replace") as handle:
                body = handle.read(MAX_ARTIFACT_BYTES + 1)
            collected[name] = body[:MAX_ARTIFACT_BYTES]
        return collected

    def cleanup(self, workdir: str) -> None:
        root = _runtime_root()
        real = os.path.realpath(workdir)
        if real.startswith(root + os.sep):
            shutil.rmtree(real, ignore_errors=True)


local_backend = LocalBoundedComputeBackend()
