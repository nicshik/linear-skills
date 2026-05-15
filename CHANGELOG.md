# Changelog

## Unreleased

- Remove project-specific example labels from `linear-custom-view` docs/tests and strengthen the public repository guard.
- Resolve direct Custom View IDs and slug IDs before falling back to workspace Custom View listing.

## 2026-05-07 - v0.2.2

- Update `certifi` minimum requirement to `2026.4.22`.

## 2026-05-07 - v0.2.1

- Add Dependabot for GitHub Actions and Python dependencies.
- Add `scripts/release_check.sh` and release runbook.
- Document release workflow in README and contributing guide.

## 2026-05-07 - v0.2.0

- Add repository-level `scripts/validate.sh` and `scripts/secret_scan.sh`.
- Add Russian README alternative.
- Document the boundary between generic Linear helpers and project-specific wrapper workflows.
- Update GitHub Actions to `actions/checkout@v6` and `actions/setup-python@v6`.
- Mark bundled skill metadata as public and bump skill metadata version to `v0.2`.

## 2026-05-07 - v0.1.0

- Publish generic Linear skills for Custom View queue reads and narrow status changes.
- Add offline fixture tests, metadata validation, CI, and secret-scan checks.
