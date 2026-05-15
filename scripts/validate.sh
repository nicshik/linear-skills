#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v rg >/dev/null 2>&1; then
  echo "ERROR: ripgrep is required for validation." >&2
  exit 2
fi

echo "== Public repository guard =="
blocked_terms=(
  "Factor""ix"
  "F""CT-"
  "/Users/""nick"
  "Wind""surf"
  "shini""hi"
  "ochered""-realizacii"
  "Agent ""Creator"
  "Factor""ix Market"
  "Max""im"
  "B""SG"
  "org""_default"
  "Орг""задачи"
  "factor""ix-codex"
)
for term in "${blocked_terms[@]}"; do
  if rg -n -i --fixed-strings --hidden --glob '!.git/**' --glob '!__pycache__/**' --glob '!*.pyc' "$term" .; then
    echo "ERROR: project-specific or local-machine term found: $term" >&2
    exit 1
  fi
done

echo "== Secret scan =="
scripts/secret_scan.sh

echo "== Compile Python sources =="
python3 -m compileall linear-change-status linear-custom-view tests
python3 -m py_compile \
  linear-change-status/scripts/change_status.py \
  linear-custom-view/scripts/custom_view.py

echo "== Fixture tests =="
python3 -m unittest discover -s tests

echo "== Skill metadata =="
python3 scripts/validate_skill_files.py

echo "== CLI help smoke =="
python3 linear-custom-view/scripts/custom_view.py --help >/dev/null
python3 linear-change-status/scripts/change_status.py --help >/dev/null

echo "Validation passed."
