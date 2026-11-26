"""Facility submissions from municipal installations to the hub (ADR 0014 Part A).

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-26

Each part is created only in a database of its role (``stored_role``):

* **hub**: ``hub_installations`` (one row per municipal installation: study area, the SHA-256 of
  its token, the key that verifies its offline files, last contact); changesets gain the
  submission fields (installation, submission UUID, pseudonymous submitter and role, base
  package version, offline flag, start of review), the kind ``submission`` and the status
  ``withdrawn``; changeset items gain ``conflict`` and its ``resolution``.
* **municipality**: ``submissions`` and ``submission_events`` (status history),
  ``user_pseudonyms`` (stable pseudonymous id per user, resolvable only here), ``hub_link``
  (one row: last contact with the hub, its study area and packages) and ``hub_downloads``
  (package downloads requested by an administrator).
"""

from collections.abc import Sequence

from alembic import op

from solidaritynode_backend.services.installation import stored_role

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUBMISSION_STATUSES = (
    "('draft', 'sent', 'received', 'rejected_by_validation', 'pending_review', 'approved', "
    "'rejected', 'published', 'imported', 'withdrawn')"
)

HUB = [
    """
    CREATE TABLE hub_installations (
        id uuid PRIMARY KEY,
        name text NOT NULL UNIQUE CHECK (length(trim(name)) > 0),
        study_area_id text NOT NULL,
        token_hash text UNIQUE,
        offline_key text,
        token_issued_at timestamptz,
        revoked_at timestamptz,
        last_contact_at timestamptz,
        last_contact_address text,
        created_at timestamptz NOT NULL DEFAULT now(),
        created_by integer REFERENCES users ON DELETE SET NULL
    )""",
    "ALTER TABLE hub_changesets DROP CONSTRAINT hub_changesets_kind_check",
    "ALTER TABLE hub_changesets ADD CONSTRAINT hub_changesets_kind_check "
    "CHECK (kind IN ('import', 'manual', 'submission'))",
    "ALTER TABLE hub_changesets DROP CONSTRAINT hub_changesets_status_check",
    "ALTER TABLE hub_changesets ADD CONSTRAINT hub_changesets_status_check "
    "CHECK (status IN ('pending', 'approved', 'rejected', 'withdrawn'))",
    """
    ALTER TABLE hub_changesets
        ADD COLUMN installation_id uuid REFERENCES hub_installations,
        ADD COLUMN submission_uuid uuid UNIQUE,
        ADD COLUMN submitted_by text,
        ADD COLUMN submitter_role text,
        ADD COLUMN base_package_version text,
        ADD COLUMN offline boolean NOT NULL DEFAULT false,
        ADD COLUMN review_started_at timestamptz,
        ADD COLUMN review_started_by integer REFERENCES users ON DELETE SET NULL""",
    """
    ALTER TABLE hub_changeset_items
        ADD COLUMN conflict jsonb,
        ADD COLUMN resolution text CHECK (resolution IN ('municipality', 'hub'))""",
]

MUNICIPALITY = [
    f"""
    CREATE TABLE submissions (
        id uuid PRIMARY KEY,
        municipality_id text NOT NULL,
        kind text NOT NULL CHECK (kind IN ('import', 'manual')),
        status text NOT NULL DEFAULT 'draft' CHECK (status IN {SUBMISSION_STATUSES}),
        data_version_id integer NOT NULL REFERENCES data_versions,
        package_id text NOT NULL,
        base_package_version text NOT NULL,
        file_name text,
        comment text NOT NULL DEFAULT '',
        complete_list boolean NOT NULL DEFAULT false,
        is_correction boolean NOT NULL DEFAULT false,
        rows jsonb NOT NULL,
        report jsonb NOT NULL,
        items jsonb NOT NULL,
        created_by integer REFERENCES users ON DELETE SET NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now(),
        sent_at timestamptz,
        offline boolean NOT NULL DEFAULT false,
        attempts integer NOT NULL DEFAULT 0,
        next_attempt_at timestamptz,
        last_error text,
        withdraw_requested boolean NOT NULL DEFAULT false,
        hub_changeset_id integer,
        hub_comment text,
        hub_decided_at timestamptz,
        hub_conflicts jsonb NOT NULL DEFAULT '[]',
        published_in text,
        imported_in text
    )""",
    "CREATE INDEX submissions_status ON submissions (status)",
    f"""
    CREATE TABLE submission_events (
        id serial PRIMARY KEY,
        submission_id uuid NOT NULL REFERENCES submissions ON DELETE CASCADE,
        from_status text CHECK (from_status IN {SUBMISSION_STATUSES}),
        to_status text NOT NULL CHECK (to_status IN {SUBMISSION_STATUSES}),
        by_user integer REFERENCES users ON DELETE SET NULL,
        by_hub text,
        at timestamptz NOT NULL DEFAULT now(),
        note text NOT NULL DEFAULT ''
    )""",
    """
    CREATE TABLE user_pseudonyms (
        user_id integer PRIMARY KEY REFERENCES users ON DELETE CASCADE,
        pseudonym text NOT NULL UNIQUE,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    """
    CREATE TABLE hub_link (
        id smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
        study_area_id text,
        installation_id text,
        installation_name text,
        last_sync_at timestamptz,
        last_contact_at timestamptz,
        last_error text,
        packages jsonb NOT NULL DEFAULT '[]',
        updated_at timestamptz NOT NULL DEFAULT now()
    )""",
    "INSERT INTO hub_link (id) VALUES (1)",
    """
    CREATE TABLE hub_downloads (
        id uuid PRIMARY KEY,
        version text NOT NULL,
        status text NOT NULL CHECK (status IN ('queued', 'done', 'failed')),
        staging_id text,
        sha256 text,
        error text,
        job_id uuid REFERENCES jobs,
        requested_by integer REFERENCES users ON DELETE SET NULL,
        requested_at timestamptz NOT NULL DEFAULT now()
    )""",
]


def upgrade() -> None:
    """Create the part of the current role."""
    role = stored_role(op.get_bind())
    for ddl in HUB if role == "hub" else MUNICIPALITY if role == "municipality" else []:
        op.execute(ddl)


def downgrade() -> None:
    """Drop the part of the current role."""
    role = stored_role(op.get_bind())
    if role == "hub":
        op.execute("ALTER TABLE hub_changeset_items DROP COLUMN conflict, DROP COLUMN resolution")
        op.execute(
            "ALTER TABLE hub_changesets DROP COLUMN installation_id, DROP COLUMN submission_uuid, "
            "DROP COLUMN submitted_by, DROP COLUMN submitter_role, "
            "DROP COLUMN base_package_version, DROP COLUMN offline, "
            "DROP COLUMN review_started_at, DROP COLUMN review_started_by"
        )
        op.execute("DROP TABLE hub_installations")
    elif role == "municipality":
        for table in ("hub_downloads", "hub_link", "user_pseudonyms", "submission_events",
                      "submissions"):
            op.execute(f"DROP TABLE {table}")
