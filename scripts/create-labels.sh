#!/usr/bin/env bash
# Create or update GitHub labels from .github/labels.yml with the GitHub CLI.
# Requires `gh auth login`. Usage: scripts/create-labels.sh [owner/repo]
set -euo pipefail

repo_args=()
if [[ $# -ge 1 ]]; then
  repo_args=(--repo "$1")
fi

labels_file="$(dirname "$0")/../.github/labels.yml"
name="" color=""
while IFS= read -r line; do
  if [[ $line =~ ^-\ name:\ \"(.*)\"$ ]]; then
    name="${BASH_REMATCH[1]}"
  elif [[ $line =~ ^\ \ color:\ \"(.*)\"$ ]]; then
    color="${BASH_REMATCH[1]}"
  elif [[ $line =~ ^\ \ description:\ \"(.*)\"$ ]]; then
    description="${BASH_REMATCH[1]}"
    gh label create "$name" --color "$color" --description "$description" --force "${repo_args[@]}"
    name="" color=""
  fi
done <"$labels_file"
