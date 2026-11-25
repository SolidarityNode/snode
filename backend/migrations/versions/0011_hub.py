"""Hub onboarding tables (ADR 0012, 0013): created only in a hub database.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-26

Guarded by the stored role (:func:`solidaritynode_backend.services.installation.stored_role`):
in a municipal installation this migration creates nothing, so hub tables never exist there.

* ``hub_sources``: registered raw sources (files in the hub storage directory), versioned,
  with licence, attribution, SHA-256 and the ``DP-NNN`` note. Registering processes nothing.
* ``hub_features``: the curated features of every onboarded area, one row per stable id.
  Rows are never deleted (a trigger refuses it): features are closed with ``valid_to``.
* ``hub_onboarding`` / ``hub_onboarding_events``: status per municipality and every transition
  with who and when.
* ``hub_processing_records``: one record per automated processing step (inputs with versions
  and checksums, parameters, outputs, checks, ``DP-NNN`` note).
* ``hub_changesets`` / ``hub_changeset_items``: facility imports and manual edits, with author,
  date, source and comment; the history of every facility.
* ``hub_study_areas`` / ``hub_packages``: study areas of installations and their published
  packages. A published package row cannot be changed or deleted (trigger).
"""

from collections.abc import Sequence

from alembic import op

from solidaritynode_backend.services.installation import stored_role

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QUALITY = "('open_data', 'estimated', 'verified_by_municipality')"
STATUSES = "('not_started', 'base_ready', 'facilities_in_progress', 'in_review', 'published')"

TABLES = [
    f"""
    CREATE TABLE hub_sources (
        id serial PRIMARY KEY,
        name text NOT NULL CHECK (length(trim(name)) > 0),
        layer_type text NOT NULL CHECK (layer_type IN ('boundaries', 'spatial_units', 'network',
            'population', 'dem', 'transit', 'groups', 'services', 'other')),
        coverage text NOT NULL,
        version text NOT NULL CHECK (length(trim(version)) > 0),
        licence text NOT NULL CHECK (length(trim(licence)) > 0),
        attribution text NOT NULL CHECK (length(trim(attribution)) > 0),
        processing_note text NOT NULL CHECK (processing_note ~ '^DP-[0-9]{{3}}$'),
        quality text NOT NULL DEFAULT 'open_data' CHECK (quality IN {QUALITY}),
        file_name text NOT NULL,
        path text NOT NULL,
        sha256 text NOT NULL,
        bytes bigint NOT NULL,
        details jsonb NOT NULL DEFAULT '{{}}',
        registered_at timestamptz NOT NULL DEFAULT now(),
        registered_by integer REFERENCES users ON DELETE SET NULL,
        UNIQUE (name, version)
    )""",
    f"""
    CREATE TABLE hub_features (
        layer text NOT NULL CHECK (layer IN ('municipalities', 'spatial_units', 'facilities',
            'network_nodes', 'network_edges')),
        feature_id text NOT NULL,
        municipality_id text NOT NULL,
        properties jsonb NOT NULL,
        geom geometry NOT NULL,
        quality text NOT NULL CHECK (quality IN {QUALITY}),
        processing_note text NOT NULL,
        valid_from date NOT NULL,
        valid_to date,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (layer, feature_id)
    )""",
    "CREATE INDEX hub_features_geom ON hub_features USING gist (geom)",
    "CREATE INDEX hub_features_municipality ON hub_features (layer, municipality_id)",
    # Hub-assigned ids are never reused: sequences only move forward.
    "CREATE SEQUENCE hub_facility_id_seq",
    "CREATE SEQUENCE hub_feature_id_seq",
    """
    CREATE FUNCTION hub_refuse_delete() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'hub features are never deleted; close them with valid_to';
    END $$""",
    """
    CREATE TRIGGER hub_features_no_delete BEFORE DELETE ON hub_features
        FOR EACH ROW EXECUTE FUNCTION hub_refuse_delete()""",
    f"""
    CREATE TABLE hub_onboarding (
        municipality_id text PRIMARY KEY,
        name text NOT NULL,
        status text NOT NULL DEFAULT 'not_started' CHECK (status IN {STATUSES}),
        last_job_id uuid REFERENCES jobs,
        updated_at timestamptz NOT NULL DEFAULT now()
    )""",
    f"""
    CREATE TABLE hub_onboarding_events (
        id serial PRIMARY KEY,
        municipality_id text NOT NULL REFERENCES hub_onboarding,
        from_status text CHECK (from_status IN {STATUSES}),
        to_status text NOT NULL CHECK (to_status IN {STATUSES}),
        by_user integer REFERENCES users ON DELETE SET NULL,
        at timestamptz NOT NULL DEFAULT now(),
        note text NOT NULL DEFAULT ''
    )""",
    """
    CREATE TABLE hub_processing_records (
        id serial PRIMARY KEY,
        kind text NOT NULL
            CHECK (kind IN ('onboarding_base', 'facility_changeset', 'package_publish')),
        municipality_id text,
        study_area_id text,
        job_id uuid REFERENCES jobs,
        status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
        processing_note text NOT NULL,
        inputs jsonb NOT NULL DEFAULT '[]',
        parameters jsonb NOT NULL DEFAULT '{}',
        outputs jsonb NOT NULL DEFAULT '{}',
        checks jsonb NOT NULL DEFAULT '[]',
        affected_municipalities text[] NOT NULL DEFAULT '{}',
        changed boolean NOT NULL DEFAULT false,
        summary text NOT NULL DEFAULT '',
        created_at timestamptz NOT NULL DEFAULT now(),
        finished_at timestamptz,
        created_by integer REFERENCES users ON DELETE SET NULL
    )""",
    "CREATE INDEX hub_records_kind ON hub_processing_records (kind, finished_at)",
    """
    CREATE TABLE hub_changesets (
        id serial PRIMARY KEY,
        kind text NOT NULL CHECK (kind IN ('import', 'manual')),
        municipality_id text NOT NULL,
        status text NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'approved', 'rejected')),
        source text NOT NULL,
        comment text NOT NULL DEFAULT '',
        licence text NOT NULL,
        attribution text NOT NULL,
        file_name text,
        file_sha256 text,
        complete_list boolean NOT NULL DEFAULT false,
        is_correction boolean NOT NULL DEFAULT false,
        report jsonb NOT NULL DEFAULT '{}',
        created_by integer REFERENCES users ON DELETE SET NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        decided_by integer REFERENCES users ON DELETE SET NULL,
        decided_at timestamptz,
        decision_comment text NOT NULL DEFAULT '',
        record_id integer REFERENCES hub_processing_records
    )""",
    """
    CREATE TABLE hub_changeset_items (
        changeset_id integer NOT NULL REFERENCES hub_changesets ON DELETE CASCADE,
        item_no integer NOT NULL,
        action text NOT NULL CHECK (action IN ('add', 'update', 'close')),
        facility_id text,
        label text NOT NULL,
        rows integer[] NOT NULL DEFAULT '{}',
        before jsonb,
        after jsonb,
        fields text[] NOT NULL DEFAULT '{}',
        PRIMARY KEY (changeset_id, item_no)
    )""",
    "CREATE INDEX hub_changeset_items_facility ON hub_changeset_items (facility_id)",
    """
    CREATE TABLE hub_study_areas (
        id text PRIMARY KEY CHECK (id ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
        name text NOT NULL CHECK (length(trim(name)) > 0),
        core_municipalities text[] NOT NULL CHECK (cardinality(core_municipalities) > 0),
        buffer_rule text NOT NULL
            CHECK (buffer_rule IN ('whole_neighbouring_municipalities', 'distance')),
        buffer_distance_m double precision CHECK (buffer_distance_m > 0),
        created_at timestamptz NOT NULL DEFAULT now(),
        created_by integer REFERENCES users ON DELETE SET NULL
    )""",
    """
    CREATE TABLE hub_packages (
        id serial PRIMARY KEY,
        study_area_id text NOT NULL REFERENCES hub_study_areas,
        version text NOT NULL CHECK (version ~ '^(0|[1-9][0-9]*)[.](0|[1-9][0-9]*)[.](0|[1-9][0-9]*)$'),
        status text NOT NULL CHECK (status IN ('building', 'published', 'failed')),
        bump text NOT NULL CHECK (bump IN ('initial', 'major', 'minor', 'patch')),
        comment text NOT NULL DEFAULT '',
        job_id uuid REFERENCES jobs,
        created date NOT NULL,
        manifest jsonb,
        archive_path text,
        archive_sha256 text,
        bytes bigint,
        error text,
        requested_at timestamptz NOT NULL DEFAULT now(),
        requested_by integer REFERENCES users ON DELETE SET NULL,
        published_at timestamptz,
        record_id integer REFERENCES hub_processing_records
    )""",
    # A failed build frees its version number; a building or published one holds it.
    """
    CREATE UNIQUE INDEX hub_packages_version ON hub_packages (study_area_id, version)
        WHERE status <> 'failed'""",
    """
    CREATE FUNCTION hub_packages_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF OLD.status = 'published' THEN
            RAISE EXCEPTION 'published package % % is immutable', OLD.study_area_id, OLD.version;
        END IF;
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END $$""",
    """
    CREATE TRIGGER hub_packages_immutable BEFORE UPDATE OR DELETE ON hub_packages
        FOR EACH ROW EXECUTE FUNCTION hub_packages_immutable()""",
]

DROP = [
    "hub_packages",
    "hub_study_areas",
    "hub_changeset_items",
    "hub_changesets",
    "hub_processing_records",
    "hub_onboarding_events",
    "hub_onboarding",
    "hub_features",
    "hub_sources",
]


def upgrade() -> None:
    """Create the hub tables, only in a hub database."""
    if stored_role(op.get_bind()) != "hub":
        return
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    for ddl in TABLES:
        op.execute(ddl)


def downgrade() -> None:
    """Drop the hub tables (nothing to do in a municipal installation)."""
    if stored_role(op.get_bind()) != "hub":
        return
    for table in DROP:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP SEQUENCE IF EXISTS hub_facility_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS hub_feature_id_seq")
    op.execute("DROP FUNCTION IF EXISTS hub_refuse_delete()")
    op.execute("DROP FUNCTION IF EXISTS hub_packages_immutable()")
