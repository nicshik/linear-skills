# Changelog

## Unreleased

- Nothing yet.

## 2026-05-26 - v0.2.4

- Add `linear-delete-issue` for checked soft deletion of one issue with read-before-delete, dry-run, exact confirmation, and guard checks.
- Run GitHub Actions CI on the self-hosted `linear-skills-ci` runner.

## 2026-05-22 - v0.2.3

- Allow `linear-update-issue` to set issue `priority` with checked aliases, dry-run support, and verified read-back.
- Add structured `issue_not_found` diagnostics for read/comment helpers so wrong issue targets are not confused with API key or connector failures.
- Allow `linear-update-issue` to set `sortOrder` for checked manual issue ordering.
- Add `linear-custom-view-update` for checked Custom View metadata and filter updates.
- Add `linear-relation-setup` for checked issue relation setup covering `related`, `blocks`, and `blocked-by`.
- Add `linear-list-issues` as a read-only issue listing fallback for migration, label cleanup, and metadata preflight.
- Add `linear-label-setup` for explicit issue label setup with dry-run and no-op behavior.
- Add `linear-update-issue` for checked issue updates covering labels, assignee, parent, title, and description.
- Add `linear-custom-view-setup` for checked Custom View creation after metadata resolution.
- Allow `linear-create-issue` to set assignee and parent while keeping missing-label setup separate.
- Add `linear-comment-issue` as a narrow comment fallback with issue resolution, dry-run, and verification.
- Add `linear-create-issue` as a narrow issue creation fallback with metadata resolution, dry-run, and verification.
- Add `linear-read-issue` as a read-only issue fallback with optional comments and relations.
- Share Linear GraphQL key loading, TLS setup, and token-safe errors across scripts.
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
