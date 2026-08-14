# Model Applicability Domain

Applicability is evaluated before model inference.

Statuses include:

- `in_domain` — inference allowed;
- `borderline` — inference allowed with prominent warning under configured policy;
- `out_of_domain` — no numeric prediction;
- `incomplete_inputs` — no numeric prediction;
- `unsupported_property` — no numeric prediction;
- `unsupported_material_family` — no numeric prediction;
- `unsupported_conditions` — no numeric prediction.

Checks cover model lifecycle, property/family support, required features, redaction, numeric feature ranges and target-condition ranges/units.

Missing or redacted required inputs are never guessed. The demo model has no hidden imputation.
