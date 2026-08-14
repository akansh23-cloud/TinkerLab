# Prediction Model Registry

`PredictionModel` is a logical model family. `PredictionModelVersion` is the immutable scientific artifact used for inference.

A version records predictor contract/version, safe artifact format/checksum, feature schema/checksum, target property/unit, uncertainty method, applicability-policy version, training-data descriptor/checksum, validation/calibration metadata and approval/retirement timestamps.

Only approved, non-retired versions whose current artifact/schema checksums match their persisted checksums are executable.

Phase 4 does not expose arbitrary executable artifact upload. `pickle`/`joblib` execution is rejected. The only executable fixture format is the reviewed `tinkerlab_linear_json_v1` contract.

Global curated demo models are seed/admin controlled. Tenant mutation endpoints cannot alter the global seeded model.
