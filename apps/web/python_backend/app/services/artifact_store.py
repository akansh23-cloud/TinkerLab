"""Content store for approved scientific artifacts (pseudopotentials, potentials, databases).

Design rules, all structural:

  * Content is **ingested** by an operator or the seed from a path the *server* chooses. No API
    payload ever supplies a source path, and ingestion is not reachable from any HTTP route.
  * Ingested content is addressed by its SHA-256 digest inside one controlled root. A stored file
    name is therefore never attacker-influenced.
  * Materializing content into a job working directory copies from the store only, through
    ``safe_join``, and re-verifies the digest first. A tampered store file is refused, not used.
  * Nothing here downloads anything. Ever.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from app.services.simulation_runtime import UnsafeExecutionRequest, safe_join

ARTIFACT_STORE_VERSION = "artifact-store-v1"
MAX_ARTIFACT_CONTENT_BYTES = 32 * 1024 * 1024

# Operator-controlled root. Overridable only through server configuration, never through a request.
ARTIFACT_STORE_ROOT = os.environ.get("TINKERLAB_ARTIFACT_STORE", "/var/lib/tinkerlab/artifacts")


class ArtifactStoreError(RuntimeError):
    pass


def store_root() -> str:
    root = os.path.realpath(ARTIFACT_STORE_ROOT)
    os.makedirs(root, mode=0o700, exist_ok=True)
    return root


def file_digest(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_content_available(checksum: str) -> bool:
    if not _valid_digest(checksum):
        return False
    return os.path.isfile(os.path.join(store_root(), checksum))


def _valid_digest(checksum: str) -> bool:
    return isinstance(checksum, str) and len(checksum) == 64 and all(c in "0123456789abcdef" for c in checksum)


def ingest_file(source_path: str | Path) -> tuple[str, int]:
    """Copy operator-selected content into the store. Returns (sha256, byte_size).

    Server-side only. Called from the seed and from administrative tooling — never from a route.
    """
    source = Path(source_path)
    if not source.is_file() or source.is_symlink():
        raise ArtifactStoreError(f"Artifact source is not a regular file: {source_path}")
    size = source.stat().st_size
    if size > MAX_ARTIFACT_CONTENT_BYTES:
        raise ArtifactStoreError(f"Artifact exceeds the {MAX_ARTIFACT_CONTENT_BYTES}-byte store bound")
    checksum = file_digest(source)
    target = os.path.join(store_root(), checksum)
    if not os.path.exists(target):
        shutil.copyfile(source, target)
        os.chmod(target, 0o400)
    return checksum, size


def materialize(checksum: str, workdir: str, file_name: str, subdirectory: str | None = None) -> str:
    """Copy stored content into a job workdir under a server-chosen name.

    The digest is re-verified before use: a store file that no longer matches its address is a
    corruption or tampering signal, and the job must fail rather than silently use it.
    """
    if not _valid_digest(checksum):
        raise UnsafeExecutionRequest("Artifact checksum is not a valid SHA-256 digest")
    source = os.path.join(store_root(), checksum)
    if not os.path.isfile(source):
        raise ArtifactStoreError(f"Approved artifact content {checksum[:12]} is not present in the store")
    if file_digest(source) != checksum:
        raise ArtifactStoreError(f"Stored artifact {checksum[:12]} failed digest re-verification; refusing to use it")
    destination_dir = workdir
    if subdirectory:
        destination_dir = safe_join(workdir, subdirectory)
        os.makedirs(destination_dir, mode=0o700, exist_ok=True)
    destination = safe_join(destination_dir, file_name)
    shutil.copyfile(source, destination)
    return destination
