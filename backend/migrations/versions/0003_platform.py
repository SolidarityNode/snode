"""Platform tables: data versions, users, scenarios, jobs, runs and results.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-24

Replaces the temporary ``demo`` schema (migration 0002) with data-package import (ADR 0013).

* ``data_versions``: one row per imported package version; exactly one is active. Older versions
  stay, because runs point to the version they used.
* ``data_features``: every feature of every layer of every version, with its stable id, metadata
  (municipality, role, quality, valid_from/valid_to, DP note) in ``properties`` and its geometry
  in the package CRS. Features are closed (``valid_to``), never deleted.
* ``data_records``: non-spatial tables (groups, services, hand-check times).
* ``data_coverage``: per municipality and layer, status and layer version.
* ``data_warnings``: edge-effect warnings per core unit (OQ-28: warning only).
* ``users``/``sessions`` (ADR 0015), ``scenarios``/``scenario_versions`` (ADR 0016),
  ``jobs`` (ADR 0006), ``runs``/``run_results``/``run_tables`` (ADR 0017, 0008).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    """
    CREATE TABLE users (
        id serial PRIMARY KEY,
        username text NOT NULL UNIQUE CHECK (username ~ '^[A-Za-z0-9_.-]{3,64}$'),
        password_hash text NOT NULL,
        role text NOT NULL CHECK (role IN ('admin', 'analyst', 'viewer')),
        active boolean NOT NULL DEFAULT true,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    """
    CREATE TABLE sessions (
        token_hash text PRIMARY KEY,
        user_id integer NOT NULL REFERENCES users ON DELETE CASCADE,
        created_at timestamptz NOT NULL DEFAULT now(),
        expires_at timestamptz NOT NULL
    )""",
    """
    CREATE TABLE data_versions (
        id serial PRIMARY KEY,
        package_id text NOT NULL,
        version text NOT NULL,
        schema_version text NOT NULL,
        created date NOT NULL,
        srid integer NOT NULL,
        manifest jsonb NOT NULL,
        manifest_sha256 text NOT NULL,
        active boolean NOT NULL DEFAULT false,
        imported_at timestamptz NOT NULL DEFAULT now(),
        imported_by integer REFERENCES users ON DELETE SET NULL,
        UNIQUE (package_id, version)
    )""",
    "CREATE UNIQUE INDEX data_versions_one_active ON data_versions (active) WHERE active",
    """
    CREATE TABLE data_features (
        data_version_id integer NOT NULL REFERENCES data_versions ON DELETE CASCADE,
        layer text NOT NULL,
        feature_id text NOT NULL,
        properties jsonb NOT NULL,
        geom geometry NOT NULL,
        PRIMARY KEY (data_version_id, layer, feature_id)
    )""",
    "CREATE INDEX data_features_geom ON data_features USING gist (geom)",
    """
    CREATE TABLE data_records (
        data_version_id integer NOT NULL REFERENCES data_versions ON DELETE CASCADE,
        table_name text NOT NULL,
        row_no integer NOT NULL,
        properties jsonb NOT NULL,
        PRIMARY KEY (data_version_id, table_name, row_no)
    )""",
    """
    CREATE TABLE data_coverage (
        data_version_id integer NOT NULL REFERENCES data_versions ON DELETE CASCADE,
        municipality_id text NOT NULL,
        layer text NOT NULL,
        status text NOT NULL
            CHECK (status IN ('missing', 'open_data', 'estimated', 'verified')),
        layer_version text NOT NULL,
        PRIMARY KEY (data_version_id, municipality_id, layer)
    )""",
    """
    CREATE TABLE data_warnings (
        data_version_id integer NOT NULL REFERENCES data_versions ON DELETE CASCADE,
        unit_id text NOT NULL,
        code text NOT NULL,
        detail text NOT NULL,
        PRIMARY KEY (data_version_id, unit_id, code, detail)
    )""",
    """
    CREATE TABLE scenarios (
        id uuid PRIMARY KEY,
        owner_id integer REFERENCES users ON DELETE SET NULL,
        visibility text NOT NULL CHECK (visibility IN ('private', 'shared')),
        is_baseline boolean NOT NULL DEFAULT false,
        latest_version integer NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        deleted_at timestamptz
    )""",
    """
    CREATE TABLE scenario_versions (
        scenario_id uuid NOT NULL REFERENCES scenarios ON DELETE CASCADE,
        version integer NOT NULL CHECK (version >= 1),
        name text NOT NULL,
        description text NOT NULL DEFAULT '',
        schema_version text NOT NULL,
        body jsonb NOT NULL,
        data_version_id integer NOT NULL REFERENCES data_versions,
        created_at timestamptz NOT NULL DEFAULT now(),
        created_by integer REFERENCES users ON DELETE SET NULL,
        PRIMARY KEY (scenario_id, version)
    )""",
    """
    CREATE TABLE jobs (
        id uuid PRIMARY KEY,
        kind text NOT NULL,
        payload jsonb NOT NULL,
        status text NOT NULL
            CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
        progress double precision NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
        error text,
        cancel_requested boolean NOT NULL DEFAULT false,
        worker text,
        created_at timestamptz NOT NULL DEFAULT now(),
        started_at timestamptz,
        finished_at timestamptz
    )""",
    "CREATE INDEX jobs_queued ON jobs (created_at) WHERE status = 'queued'",
    """
    CREATE TABLE runs (
        id uuid PRIMARY KEY,
        scenario_id uuid NOT NULL REFERENCES scenarios,
        scenario_version integer NOT NULL,
        data_version_id integer NOT NULL REFERENCES data_versions,
        package_id text NOT NULL,
        package_version text NOT NULL,
        code_version text NOT NULL,
        model_id text NOT NULL,
        model_version text NOT NULL,
        seed bigint NOT NULL,
        config jsonb NOT NULL,
        input_hash text NOT NULL,
        is_baseline boolean NOT NULL DEFAULT false,
        job_id uuid NOT NULL REFERENCES jobs,
        created_by integer REFERENCES users ON DELETE SET NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        indicators jsonb,
        diagnostics jsonb,
        samples_path text,
        FOREIGN KEY (scenario_id, scenario_version) REFERENCES scenario_versions
    )""",
    "CREATE INDEX runs_input_hash ON runs (input_hash)",
    """
    CREATE TABLE run_results (
        run_id uuid NOT NULL REFERENCES runs ON DELETE CASCADE,
        unit_id text NOT NULL,
        group_id text NOT NULL,
        service_id text NOT NULL,
        time_label text NOT NULL,
        indicator text NOT NULL,
        value double precision,
        low double precision,
        high double precision,
        baseline double precision,
        edge_effect_warning boolean NOT NULL DEFAULT false,
        PRIMARY KEY (run_id, unit_id, group_id, service_id, time_label, indicator)
    )""",
    """
    CREATE TABLE run_tables (
        run_id uuid NOT NULL REFERENCES runs ON DELETE CASCADE,
        table_name text NOT NULL,
        rows jsonb NOT NULL,
        PRIMARY KEY (run_id, table_name)
    )""",
]


def upgrade() -> None:
    """Drop the temporary ``demo`` schema and create the platform tables."""
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("DROP SCHEMA IF EXISTS demo CASCADE")
    for ddl in TABLES:
        op.execute(ddl)


def downgrade() -> None:
    """Drop the platform tables (the ``demo`` schema of 0002 is recreated empty)."""
    for table in (
        "run_tables",
        "run_results",
        "runs",
        "jobs",
        "scenario_versions",
        "scenarios",
        "data_warnings",
        "data_coverage",
        "data_records",
        "data_features",
        "data_versions",
        "sessions",
        "users",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("CREATE SCHEMA IF NOT EXISTS demo")
