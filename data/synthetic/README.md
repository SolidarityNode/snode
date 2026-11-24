# Synthetic data

Only **synthetic** data may be committed here: invented spatial units, groups, facilities and tickets that describe no real person, place or service. Real data stays outside the repository (see CLAUDE.md "Data and privacy rules").

Each dataset added here should state how it was generated (script and seed) so it can be reproduced.

## Datasets

| Directory | Content | Generator | Processing note |
| --- | --- | --- | --- |
| [`demo/`](demo/README.md) | Two fictional municipalities (6 core + 2 buffer units), 3 groups, 2 services, 4 facilities, walking and car network, hand-check travel times, one reference disruption scenario. Used by `make seed`, tests and UAT | `scripts/generate_demo_data.py` (deterministic) | [DP-001](../../docs/data-processing/DP-001-synthetic-demo-dataset.md) |
