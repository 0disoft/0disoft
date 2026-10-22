#!/usr/bin/env bash
set -euo pipefail

# Only resolve notices created by this workflow, after the private card is published.
issues="$(gh issue list --repo "$GITHUB_REPOSITORY" --state open \
  --label buildmarks-degraded --author 'github-actions[bot]' --limit 100 \
  --json number,title \
  --jq '.[] | select(.title == "Buildmarks card fell back to public-only data") | .number')"

run_url="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
while IFS= read -r issue; do
  [ -n "$issue" ] || continue
  gh issue close "$issue" --repo "$GITHUB_REPOSITORY" \
    --comment "Private-local collection recovered and the validated card is published. Workflow run: $run_url"
done <<< "$issues"
