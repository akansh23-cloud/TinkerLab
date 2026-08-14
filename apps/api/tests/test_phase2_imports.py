import json

from app.db.seed import sid
from app.models.entities import ImportBatch, Material, MaterialIdentifier, SourceRecord
from app.services.ingestion import commit_import, preview_import


def sample_payload(external_id="fixture-private-001", canonical="import-demo-private"):
    return json.dumps({
        "materials": [{
            "external_record_id": external_id,
            "canonical_name": canonical,
            "display_name": "Imported Private Demo Material",
            "material_family": "polymer",
            "visibility": "private",
            "identifiers": [{"namespace": "customer_code", "value": f"CUST-{external_id}", "is_primary": True}],
            "composition": [
                {"component_name": "Private matrix", "component_role": "matrix", "amount_value": 90, "amount_unit": "%", "amount_basis": "weight_percent"},
                {"component_name": "Private additive", "is_redacted": True, "redaction_label": "CUSTOMER-SECRET", "amount_basis": "qualitative"}
            ],
            "process_states": [{"state_label": "conditioned specimen", "process_name": "customer process", "parameters": {"confidential": True}}],
            "evidence": [{"key": "e1", "evidence_type": "user_provided", "title": "Customer import fixture", "method": "Imported customer record"}],
            "observations": [{
                "property_key": "density", "value_type": "numeric", "numeric_value": 1230, "unit": "kg/m^3", "evidence_key": "e1",
                "condition_set": {"temperature_value": 23, "temperature_unit": "degC"}
            }]
        }]
    })


def test_import_preview_and_commit_are_idempotent(db):
    content = sample_payload()
    preview = preview_import(db, "json", content)
    assert preview["valid"] is True
    assert preview["material_count"] == 1
    first = commit_import(db, organisation_id=sid("org"), input_format="json", content=content, provider_key="local_import", idempotency_key="test-1")
    second = commit_import(db, organisation_id=sid("org"), input_format="json", content=content, provider_key="local_import", idempotency_key="test-1")
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert first["import_id"] == second["import_id"]
    assert db.query(ImportBatch).filter_by(payload_checksum=first["payload_checksum"], status="committed").count() == 1
    material = db.query(Material).filter_by(canonical_name="import-demo-private").one()
    assert material.owner_organisation_id == sid("org")
    assert material.visibility == "private"
    assert db.query(SourceRecord).filter_by(external_record_id="fixture-private-001").count() == 1
    assert db.query(MaterialIdentifier).filter_by(material_id=material.id).count() == 1


def test_invalid_import_is_not_committed(db):
    bad = json.dumps({"materials": [{"external_record_id": "bad", "canonical_name": "bad", "display_name": "Bad", "material_family": "polymer", "evidence": [], "observations": [{"property_key": "not_a_property", "numeric_value": 1, "unit": "MPa", "evidence_key": "missing"}]}]})
    preview = preview_import(db, "json", bad)
    assert preview["valid"] is False
    assert preview["errors"]
