# solidaritynode-core

The modelling library of SolidarityNode. Pure Python, no web framework, no database driver.

At this stage it contains **only** the typed domain model (`solidaritynode_core.model`) and typed
interfaces (`Protocol`s) for every module. No scientific method is implemented yet; see
`docs/specs/00-domain-model.md` and `docs/specs/open-questions.md`.

```bash
uv sync --locked          # install
uv run pytest             # tests
uv run ruff check . && uv run mypy   # lint and type check
```
