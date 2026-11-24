"""Every subpackage imports, documents its spec sections, and core stays independent."""

from __future__ import annotations

import ast
import importlib
import re
import tomllib
from pathlib import Path

import pytest

import solidaritynode_core
from solidaritynode_core import SUBPACKAGES

CORE_ROOT = Path(__file__).resolve().parents[1]
SRC = CORE_ROOT / "src" / "solidaritynode_core"

# Web frameworks, servers, database layers and drivers, and the other apps (CLAUDE.md).
FORBIDDEN_MODULES = {
    "fastapi",
    "starlette",
    "flask",
    "django",
    "uvicorn",
    "gunicorn",
    "pydantic_settings",
    "sqlalchemy",
    "alembic",
    "psycopg",
    "psycopg2",
    "asyncpg",
    "geoalchemy2",
    "sqlmodel",
    "pymongo",
    "redis",
    "celery",
    "httpx",
    "requests",
    "aiohttp",
    "backend",
    "frontend",
    "solidaritynode_backend",
}
FORBIDDEN_DISTRIBUTIONS = FORBIDDEN_MODULES | {
    "psycopg-binary",
    "psycopg2-binary",
    "pydantic-settings",
}


def test_module_map_matches_spec() -> None:
    assert SUBPACKAGES == (
        "model",
        "bayes",
        "accessibility",
        "demand",
        "capacity",
        "service_gap",
        "latent_need",
        "scenarios",
        "vulnerability",
        "operations",
        "dynamics",
        "resilience",
        "uncertainty",
        "sensitivity",
        "validation",
    )
    on_disk = {p.name for p in SRC.iterdir() if (p / "__init__.py").is_file()}
    assert on_disk == set(SUBPACKAGES)


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports_and_cites_sections(name: str) -> None:
    module = importlib.import_module(f"solidaritynode_core.{name}")
    doc = module.__doc__ or ""
    assert re.search(r"(Paper \d|Papers \d)", doc), f"{name} docstring must cite paper sections"


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_public_api_is_documented(name: str) -> None:
    module = importlib.import_module(f"solidaritynode_core.{name}")
    for symbol in getattr(module, "__all__", ()):
        obj = getattr(module, symbol)
        if callable(obj) or isinstance(obj, type):
            assert getattr(obj, "__doc__", None), f"{name}.{symbol} has no docstring"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def find_forbidden_imports(root: Path) -> dict[str, set[str]]:
    """Return ``{file: forbidden top-level modules}`` for every Python file under ``root``."""
    hits: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        bad = _imported_modules(path) & FORBIDDEN_MODULES
        if bad:
            hits[str(path.relative_to(root))] = bad
    return hits


def test_core_imports_no_web_database_or_app_modules() -> None:
    assert find_forbidden_imports(SRC) == {}


def test_forbidden_import_detector_works(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text("import fastapi\nfrom sqlalchemy.orm import Session\n")
    assert find_forbidden_imports(tmp_path) == {"bad.py": {"fastapi", "sqlalchemy"}}


def test_core_declares_no_web_or_database_dependency() -> None:
    project = tomllib.loads((CORE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = project["project"]["dependencies"]
    names = {re.split(r"[<>=!~\[ ;]", dep, maxsplit=1)[0].lower() for dep in declared}
    assert not names & FORBIDDEN_DISTRIBUTIONS


def test_version_is_exposed() -> None:
    assert isinstance(solidaritynode_core.__version__, str)
