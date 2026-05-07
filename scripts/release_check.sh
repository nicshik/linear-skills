#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== Release validation =="
scripts/validate.sh

echo "== Whitespace diff check =="
git diff --check

echo "== Git status =="
status="$(git status --short)"
if [ -n "$status" ]; then
  printf '%s\n' "$status" >&2
  echo "ERROR: working tree is not clean." >&2
  exit 1
fi

echo "Release check passed."
