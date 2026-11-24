#!/usr/bin/env bash
# Check that every non-merge commit in BASE..HEAD has a Signed-off-by trailer matching
# its author (Developer Certificate of Origin). Usage: scripts/check-dco.sh BASE HEAD
set -euo pipefail

base="${1:?base revision}"
head="${2:?head revision}"
status=0

while read -r sha; do
  author="$(git log -1 --format='%an <%ae>' "$sha")"
  trailers="$(git log -1 --format='%(trailers:key=Signed-off-by,valueonly)' "$sha")"
  if ! grep -Fqx -- "$author" <<<"$trailers"; then
    echo "::error::commit ${sha:0:12} lacks 'Signed-off-by: ${author}' (use git commit -s)"
    status=1
  fi
done < <(git rev-list --no-merges "${base}..${head}")

if [[ $status -eq 0 ]]; then
  echo "All commits in ${base:0:12}..${head:0:12} are signed off."
fi
exit "$status"
