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
python3 -m compileall linear-change-status linear-comment-issue linear-create-issue linear-custom-view linear-custom-view-setup linear-custom-view-update linear-label-setup linear-list-issues linear-read-issue linear-relation-setup linear-update-issue linear_common tests
python3 -m py_compile \
  linear-change-status/scripts/change_status.py \
  linear-comment-issue/scripts/comment_issue.py \
  linear-create-issue/scripts/create_issue.py \
  linear-custom-view/scripts/custom_view.py \
  linear-custom-view-setup/scripts/custom_view_setup.py \
  linear-custom-view-update/scripts/custom_view_update.py \
  linear-label-setup/scripts/label_setup.py \
  linear-list-issues/scripts/list_issues.py \
  linear-read-issue/scripts/read_issue.py \
  linear-relation-setup/scripts/relation_setup.py \
  linear-update-issue/scripts/update_issue.py \
  linear_common/graphql.py

echo "== Fixture tests =="
python3 -m unittest discover -s tests

echo "== Skill metadata =="
python3 scripts/validate_skill_files.py

echo "== CLI help smoke =="
python3 linear-custom-view/scripts/custom_view.py --help >/dev/null
python3 linear-custom-view-update/scripts/custom_view_update.py --help >/dev/null
python3 linear-change-status/scripts/change_status.py --help >/dev/null
python3 linear-comment-issue/scripts/comment_issue.py --help >/dev/null
python3 linear-create-issue/scripts/create_issue.py --help >/dev/null
python3 linear-read-issue/scripts/read_issue.py --help >/dev/null
python3 linear-label-setup/scripts/label_setup.py --help >/dev/null
python3 linear-list-issues/scripts/list_issues.py --help >/dev/null
python3 linear-relation-setup/scripts/relation_setup.py --help >/dev/null
python3 linear-update-issue/scripts/update_issue.py --help >/dev/null
python3 linear-custom-view-setup/scripts/custom_view_setup.py --help >/dev/null

echo "Validation passed."
