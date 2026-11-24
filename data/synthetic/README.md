# Synthetic data

Only **synthetic** data may be committed here: invented spatial units, groups, facilities and tickets that describe no real person, place or service. Real data stays outside the repository (see AGENTS.md "Data and privacy rules").

Each dataset added here should state how it was generated (script and seed) so it can be reproduced.

## Datasets

| Directory | Content | Generator | Processing note |
| --- | --- | --- | --- |
| [`demo/`](demo/README.md) | Two fictional municipalities (6 core + 2 buffer units), 3 groups, 2 services, 4 facilities, walking and car network, hand-check travel times, one reference disruption scenario. Source of the demo packages; read by core tests | `scripts/generate_demo_data.py` (deterministic) | [DP-001](../../docs/data-processing/DP-001-synthetic-demo-dataset.md) |
| [`packages/`](packages/README.md) | Demo data packages 1.0.0 (neighbour B without facilities) and 1.1.0 (B onboarded, one capacity corrected, one facility closed). Imported by `make seed` and UAT | `scripts/build_demo_packages.py` (deterministic) | [DP-002](../../docs/data-processing/DP-002-synthetic-demo-packages.md) |
