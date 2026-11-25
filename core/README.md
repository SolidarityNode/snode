# solidaritynode-core

The modelling library of SolidarityNode. Pure Python, no web framework, no database driver.

At this stage it contains the typed domain model (`solidaritynode_core.model`), typed interfaces
(`Protocol`s) for every module, the model registry, the scenario overlay and the **diagnostic
model** `diagnostic-v0` (`solidaritynode_core.validation.diagnostic`), which only proves the
platform's mechanics and is not a research result. No scientific method is implemented yet; see
`docs/specs/00-domain-model.md` and `docs/specs/open-questions.md`.

```bash
uv sync --locked          # install
uv run pytest             # tests
uv run ruff check . && uv run mypy   # lint and type check
```
