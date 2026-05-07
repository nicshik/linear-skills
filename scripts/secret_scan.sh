#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v rg >/dev/null 2>&1; then
  echo "ERROR: ripgrep is required for secret scan." >&2
  exit 2
fi

set +e
rg -n -I --hidden \
  --glob '!.git/**' \
  --glob '!__pycache__/**' \
  --glob '!*.pyc' \
  -e 'LINEAR_API_KEY=[A-Za-z0-9_./+=:-]{20,}' \
  -e 'lin_api_[A-Za-z0-9_]{20,}' \
  -e 'sk-[A-Za-z0-9_-]{20,}' \
  -e 'gh[pousr]_[A-Za-z0-9_]{20,}' \
  -e 'BEGIN [A-Z ]*PRIVATE KEY' \
  -e 'Bearer [A-Za-z0-9._~+/=-]{20,}' \
  -e '[A-Za-z][A-Za-z0-9+.-]*://user:password@' \
  .
rc="$?"
set -e

if [ "$rc" -eq 0 ]; then
  echo "ERROR: secret-like value found." >&2
  exit 1
fi
if [ "$rc" -gt 1 ]; then
  exit "$rc"
fi

echo "Secret scan passed."
