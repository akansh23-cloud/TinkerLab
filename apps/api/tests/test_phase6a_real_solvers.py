"""End-to-end tests against REAL external solvers.

These tests execute actual scientific software. They are skipped — never faked — when the binary is
absent or unusable on the host. A skip is recorded as EXTERNALLY_UNVERIFIED in the implementation
report; it is never reported as a pass.

The invariant under test is not "the solver returns a number". It is:

    a real solver either produces a converged, parsed, unit-valid result that yields exactly one
    property estimate, or it produces no estimate at all — and never anything in between.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from app.db.seed import sid
from app.models.entities import (
    MaterialPropertyObservation,
    PropertyPrediction,
    SimulationArtifact,
    SimulationJob,
    SimulationPropertyEstimate,
    SimulationResult,
)
from app.services.simulation import create_workflow, execute_workflow, preview_routes
from app.services.simulation_runtime import resolve_executable, sanitized_environment

ORG_ID = sid("org")
USER_ID = sid("user")
BASELINE_ID = sid("material:demo-polymer-baseline")
SILICON_ID = sid("material:silicon")

LAMMPS_PATH = resolve_executable("lammps")[0]
QE_PATH = resolve_executable("quantum_espresso_pw")[0]


def _qe_is_usable() -> tuple[bool, str]:
    """Probe whether pw.x can actually complete a real SCF on this host.

    The probe deliberately uses a genuine pseudopotential and the same argv invocation the adapter
    uses. A probe that referenced a missing pseudopotential would exit early on a file error and
    report "usable" for a binary that in fact aborts on any real input — a false pass.

    Some distribution builds of Quantum ESPRESSO abort with a fortify buffer-overflow while parsing
    input. Present-but-unusable is a different fact from absent, and both differ from working.
    """
    if not QE_PATH:
        return False, "pw.x is not installed"
    pseudo_source = None
    pseudo_dir = Path(os.environ.get("TINKERLAB_SYSTEM_PSEUDO_DIR", "/usr/share/espresso/pseudo"))
    for name in ("Si.pz-vbc.UPF", "H.pz-vbc.UPF"):
        if (pseudo_dir / name).is_file():
            pseudo_source = pseudo_dir / name
            break
    if pseudo_source is None:
        return False, "no pseudopotential is available on this host to probe pw.x with"
    element = pseudo_source.name.split(".")[0]
    with tempfile.TemporaryDirectory(prefix="tinkerlab-qe-probe-") as workdir:
        (Path(workdir) / "pseudo").mkdir()
        (Path(workdir) / "out").mkdir()
        shutil.copyfile(pseudo_source, Path(workdir) / "pseudo" / pseudo_source.name)
        (Path(workdir) / "pw.in").write_text(
            "&CONTROL\n calculation='scf'\n prefix='probe'\n outdir='out'\n pseudo_dir='pseudo'\n/\n"
            "&SYSTEM\n ibrav=0\n nat=1\n ntyp=1\n ecutwfc=12.0\n occupations='smearing'\n"
            " smearing='gaussian'\n degauss=0.05\n/\n&ELECTRONS\n conv_thr=1.0d-4\n/\n"
            f"ATOMIC_SPECIES\n {element} 1.0 {pseudo_source.name}\n"
            "CELL_PARAMETERS angstrom\n 6.0 0.0 0.0\n 0.0 6.0 0.0\n 0.0 0.0 6.0\n"
            f"ATOMIC_POSITIONS crystal\n {element} 0.0 0.0 0.0\nK_POINTS gamma\n"
        )
        try:
            completed = subprocess.run(
                [QE_PATH, "-input", "pw.in"], cwd=workdir, capture_output=True, text=True,
                timeout=180, env=sanitized_environment(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return False, f"pw.x could not be executed: {exc}"
    blob = completed.stdout + completed.stderr
    if "buffer overflow detected" in blob or completed.returncode in (134, -6):
        return False, (
            "pw.x aborts with a fortify buffer-overflow while parsing input on this host "
            "(distribution build defect, not a TinkerLab adapter fault)"
        )
    if completed.returncode != 0:
        return False, f"pw.x probe exited with code {completed.returncode}"
    if "JOB DONE" not in blob:
        return False, "pw.x probe did not reach JOB DONE"
    return True, "pw.x completed a probe SCF"


QE_USABLE, QE_REASON = _qe_is_usable()

lammps_required = pytest.mark.skipif(
    LAMMPS_PATH is None, reason="EXTERNALLY_UNVERIFIED: no allowlisted LAMMPS binary on this host"
)
qe_required = pytest.mark.skipif(not QE_USABLE, reason=f"EXTERNALLY_UNVERIFIED: {QE_REASON}")


def _route_for(db, target_id: str, method_key: str) -> dict:
    preview = preview_routes(
        db, target_kind="known_material", target_id=target_id, organisation_id=ORG_ID,
        purpose="energy_stability",
    )
    matches = [r for r in preview["routes"] if r["method_key"] == method_key]
    assert matches, f"no route produced for {method_key}"
    return matches[0]


# --- LAMMPS -------------------------------------------------------------------------------------
@lammps_required
def test_real_lammps_converged_run_produces_exactly_one_estimate(db):
    route = _route_for(db, BASELINE_ID, "md_reduced_unit_minimization_v1")
    assert route["route_status"] == "ready", route["reasons"]
    workflow = create_workflow(
        db, organisation_id=ORG_ID, created_by=USER_ID, target_kind="known_material",
        target_id=BASELINE_ID, method_key="md_reduced_unit_minimization_v1",
        provider_version_id=route["provider_version_id"],
        parameters={"minimization_energy_tolerance": 1e-12, "minimization_force_tolerance": 1e-4,
                    "max_iterations": 1000, "max_force_evaluations": 10000},
    )
    execute_workflow(db, workflow)
    result = db.query(SimulationResult).filter_by(workflow_id=workflow.id).one()
    assert result.operational_status == "completed"
    assert result.scientific_status == "converged"

    estimates = db.query(SimulationPropertyEstimate).filter_by(simulation_result_id=result.id).all()
    assert len(estimates) == 1
    estimate = estimates[0]
    # Four LJ particles placed near equilibrium separation relax to three interacting pairs at the
    # potential minimum: -0.5 reduced units each. This is arithmetic about the fixture, not a claim
    # about any real substance.
    assert estimate.canonical_value == pytest.approx(-1.5, abs=1e-6)
    assert estimate.canonical_unit == "1"
    assert estimate.scientific_origin == "physics_simulation"

    # The registered potential artifact was genuinely consumed by the solver input.
    artifacts = db.query(SimulationArtifact).filter_by(workflow_id=workflow.id).all()
    script = next(a for a in artifacts if a.file_name == "tinkerlab.in")
    assert "include potentials/" in (script.inline_preview or "")

    job = db.query(SimulationJob).filter_by(workflow_id=workflow.id).one()
    assert job.process_exit_code == 0
    assert job.command_descriptor["shell"] is False
    assert job.command_descriptor["executable_key"] == "lammps"


@lammps_required
def test_real_lammps_clean_exit_with_unmet_tolerance_yields_no_value(db):
    """The headline invariant, proven against real scientific software rather than a fixture."""
    route = _route_for(db, BASELINE_ID, "md_reduced_unit_minimization_v1")
    workflow = create_workflow(
        db, organisation_id=ORG_ID, created_by=USER_ID, target_kind="known_material",
        target_id=BASELINE_ID, method_key="md_reduced_unit_minimization_v1",
        provider_version_id=route["provider_version_id"],
        parameters={"minimization_energy_tolerance": 1e-12, "minimization_force_tolerance": 1e-9,
                    "max_iterations": 20, "max_force_evaluations": 200},
    )
    execute_workflow(db, workflow)
    result = db.query(SimulationResult).filter_by(workflow_id=workflow.id).one()
    job = db.query(SimulationJob).filter_by(workflow_id=workflow.id).one()

    assert job.process_exit_code == 0, "LAMMPS exited cleanly"
    assert result.operational_status == "completed"
    assert result.scientific_status == "unconverged"
    # A real number WAS parsed out of the real solver, and it is still not accepted as a value.
    assert "md_reduced_potential_energy" in result.parsed_quantities
    assert db.query(SimulationPropertyEstimate).filter_by(simulation_result_id=result.id).count() == 0


@lammps_required
def test_real_lammps_run_creates_no_observations_or_predictions(db):
    observations = db.query(MaterialPropertyObservation).count()
    predictions = db.query(PropertyPrediction).count()
    route = _route_for(db, BASELINE_ID, "md_reduced_unit_minimization_v1")
    workflow = create_workflow(
        db, organisation_id=ORG_ID, created_by=USER_ID, target_kind="known_material",
        target_id=BASELINE_ID, method_key="md_reduced_unit_minimization_v1",
        provider_version_id=route["provider_version_id"],
        parameters={"minimization_energy_tolerance": 1e-12, "minimization_force_tolerance": 1e-4,
                    "max_iterations": 1000, "max_force_evaluations": 10000},
    )
    execute_workflow(db, workflow)
    assert db.query(MaterialPropertyObservation).count() == observations
    assert db.query(PropertyPrediction).count() == predictions


@lammps_required
def test_real_lammps_refuses_when_potential_artifact_content_is_removed(db, monkeypatch):
    """A registered artifact whose content vanished must fail the job, never fall back to defaults."""
    import app.services.artifact_store as store

    route = _route_for(db, BASELINE_ID, "md_reduced_unit_minimization_v1")
    workflow = create_workflow(
        db, organisation_id=ORG_ID, created_by=USER_ID, target_kind="known_material",
        target_id=BASELINE_ID, method_key="md_reduced_unit_minimization_v1",
        provider_version_id=route["provider_version_id"],
        parameters={"minimization_energy_tolerance": 1e-12, "minimization_force_tolerance": 1e-4,
                    "max_iterations": 100, "max_force_evaluations": 1000},
    )

    def _absent(checksum, workdir, file_name, subdirectory=None):
        raise store.ArtifactStoreError(f"Approved artifact content {checksum[:12]} is not present in the store")

    monkeypatch.setattr("app.services.simulation.materialize", _absent)
    execute_workflow(db, workflow)
    result = db.query(SimulationResult).filter_by(workflow_id=workflow.id).one()
    assert result.operational_status == "failed"
    assert result.scientific_status == "not_applicable"
    assert db.query(SimulationPropertyEstimate).filter_by(simulation_result_id=result.id).count() == 0


# --- Quantum ESPRESSO ---------------------------------------------------------------------------
@qe_required
def test_real_quantum_espresso_silicon_scf(db):
    route = _route_for(db, SILICON_ID, "dft_single_point_energy_v1")
    assert route["route_status"] == "ready", route["reasons"]
    workflow = create_workflow(
        db, organisation_id=ORG_ID, created_by=USER_ID, target_kind="known_material",
        target_id=SILICON_ID, method_key="dft_single_point_energy_v1",
        provider_version_id=route["provider_version_id"],
        parameters={"ecutwfc_ry": 18.0, "ecutrho_ry": 72.0, "kpoint_grid": [2, 2, 2],
                    "conv_thr_ry": 1e-6, "occupations": "fixed"},
    )
    execute_workflow(db, workflow)
    result = db.query(SimulationResult).filter_by(workflow_id=workflow.id).one()
    estimates = db.query(SimulationPropertyEstimate).filter_by(simulation_result_id=result.id).all()

    if result.scientific_status == "converged":
        assert len(estimates) == 1
        assert estimates[0].canonical_unit == "Ry"
        # Silicon's SCF total energy with this pseudopotential is strongly negative. The assertion is
        # deliberately loose: this test proves the pipeline is wired to real DFT output, and does not
        # assert a reference value that would depend on cutoff, k-points and pseudopotential choice.
        assert estimates[0].canonical_value < 0
    else:
        assert estimates == [], "a non-converged DFT run must yield no property estimate"


@qe_required
def test_real_quantum_espresso_consumes_registered_pseudopotential(db):
    route = _route_for(db, SILICON_ID, "dft_single_point_energy_v1")
    workflow = create_workflow(
        db, organisation_id=ORG_ID, created_by=USER_ID, target_kind="known_material",
        target_id=SILICON_ID, method_key="dft_single_point_energy_v1",
        provider_version_id=route["provider_version_id"],
        parameters={"ecutwfc_ry": 12.0, "ecutrho_ry": 48.0, "kpoint_grid": [1, 1, 1],
                    "conv_thr_ry": 1e-4, "occupations": "fixed"},
    )
    execute_workflow(db, workflow)
    artifacts = db.query(SimulationArtifact).filter_by(workflow_id=workflow.id).all()
    pw_input = next(a for a in artifacts if a.file_name == "pw.in")
    assert ".UPF" in (pw_input.inline_preview or ""), "the real registered pseudopotential must be referenced"
    assert "MISSING" not in (pw_input.inline_preview or "")


def test_solver_availability_is_reported_honestly():
    """Runs on every host: whatever is or is not installed, the registry must say so accurately."""
    from app.services.simulation_adapters import get_adapter

    lammps = get_adapter("lammps_local_v1").check_availability()
    assert lammps.available is (LAMMPS_PATH is not None)
    quantum_espresso = get_adapter("quantum_espresso_local_v1").check_availability()
    assert quantum_espresso.available is (QE_PATH is not None)
    for interface_only in ("calphad_interface_v1", "ml_force_field_interface_v1"):
        availability = get_adapter(interface_only).check_availability()
        assert availability.available is False
        assert availability.reason_code == "interface_only"
