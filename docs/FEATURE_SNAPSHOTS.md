# Prediction Feature Snapshots

A persisted prediction never depends on mutable "current candidate state" alone. `PredictionInputSnapshot` records the normalized model input used at inference time.

Snapshots include target kind/id, feature-schema version, normalized features, feature checksum, source scientific object checksum, condition checksum, missing features, redaction flags and unit-normalization version.

Known materials are featurized from Phase-2 structured composition/process state. Hypotheses are featurized from Phase-3 concrete proposed composition/process parameters. Baseline observations are never copied into hypothesis features.

The generic polymer demo uses only generic formulation quantities; it does not derive fictional chemistry descriptors from names.
