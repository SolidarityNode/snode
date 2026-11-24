"""Temporary schema ``demo`` for the synthetic demo dataset.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24

Holds the synthetic demo dataset loaded by ``make seed`` (``data/synthetic/demo/``, DP-001)
for tests and UAT. **Temporary:** this schema is not the research data model (ADR 0003) and
will be replaced by data-package import in the platform PR (ADR 0013). Nothing is created in
``public``. Geometries use EPSG:2100.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SRID = 2100

TABLES = [
    """
    CREATE TABLE demo.package (
        package_id text PRIMARY KEY,
        version text NOT NULL,
        manifest jsonb NOT NULL,
        loaded_at timestamptz NOT NULL DEFAULT now()
    )""",
    f"""
    CREATE TABLE demo.municipalities (
        municipality_id text PRIMARY KEY,
        name text NOT NULL,
        role text NOT NULL CHECK (role IN ('core', 'buffer')),
        geom geometry(Polygon, {SRID}) NOT NULL
    )""",
    f"""
    CREATE TABLE demo.spatial_units (
        unit_id text PRIMARY KEY,
        name text NOT NULL,
        municipality_id text NOT NULL REFERENCES demo.municipalities,
        role text NOT NULL CHECK (role IN ('core', 'buffer')),
        quality text,
        valid_from date,
        valid_to date,
        centroid_node_id text,
        geom geometry(Polygon, {SRID}) NOT NULL,
        centroid geometry(Point, {SRID})
    )""",
    """
    CREATE TABLE demo.population_groups (
        group_id text PRIMARY KEY,
        name text NOT NULL,
        definition_rule text NOT NULL
    )""",
    """
    CREATE TABLE demo.population (
        unit_id text NOT NULL REFERENCES demo.spatial_units,
        group_id text NOT NULL REFERENCES demo.population_groups,
        population integer NOT NULL CHECK (population >= 0),
        PRIMARY KEY (unit_id, group_id)
    )""",
    """
    CREATE TABLE demo.services (
        service_id text PRIMARY KEY,
        name text NOT NULL,
        service_unit text NOT NULL,
        max_acceptable_wait interval
    )""",
    f"""
    CREATE TABLE demo.facilities (
        facility_id text PRIMARY KEY,
        name text NOT NULL,
        facility_type text NOT NULL,
        municipality_id text NOT NULL REFERENCES demo.municipalities,
        role text NOT NULL CHECK (role IN ('core', 'buffer')),
        node_id text,
        quality text,
        valid_from date,
        valid_to date,
        geom geometry(Point, {SRID}) NOT NULL
    )""",
    """
    CREATE TABLE demo.facility_services (
        facility_id text NOT NULL REFERENCES demo.facilities,
        service_id text NOT NULL REFERENCES demo.services,
        places double precision,
        staff double precision,
        throughput double precision,
        PRIMARY KEY (facility_id, service_id)
    )""",
    f"""
    CREATE TABLE demo.network_nodes (
        node_id text PRIMARY KEY,
        kind text NOT NULL,
        geom geometry(Point, {SRID}) NOT NULL
    )""",
    """
    CREATE TABLE demo.network_edges (
        edge_id text NOT NULL,
        mode text NOT NULL,
        from_node_id text NOT NULL REFERENCES demo.network_nodes,
        to_node_id text NOT NULL REFERENCES demo.network_nodes,
        length_m double precision NOT NULL,
        travel_time_min double precision NOT NULL,
        closable boolean NOT NULL,
        PRIMARY KEY (edge_id, mode)
    )""",
    """
    CREATE TABLE demo.hand_check_travel_times (
        scenario_id text NOT NULL,
        mode text NOT NULL,
        unit_id text NOT NULL REFERENCES demo.spatial_units,
        facility_id text NOT NULL REFERENCES demo.facilities,
        travel_time_min double precision NOT NULL,
        path text NOT NULL,
        PRIMARY KEY (scenario_id, mode, unit_id, facility_id)
    )""",
    """
    CREATE TABLE demo.scenarios (
        scenario_id text PRIMARY KEY,
        version integer NOT NULL,
        body jsonb NOT NULL
    )""",
]


def upgrade() -> None:
    """Create the temporary ``demo`` schema and its tables."""
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE SCHEMA IF NOT EXISTS demo")
    op.execute(
        "COMMENT ON SCHEMA demo IS 'Synthetic demo dataset (make seed). Temporary: "
        "replaced by data-package import in the platform PR (ADR 0013).'"
    )
    for ddl in TABLES:
        op.execute(ddl)


def downgrade() -> None:
    """Drop the ``demo`` schema and everything in it."""
    op.execute("DROP SCHEMA IF EXISTS demo CASCADE")
