# Prediction Reproducibility

Scientific checksums exclude timestamps and display labels.

A prediction result checksum depends on:

- model/version and artifact checksum;
- predictor contract version;
- normalized feature checksum;
- target property;
- normalized target-condition checksum;
- prediction configuration checksum;
- applicability status;
- deterministic output + uncertainty representation.

A run checksum is derived from ordered target-result checksums.

Tests prove identical immutable inputs reproduce identical result/run checksums and meaningful condition changes change the result checksum.
