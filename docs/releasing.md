# Releasing

> For the maintainer. The version lives in one place, the file [`VERSION`](../VERSION) at the repository root.

## Versions

SolidarityNode follows [semantic versioning](https://semver.org/). While the version is **0.x**:

- the **minor** number (0.**1**.0 → 0.**2**.0) goes up for new features **and** for breaking changes (API, scenario schema, data package schema, configuration, database migrations that need care);
- the **patch** number (0.1.**0** → 0.1.**1**) goes up for fixes only, with no migration and no change of behaviour beyond the fix;
- 1.0.0 will mean a stable API and data formats for installations.

`VERSION` is the single source. `make version-sync` writes it into `core/pyproject.toml`, `backend/pyproject.toml`, `frontend/package.json` and the uv locks; `make lint` fails if they differ. From there it reaches `/version`, the frontend footer, the run reproducibility record (`environment.solidaritynode`) and the documentation site footer.

Model versions (for example `diagnostic-v0 0.2.1`) and data package versions are separate and recorded on every run.

## What a release must include

- [ ] Every merged change since the last release has a line under **Unreleased** in [`CHANGELOG.md`](../CHANGELOG.md), and the affected [user guide](user-guide/index.md) pages are updated.
- [ ] **UAT passed** on the release commit: `make uat`, then the current checklists in [`docs/uat/`](uat/README.md), by the maintainer.
- [ ] CI green on `main`: lint, tests, end-to-end, docs, licences.
- [ ] **Migrations**: every new Alembic migration listed in the changelog, with what it does to existing data.
- [ ] **Upgrade notes for installations** in the changelog section: new or changed settings (`.env.example`), migrations, data package or scenario schema changes, anything an administrator must do, and whether a backup is needed first.
- [ ] Known limitations stated.

## How to cut a release

```mermaid
flowchart LR
    A["branch release/vX.Y.Z"] --> B["CHANGELOG: Unreleased → X.Y.Z (date)"]
    B --> C["VERSION → X.Y.Z<br/>make version-sync"]
    C --> D["make lint test docs-build<br/>PR, CI, UAT"]
    D --> E["merge to main"]
    E --> F["tag vX.Y.Z on main"]
    F --> G["GitHub Release<br/>notes = changelog section"]
    F --> H["docs workflow publishes<br/>docs version X.Y (latest)"]
```

1. On a branch `release/vX.Y.Z`: in `CHANGELOG.md`, rename **Unreleased** to `[X.Y.Z] - YYYY-MM-DD`, start a new empty **Unreleased** section above it, and update the comparison links at the bottom.
2. Write `X.Y.Z` into `VERSION` and run `make version-sync`.
3. Run `make lint test docs-build`, open a PR titled `chore(release): vX.Y.Z`, wait for CI and UAT, merge.
4. Tag the merge commit and push the tag (signed tags are welcome):
   ```bash
   git switch main && git pull
   git tag -a vX.Y.Z -m "SolidarityNode X.Y.Z"
   git push origin vX.Y.Z
   ```
5. Create the GitHub Release from the tag, with the changelog section of `X.Y.Z` as the notes:
   ```bash
   gh release create vX.Y.Z --title "SolidarityNode X.Y.Z" --notes-file <(python3 - <<'PY'
   import re, pathlib
   text = pathlib.Path("CHANGELOG.md").read_text()
   print(re.search(r"## \[X\.Y\.Z\][^\n]*\n(.*?)(?=\n## \[)", text, re.S).group(1).strip())
   PY
   )
   ```
6. The tag starts the `docs` workflow, which publishes the documentation as version `X.Y` with the alias `latest` (the default version of the site). `dev` keeps following `main`.
7. Update `CITATION.cff` (`version`, `date-released`) in the next PR if it was not done in the release PR.

## Documentation versions

The site is versioned with [mike](https://github.com/jimporter/mike): `dev` is built from `main` on every push, and each release tag `vX.Y.Z` publishes `X.Y` (patch releases overwrite their minor version) and moves `latest` to it. The version selector at the top of the site lists them.

**One-time setup (maintainer):** in the repository settings, **Settings → Pages → Build and deployment → Source: Deploy from a branch**, branch `gh-pages`, folder `/ (root)`. The branch is created by the first run of the `docs` workflow on `main`. The site is then at <https://solidaritynode.github.io/snode/>.
