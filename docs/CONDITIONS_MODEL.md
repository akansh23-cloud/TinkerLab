# Observation Conditions

`ObservationConditionSet` provides typed common conditions:

- temperature + unit
- pressure + unit
- humidity percent
- strain rate
- sample orientation
- frequency + unit
- material/process state
- extensibility metadata

Units are validated before storage. Offset temperature conversion is handled by the units service.

Selection semantics are conservative: an explicitly contradictory reported condition makes an observation inapplicable for the requested context; an unreported condition may remain a lower-ranked fallback and is clearly labelled `partial` rather than exact.
