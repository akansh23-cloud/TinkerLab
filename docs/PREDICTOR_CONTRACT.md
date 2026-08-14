# Property Predictor Contract

A registered predictor declares a key, contract version, supported safe artifact formats, deterministic behavior and maximum batch size.

Phase-4 execution follows:

```text
Target(s)
  -> deterministic feature snapshot(s)
  -> applicability assessment
  -> applicable subset
  -> one bounded predict_batch call
  -> uncertainty-bearing outputs
  -> immutable prediction records
```

The predictor cannot discover arbitrary Python modules from a user path. Predictor implementations are explicitly code-registered.

The seeded `demo_linear_json` predictor is deterministic and interpretable. It is a software fixture, not a validated scientific model.
