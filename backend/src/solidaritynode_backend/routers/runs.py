"""Runs router (placeholder, no endpoints yet).

Will start model runs as **background jobs** (``solidaritynode_backend.jobs``), never inside a
request handler (CLAUDE.md). Queue technology: ADR 0006.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/runs", tags=["runs"])
