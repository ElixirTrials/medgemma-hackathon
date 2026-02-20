#!/usr/bin/env bash
# One-time script to redact a leaked secret from git history.
# The secret appeared in Entire checkpoint full.jsonl files (now only in history).
#
# Prerequisites:
#   - git-filter-repo: pip install git-filter-repo   OR   brew install git-filter-repo
#
# Usage:
#   1. Back up the repo: git clone --mirror . ../medgemma-hackathon-backup.git
#   2. Set the leaked secret: export LEAKED_SECRET='caa516d8-27ee-4fbd-a857-cf24b48e0b73'
#   3. Run: ./scripts/redact_leaked_secret_from_history.sh
#   4. Re-add origin (filter-repo removes remotes): git remote add origin <repo-url>
#   5. Force-push: git push --force --all origin  [and --force --tags origin if needed]
#   6. Rotate the secret at its source (revoke/regenerate wherever it was used).
#   7. Delete this script if you don't want to keep it: rm scripts/redact_leaked_secret_from_history.sh
#
# Warning: Rewriting history changes all commit hashes. Collaborators must re-clone or rebase.

set -euo pipefail

if [[ -z "${LEAKED_SECRET:-}" ]]; then
  echo "Error: Set LEAKED_SECRET to the value to redact, e.g.:" >&2
  echo "  export LEAKED_SECRET='caa516d8-27ee-4fbd-a857-cf24b48e0b73'" >&2
  exit 1
fi

if ! command -v git-filter-repo &>/dev/null; then
  echo "Error: git-filter-repo not found. Install with:" >&2
  echo "  pip install git-filter-repo   OR   brew install git-filter-repo" >&2
  exit 1
fi

REPLACEMENT="REDACTED-LEAKED-SECRET-ROTATED"
REPLACE_FILE=$(mktemp)
trap 'rm -f "$REPLACE_FILE"' EXIT

# Capture origin URL before filter-repo removes it
ORIGIN_URL=$(git remote get-url origin 2>/dev/null || true)

# Format: literal==>replacement (replace in all blobs)
echo "${LEAKED_SECRET}==>${REPLACEMENT}" > "$REPLACE_FILE"

echo "Redacting secret from full git history..."
git filter-repo --replace-text "$REPLACE_FILE" --force

echo "Done. Next steps (filter-repo removed remotes; re-add and push):"
if [[ -n "$ORIGIN_URL" ]]; then
  echo "    git remote add origin $ORIGIN_URL"
else
  echo "    git remote add origin <your-repo-url>"
fi
echo "    git push --force --all origin"
echo "    git push --force --tags origin   # if you use tags"
echo "  Then rotate the secret at its source and have collaborators re-clone or rebase."
