#!/bin/sh
# Delete all but the newest Actions cache on this ref whose key starts with $1.
set -eu
gh cache list -R "$GITHUB_REPOSITORY" --ref "$GITHUB_REF" --key "$1" \
    --sort created_at --order desc --limit 100 --json id --jq '.[1:][].id' |
    while read -r id; do
        gh cache delete "$id" -R "$GITHUB_REPOSITORY"
    done
