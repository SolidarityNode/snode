"""Administration commands (used by the Makefile).

::

    python -m solidaritynode_backend.cli import-package PATH [--yes] [--preview-only]
    python -m solidaritynode_backend.cli import-package - [--yes]   # archive on stdin
    python -m solidaritynode_backend.cli create-admin                # interactive
    python -m solidaritynode_backend.cli seed-demo-users             # APP_ENV=development only
    python -m solidaritynode_backend.cli wait-runs [--timeout 120]   # until no job is pending
    python -m solidaritynode_backend.cli export-schemas DIR          # JSON Schema and OpenAPI
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from solidaritynode_backend.auth import create_user
from solidaritynode_backend.config import Settings, get_settings
from solidaritynode_backend.orm import DataVersion, Job, User
from solidaritynode_backend.services.installation import RoleMismatchError, check_role
from solidaritynode_backend.services.packages import (
    PackageError,
    activate_version,
    import_package,
    opened_package,
    preview_package,
    read_package,
)

__all__ = ["DEMO_USERS", "NOTHING_TO_DO", "main"]

#: Exit code of ``import-package --preview-only`` when the version is already imported.
NOTHING_TO_DO = 3

#: Demo accounts for UAT, created only when APP_ENV=development (docs/uat/README.md).
#: These passwords are public on purpose; never use them outside a local development stack.
DEMO_USERS = (
    ("demo-admin", "demo-admin-pass", "admin"),
    ("demo-analyst", "demo-analyst-pass", "analyst"),
)


def _session(settings: Settings) -> Session:
    return Session(create_engine(settings.database_url.get_secret_value()))


def _print_preview(p: dict[str, Any]) -> None:
    active = p["active"]
    print(f"Package {p['package_id']} {p['version']} (schema {p['schema_version']})")
    print(f"Active data: {active['package_id'] + ' ' + active['version'] if active else 'none'}")
    print(f"Status: {p['status']}")
    for layer, d in p["layers"].items():
        print(
            f"  {layer:<15} added {len(d['added'])}, changed {len(d['changed'])}, "
            f"closed {len(d['closed'])}, unchanged {d['unchanged']}"
        )
        for fid in d["added"]:
            print(f"      + {fid}")
        for change in d["changed"]:
            print(f"      ~ {change['id']} ({', '.join(change['fields'])})")
        for fid in d["closed"]:
            print(f"      x {fid} closed")
    for c in p["coverage_changes"]:
        print(f"  coverage {c['municipality_id']}/{c['layer']}: {c['before']} -> {c['after']}")
    for w in p["warnings"]:
        print(f"  warning: {w}")
    for problem in p["problems"]:
        print(f"  PROBLEM: {problem}")


def _import(settings: Settings, source: Path, yes: bool, preview_only: bool) -> int:
    with opened_package(source) as directory:
        content = read_package(directory)
    with _session(settings) as db:
        preview = preview_package(db, content)
        _print_preview(preview)
        if preview["problems"]:
            print("Import refused.", file=sys.stderr)
            return 1
        if preview["status"] == "same_version":
            print("This version is already imported: nothing to do.")
            return NOTHING_TO_DO if preview_only else 0
        if preview_only:
            return 0
        if not yes:
            answer = input("Import this package? Type 'yes' to confirm: ")
            if answer.strip() != "yes":
                print("Aborted; nothing imported.")
                return 1
        outcome = import_package(db, settings, content, None)
        db.commit()
    print(f"Imported as data version {outcome.data_version_id} (now active).")
    print(f"Baseline run queued: {outcome.baseline_run_id}")
    for r in outcome.revalidation:
        print(f"  scenario '{r['name']}' needs attention: {'; '.join(r['problems'])}")
    return 0


def import_command(settings: Settings, path: str, yes: bool, preview_only: bool) -> int:
    """Import a package directory or archive (``-`` reads an archive from stdin)."""
    try:
        if path == "-":
            with tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / "package"
                archive.write_bytes(sys.stdin.buffer.read())
                return _import(settings, archive, yes, preview_only)
        return _import(settings, Path(path), yes, preview_only)
    except PackageError as exc:
        print(f"import-package: {exc}", file=sys.stderr)
        return 1


def activate_command(settings: Settings, version: str, package_id: str | None, yes: bool) -> int:
    """Make an earlier imported data version active again (rollback).

    Without ``--yes`` it only describes what would happen and exits ``NOTHING_TO_DO`` (3) when
    that version is already active, so ``make activate-version`` can ask first.
    """
    with _session(settings) as db:
        query = select(DataVersion).where(DataVersion.version == version)
        if package_id:
            query = query.where(DataVersion.package_id == package_id)
        found = list(db.scalars(query))
        if not found:
            print(f"activate-version: no imported data version {version}", file=sys.stderr)
            return 1
        if len(found) > 1:
            ids = ", ".join(dv.package_id for dv in found)
            print(
                f"activate-version: {version} exists for {ids}; add --package-id", file=sys.stderr
            )
            return 1
        dv = found[0]
        active = db.scalar(select(DataVersion).where(DataVersion.active))
        if dv.active:
            print(f"Data version {dv.package_id} {dv.version} is already active: nothing to do.")
            return NOTHING_TO_DO
        print(
            f"Data version {dv.package_id} {dv.version} (imported {dv.imported_at:%Y-%m-%d}) will "
            f"become active again instead of {active.version if active else 'none'}. A baseline "
            "run is queued on it and every scenario is revalidated; nothing is deleted."
        )
        if not yes:
            return 0
        try:
            outcome = activate_version(db, settings, dv.id, None)
        except PackageError as exc:
            print(f"activate-version: {exc}", file=sys.stderr)
            return 1
        db.commit()
    print(f"Data version {version} is active again. Baseline run: {outcome.baseline_run_id}.")
    for entry in outcome.revalidation:
        print(f"  needs attention: {entry['name']}: {'; '.join(entry['problems'])}")
    return 0


def create_admin(settings: Settings) -> int:
    """Create an administrator interactively."""
    username = input("Admin username: ").strip()
    password = getpass.getpass("Password (at least 12 characters; common passwords are refused): ")
    if password != getpass.getpass("Repeat password: "):
        print("Passwords differ; nothing created.", file=sys.stderr)
        return 1
    with _session(settings) as db:
        try:
            create_user(db, username, password, "admin")
        except ValueError as exc:
            print(f"create-admin: {exc}", file=sys.stderr)
            return 1
        db.commit()
    print(f"Administrator {username!r} created.")
    return 0


def seed_demo_users(settings: Settings) -> int:
    """Create the UAT demo accounts (idempotent; development only)."""
    if settings.app_env != "development":
        print("seed-demo-users: refused, APP_ENV is not development.", file=sys.stderr)
        return 1
    with _session(settings) as db:
        for username, password, role in DEMO_USERS:
            if db.scalar(select(User.id).where(User.username == username)) is None:
                create_user(db, username, password, role)  # type: ignore[arg-type]
                print(f"created demo user {username} ({role})")
        db.commit()
    return 0


def wait_runs(settings: Settings, timeout: float) -> int:
    """Wait until no job is queued or running."""
    deadline = time.monotonic() + timeout
    with _session(settings) as db:
        while True:
            pending = db.scalar(
                select(func.count()).select_from(Job).where(Job.status.in_(("queued", "running")))
            )
            db.rollback()
            if not pending:
                print("No pending runs.")
                return 0
            if time.monotonic() > deadline:
                print(f"wait-runs: {pending} job(s) still pending; is the worker running?")
                return 1
            time.sleep(1)


def export_schemas(directory: Path) -> int:
    """Write ``scenario.schema.json`` and ``openapi.json`` to ``directory``."""
    from solidaritynode_backend.main import create_app
    from solidaritynode_backend.schemas.scenario import export_json_schema

    directory.mkdir(parents=True, exist_ok=True)
    export_json_schema(directory / "scenario.schema.json")
    openapi = create_app().openapi()
    (directory / "openapi.json").write_text(json.dumps(openapi, indent=2, sort_keys=True) + "\n")
    print(f"wrote {directory}/scenario.schema.json and openapi.json")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(prog="solidaritynode_backend.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import-package", help="validate, preview and import a data package")
    imp.add_argument("path", help="package directory or archive, or - for an archive on stdin")
    imp.add_argument("--yes", action="store_true", help="import without asking")
    imp.add_argument(
        "--preview-only",
        action="store_true",
        help=f"show the preview and stop (exit {NOTHING_TO_DO} if already imported)",
    )
    act = sub.add_parser("activate-version", help="make an earlier data version active again")
    act.add_argument("version", help="data package version, for example 1.0.0")
    act.add_argument("--package-id", help="needed only if several packages have that version")
    act.add_argument("--yes", action="store_true", help="activate (otherwise only describe)")
    sub.add_parser("create-admin", help="create an administrator interactively")
    sub.add_parser("seed-demo-users", help="create UAT demo users (development only)")
    wait = sub.add_parser("wait-runs", help="wait until no job is pending")
    wait.add_argument("--timeout", type=float, default=180)
    exp = sub.add_parser("export-schemas", help="write the scenario JSON Schema and OpenAPI")
    exp.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    settings = get_settings()
    if args.command != "export-schemas":
        try:
            check_role(
                create_engine(settings.database_url.get_secret_value()), settings.deployment_mode
            )
        except RoleMismatchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if args.command == "import-package":
        return import_command(settings, args.path, args.yes, args.preview_only)
    if args.command == "activate-version":
        return activate_command(settings, args.version, args.package_id, args.yes)
    if args.command == "create-admin":
        return create_admin(settings)
    if args.command == "seed-demo-users":
        return seed_demo_users(settings)
    if args.command == "wait-runs":
        return wait_runs(settings, args.timeout)
    return export_schemas(args.directory)


if __name__ == "__main__":
    raise SystemExit(main())
