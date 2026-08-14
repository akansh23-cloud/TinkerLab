# Prediction Selection Policy

Phase-4 comparison behavior is explicit and backward-compatible.

Default project comparison does **not** use model predictions. It preserves Phase-3/Phase-2 semantics.

A caller may opt in using a specific `prediction_run_id`. Then:

1. applicable known evidence remains preferred;
2. a prediction may fill a missing value slot only for the matching target/property in that explicit run;
3. inapplicable/failed predictions never fill values;
4. uncertainty intervals are evaluated conservatively;
5. UI/API include `value_origin`, prediction ID/version/interval and applicability.

Thus a prediction does not silently rewrite historical evidence semantics.
