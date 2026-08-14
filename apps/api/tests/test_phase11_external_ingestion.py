"""Phase 11 — External ingestion tests.

Every test here runs against `FixtureTransport`, replaying payloads shaped like the real provider
responses. That is a deliberate constraint, not a limitation: a connector test that depends on a
live third-party API is a test that fails for reasons unrelated to the code, and a test suite that
fails randomly stops being read.

What these tests **do** verify: normalisation, unit handling, licence enforcement, snapshot
determinism, method-bias warnings and the 0 K state problem.

What they **cannot** verify: that the live endpoints still return this shape. Provider schemas
change. The fixtures below must be re-recorded against the real APIs before production use — see
`docs/PHASE_11_DATA_INGESTION.md`.
"""

from __future__ import annotations

import pytest

from app.models.entities import (
    ComputationalMethod,
    DatasetSnapshot,
    Evidence,
    IndustrialEvidence,
    Material,
    MaterialComponent,
    MaterialIdentifier,
    MaterialPropertyDefinition,
    MaterialPropertyObservation,
    MaterialState,
    Organisation,
    StateCompositionComponent,
    SourceProvider,
    SourceRecord,
)
from app.services.ingest import (
    CompToxConnector,
    ConnectorError,
    FixtureTransport,
    LicenceError,
    MaterialsProjectConnector,
    OptimadeConnector,
    PubChemConnector,
    connector_registry,
    ingest,
)
from app.services.ingest.base import LicenceTerms, RateLimiter, assert_ingest_permitted
from app.services.ingest.methods import (
    applicability_warnings,
    ensure_methods,
    has_blocking_warning,
    method_for_provider_record,
)
from app.services.replacement.licensing import (
    attribution_block,
    licence_audit,
    referenced_snapshot_ids,
    snapshot_manifest,
)

# ---------------------------------------------------------------------------------------------
# Fixtures shaped like real provider responses
# ---------------------------------------------------------------------------------------------
OPTIMADE_PAYLOAD = {
    "data": [
        {
            "id": "mp-1234",
            "type": "structures",
            "attributes": {
                "chemical_formula_reduced": "SiC",
                "chemical_formula_descriptive": "SiC",
                "elements": ["C", "Si"],
                "nelements": 2,
                "nsites": 4,
                "lattice_vectors": [[3.09, 0, 0], [-1.54, 2.67, 0], [0, 0, 5.05]],
                "cartesian_site_positions": [[0, 0, 0], [0, 0, 1.89]],
                "species_at_sites": ["Si", "C"],
                "structure_features": [],
                "last_modified": "2026-03-01T00:00:00Z",
            },
        },
        {
            "id": "mp-5678",
            "type": "structures",
            "attributes": {
                "chemical_formula_reduced": "GaN",
                "elements": ["Ga", "N"],
                "nelements": 2,
                "nsites": 4,
                "structure_features": [],
            },
        },
    ],
    "meta": {"api_version": "1.1.0", "more_data_available": False,
             "provider": {"name": "Materials Project", "prefix": "mp"}},
}

MP_PAYLOAD = {
    "data": [
        {
            "material_id": "mp-1234",
            "formula_pretty": "SiC",
            "elements": ["Si", "C"],
            "nelements": 2,
            "symmetry": {"crystal_system": "Hexagonal", "symbol": "P6_3mc", "number": 186},
            "band_gap": 2.28,
            "formation_energy_per_atom": -0.34,
            "energy_above_hull": 0.0,
            "density": 3.21,
            "bulk_modulus_vrh": 211.0,
            "is_stable": True,
            "theoretical": False,
            "database_IDs": {"icsd": ["icsd-123"]},
            "last_updated": "2026-04-13T00:00:00Z",
        },
        {
            "material_id": "mp-9999",
            "formula_pretty": "XyZ2",
            "elements": ["Xy", "Z"],
            "nelements": 2,
            "symmetry": {"crystal_system": "Cubic", "symbol": "Fm-3m", "number": 225},
            "band_gap": 3.9,
            "formation_energy_per_atom": 0.12,
            "energy_above_hull": 0.09,
            "is_stable": False,
            "theoretical": True,
            "last_updated": "2026-04-13T00:00:00Z",
        },
    ],
    "meta": {"api_version": "0.45.0", "db_version": "2026.04.13", "total_doc": 2},
}

PUBCHEM_PAYLOAD = {
    "PropertyTable": {
        "Properties": [{
            "CID": 24261,
            "MolecularFormula": "CSi",
            "MolecularWeight": "40.10",
            "CanonicalSMILES": "[C].[Si]",
            "InChI": "InChI=1S/C.Si",
            "InChIKey": "HBMJWWWQQXIZIP-UHFFFAOYSA-N",
            "IUPACName": "silicon carbide",
        }]
    }
}

COMPTOX_PAYLOAD = [
    {"listName": "PFASMASTER", "listDescription": "EPA PFAS master list", "dtxsid": "DTXSID001"},
    {"listName": "TSCA_ACTIVE_NCTE_0219", "listDescription": "TSCA active", "dtxsid": "DTXSID001"},
]


@pytest.fixture()
def org(db):
    return db.query(Organisation).first()


def _optimade(payload=None):
    fixtures = {"https://example.optimade.org/v1/structures": payload or OPTIMADE_PAYLOAD}
    return OptimadeConnector(
        FixtureTransport(fixtures, strict=False),
        base_url="https://example.optimade.org", provider_id="mp",
    )


def _mp(payload=None):
    fixtures = {"https://api.materialsproject.org/materials/summary/": payload or MP_PAYLOAD}
    return MaterialsProjectConnector(
        FixtureTransport(fixtures, strict=False), api_key="test-key"
    )


def _pubchem(payload=None):
    return PubChemConnector(
        FixtureTransport({}, strict=False) if payload is None else FixtureTransport({}, strict=False)
    )


# ---------------------------------------------------------------------------------------------
# Registry and framework
# ---------------------------------------------------------------------------------------------
def test_all_connectors_are_registered():
    assert set(connector_registry.list_keys()) >= {
        "optimade", "materials_project", "pubchem", "epa_comptox"
    }


def test_every_connector_declares_licence_terms():
    for key in connector_registry.list_keys():
        connector_cls = connector_registry.get(key)
        assert connector_cls.licence is not None, f"{key} must declare licence terms"
        assert connector_cls.licence.attribution_text


def test_fixture_transport_rejects_unregistered_calls():
    transport = FixtureTransport({"https://a/b": {"ok": True}}, strict=True)
    assert transport.get_json("https://a/b") == {"ok": True}
    with pytest.raises(ConnectorError):
        transport.get_json("https://a/unknown")


def test_rate_limiter_is_a_no_op_when_unset():
    limiter = RateLimiter(per_second=None)
    limiter.wait()  # must not raise or sleep


# ---------------------------------------------------------------------------------------------
# Licence enforcement
# ---------------------------------------------------------------------------------------------
def test_provider_registration_records_the_licence_position(db):
    connector = _mp()
    provider = connector.ensure_provider(db)
    assert provider.license_identifier == "CC-BY-4.0"
    assert provider.commercial_use_permitted is True
    assert provider.attribution_required is True
    assert "Materials Project" in provider.attribution_text
    assert provider.license_reviewed_at is not None
    db.rollback()


def test_unreviewed_provider_cannot_be_ingested_from(db):
    provider = SourceProvider(
        key="unreviewed_test_provider", display_name="Unreviewed", provider_type="external_api",
    )
    db.add(provider)
    db.flush()
    with pytest.raises(LicenceError) as excinfo:
        assert_ingest_permitted(provider)
    assert "LICENCE_NOT_REVIEWED" in str(excinfo.value)
    db.rollback()


def test_non_commercial_provider_is_refused_in_commercial_context(db):
    provider = SourceProvider(
        key="noncommercial_test", display_name="Academic only", provider_type="external_api",
        license_identifier="CC-BY-NC-4.0", commercial_use_permitted=False,
    )
    db.add(provider)
    db.flush()
    with pytest.raises(LicenceError) as excinfo:
        assert_ingest_permitted(provider, commercial_context=True)
    assert "COMMERCIAL_USE_NOT_PERMITTED" in str(excinfo.value)
    # The same provider is fine for internal research use.
    assert_ingest_permitted(provider, commercial_context=False)
    db.rollback()


# ---------------------------------------------------------------------------------------------
# OPTIMADE
# ---------------------------------------------------------------------------------------------
def test_optimade_normalizes_structure_fields():
    connector = _optimade()
    result = connector.fetch(filter='elements HAS "Si"')
    assert len(result.records) == 2
    normalized = connector.normalize(result.records[0])
    assert normalized["chemical_formula"] == "SiC"
    assert normalized["elements"] == ["C", "Si"]
    assert normalized["n_sites"] == 4
    # OPTIMADE carries structure, not properties.
    assert normalized["observations"] == []


def test_optimade_flags_unreviewed_subprovider_licences():
    connector = OptimadeConnector(
        FixtureTransport({"https://x/v1/structures": OPTIMADE_PAYLOAD}, strict=False),
        base_url="https://x", provider_id="some_new_provider",
    )
    result = connector.fetch(filter="nelements=2")
    assert result.metadata["licence_reviewed"] is False
    assert result.metadata["sub_provider_licence"] == "UNREVIEWED"


def test_optimade_requires_a_filter():
    with pytest.raises(ConnectorError):
        _optimade().fetch()


def test_optimade_external_ids_are_namespaced_by_subprovider():
    connector = _optimade()
    result = connector.fetch(filter="nelements=2")
    assert connector.external_id(result.records[0]) == "mp:mp-1234"


# ---------------------------------------------------------------------------------------------
# Materials Project
# ---------------------------------------------------------------------------------------------
def test_materials_project_requires_an_api_key():
    connector = MaterialsProjectConnector(FixtureTransport({}, strict=False))
    with pytest.raises(ConnectorError) as excinfo:
        connector.fetch()
    assert "API key" in str(excinfo.value)


def test_materials_project_maps_properties_with_units():
    connector = _mp()
    result = connector.fetch()
    normalized = connector.normalize(result.records[0])
    by_key = {o["property_key"]: o for o in normalized["observations"]}
    assert by_key["band_gap"]["numeric_value"] == 2.28
    assert by_key["band_gap"]["unit"] == "eV"
    assert by_key["bulk_modulus"]["unit"] == "GPa"
    assert by_key["formation_energy_per_atom"]["unit"] == "eV/atom"


def test_computed_values_carry_zero_kelvin_conditions():
    """The load-bearing honesty: a DFT number describes 0 K, not the operating temperature."""
    connector = _mp()
    normalized = connector.normalize(_mp().fetch().records[0])
    for observation in normalized["observations"]:
        assert observation["conditions"]["temperature_k"] == 0.0
        assert observation["computed"] is True


def test_theoretical_structures_are_flagged():
    connector = _mp()
    records = connector.fetch().records
    real = connector.normalize(records[0])
    hypothetical = connector.normalize(records[1])
    assert real["is_theoretical"] is False
    assert hypothetical["is_theoretical"] is True


def test_snapshot_records_provider_database_version():
    connector = _mp()
    result = connector.fetch()
    assert result.provider_version == "2026.04.13"
    assert result.is_reproducible is True


def test_missing_provider_version_marks_snapshot_unpinned():
    payload = {"data": MP_PAYLOAD["data"], "meta": {"total_doc": 2}}
    connector = _mp(payload)
    result = connector.fetch()
    assert result.provider_version is None
    assert result.is_reproducible is False
    assert "time-stamped, not pinned" in result.reproducibility_note


# ---------------------------------------------------------------------------------------------
# Computational method provenance
# ---------------------------------------------------------------------------------------------
def test_method_inference_keeps_unknown_computational_method_unknown():
    # Missing method provenance must never become an invented PBE claim.
    assert method_for_provider_record("materials_project", {}) == "dft_unspecified_static"
    assert method_for_provider_record("materials_project", {"run_type": "HSE06"}) == "dft_hse06_static"
    assert method_for_provider_record("materials_project", {"run_type": "R2SCAN"}) == "dft_scan_static"
    assert method_for_provider_record("materials_project", {"run_type": "GGA+U"}) == "dft_gga_plus_u_static"
    assert method_for_provider_record("pubchem", {}) == "reference_database_record"
    assert method_for_provider_record("epa_comptox", {}) == "regulatory_reference"


def test_pbe_band_gap_carries_a_high_severity_warning(db):
    methods = ensure_methods(db)
    warnings = applicability_warnings(methods["dft_pbe_static"], "band_gap")
    codes = {w["code"] for w in warnings}
    assert "SYSTEMATIC_METHOD_BIAS" in codes
    bias = next(w for w in warnings if w["code"] == "SYSTEMATIC_METHOD_BIAS")
    assert bias["direction"] == "underestimates"
    assert bias["severity"] == "high"
    assert has_blocking_warning(warnings) is True
    db.rollback()


def test_hybrid_functional_band_gap_is_not_blocking(db):
    methods = ensure_methods(db)
    warnings = applicability_warnings(methods["dft_hse06_static"], "band_gap")
    assert has_blocking_warning(warnings) is False
    db.rollback()


def test_temperature_mismatch_produces_a_warning(db):
    methods = ensure_methods(db)
    warnings = applicability_warnings(
        methods["dft_pbe_static"], "band_gap", requirement_temperature_k=525.0
    )
    mismatch = next(w for w in warnings if w["code"] == "COMPUTED_AT_DIFFERENT_TEMPERATURE")
    assert mismatch["computed_temperature_k"] == 0.0
    assert mismatch["required_temperature_k"] == 525.0
    assert mismatch["severity"] == "high"
    db.rollback()


def test_experimental_method_carries_no_bias_warnings(db):
    methods = ensure_methods(db)
    assert applicability_warnings(methods["experimental_measured"], "band_gap") == []
    db.rollback()


def test_method_catalogue_registration_is_idempotent(db):
    first = ensure_methods(db)
    second = ensure_methods(db)
    assert set(first) == set(second)
    assert db.query(ComputationalMethod).filter_by(key="dft_pbe_static").count() == 1
    db.rollback()


# ---------------------------------------------------------------------------------------------
# End-to-end persistence
# ---------------------------------------------------------------------------------------------
def test_ingest_writes_the_full_provenance_chain(db, org):
    result = ingest(
        db, _mp(), dataset_key="mp-sic-test", organisation_id=org.id,
        requirement_temperature_k=525.0,
    )
    assert result["ingested"] == 2
    assert result["observations"] > 0
    assert result["provider_version"] == "2026.04.13"

    snapshot = db.get(DatasetSnapshot, result["dataset_snapshot_id"])
    assert snapshot is not None and snapshot.record_count == 2

    record = db.query(SourceRecord).filter_by(dataset_snapshot_id=snapshot.id).first()
    assert record is not None

    evidence = db.query(Evidence).filter_by(dataset_snapshot_id=snapshot.id).first()
    assert evidence is not None
    assert evidence.computational_method_id is not None
    assert evidence.metadata_json["license_identifier"] == "CC-BY-4.0"
    db.rollback()


def test_ingested_computed_values_land_on_a_zero_kelvin_state(db, org):
    ingest(db, _mp(), dataset_key="mp-state-test", organisation_id=org.id)
    state = (
        db.query(MaterialState)
        .filter(MaterialState.organisation_id == org.id,
                MaterialState.label.like("%computed%"))
        .first()
    )
    assert state is not None
    assert state.temperature_k == 0.0
    assert "not a measurement" in (state.provenance_note or "")
    db.rollback()


def test_ingest_is_idempotent_on_repeat(db, org):
    first = ingest(db, _mp(), dataset_key="mp-idem", organisation_id=org.id)
    second = ingest(db, _mp(), dataset_key="mp-idem", organisation_id=org.id)
    assert first["ingested"] == 2
    assert second["ingested"] == 0
    assert second["already_ingested"] == 2
    db.rollback()


def test_observation_with_unmappable_unit_is_skipped_not_guessed(db, org):
    payload = {
        "data": [{
            "material_id": "mp-bad", "formula_pretty": "BadUnits", "elements": ["Si"],
            "nelements": 1, "symmetry": {}, "band_gap": 1.0, "density": 3.0,
        }],
        "meta": {"db_version": "2026.04.13"},
    }
    connector = _mp(payload)
    # Corrupt the mapping so band_gap arrives with an incompatible unit.
    from app.services.ingest import structures as structures_module

    original = dict(structures_module.MP_PROPERTY_MAP)
    structures_module.MP_PROPERTY_MAP["band_gap"] = ("band_gap", "GPa")
    try:
        # Ids are UUIDs, so "the newest row" has to be found by set difference, not by ordering.
        before = {o.id for o in db.query(MaterialPropertyObservation).all()}
        result = ingest(db, connector, dataset_key="mp-bad-units", organisation_id=org.id)
        after = {o.id for o in db.query(MaterialPropertyObservation).all()}
        new_ids = after - before

        # The record is still ingested for its structural content, but the dimensionally-wrong
        # band gap is refused rather than coerced into the nearest definition. Only density lands.
        assert result["ingested"] == 1
        assert result["observations"] == 1
        assert len(new_ids) == 1
        written_keys = {
            db.get(MaterialPropertyDefinition, db.get(MaterialPropertyObservation, oid)
                   .property_definition_id).key
            for oid in new_ids
        }
        assert written_keys == {"density"}
        assert "band_gap" not in written_keys
    finally:
        structures_module.MP_PROPERTY_MAP.clear()
        structures_module.MP_PROPERTY_MAP.update(original)
        db.rollback()


def test_connector_declaring_non_commercial_licence_is_refused(db, org):
    """A connector's declared terms are authoritative and are re-asserted on every registration,
    so a licence position cannot drift in the database. What must be blocked is a connector whose
    declared licence genuinely forbids the use it is being put to."""

    class NonCommercialConnector(MaterialsProjectConnector):
        key = "test_non_commercial"
        display_name = "Academic-only test source"
        licence = LicenceTerms(
            identifier="CC-BY-NC-4.0", url=None, commercial_use_permitted=False,
            redistribution_permitted=False, attribution_required=True,
            attribution_text="Academic-only test source.",
        )

    connector = NonCommercialConnector(
        FixtureTransport({"https://api.materialsproject.org/materials/summary/": MP_PAYLOAD},
                         strict=False),
        api_key="test-key",
    )
    with pytest.raises(LicenceError) as excinfo:
        ingest(db, connector, dataset_key="nc-blocked", organisation_id=org.id)
    assert "COMMERCIAL_USE_NOT_PERMITTED" in str(excinfo.value)

    # The same source remains usable for internal research.
    result = ingest(
        db, connector, dataset_key="nc-internal", organisation_id=org.id,
        commercial_context=False,
    )
    assert result["ingested"] == 2
    db.rollback()


def test_connector_registration_re_asserts_declared_licence(db):
    """Tampering with the stored position is corrected on the next registration."""
    connector = _mp()
    provider = connector.ensure_provider(db)
    provider.commercial_use_permitted = None
    provider.license_identifier = "tampered"
    db.flush()
    refreshed = connector.ensure_provider(db)
    assert refreshed.commercial_use_permitted is True
    assert refreshed.license_identifier == "CC-BY-4.0"
    db.rollback()


# ---------------------------------------------------------------------------------------------
# Substance and regulatory connectors
# ---------------------------------------------------------------------------------------------
def test_pubchem_normalizes_identity_and_molar_mass():
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/silicon%20carbide/property/"
        "MolecularFormula,MolecularWeight,CanonicalSMILES,InChI,InChIKey,IUPACName/JSON"
    )
    connector = PubChemConnector(FixtureTransport({url: PUBCHEM_PAYLOAD}, strict=False))
    result = connector.fetch(namespace="name", identifier="silicon%20carbide")
    normalized = connector.normalize(result.records[0])
    namespaces = {i["namespace"] for i in normalized["identifiers"]}
    assert "inchikey" in namespaces and "pubchem_cid" in namespaces
    assert normalized["observations"][0]["property_key"] == "molar_mass"
    assert normalized["observations"][0]["unit"] == "g/mol"


def test_pubchem_snapshot_is_honestly_marked_unpinnable():
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/24261/property/"
        "MolecularFormula,MolecularWeight,CanonicalSMILES,InChI,InChIKey,IUPACName/JSON"
    )
    connector = PubChemConnector(FixtureTransport({url: PUBCHEM_PAYLOAD}, strict=False))
    result = connector.fetch(namespace="cid", identifier="24261")
    assert result.is_reproducible is False
    assert "does not expose a dataset version" in result.reproducibility_note


def test_pubchem_rejects_unknown_namespace():
    connector = PubChemConnector(FixtureTransport({}, strict=False))
    with pytest.raises(ConnectorError):
        connector.fetch(namespace="not_a_namespace", identifier="x")


def test_comptox_list_membership_is_evidence_not_a_verdict():
    url = "https://api-ccte.epa.gov/chemical/list/search/by-dtxsid/DTXSID001"
    connector = CompToxConnector(FixtureTransport({url: COMPTOX_PAYLOAD}, strict=False),
                                 api_key="test-key")
    result = connector.fetch(mode="by_dtxsid", dtxsid="DTXSID001")
    normalized = connector.normalize(result.records[0])
    assert normalized["indicates_pfas"] is True
    evidence = normalized["industrial_evidence"][0]
    assert evidence["category"] == "regulatory"
    assert evidence["boolean_value"] is True
    # The wording must not assert a rejection.
    assert "not an automatic" in evidence["notes"]


def test_comptox_requires_an_api_key():
    with pytest.raises(ConnectorError):
        CompToxConnector(FixtureTransport({}, strict=False)).fetch(dtxsid="X")


# ---------------------------------------------------------------------------------------------
# Licence audit and dossier gating
# ---------------------------------------------------------------------------------------------
def test_licence_audit_clears_permissively_licensed_evidence(db, org):
    result = ingest(db, _mp(), dataset_key="mp-audit", organisation_id=org.id)
    evidence_ids = [r["evidence_id"] for r in result["results"] if r.get("evidence_id")]
    audit = licence_audit(db, evidence_ids=evidence_ids)
    assert audit["export_permitted"] is True
    assert any(p["license_identifier"] == "CC-BY-4.0" for p in audit["providers"])
    db.rollback()


def test_licence_audit_blocks_unreviewed_evidence(db, org):
    result = ingest(db, _mp(), dataset_key="mp-audit-block", organisation_id=org.id)
    evidence_ids = [r["evidence_id"] for r in result["results"] if r.get("evidence_id")]
    provider = db.query(SourceProvider).filter_by(key="materials_project").one()
    provider.commercial_use_permitted = None
    db.flush()
    audit = licence_audit(db, evidence_ids=evidence_ids)
    assert audit["export_permitted"] is False
    assert audit["blocking"]
    db.rollback()


def test_attribution_block_names_every_source_requiring_credit(db, org):
    result = ingest(db, _mp(), dataset_key="mp-attrib", organisation_id=org.id)
    evidence_ids = [r["evidence_id"] for r in result["results"] if r.get("evidence_id")]
    block = attribution_block(db, evidence_ids=evidence_ids)
    assert block["entries"]
    assert any("Materials Project" in e["attribution"] for e in block["entries"])
    db.rollback()


def test_snapshot_manifest_flags_unpinned_datasets(db, org):
    payload = {"data": MP_PAYLOAD["data"], "meta": {"total_doc": 2}}
    result = ingest(db, _mp(payload), dataset_key="mp-unpinned", organisation_id=org.id)
    manifest = snapshot_manifest(db, snapshot_ids=[result["dataset_snapshot_id"]])
    assert manifest["fully_reproducible"] is False
    assert manifest["unpinned_count"] == 1
    assert "re-checked before any regulatory filing" in manifest["note"]
    db.rollback()


def test_locally_produced_evidence_needs_no_licence(db):
    """Customer measurements have no external provider and must never block an export."""
    audit = licence_audit(db, evidence_ids=[])
    assert audit["export_permitted"] is True
    assert audit["providers"] == []


# ---------------------------------------------------------------------------------------------
# Phase 11.1 adversarial integrity regressions
# ---------------------------------------------------------------------------------------------
def test_snapshot_checksum_changes_when_record_content_changes(db, org):
    first_payload = {"data": [dict(MP_PAYLOAD["data"][0], band_gap=1.0)], "meta": MP_PAYLOAD["meta"]}
    second_payload = {"data": [dict(MP_PAYLOAD["data"][0], band_gap=3.0)], "meta": MP_PAYLOAD["meta"]}
    first_result = _mp(first_payload).fetch(max_records=1)
    first_provider = _mp(first_payload).ensure_provider(db)
    first_snapshot = _mp(first_payload).create_snapshot(
        db, first_provider, first_result, dataset_key="checksum-a", organisation_id=org.id
    )
    second_result = _mp(second_payload).fetch(max_records=1)
    second_snapshot = _mp(second_payload).create_snapshot(
        db, first_provider, second_result, dataset_key="checksum-a", organisation_id=org.id
    )
    assert first_snapshot.content_checksum != second_snapshot.content_checksum
    db.rollback()


def test_optimade_api_version_is_not_misrepresented_as_dataset_version():
    result = _optimade().fetch(filter="nelements=2")
    assert result.metadata["api_version"] == "1.1.0"
    assert result.provider_version is None
    assert result.is_reproducible is False
    assert "not a dataset pin" in result.reproducibility_note


def test_optimade_follows_pagination_when_more_data_is_available():
    first = {
        "data": [OPTIMADE_PAYLOAD["data"][0]],
        "meta": {"api_version": "1.1.0", "database_version": "2026-08-01", "more_data_available": True},
        "links": {"next": "https://example.optimade.org/v1/structures?page_offset=1"},
    }
    second = {
        "data": [OPTIMADE_PAYLOAD["data"][1]],
        "meta": {"api_version": "1.1.0", "database_version": "2026-08-01", "more_data_available": False},
    }
    connector = OptimadeConnector(FixtureTransport({
        "https://example.optimade.org/v1/structures": first,
        "https://example.optimade.org/v1/structures?page_offset=1": second,
    }, strict=False), base_url="https://example.optimade.org", provider_id="mp")
    result = connector.fetch(filter="nelements=2")
    assert len(result.records) == 2
    assert result.provider_version == "2026-08-01"
    assert result.metadata["complete_result_set"] is True
    assert result.is_reproducible is True


def test_pubchem_persists_orm_identifiers_and_reference_method(db, org):
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/24261/property/"
        "MolecularFormula,MolecularWeight,CanonicalSMILES,InChI,InChIKey,IUPACName/JSON"
    )
    connector = PubChemConnector(FixtureTransport({url: PUBCHEM_PAYLOAD}, strict=True))
    result = ingest(
        db, connector, dataset_key="pubchem-sic", organisation_id=org.id,
        namespace="cid", identifier="24261",
    )
    assert result["ingested"] == 1
    item = result["results"][0]
    identifiers = db.query(MaterialIdentifier).filter_by(material_id=item["material_id"]).all()
    assert {row.namespace for row in identifiers} >= {"pubchem_cid", "inchikey"}
    evidence = db.get(Evidence, item["evidence_id"])
    assert evidence.evidence_type == "external_reference"
    assert evidence.computational_method_id is None
    assert evidence.metadata_json["method_key"] == "reference_database_record"
    assert "experimental" not in (evidence.method or "").casefold()
    db.rollback()


def test_formula_stoichiometry_is_preserved_for_ga2o3(db, org):
    payload = {
        "data": [{
            "material_id": "mp-ga2o3", "formula_pretty": "Ga2O3", "elements": ["Ga", "O"],
            "nelements": 2, "symmetry": {}, "band_gap": 4.8, "theoretical": False,
        }],
        "meta": {"db_version": "2026.08.01", "total_doc": 1},
    }
    result = ingest(db, _mp(payload), dataset_key="ga2o3", organisation_id=org.id)
    state_id = result["results"][0]["state_id"]
    rows = db.query(StateCompositionComponent).filter_by(state_id=state_id).all()
    stoich = {row.element: row.stoichiometry for row in rows}
    assert stoich == {"Ga": pytest.approx(2.0), "O": pytest.approx(3.0)}
    components = db.query(MaterialComponent).filter_by(material_id=result["results"][0]["material_id"]).all()
    assert {row.component_name: row.amount_value for row in components} == {
        "Ga": pytest.approx(2.0), "O": pytest.approx(3.0)
    }
    db.rollback()


def test_unparseable_formula_never_falls_back_to_one_to_one_stoichiometry(db, org):
    payload = {
        "data": [{
            "material_id": "mp-unsafe-formula", "formula_pretty": "Ga??O", "elements": ["Ga", "O"],
            "nelements": 2, "symmetry": {}, "band_gap": 1.2,
        }],
        "meta": {"db_version": "2026.08.01", "total_doc": 1},
    }
    result = ingest(db, _mp(payload), dataset_key="unsafe-formula", organisation_id=org.id)
    state_id = result["results"][0]["state_id"]
    assert db.query(StateCompositionComponent).filter_by(state_id=state_id).count() == 0
    db.rollback()


def test_comptox_list_name_does_not_collapse_distinct_substances(db, org):
    url = "https://api-ccte.epa.gov/chemical/list/search/by-name/PFASMASTER"
    records = [
        {"listName": "PFASMASTER", "dtxsid": "DTXSID001", "preferredName": "Chemical One"},
        {"listName": "PFASMASTER", "dtxsid": "DTXSID002", "preferredName": "Chemical Two"},
    ]
    connector = CompToxConnector(FixtureTransport({url: records}, strict=True), api_key="test-key")
    result = ingest(
        db, connector, dataset_key="pfas-members", organisation_id=org.id,
        mode="list_contents", list_name="PFASMASTER",
    )
    material_ids = {row["material_id"] for row in result["results"]}
    assert len(material_ids) == 2
    identifiers = db.query(MaterialIdentifier).filter(MaterialIdentifier.material_id.in_(material_ids)).all()
    assert {row.value for row in identifiers if row.namespace == "dtxsid"} == {"DTXSID001", "DTXSID002"}
    industrial = db.query(IndustrialEvidence).filter(IndustrialEvidence.material_id.in_(material_ids)).all()
    assert len(industrial) == 2
    assert all(row.source_record_id for row in industrial)
    db.rollback()


def test_cross_provider_materials_project_identity_converges(db, org):
    mp_result = ingest(db, _mp(), dataset_key="mp-identity", organisation_id=org.id, max_records=1)
    mp_material_id = mp_result["results"][0]["material_id"]
    optimade_payload = dict(OPTIMADE_PAYLOAD)
    optimade_payload["data"] = [OPTIMADE_PAYLOAD["data"][0]]
    optimade_payload["meta"] = {
        **OPTIMADE_PAYLOAD["meta"], "database_version": "2026.08.01", "more_data_available": False,
    }
    opt_result = ingest(
        db, _optimade(optimade_payload), dataset_key="optimade-identity", organisation_id=org.id,
        filter='id="mp-1234"',
    )
    assert opt_result["results"][0]["material_id"] == mp_material_id
    assert opt_result["results"][0]["identity_match_class"] == "exact"
    db.rollback()


def test_redistribution_restricted_provider_blocks_export_audit(db, org):
    result = ingest(db, _mp(), dataset_key="mp-restricted", organisation_id=org.id, max_records=1)
    evidence_ids = [row["evidence_id"] for row in result["results"]]
    provider = db.query(SourceProvider).filter_by(key="materials_project").one()
    provider.redistribution_permitted = False
    provider.license_reviewed_by = "human:compliance"
    db.flush()
    audit = licence_audit(db, evidence_ids=evidence_ids)
    assert audit["export_permitted"] is False
    assert audit["blocking"][0]["status"] == "REDISTRIBUTION_RESTRICTED"
    db.rollback()


def test_human_reviewed_licence_is_not_overwritten_by_connector(db):
    connector = _mp()
    provider = connector.ensure_provider(db)
    provider.license_identifier = "CUSTOM-REVIEW"
    provider.commercial_use_permitted = True
    provider.redistribution_permitted = False
    provider.license_reviewed_by = "human:legal"
    db.flush()
    refreshed = connector.ensure_provider(db)
    assert refreshed.license_identifier == "CUSTOM-REVIEW"
    assert refreshed.redistribution_permitted is False
    assert refreshed.license_reviewed_by == "human:legal"
    db.rollback()


def test_only_referenced_external_snapshots_enter_manifest(db, org):
    used = ingest(db, _mp(), dataset_key="used-snapshot", organisation_id=org.id, max_records=1)
    unused = ingest(db, _mp(), dataset_key="unused-snapshot", organisation_id=org.id, max_records=1)
    used_evidence = [row["evidence_id"] for row in used["results"] if row.get("evidence_id")]
    ids = referenced_snapshot_ids(db, evidence_ids=used_evidence)
    assert ids == [used["dataset_snapshot_id"]]
    assert unused["dataset_snapshot_id"] not in ids
    db.rollback()


def test_external_data_provider_and_snapshot_api(client, db, org):
    result = ingest(db, _mp(), dataset_key="api-snapshot", organisation_id=org.id, max_records=1)
    db.commit()
    providers = client.get("/external-data/providers")
    assert providers.status_code == 200
    assert {row["key"] for row in providers.json()} >= {"materials_project", "pubchem", "epa_comptox", "optimade"}
    snapshots = client.get("/external-data/snapshots", headers={"X-Organisation-ID": org.id})
    assert snapshots.status_code == 200
    assert any(row["id"] == result["dataset_snapshot_id"] for row in snapshots.json())


# ---------------------------------------------------------------------------------------------
# Units introduced for external sources
# ---------------------------------------------------------------------------------------------
def test_external_source_units_convert_correctly():
    from app.services.units import convert

    assert convert(1.0, "eV", "meV") == pytest.approx(1000.0)
    assert convert(1.0, "S/cm", "S/m") == pytest.approx(100.0)
    assert convert(10000.0, "ppm", "wt%") == pytest.approx(1.0)
    assert convert(1.0, "megatonne", "tonne") == pytest.approx(1e6)
    assert convert(1000.0, "USD/tonne", "USD/kg") == pytest.approx(1.0)
    assert convert(1.0, "W/(cm*K)", "W/(m*K)") == pytest.approx(100.0)


def test_ambiguous_kt_alias_is_not_registered():
    """`kt` is knots in pint. A silent five-order-of-magnitude error in a tonnage figure is worse
    than an unsupported-unit exception, so the alias was deliberately removed."""
    from app.services.units import UNITS, UnitError, ensure_known

    assert "kt" not in UNITS
    with pytest.raises(UnitError):
        ensure_known("kt")


def test_domain_units_bypass_pint():
    from app.services.units import INTERNAL_ONLY_UNITS

    for unit in ("eV/atom", "wt%", "USD/tonne", "tonne", "ppb"):
        assert unit in INTERNAL_ONLY_UNITS


def test_method_level_warnings_are_not_repeated_per_observation(db, org):
    """A temperature mismatch describes the calculation, not each property, so it appears once."""
    result = ingest(
        db, _mp(), dataset_key="mp-dedupe", organisation_id=org.id,
        requirement_temperature_k=525.0,
    )
    evidence_id = next(r["evidence_id"] for r in result["results"] if r.get("evidence_id"))
    evidence = db.get(Evidence, evidence_id)
    codes = [w["code"] for w in evidence.applicability_warnings]

    assert codes.count("COMPUTED_AT_DIFFERENT_TEMPERATURE") == 1
    assert codes.count("NO_ZERO_POINT_ENERGY") == 1
    # Property-level bias warnings remain per property.
    bias = [w for w in evidence.applicability_warnings if w["code"] == "SYSTEMATIC_METHOD_BIAS"]
    assert len({w["property_key"] for w in bias}) == len(bias)
    # Highest severity first, so a reader sees the blocking problem before the footnote.
    severities = [w["severity"] for w in evidence.applicability_warnings]
    assert severities == sorted(severities, key=lambda s: {"high": 0, "medium": 1, "low": 2}[s])
    db.rollback()


def test_external_data_method_catalogue_and_evidence_provenance_are_visible(client, db, org):
    payload = {
        "data": [{
            "material_id": "mp-api-provenance", "formula_pretty": "SiC", "elements": ["Si", "C"],
            "nelements": 2, "symmetry": {}, "band_gap": 2.4, "theoretical": False,
        }],
        "meta": {"db_version": "2026.08.14", "total_doc": 1},
    }
    result = ingest(db, _mp(payload), dataset_key="api-provenance", organisation_id=org.id, max_records=1)
    db.commit()

    methods = client.get("/external-data/methods")
    assert methods.status_code == 200
    method_keys = {row["key"] for row in methods.json()}
    assert "dft_unspecified_static" in method_keys

    evidence_id = next(row["evidence_id"] for row in result["results"] if row.get("evidence_id"))
    evidence_response = client.get("/evidence", headers={"X-Organisation-ID": org.id})
    assert evidence_response.status_code == 200
    evidence = next(row for row in evidence_response.json() if row["id"] == evidence_id)
    assert evidence["dataset_snapshot_id"] == result["dataset_snapshot_id"]
    assert evidence["computational_method_id"] is not None
    assert isinstance(evidence["applicability_warnings"], list)
    assert evidence["source_record"]["dataset_snapshot_id"] == result["dataset_snapshot_id"]
    assert evidence["provider"]["license_identifier"]
    assert evidence["provider"]["commercial_use_permitted"] is True
    assert "redistribution_permitted" in evidence["provider"]


def test_external_ingestion_rejects_local_optimade_ssrf_target(client, org):
    response = client.post(
        "/external-data/ingest",
        headers={"X-Organisation-ID": org.id},
        json={
            "provider": "optimade",
            "dataset_key": "ssrf-test",
            "query": {"filter": 'elements HAS "Si"'},
            "optimade_base_url": "https://localhost",
            "optimade_provider_id": "local",
        },
    )
    assert response.status_code == 422
    assert "Private/local" in response.json()["detail"]


def test_external_ingestion_query_size_is_bounded(client, org):
    response = client.post(
        "/external-data/ingest",
        headers={"X-Organisation-ID": org.id},
        json={
            "provider": "pubchem",
            "dataset_key": "oversized-query",
            "query": {"identifier": "x" * 21_000},
        },
    )
    assert response.status_code == 422


def test_materials_project_mixed_workflows_bind_methods_per_property(db, org):
    payload = {
        "data": [{
            "material_id": "mp-mixed-methods",
            "formula_pretty": "SiC",
            "elements": ["Si", "C"],
            "nelements": 2,
            "symmetry": {},
            "band_gap": 3.1,
            "density": 3.21,
            "theoretical": False,
            "calculation_provenance": {
                "band_gap": {"functional": "HSE06"},
                "density": {"functional": "SCAN"},
            },
        }],
        "meta": {"db_version": "2026.08.14", "total_doc": 1},
    }
    result = ingest(db, _mp(payload), dataset_key="mixed-methods", organisation_id=org.id)
    item = result["results"][0]
    assert item["evidence_method"] == "dft_unspecified_static"
    assert len(set(item["observation_evidence_ids"])) == 2

    observations = (
        db.query(MaterialPropertyObservation)
        .filter_by(material_id=item["material_id"])
        .all()
    )
    property_methods = {}
    for observation in observations:
        evidence = db.get(Evidence, observation.evidence_id)
        method = db.get(ComputationalMethod, evidence.computational_method_id)
        definition = db.get(MaterialPropertyDefinition, observation.property_definition_id)
        property_methods[definition.key] = method.key
        assert evidence.parent_evidence_id == item["evidence_id"]
        assert evidence.metadata_json["property_scoped_method_provenance"] is True

    assert property_methods["band_gap"] == "dft_hse06_static"
    assert property_methods["density"] == "dft_scan_static"
    db.rollback()
