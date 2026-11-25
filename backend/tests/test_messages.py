"""Message catalogue: one English template per code, exported for translation (ADR 0007)."""

from __future__ import annotations

import string
from pathlib import Path

from solidaritynode_core.model.messages import CORE_MESSAGES

from solidaritynode_backend.messages import BACKEND_MESSAGES, all_messages, messages_json

ROOT = Path(__file__).resolve().parents[2]


def test_codes_are_unique_and_templates_parse() -> None:
    assert not set(CORE_MESSAGES) & set(BACKEND_MESSAGES)
    for code, template in all_messages().items():
        fields = [f for _, f, _, _ in string.Formatter().parse(template) if f is not None]
        assert all(f.isidentifier() for f in fields), code


def test_exported_catalogue_is_current() -> None:
    """Run ``make schemas`` after changing a template (the frontend translates by code)."""
    expected = messages_json()
    for path in ("docs/schemas/messages.json", "frontend/src/api/messages.json"):
        assert (ROOT / path).read_text() == expected, f"{path} is stale: run make schemas"
