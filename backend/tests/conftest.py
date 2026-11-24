"""Test configuration: the suite runs with ``APP_ENV=test``."""

from __future__ import annotations

import os

os.environ["APP_ENV"] = "test"
