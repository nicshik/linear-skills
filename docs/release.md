# Release Runbook

Use this checklist for `linear-skills` releases.

## Before Commit

```bash
scripts/validate.sh
git diff --check
git status --short
```

Commit and push the intended changes:

```bash
git add <changed-files>
git commit -m "<message>"
git push origin main
```

## After CI

Wait for GitHub Actions to pass on `main`, then run:

```bash
scripts/release_check.sh
```

## Tag And Release

Create and push an annotated tag:

```bash
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

Create a GitHub Release from the tag. Release notes should include:

- supported Python versions verified by CI;
- whether the release changes scripts, skill instructions, or only repository tooling;
- any security or migration notes for API key handling.
