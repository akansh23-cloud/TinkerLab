"""Phase-6 simulation adapters.

Four honest categories, never blurred:

  * ``software_fixture_harmonic_v1`` — implemented, executable, deterministic. A reduced-unit
    numerical fixture that validates the *operating system*, not materials science.
  * ``lammps_local_v1`` / ``quantum_espresso_local_v1`` — real reviewed adapters. They build inputs
    from code-defined templates and execute only through the bounded local runner. If the binary or
    a registered artifact is absent, they refuse; they never fabricate a number.
  * ``calphad_interface_v1`` / ``ml_force_field_interface_v1`` — interface only. Execution is
    permanently disabled in Phase 6; without a reviewed database or licensed weights there is no
    numerical result at all.

Adapters are registered in code. No import path, executable path, container image or script may be
supplied through any API payload.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from app.domain.contracts import (
    ApplicabilityDecision,
    InputBundle,
    ProviderAvailability,
    SafeCommandDescriptor,
    SimulationCapabilities,
)
from app.domain.enums import (
    RepresentationType,
    SimulationFidelity,
    SimulationJobStatus,
    SimulationMethodFamily,
    SimulationScientificStatus,
)
from app.services.simulation_runtime import (
    ENVIRONMENT_ALLOWLIST,
    ExecutionOutcome,
    local_backend,
    probe_executable_version,
)

ADAPTER_CONTRACT_VERSION = "simulation-adapter-v1"

# Standard atomic weights, used only to populate the ATOMIC_SPECIES mass column that pw.x requires.
# The mass does not affect an SCF total energy; it is metadata, not a fitted scientific parameter.
ATOMIC_MASSES: dict[str, float] = {
    "H": 1.008, "He": 4.003, "Li": 6.94, "Be": 9.012, "B": 10.81, "C": 12.011, "N": 14.007,
    "O": 15.999, "F": 18.998, "Ne": 20.180, "Na": 22.990, "Mg": 24.305, "Al": 26.982,
    "Si": 28.085, "P": 30.974, "S": 32.06, "Cl": 35.45, "Ar": 39.95, "K": 39.098, "Ca": 40.078,
    "Ti": 47.867, "V": 50.942, "Cr": 51.996, "Mn": 54.938, "Fe": 55.845, "Co": 58.933,
    "Ni": 58.693, "Cu": 63.546, "Zn": 65.38, "Ga": 69.723, "Ge": 72.630, "As": 74.922,
    "Se": 78.971, "Br": 79.904, "Zr": 91.224, "Nb": 92.906, "Mo": 95.95, "Ag": 107.868,
    "Cd": 112.414, "In": 114.818, "Sn": 118.710, "Sb": 121.760, "Te": 127.60, "I": 126.904,
    "Ba": 137.327, "Hf": 178.486, "Ta": 180.948, "W": 183.84, "Pt": 195.084, "Au": 196.967,
    "Pb": 207.2, "Bi": 208.980,
}

SOFTWARE_FIXTURE_WARNING = (
    "SOFTWARE VALIDATION SIMULATION FIXTURE — not a validated real-material physics model."
)
SIMULATION_WARNING = (
    "PHYSICS SIMULATION — computational evidence only; not a physical experiment, not a "
    "manufacturing proof, and not a synthesizability claim."
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _reason(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **extra}


class BaseAdapter:
    """Shared refusal helpers. Every adapter must be able to say no with a typed reason."""

    key = "abstract"
    contract_version = ADAPTER_CONTRACT_VERSION
    # Sub-directory of the job workdir into which approved artifact content is materialized.
    # Server-defined per adapter; never influenced by a request.
    artifact_subdirectory: str | None = None
    # Scratch directories the solver expects to exist. Also server-defined.
    scratch_subdirectories: tuple[str, ...] = ()

    def capabilities(self) -> SimulationCapabilities:  # pragma: no cover - abstract
        raise NotImplementedError

    def check_availability(self) -> ProviderAvailability:  # pragma: no cover - abstract
        raise NotImplementedError

    def _representation_check(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        caps = self.capabilities()
        reasons: list[dict[str, Any]] = []
        representation = context.get("representation")
        if not representation:
            reasons.append(_reason(
                "REPRESENTATION_ABSENT",
                f"No scientific representation of a supported type exists for this target. "
                f"Supported: {', '.join(caps.supported_representation_types)}.",
            ))
            return reasons
        if representation["representation_type"] not in caps.supported_representation_types:
            reasons.append(_reason(
                "REPRESENTATION_TYPE_UNSUPPORTED",
                f"A {representation['representation_type']} representation cannot support "
                f"{caps.method_family}; atoms, topology and phases are never inferred from it.",
                representation_type=representation["representation_type"],
            ))
        if representation["representation_format"] not in caps.supported_representation_formats:
            reasons.append(_reason(
                "REPRESENTATION_FORMAT_UNSUPPORTED",
                f"Representation format {representation['representation_format']} is not declared by this provider version.",
            ))
        if representation.get("completeness_status") != "complete":
            reasons.append(_reason(
                "REPRESENTATION_INCOMPLETE",
                "The representation is incomplete or redacted; missing scientific content is never repaired.",
                completeness=representation.get("completeness_status"),
            ))
        if representation.get("validation_status") != "valid":
            reasons.append(_reason(
                "REPRESENTATION_NOT_VALID",
                "The representation did not pass deterministic structural validation.",
                validation_status=representation.get("validation_status"),
            ))
        size = representation.get("atom_count") or representation.get("component_count") or 0
        if caps.maximum_target_size and size > caps.maximum_target_size:
            reasons.append(_reason(
                "TARGET_TOO_LARGE",
                f"Target size {size} exceeds the bounded Phase-6 maximum of {caps.maximum_target_size}.",
            ))
        return reasons

    def _support_check(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        caps = self.capabilities()
        reasons: list[dict[str, Any]] = []
        method_key = context.get("method_key")
        if method_key and method_key not in caps.supported_method_keys:
            reasons.append(_reason("METHOD_UNSUPPORTED", f"Method {method_key} is not declared by this provider version."))
        family = context.get("material_family")
        if family and caps.supported_material_families and family not in caps.supported_material_families:
            reasons.append(_reason(
                "MATERIAL_FAMILY_UNSUPPORTED",
                f"Material family {family} is outside this provider version's declared applicability.",
            ))
        property_key = context.get("property_key")
        if property_key and property_key not in caps.supported_property_keys:
            reasons.append(_reason(
                "PROPERTY_UNSUPPORTED",
                f"Property {property_key} is not produced by this method; no substitute quantity is offered.",
            ))
        conditions = context.get("conditions") or {}
        unsupported = sorted(set(conditions) - set(context.get("supported_condition_keys") or []))
        if unsupported:
            reasons.append(_reason(
                "CONDITIONS_UNSUPPORTED",
                f"Requested conditions are not supported by this method: {', '.join(unsupported)}.",
            ))
        return reasons

    def _artifact_check(self, context: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
        caps = self.capabilities()
        available = set(context.get("available_artifact_types") or [])
        missing = [a for a in caps.required_artifact_types if a not in available]
        if not missing:
            return [], []
        return [_reason(
            "REGISTERED_ARTIFACT_MISSING",
            f"Required approved scientific artifacts are not registered: {', '.join(missing)}. "
            "TinkerLab never downloads potentials, pseudopotentials or thermodynamic databases during a run.",
        )], missing


class SoftwareFixtureHarmonicAdapter(BaseAdapter):
    """Deterministic reduced-unit numerical fixture.

    Minimizes E(x) = 0.5*k*x^2 - b*x + c by damped fixed-step iteration. The analytic minimum,
    E* = c - b^2 / (2k), makes convergence verifiable without any physical claim: the quantity is
    dimensionless and reduced, and it is mapped only onto the explicitly synthetic demo property.
    """

    key = "software_fixture_harmonic_v1"
    parser_key = "software_fixture_parser_v1"
    parser_version = "1.0"
    builder_key = "software_fixture_builder_v1"
    builder_version = "1.0"
    convergence_key = "software_fixture_convergence_v1"
    convergence_version = "1.0"

    def capabilities(self) -> SimulationCapabilities:
        return SimulationCapabilities(
            method_family=SimulationMethodFamily.ANALYTICAL_FIXTURE,
            supported_method_keys=("software_fixture_energy_minimization_v1",),
            supported_representation_types=(RepresentationType.SOFTWARE_VALIDATION_FIXTURE,),
            supported_representation_formats=("software_fixture_json_v1",),
            supported_material_families=(),
            supported_property_keys=("software_fixture_reduced_energy",),
            required_artifact_types=(),
            fidelity=SimulationFidelity.SOFTWARE_FIXTURE,
            deterministic=True,
            execution_supported=True,
            maximum_target_size=64,
            maximum_wall_time_seconds=30,
            resource_class="in_process_fixture",
            known_limitations=(
                SOFTWARE_FIXTURE_WARNING,
                "Reduced dimensionless units only; the value is not an energy of any real material.",
                "Validates routing, snapshots, workflows, jobs, artifacts, parsing, convergence and checksums.",
            ),
        )

    def check_availability(self) -> ProviderAvailability:
        # In-process and code-reviewed: no external executable, so availability cannot regress.
        return ProviderAvailability(True, "available", "In-process deterministic software-validation fixture.")

    def validate_target(self, context: dict[str, Any]) -> ApplicabilityDecision:
        reasons = self._representation_check(context) + self._support_check(context)
        if reasons:
            code = "incomplete_representation" if any(
                r["code"] in {"REPRESENTATION_INCOMPLETE", "REPRESENTATION_ABSENT"} for r in reasons
            ) else "not_applicable"
            return ApplicabilityDecision(code, tuple(reasons))
        return ApplicabilityDecision("ready", (_reason(
            "FIXTURE_APPLICABLE", "Reduced-unit software-validation fixture is applicable to this fixture representation."),))

    def build_inputs(self, context: dict[str, Any]) -> InputBundle:
        representation = context["representation"]
        content = representation["content"]
        params = context.get("parameters") or {}
        normalized = {
            "stiffness": float(content["parameters"]["stiffness"]),
            "initial_displacement": float(content["parameters"]["initial_displacement"]),
            "linear_bias": float(content["parameters"].get("linear_bias", 0.0)),
            "energy_offset": float(content["parameters"].get("energy_offset", 0.0)),
            "step_size": float(params["step_size"]),
            "max_iterations": int(params["max_iterations"]),
            "gradient_tolerance": float(params["gradient_tolerance"]),
        }
        control = "\n".join(f"{k} {normalized[k]}" for k in sorted(normalized)) + "\n"
        return InputBundle(
            builder_key=self.builder_key, builder_version=self.builder_version,
            normalized_parameters=normalized,
            files={"fixture.in": control, "fixture.manifest.json": canonical_json(
                {"fixture_key": content["fixture_key"], "unit_basis": "reduced_dimensionless",
                 "declaration": SOFTWARE_FIXTURE_WARNING})},
            artifact_references=(),
        )

    def command_descriptor(self, context: dict[str, Any]) -> SafeCommandDescriptor | None:
        # In-process fixture: there is no subprocess to describe, and none is ever constructed.
        return None

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        p = context["normalized_parameters"]
        k, bias = p["stiffness"], p["linear_bias"]
        x = p["initial_displacement"]
        step, tolerance, max_iterations = p["step_size"], p["gradient_tolerance"], p["max_iterations"]
        iterations = 0
        gradient = k * x - bias
        trace: list[str] = []
        while iterations < max_iterations and abs(gradient) > tolerance and math.isfinite(x):
            x = x - step * gradient
            gradient = k * x - bias
            iterations += 1
            if iterations <= 10 or iterations % 50 == 0:
                trace.append(f"iter {iterations} x {x:.12g} grad {gradient:.12g}")
        energy = 0.5 * k * x * x - bias * x + p["energy_offset"]
        stdout = "\n".join([
            "TinkerLab software-validation fixture (reduced units)",
            SOFTWARE_FIXTURE_WARNING,
            *trace,
            f"final_displacement {x:.12g}",
            f"final_gradient {gradient:.12g}",
            f"iterations {iterations}",
            f"reduced_energy {energy:.12g}",
            "fixture_complete",
        ]) + "\n"
        return {
            "status": SimulationJobStatus.COMPLETED, "exit_code": 0, "failure_code": None,
            "stdout": stdout, "stderr": "", "stdout_truncated": False, "stderr_truncated": False,
            "elapsed_seconds": 0.0, "output_files": {"fixture.out": stdout},
        }

    def parse_outputs(self, context: dict[str, Any]) -> dict[str, Any]:
        stdout = context.get("stdout", "")
        values: dict[str, float] = {}
        for line in stdout.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] in {"final_displacement", "final_gradient", "iterations", "reduced_energy"}:
                try:
                    values[parts[0]] = float(parts[1])
                except ValueError:
                    return {"parse_status": "parser_failed", "quantities": {}, "warnings": [f"Unparseable value on line: {line[:80]}"]}
        if "reduced_energy" not in values or "final_gradient" not in values:
            return {"parse_status": "parser_failed", "quantities": {},
                    "warnings": ["Fixture output did not contain the required reduced-unit quantities."]}
        if not all(math.isfinite(v) for v in values.values()):
            # A completed process that produced NaN/inf yields no property value at all.
            return {"parse_status": "parser_failed", "quantities": {},
                    "warnings": ["Non-finite numerical output rejected; no property estimate is produced."]}
        return {
            "parse_status": "parsed",
            "quantities": {
                "software_fixture_reduced_energy": {"value": values["reduced_energy"], "unit": "1"},
                "final_gradient": {"value": values["final_gradient"], "unit": "1"},
                "iterations": {"value": values["iterations"], "unit": "1"},
            },
            "warnings": [],
        }

    def assess_convergence(self, context: dict[str, Any]) -> dict[str, Any]:
        quantities = context.get("quantities") or {}
        p = context["normalized_parameters"]
        criteria = {"gradient_tolerance": p["gradient_tolerance"], "max_iterations": p["max_iterations"],
                    "evaluator": [self.convergence_key, self.convergence_version]}
        if not quantities:
            return {"scientific_status": SimulationScientificStatus.PARSER_FAILED, "metrics": {}, "criteria": criteria,
                    "warnings": ["No parsed quantities; convergence cannot be asserted."]}
        gradient = abs(float(quantities["final_gradient"]["value"]))
        iterations = int(quantities["iterations"]["value"])
        converged = gradient <= p["gradient_tolerance"]
        metrics = {"final_gradient_magnitude": gradient, "iterations": iterations,
                   "gradient_tolerance": p["gradient_tolerance"], "iteration_budget_exhausted": iterations >= p["max_iterations"]}
        if converged:
            return {"scientific_status": SimulationScientificStatus.CONVERGED, "metrics": metrics, "criteria": criteria, "warnings": []}
        return {
            "scientific_status": SimulationScientificStatus.UNCONVERGED, "metrics": metrics, "criteria": criteria,
            "warnings": ["Gradient tolerance was not met within the iteration budget; the completed process is "
                         "NOT a converged result and yields no accepted property estimate."],
        }


class LammpsLocalAdapter(BaseAdapter):
    """Reviewed LAMMPS boundary. Requires atomistic topology plus a registered potential artifact."""

    key = "lammps_local_v1"
    parser_key = "lammps_thermo_parser_v1"
    parser_version = "1.0"
    builder_key = "lammps_input_builder_v1"
    builder_version = "1.0"
    convergence_key = "lammps_convergence_v1"
    convergence_version = "1.0"
    executable_key = "lammps"
    artifact_subdirectory = "potentials"

    def capabilities(self) -> SimulationCapabilities:
        return SimulationCapabilities(
            method_family=SimulationMethodFamily.MD,
            supported_method_keys=("md_reduced_unit_minimization_v1",),
            supported_representation_types=(RepresentationType.MOLECULAR_TOPOLOGY,),
            supported_representation_formats=("atomistic_topology_json_v1",),
            supported_material_families=(),
            supported_property_keys=("md_reduced_potential_energy",),
            required_artifact_types=("force_field",),
            fidelity=SimulationFidelity.EMPIRICAL_ATOMISTIC,
            deterministic=False,
            execution_supported=True,
            maximum_target_size=512,
            maximum_wall_time_seconds=300,
            resource_class="local_small",
            known_limitations=(
                "Requires an explicitly registered, approved and checksummed potential artifact.",
                "Generic formulation-level polymer descriptions are rejected: topology is never invented.",
                "Empirical potentials carry method error that is not a statistical prediction interval.",
            ),
        )

    def check_availability(self) -> ProviderAvailability:
        found, binary, version = probe_executable_version(self.executable_key, ("-h",))
        if not found:
            return ProviderAvailability(
                False, "executable_not_installed",
                "No allowlisted LAMMPS binary is installed on this host; the route stays unavailable.",
            )
        return ProviderAvailability(True, "available", "Allowlisted LAMMPS binary detected.", binary, version, True)

    def validate_target(self, context: dict[str, Any]) -> ApplicabilityDecision:
        reasons = self._representation_check(context) + self._support_check(context)
        artifact_reasons, missing = self._artifact_check(context)
        representation = context.get("representation")
        if representation and representation.get("content", {}).get("force_field_key") is None:
            reasons.append(_reason(
                "FORCE_FIELD_MAPPING_ABSENT",
                "The topology declares no force-field mapping key; a potential is never guessed from atom labels.",
            ))
        if artifact_reasons:
            return ApplicabilityDecision("missing_registered_artifact", tuple(reasons + artifact_reasons), (), tuple(missing))
        if reasons:
            code = "incomplete_representation" if any(
                r["code"] in {"REPRESENTATION_INCOMPLETE", "REPRESENTATION_ABSENT", "FORCE_FIELD_MAPPING_ABSENT"} for r in reasons
            ) else "not_applicable"
            return ApplicabilityDecision(code, tuple(reasons))
        return ApplicabilityDecision("ready", (_reason("MD_APPLICABLE", "Atomistic topology and a registered potential are present."),))

    def build_inputs(self, context: dict[str, Any]) -> InputBundle:
        representation = context["representation"]
        content = representation["content"]
        params = context.get("parameters") or {}
        normalized = {
            "minimization_energy_tolerance": float(params["minimization_energy_tolerance"]),
            "minimization_force_tolerance": float(params["minimization_force_tolerance"]),
            "max_iterations": int(params["max_iterations"]),
            "max_force_evaluations": int(params["max_force_evaluations"]),
            "units": "lj",
        }
        potential_references = [
            a for a in (context.get("artifact_references") or []) if a.get("artifact_type") == "force_field"
        ]
        if not potential_references:
            raise ValueError("No approved interatomic potential artifact is registered for this route")
        potential_file = str(potential_references[0]["file_name"])
        box = content.get("box") or [10.0, 10.0, 10.0]
        data_lines = [
            "TinkerLab generated LAMMPS data file (reduced units)", "",
            f"{len(content['atoms'])} atoms", f"{len(content['atom_types'])} atom types", "",
            f"0.0 {float(box[0]):.6f} xlo xhi", f"0.0 {float(box[1]):.6f} ylo yhi", f"0.0 {float(box[2]):.6f} zlo zhi", "",
            "Masses", "",
        ]
        data_lines += [f"{t['id']} {float(t['mass_amu']):.6f}" for t in content["atom_types"]]
        data_lines += ["", "Atoms # atomic", ""]
        data_lines += [
            f"{a['id']} {a['type']} {a['position'][0]:.6f} {a['position'][1]:.6f} {a['position'][2]:.6f}"
            for a in content["atoms"]
        ]
        # Code-defined template only. No caller-provided text is ever interpolated into solver control files.
        script = "\n".join([
            "# TinkerLab reviewed LAMMPS template — no user-authored commands are accepted.",
            "units lj", "atom_style atomic", "boundary p p p",
            "read_data tinkerlab.data",
            "pair_style lj/cut 2.5",
            # The pair coefficients come from the registered potential artifact, not from an inline
            # default. Without the approved artifact the run fails rather than silently using
            # made-up parameters.
            f"include potentials/{potential_file}",
            "thermo 10", "thermo_style custom step pe fmax",
            f"minimize {normalized['minimization_energy_tolerance']} {normalized['minimization_force_tolerance']} "
            f"{normalized['max_iterations']} {normalized['max_force_evaluations']}",
            "print \"tinkerlab_final_potential_energy $(pe)\"",
            "print \"tinkerlab_final_fmax $(fmax)\"",
        ]) + "\n"
        return InputBundle(
            builder_key=self.builder_key, builder_version=self.builder_version,
            normalized_parameters=normalized,
            files={"tinkerlab.in": script, "tinkerlab.data": "\n".join(data_lines) + "\n"},
            artifact_references=tuple(context.get("artifact_references") or ()),
        )

    def command_descriptor(self, context: dict[str, Any]) -> SafeCommandDescriptor | None:
        return SafeCommandDescriptor(
            executable_key=self.executable_key, argv=("-in", "tinkerlab.in", "-log", "tinkerlab.log"),
            stdin_file=None, timeout_seconds=int(context.get("timeout_seconds", 120)),
            environment_allowlist=ENVIRONMENT_ALLOWLIST,
        )

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        outcome: ExecutionOutcome = local_backend.execute(context["command_descriptor"], context["workdir"])
        files = local_backend.collect_outputs(context["workdir"], ("tinkerlab.log",))
        return {
            "status": outcome.status, "exit_code": outcome.exit_code, "failure_code": outcome.failure_code,
            "stdout": outcome.stdout, "stderr": outcome.stderr, "stdout_truncated": outcome.stdout_truncated,
            "stderr_truncated": outcome.stderr_truncated, "elapsed_seconds": outcome.elapsed_seconds,
            "output_files": files,
        }

    def parse_outputs(self, context: dict[str, Any]) -> dict[str, Any]:
        blob = context.get("stdout", "") + "\n" + "\n".join((context.get("output_files") or {}).values())
        quantities: dict[str, Any] = {}
        for line in blob.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == "tinkerlab_final_potential_energy":
                try:
                    quantities["md_reduced_potential_energy"] = {"value": float(parts[1]), "unit": "1"}
                except ValueError:
                    return {"parse_status": "parser_failed", "quantities": {}, "warnings": ["Unparseable energy value."]}
            if len(parts) == 2 and parts[0] == "tinkerlab_final_fmax":
                try:
                    quantities["final_fmax"] = {"value": float(parts[1]), "unit": "1"}
                except ValueError:
                    return {"parse_status": "parser_failed", "quantities": {}, "warnings": ["Unparseable force value."]}
        if "md_reduced_potential_energy" not in quantities:
            return {"parse_status": "parser_failed", "quantities": {},
                    "warnings": ["LAMMPS output did not contain the expected TinkerLab thermo markers."]}
        if not all(math.isfinite(float(v["value"])) for v in quantities.values()):
            return {"parse_status": "parser_failed", "quantities": {}, "warnings": ["Non-finite LAMMPS output rejected."]}
        return {"parse_status": "parsed", "quantities": quantities, "warnings": []}

    def assess_convergence(self, context: dict[str, Any]) -> dict[str, Any]:
        quantities = context.get("quantities") or {}
        p = context["normalized_parameters"]
        criteria = {"force_tolerance": p["minimization_force_tolerance"],
                    "evaluator": [self.convergence_key, self.convergence_version]}
        if "final_fmax" not in quantities:
            return {"scientific_status": SimulationScientificStatus.PARTIAL, "metrics": {}, "criteria": criteria,
                    "warnings": ["Maximum force was not reported; minimization convergence cannot be asserted."]}
        fmax = abs(float(quantities["final_fmax"]["value"]))
        metrics = {"final_fmax": fmax, "force_tolerance": p["minimization_force_tolerance"]}
        if fmax <= p["minimization_force_tolerance"]:
            return {"scientific_status": SimulationScientificStatus.CONVERGED, "metrics": metrics, "criteria": criteria, "warnings": []}
        return {"scientific_status": SimulationScientificStatus.UNCONVERGED, "metrics": metrics, "criteria": criteria,
                "warnings": ["Force tolerance not met; process completion is not scientific convergence."]}


class QuantumEspressoLocalAdapter(BaseAdapter):
    """Reviewed Quantum ESPRESSO boundary for periodic single-point energies only."""

    key = "quantum_espresso_local_v1"
    parser_key = "qe_pw_parser_v1"
    parser_version = "1.0"
    builder_key = "qe_pw_input_builder_v1"
    builder_version = "1.0"
    convergence_key = "qe_scf_convergence_v1"
    convergence_version = "1.0"
    executable_key = "quantum_espresso_pw"
    artifact_subdirectory = "pseudo"
    scratch_subdirectories = ("out",)

    def capabilities(self) -> SimulationCapabilities:
        return SimulationCapabilities(
            method_family=SimulationMethodFamily.DFT,
            supported_method_keys=("dft_single_point_energy_v1",),
            supported_representation_types=(RepresentationType.PERIODIC_ATOMIC_STRUCTURE,),
            supported_representation_formats=("periodic_structure_json_v1",),
            supported_material_families=("crystalline_inorganic", "ceramic", "alloy"),
            supported_property_keys=("total_energy",),
            required_artifact_types=("pseudopotential",),
            fidelity=SimulationFidelity.FIRST_PRINCIPLES,
            deterministic=True,
            execution_supported=True,
            maximum_target_size=64,
            maximum_wall_time_seconds=600,
            resource_class="local_medium",
            known_limitations=(
                "Requires a periodic crystal structure and an approved checksummed pseudopotential per element.",
                "Cutoffs and k-point density are explicit scientific parameters, never hidden defaults.",
                "Formulation-level polymer descriptions are structurally rejected.",
                "A converged single-point energy is not a synthesizability or stability-in-service claim.",
            ),
        )

    def check_availability(self) -> ProviderAvailability:
        found, binary, version = probe_executable_version(self.executable_key, ("-h",))
        if not found:
            return ProviderAvailability(
                False, "executable_not_installed",
                "No allowlisted Quantum ESPRESSO pw.x binary is installed on this host; the route stays unavailable.",
            )
        return ProviderAvailability(True, "available", "Allowlisted pw.x binary detected.", binary, version, True)

    def validate_target(self, context: dict[str, Any]) -> ApplicabilityDecision:
        reasons = self._representation_check(context) + self._support_check(context)
        artifact_reasons, missing = self._artifact_check(context)
        representation = context.get("representation")
        if representation:
            elements = set(representation.get("chemical_elements") or [])
            covered = set(context.get("artifact_covered_elements") or [])
            uncovered = sorted(elements - covered)
            if uncovered and not artifact_reasons:
                artifact_reasons.append(_reason(
                    "PSEUDOPOTENTIAL_MISSING_FOR_ELEMENTS",
                    f"No approved pseudopotential is registered for: {', '.join(uncovered)}. "
                    "Pseudopotentials are never downloaded during a run.",
                    elements=uncovered,
                ))
                missing = ["pseudopotential"]
        if artifact_reasons:
            return ApplicabilityDecision("missing_registered_artifact", tuple(reasons + artifact_reasons), (), tuple(missing))
        if reasons:
            code = "incomplete_representation" if any(
                r["code"] in {"REPRESENTATION_INCOMPLETE", "REPRESENTATION_ABSENT"} for r in reasons
            ) else "not_applicable"
            return ApplicabilityDecision(code, tuple(reasons))
        return ApplicabilityDecision("ready", (_reason("DFT_APPLICABLE", "Periodic structure and pseudopotential coverage are present."),))

    def build_inputs(self, context: dict[str, Any]) -> InputBundle:
        representation = context["representation"]
        content = representation["content"]
        params = context.get("parameters") or {}
        normalized: dict[str, Any] = {
            "ecutwfc_ry": float(params["ecutwfc_ry"]),
            "ecutrho_ry": float(params["ecutrho_ry"]),
            "kpoint_grid": [int(v) for v in params["kpoint_grid"]],
            "conv_thr_ry": float(params["conv_thr_ry"]),
            "occupations": str(params["occupations"]),
        }
        lattice = content["lattice_vectors"]
        species = sorted({s["element"] for s in content["sites"]})
        artifact_map = {a["element"]: a["file_name"] for a in (context.get("artifact_references") or []) if "element" in a}
        lines = [
            "&CONTROL", "  calculation = 'scf'", "  prefix = 'tinkerlab'", "  outdir = 'out'",
            "  pseudo_dir = 'pseudo'", "/", "&SYSTEM", "  ibrav = 0",
            f"  nat = {len(content['sites'])}", f"  ntyp = {len(species)}",
            f"  ecutwfc = {normalized['ecutwfc_ry']}", f"  ecutrho = {normalized['ecutrho_ry']}",
            f"  occupations = '{normalized['occupations']}'", "/", "&ELECTRONS",
            f"  conv_thr = {normalized['conv_thr_ry']}", "/", "ATOMIC_SPECIES",
        ]
        missing_species = [el for el in species if el not in artifact_map]
        if missing_species:
            # Never emit a placeholder filename that would make pw.x fail obscurely at run time.
            raise ValueError(
                f"No approved pseudopotential is registered for: {', '.join(missing_species)}"
            )
        lines += [f"  {el} {ATOMIC_MASSES.get(el, 1.0)} {artifact_map[el]}" for el in species]
        lines += ["CELL_PARAMETERS angstrom"]
        lines += [f"  {row[0]:.8f} {row[1]:.8f} {row[2]:.8f}" for row in lattice]
        lines += ["ATOMIC_POSITIONS crystal"]
        lines += [
            f"  {s['element']} {s['fractional_coordinates'][0]:.8f} {s['fractional_coordinates'][1]:.8f} {s['fractional_coordinates'][2]:.8f}"
            for s in content["sites"]
        ]
        grid = [int(v) for v in params["kpoint_grid"]]
        lines += ["K_POINTS automatic", f"  {grid[0]} {grid[1]} {grid[2]} 0 0 0"]
        return InputBundle(
            builder_key=self.builder_key, builder_version=self.builder_version,
            normalized_parameters=normalized, files={"pw.in": "\n".join(lines) + "\n"},
            artifact_references=tuple(context.get("artifact_references") or ()),
        )

    def command_descriptor(self, context: dict[str, Any]) -> SafeCommandDescriptor | None:
        return SafeCommandDescriptor(
            executable_key=self.executable_key, argv=("-input", "pw.in"), stdin_file=None,
            timeout_seconds=int(context.get("timeout_seconds", 300)), environment_allowlist=ENVIRONMENT_ALLOWLIST,
        )

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        outcome: ExecutionOutcome = local_backend.execute(context["command_descriptor"], context["workdir"])
        return {
            "status": outcome.status, "exit_code": outcome.exit_code, "failure_code": outcome.failure_code,
            "stdout": outcome.stdout, "stderr": outcome.stderr, "stdout_truncated": outcome.stdout_truncated,
            "stderr_truncated": outcome.stderr_truncated, "elapsed_seconds": outcome.elapsed_seconds,
            "output_files": {},
        }

    def parse_outputs(self, context: dict[str, Any]) -> dict[str, Any]:
        stdout = context.get("stdout", "")
        quantities: dict[str, Any] = {}
        scf_converged = False
        for line in stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("!") and "total energy" in stripped:
                parts = stripped.split()
                for index, token in enumerate(parts):
                    if token == "=" and index + 1 < len(parts):
                        try:
                            quantities["total_energy"] = {"value": float(parts[index + 1]), "unit": "Ry"}
                        except ValueError:
                            return {"parse_status": "parser_failed", "quantities": {},
                                    "warnings": ["Unparseable total-energy value in pw.x output."]}
                        break
            if "convergence has been achieved" in stripped:
                scf_converged = True
        if "total_energy" not in quantities:
            return {"parse_status": "parser_failed", "quantities": {},
                    "warnings": ["pw.x output did not contain a final total energy."]}
        if not math.isfinite(float(quantities["total_energy"]["value"])):
            return {"parse_status": "parser_failed", "quantities": {}, "warnings": ["Non-finite total energy rejected."]}
        quantities["scf_converged"] = {"value": 1.0 if scf_converged else 0.0, "unit": "1"}
        return {"parse_status": "parsed", "quantities": quantities, "warnings": []}

    def assess_convergence(self, context: dict[str, Any]) -> dict[str, Any]:
        quantities = context.get("quantities") or {}
        criteria = {"requires_scf_convergence_flag": True,
                    "evaluator": [self.convergence_key, self.convergence_version]}
        if not quantities:
            return {"scientific_status": SimulationScientificStatus.PARSER_FAILED, "metrics": {}, "criteria": criteria,
                    "warnings": ["No parsed quantities."]}
        converged = bool(quantities.get("scf_converged", {}).get("value"))
        metrics = {"scf_converged": converged}
        if converged:
            return {"scientific_status": SimulationScientificStatus.CONVERGED, "metrics": metrics, "criteria": criteria, "warnings": []}
        # Exit code 0 with no SCF convergence flag is explicitly NOT a converged scientific result.
        return {"scientific_status": SimulationScientificStatus.UNCONVERGED, "metrics": metrics, "criteria": criteria,
                "warnings": ["pw.x did not report SCF convergence; no property estimate is accepted."]}


class InterfaceOnlyAdapter(BaseAdapter):
    """Capability seam with execution permanently disabled in Phase 6."""

    def __init__(self, key: str, method_family: str, representation_type: str, representation_format: str,
                 required_artifact_types: tuple[str, ...], fidelity: str, reason: str, limitations: tuple[str, ...]):
        self.key = key
        self._method_family = method_family
        self._representation_type = representation_type
        self._representation_format = representation_format
        self._required_artifact_types = required_artifact_types
        self._fidelity = fidelity
        self._reason = reason
        self._limitations = limitations
        self.parser_key = f"{key}_parser"
        self.parser_version = "0.0"
        self.builder_key = f"{key}_builder"
        self.builder_version = "0.0"
        self.convergence_key = f"{key}_convergence"
        self.convergence_version = "0.0"

    def capabilities(self) -> SimulationCapabilities:
        return SimulationCapabilities(
            method_family=self._method_family, supported_method_keys=(),
            supported_representation_types=(self._representation_type,),
            supported_representation_formats=(self._representation_format,),
            supported_material_families=(), supported_property_keys=(),
            required_artifact_types=self._required_artifact_types, fidelity=self._fidelity,
            deterministic=True, execution_supported=False, maximum_target_size=0,
            maximum_wall_time_seconds=0, resource_class="unavailable",
            known_limitations=self._limitations,
        )

    def check_availability(self) -> ProviderAvailability:
        return ProviderAvailability(False, "interface_only", self._reason)

    def validate_target(self, context: dict[str, Any]) -> ApplicabilityDecision:
        return ApplicabilityDecision("provider_unavailable", (_reason("INTERFACE_ONLY", self._reason),),
                                     (), self._required_artifact_types)

    def build_inputs(self, context: dict[str, Any]) -> InputBundle:
        raise NotImplementedError(self._reason)

    def command_descriptor(self, context: dict[str, Any]) -> SafeCommandDescriptor | None:
        return None

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(self._reason)

    def parse_outputs(self, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(self._reason)

    def assess_convergence(self, context: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError(self._reason)


CALPHAD_ADAPTER = InterfaceOnlyAdapter(
    key="calphad_interface_v1",
    method_family=SimulationMethodFamily.CALPHAD,
    representation_type=RepresentationType.PHASE_DESCRIPTION,
    representation_format="phase_description_json_v1",
    required_artifact_types=("thermodynamic_database",),
    fidelity=SimulationFidelity.THERMODYNAMIC_PHASE_MODEL,
    reason="Interface only in Phase 6. No reviewed thermodynamic database is registered, so no "
           "numerical CALPHAD result is produced and no phase diagram is generated.",
    limitations=(
        "Requires a component/phase representation plus an approved thermodynamic database artifact.",
        "Phase diagrams are never generated from invented database values.",
    ),
)

ML_FORCE_FIELD_ADAPTER = InterfaceOnlyAdapter(
    key="ml_force_field_interface_v1",
    method_family=SimulationMethodFamily.ML_FORCE_FIELD_FUTURE,
    representation_type=RepresentationType.MOLECULAR_TOPOLOGY,
    representation_format="atomistic_topology_json_v1",
    required_artifact_types=("force_field",),
    fidelity=SimulationFidelity.ML_INTERATOMIC_FUTURE,
    reason="Interface only in Phase 6. No licensed and reviewed ML interatomic potential weights are "
           "registered; weights are never downloaded. No model weights means the provider is unavailable.",
    limitations=("Requires separately reviewed, licensed and registered model weights.",),
)

ADAPTERS: dict[str, Any] = {
    a.key: a for a in (
        SoftwareFixtureHarmonicAdapter(),
        LammpsLocalAdapter(),
        QuantumEspressoLocalAdapter(),
        CALPHAD_ADAPTER,
        ML_FORCE_FIELD_ADAPTER,
    )
}


def get_adapter(adapter_key: str) -> Any:
    adapter = ADAPTERS.get(adapter_key)
    if adapter is None:
        # Registration is code-only; an unknown key is a configuration error, never an import hook.
        raise ValueError(f"Unknown simulation adapter: {adapter_key}")
    return adapter


def adapter_descriptor(adapter_key: str) -> dict[str, Any]:
    adapter = get_adapter(adapter_key)
    caps = adapter.capabilities()
    availability = adapter.check_availability()
    return {
        "adapter_key": adapter.key,
        "contract_version": ADAPTER_CONTRACT_VERSION,
        "method_family": caps.method_family,
        "supported_method_keys": list(caps.supported_method_keys),
        "supported_representation_types": list(caps.supported_representation_types),
        "supported_representation_formats": list(caps.supported_representation_formats),
        "supported_property_keys": list(caps.supported_property_keys),
        "required_artifact_types": list(caps.required_artifact_types),
        "fidelity": caps.fidelity,
        "deterministic": caps.deterministic,
        "execution_supported": caps.execution_supported,
        "maximum_target_size": caps.maximum_target_size,
        "maximum_wall_time_seconds": caps.maximum_wall_time_seconds,
        "resource_class": caps.resource_class,
        "known_limitations": list(caps.known_limitations),
        "availability": {
            "available": availability.available, "reason_code": availability.reason_code,
            "detail": availability.detail, "executable_name": availability.executable_name,
            "executable_version": availability.executable_version,
        },
    }
