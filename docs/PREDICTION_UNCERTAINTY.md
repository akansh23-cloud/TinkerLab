# Prediction Uncertainty

Every Phase-4 numeric prediction must carry uncertainty. A point estimate without an uncertainty method is invalid for this subsystem.

The synthetic demo predictor uses a **fixed validation residual interval** from its deterministic synthetic software-validation fixture. Its seeded interval half-width and reported coverage describe only that synthetic fixture; they are not evidence of real-material calibration.

## Hard constraint interpretation

For inequalities, the whole interval is evaluated:

- interval wholly satisfies -> `PASS`, origin `model_prediction`;
- interval wholly violates -> `FAIL`, origin `model_prediction`;
- interval intersects the decision boundary -> `UNKNOWN`, reason `PREDICTION_INTERVAL_CROSSES_CONSTRAINT`.

Equality/target behavior is conservative: an interval spanning the target is not treated as proof of equality.

Known evidence continues to be evaluated independently and is preferred by the default evidence policy.
