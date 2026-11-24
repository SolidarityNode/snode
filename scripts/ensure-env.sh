#!/usr/bin/env bash
# Create .env from .env.example if it is missing, then warn about keys that are set in
# .env.example but missing from .env. Never overwrites or edits an existing .env.
# Used by `make setup` (CLAUDE.md, "Configuration").
set -euo pipefail

example="${1:-.env.example}"
target="${2:-.env}"

if [ ! -f "$target" ]; then
  cp "$example" "$target"
  echo "Created $target from $example (development defaults; placeholders are 'change-me')."
  exit 0
fi

keys() { grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$1" | cut -d= -f1 | sort -u; }

missing="$(comm -23 <(keys "$example") <(keys "$target"))"
if [ -n "$missing" ]; then
  echo "WARNING: $target lacks keys that $example defines:" >&2
  while IFS= read -r key; do
    echo "  - $key" >&2
  done <<< "$missing"
  echo "Copy them from $example (defaults are safe for development)." >&2
fi
