# Conflict Detection Policy

Conflict detection is configured per property definition.

Supported policies:

- `relative`: relative difference exceeds property-specific tolerance.
- `absolute`: absolute difference exceeds property-specific tolerance.
- `uncertainty_overlap`: reported uncertainty intervals do not overlap.
- `informational`: no automatic conflict assertion.

Only observations in equivalent typed condition contexts are automatically compared. A curator preference records a resolution posture but does not delete or alter the conflicting observation.
