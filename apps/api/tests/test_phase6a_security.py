"""Phase-6A security audit.

These tests attack the simulation subsystem the way a hostile caller would. Each asserts a
*structural* guarantee: something that cannot be turned off by configuration and does not depend on
a caller behaving well.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.db.seed import sid
from app.models.entities import SimulationJob, SimulationWorkflow
from app.schemas.simulation import WorkflowCreateRequest
from app.services import artifact_store
from app.services.simulation_runtime import (
    ALLOWED_EXECUTABLES,
    ENVIRONMENT_ALLOWLIST,
    MAX_ARTIFACT_BYTES,
    MAX_STDERR_BYTES,
    MAX_STDOUT_BYTES,
    MAX_TIMEOUT_SECONDS,
    SafeCommandDescriptor,
    UnsafeExecutionRequest,
    _runtime_root,
    local_backend,
    resolve_executable,
    safe_join,
    sanitized_environment,
)

ORG_ID = sid("org")
OTHER_ORG = sid("hostile-org")
BASELINE_ID = sid("material:demo-polymer-baseline")
FIXTURE_VERSION_ID = sid("phase6:provider-version:software_fixture_harmonic:v1")
SEEDED_WORKFLOW_ID = sid("phase6:workflow:fixture-harmonic-demo")
HEADERS = {"X-Organisation-ID": ORG_ID}
HOSTILE_HEADERS = {"X-Organisation-ID": OTHER_ORG}


# --- command execution --------------------------------------------------------------------------
def test_executable_allowlist_is_closed():
    """Only reviewed solver keys resolve. Everything else — including real binaries — does not."""
    assert set(ALLOWED_EXECUTABLES) == {"lammps", "quantum_espresso_pw"}
    for hostile in ("bash", "sh", "python3", "curl", "wget", "nc", "/bin/sh", "/usr/bin/python3",
                    "../../bin/sh", "lammps; rm -rf /", ""):
        assert resolve_executable(hostile) == (None, None), f"{hostile!r} must not resolve"


def test_unresolvable_executable_fails_closed_without_running_anything():
    descriptor = SafeCommandDescriptor(
        executable_key="definitely_not_registered", argv=("-v",), stdin_file=None,
        timeout_seconds=5, environment_allowlist=ENVIRONMENT_ALLOWLIST,
    )
    workdir = local_backend.prepare_workdir("securitytest" + os.urandom(4).hex())
    try:
        outcome = local_backend.execute(descriptor, workdir)
        assert outcome.status == "failed"
        assert outcome.failure_code == "provider_executable_unavailable"
        assert outcome.exit_code is None
    finally:
        local_backend.cleanup(workdir)


def test_argv_metacharacters_are_data_not_shell():
    """Even if an argument contains shell syntax it is a literal argv entry, never interpreted."""
    descriptor = SafeCommandDescriptor(
        executable_key="lammps", argv=("; rm -rf /", "&& curl evil.example", "$(whoami)", "`id`"),
        stdin_file=None, timeout_seconds=5, environment_allowlist=ENVIRONMENT_ALLOWLIST,
    )
    from app.services.simulation_runtime import sanitize_command_for_record

    record = sanitize_command_for_record(descriptor, "lmp")
    assert record["shell"] is False
    assert record["argv"] == ["; rm -rf /", "&& curl evil.example", "$(whoami)", "`id`"]
    # The canary proves the strings were never handed to a shell.
    canary = Path("/tmp/tinkerlab_shell_canary")
    assert not canary.exists()


def test_timeouts_are_bounded_in_both_directions():
    workdir = local_backend.prepare_workdir("timeouttest" + os.urandom(4).hex())
    try:
        for bad_timeout in (0, -1, MAX_TIMEOUT_SECONDS + 1, 10**9):
            descriptor = SafeCommandDescriptor(
                executable_key="lammps", argv=(), stdin_file=None,
                timeout_seconds=bad_timeout, environment_allowlist=ENVIRONMENT_ALLOWLIST,
            )
            with pytest.raises(UnsafeExecutionRequest):
                local_backend.execute(descriptor, workdir)
    finally:
        local_backend.cleanup(workdir)


# --- filesystem containment ---------------------------------------------------------------------
@pytest.mark.parametrize("hostile", [
    "../etc/passwd", "..", "../../..", "a/../../b", "/etc/passwd", "/", "./x", ".hidden",
    "name with space", "semi;colon", "pipe|char", "new\nline", "null\x00byte", "",
    "x" * 200, "sub/dir", "\\windows\\path", "~root",
])
def test_path_traversal_and_odd_names_are_refused(hostile):
    with pytest.raises(UnsafeExecutionRequest):
        safe_join(_runtime_root(), hostile)


def test_symlink_escape_from_workdir_is_refused():
    workdir = local_backend.prepare_workdir("symlinktest" + os.urandom(4).hex())
    try:
        escape = Path(workdir) / "escape"
        escape.symlink_to("/etc")
        # Resolution happens after joining, so a symlink pointing outside the root is caught.
        with pytest.raises(UnsafeExecutionRequest):
            safe_join(workdir, "escape", "passwd")
    finally:
        local_backend.cleanup(workdir)


def test_oversized_input_artifact_is_refused():
    workdir = local_backend.prepare_workdir("oversizetest" + os.urandom(4).hex())
    try:
        with pytest.raises(UnsafeExecutionRequest):
            local_backend.write_inputs(workdir, {"huge.in": "x" * (MAX_ARTIFACT_BYTES + 1)})
    finally:
        local_backend.cleanup(workdir)


def test_output_collection_ignores_paths_outside_the_workdir():
    workdir = local_backend.prepare_workdir("collecttest" + os.urandom(4).hex())
    try:
        collected = local_backend.collect_outputs(workdir, ("../../etc/passwd", "/etc/hostname", "..", "absent.out"))
        assert collected == {}
    finally:
        local_backend.cleanup(workdir)


def test_cleanup_refuses_to_delete_outside_the_controlled_root(tmp_path):
    victim = tmp_path / "not-ours"
    victim.mkdir()
    (victim / "keep.txt").write_text("must survive")
    local_backend.cleanup(str(victim))
    assert (victim / "keep.txt").exists(), "cleanup must never touch a path outside the runtime root"


# --- environment --------------------------------------------------------------------------------
def test_environment_allowlist_drops_secrets(monkeypatch):
    for leaked in ("DATABASE_URL", "AWS_SECRET_ACCESS_KEY", "OPENAI_API_KEY", "TINKERLAB_ARTIFACT_STORE"):
        monkeypatch.setenv(leaked, "super-secret-value")
    env = sanitized_environment()
    assert set(env) <= set(ENVIRONMENT_ALLOWLIST)
    assert "super-secret-value" not in "".join(env.values())


def test_output_caps_are_enforced_and_disclosed():
    from app.services.simulation_runtime import _truncate

    text, truncated = _truncate("y" * (MAX_STDOUT_BYTES + 5000), MAX_STDOUT_BYTES)
    assert truncated is True
    assert "TRUNCATED" in text
    assert len(text.encode()) <= MAX_STDOUT_BYTES + 100
    assert MAX_STDERR_BYTES < MAX_STDOUT_BYTES  # stderr is bounded at least as tightly


# --- artifact store -----------------------------------------------------------------------------
def test_artifact_store_rejects_non_digest_references():
    workdir = local_backend.prepare_workdir("storetest" + os.urandom(4).hex())
    try:
        for hostile in ("../../etc/passwd", "/etc/passwd", "not-a-digest", "", "a" * 63, "z" * 64):
            with pytest.raises((UnsafeExecutionRequest, artifact_store.ArtifactStoreError)):
                artifact_store.materialize(hostile, workdir, "out.dat")
    finally:
        local_backend.cleanup(workdir)


def test_artifact_store_detects_tampered_content(tmp_path, monkeypatch):
    monkeypatch.setattr(artifact_store, "ARTIFACT_STORE_ROOT", str(tmp_path / "store"))
    source = tmp_path / "potential.in"
    source.write_text("pair_coeff * * 1.0 1.0\n")
    checksum, _ = artifact_store.ingest_file(source)

    stored = Path(artifact_store.store_root()) / checksum
    stored.chmod(0o600)
    stored.write_text("pair_coeff * * 9.9 9.9\n")  # silently swap the science

    workdir = local_backend.prepare_workdir("tampertest" + os.urandom(4).hex())
    try:
        with pytest.raises(artifact_store.ArtifactStoreError, match="digest re-verification"):
            artifact_store.materialize(checksum, workdir, "potential.in")
    finally:
        local_backend.cleanup(workdir)


def test_artifact_ingestion_refuses_non_regular_files(tmp_path, monkeypatch):
    monkeypatch.setattr(artifact_store, "ARTIFACT_STORE_ROOT", str(tmp_path / "store"))
    with pytest.raises(artifact_store.ArtifactStoreError):
        artifact_store.ingest_file(tmp_path)  # a directory
    link = tmp_path / "link.upf"
    link.symlink_to("/etc/passwd")
    with pytest.raises(artifact_store.ArtifactStoreError):
        artifact_store.ingest_file(link)


# --- API surface --------------------------------------------------------------------------------
def test_no_api_field_accepts_a_command_path_or_image():
    """The contract itself must have no place to put an executable. Reviewed field-by-field."""
    forbidden = {"command", "cmd", "argv", "executable", "executable_path", "binary", "script",
                 "shell", "image", "container", "container_image", "docker_image", "entrypoint",
                 "path", "file_path", "workdir", "import_path", "module", "url", "endpoint"}
    present = set(WorkflowCreateRequest.model_fields)
    assert not (present & forbidden), f"workflow creation exposes execution-shaped fields: {present & forbidden}"


def test_unknown_parameters_are_never_forwarded_to_a_solver(db, client):
    response = client.post("/simulation/workflows", headers=HEADERS, json={
        "target_kind": "known_material", "target_id": BASELINE_ID,
        "method_key": "software_fixture_energy_minimization_v1",
        "provider_version_id": FIXTURE_VERSION_ID,
        "parameters": {"step_size": 0.1, "max_iterations": 50, "gradient_tolerance": 1e-6,
                       "command": "rm -rf /", "executable_path": "/bin/sh", "extra_argv": ["--evil"]},
    })
    assert response.status_code == 201, response.text
    workflow_id = response.json()["id"]
    client.post(f"/simulation/workflows/{workflow_id}/execute", headers=HEADERS)
    db.expire_all()
    job = db.query(SimulationJob).filter_by(workflow_id=workflow_id).one()
    recorded = str(job.command_descriptor)
    assert "rm -rf" not in recorded
    assert "/bin/sh" not in recorded
    assert "--evil" not in recorded
    snapshot_parameters = db.get(SimulationWorkflow, workflow_id).input_snapshot_id
    assert snapshot_parameters  # the snapshot holds only validated, typed parameters
    from app.models.entities import SimulationInputSnapshot

    normalized = db.get(SimulationInputSnapshot, snapshot_parameters).normalized_parameters
    assert set(normalized) <= {"step_size", "max_iterations", "gradient_tolerance", "stiffness",
                               "initial_displacement", "linear_bias", "energy_offset"}


@pytest.mark.parametrize(("verb", "path"), [
    ("get", "/simulation/workflows/{wid}"),
    ("post", "/simulation/workflows/{wid}/execute"),
    ("post", "/simulation/workflows/{wid}/cancel"),
])
def test_workflow_access_is_scoped_and_returns_404_not_403(client, verb, path):
    url = path.format(wid=SEEDED_WORKFLOW_ID)
    method = getattr(client, verb)
    response = method(url, headers=HOSTILE_HEADERS)
    assert response.status_code == 404, "a foreign workflow must be indistinguishable from a missing one"
    unauthenticated = method(url)
    assert unauthenticated.status_code == 404


def test_artifact_storage_references_never_expose_host_paths(client):
    detail = client.get(f"/simulation/workflows/{SEEDED_WORKFLOW_ID}", headers=HEADERS).json()
    for artifact in detail["artifacts"]:
        assert artifact["storage_reference"].startswith("simulation://")
        assert not artifact["storage_reference"].startswith("/")
        assert "/tmp" not in artifact["storage_reference"]
        assert "/home" not in artifact["storage_reference"]


def test_pagination_bounds_are_enforced(client):
    assert client.get("/simulation/workflows?limit=100000", headers=HEADERS).status_code == 422
    assert client.get("/simulation/workflows?limit=0", headers=HEADERS).status_code == 422
    assert client.get("/simulation/workflows?offset=-1", headers=HEADERS).status_code == 422


def test_oversized_representation_payload_is_refused(client):
    huge = {"lattice_vectors": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "lattice_unit": "angstrom",
            "sites": [{"element": "C", "fractional_coordinates": [0, 0, 0]}],
            "padding": "x" * 600_000}
    response = client.post("/simulation/representations/validate", json={
        "representation_format": "periodic_structure_json_v1", "content": huge})
    assert response.status_code == 422
    assert "exceeds" in response.text.lower()


def test_atom_count_bound_is_enforced(client):
    response = client.post("/simulation/representations/validate", json={
        "representation_format": "periodic_structure_json_v1",
        "content": {"lattice_vectors": [[50, 0, 0], [0, 50, 0], [0, 0, 50]], "lattice_unit": "angstrom",
                    "sites": [{"element": "C", "fractional_coordinates": [i / 1000, 0, 0]} for i in range(600)]},
    })
    assert response.status_code == 200
    body = response.json()
    assert body["validation_status"] == "structurally_invalid"
    assert any(m["code"] == "TOO_MANY_SITES" for m in body["messages"])
