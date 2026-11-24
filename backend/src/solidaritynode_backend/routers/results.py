"""Results router (placeholder, no endpoints yet).

Will serve run results indexed by ``spatial unit × social group × service × time`` with their
uncertainty (AGENTS.md invariants 1 and 6). Large arrays are stored in Parquet (ADR 0008);
the database holds the index.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/results", tags=["results"])
