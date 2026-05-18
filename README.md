# Linear Skills

[Русский](README.ru.md)

Codex skills and small Python scripts for direct Linear GraphQL API workflows.

This repository is useful when the standard Linear connector is read-only, unavailable, or blocked by a tool guard, but you still need a narrow, auditable way to automate Linear actions with your own personal API key.

The repository is intentionally generic. Project-specific queues, delivery rules, issue prefixes, and "Done" policies should live in a separate wrapper skill or project repository.

## Included Skills

| Skill | Purpose |
| --- | --- |
| `linear-change-status` | Change a Linear issue workflow state and verify the result. |
| `linear-comment-issue` | Add one comment to a Linear issue after reading and verifying the target issue. |
| `linear-create-issue` | Create one Linear issue after resolving target team, status, project, and labels. |
| `linear-custom-view` | Read a Linear Custom View and return its issues in manual order. |
| `linear-custom-view-setup` | Ensure one team Custom View exists after resolving team, project, and labels. |
| `linear-label-setup` | Ensure issue labels exist in a team, with dry-run and no-op behavior. |
| `linear-list-issues` | Read filtered issue lists for migration, label cleanup, and metadata preflight. |
| `linear-read-issue` | Read one Linear issue, with optional comments and relations, as a read-only fallback. |
| `linear-update-issue` | Update one existing issue after a read-before-write check and verify the result. |

## Repository Layout

```text
linear-change-status/
  SKILL.md
  agents/openai.yaml
  scripts/change_status.py
linear-comment-issue/
  SKILL.md
  agents/openai.yaml
  scripts/comment_issue.py
linear-create-issue/
  SKILL.md
  agents/openai.yaml
  scripts/create_issue.py
linear-custom-view/
  SKILL.md
  agents/openai.yaml
  scripts/custom_view.py
linear-custom-view-setup/
  SKILL.md
  agents/openai.yaml
  scripts/custom_view_setup.py
linear-label-setup/
  SKILL.md
  agents/openai.yaml
  scripts/label_setup.py
linear-list-issues/
  SKILL.md
  agents/openai.yaml
  scripts/list_issues.py
linear-read-issue/
  SKILL.md
  agents/openai.yaml
  scripts/read_issue.py
linear-update-issue/
  SKILL.md
  agents/openai.yaml
  scripts/update_issue.py
linear_common/
  graphql.py
docs/
  codex-approvals.md
examples/
  default.rules.snippet
scripts/
  validate.sh
  secret_scan.sh
  release_check.sh
```

## Requirements

- Python 3.10 or newer.
- A Linear personal API key with access to the target workspace.
- Optional but recommended: `certifi` for reliable TLS certificate handling on macOS Python installs.

Install the optional Python dependency:

```bash
python3 -m pip install -r requirements.txt
```

## API Key Setup

Set the key in your shell:

```bash
export LINEAR_API_KEY=<linear-api-key>
```

Or pass a local env file:

```bash
python3 linear-custom-view/scripts/custom_view.py <view-url> --env-file /path/to/.env.local
```

The env file should contain:

```text
LINEAR_API_KEY=<linear-api-key>
```

Do not commit real API keys. `.env` and `.env.*` are ignored by this repository.

## Usage

Read a Custom View queue in manual order:

```bash
python3 linear-custom-view/scripts/custom_view.py \
  "https://linear.app/example/view/my-view-123abc" \
  --env-file /path/to/.env.local \
  --limit 50
```

Return the first actionable row and explain the view filter:

```bash
python3 linear-custom-view/scripts/custom_view.py \
  "https://linear.app/example/view/my-view-123abc" \
  --env-file /path/to/.env.local \
  --json --first --explain-filter
```

Change an issue status:

```bash
python3 linear-change-status/scripts/change_status.py LIN-123 Done \
  --env-file /path/to/.env.local
```

Read one issue without updating Linear:

```bash
python3 linear-read-issue/scripts/read_issue.py LIN-123 \
  --env-file /path/to/.env.local \
  --include-comments --include-relations
```

List open issues with no labels:

```bash
python3 linear-list-issues/scripts/list_issues.py \
  --team LIN \
  --project "Example Project" \
  --open-only \
  --without-labels \
  --env-file /path/to/.env.local \
  --json
```

Create one issue after verifying metadata:

```bash
python3 linear-create-issue/scripts/create_issue.py \
  --team LIN \
  --project "Example Project" \
  --status Backlog \
  --label Idea \
  --optional-label Product \
  --assignee "Example User" \
  --parent LIN-100 \
  --title "Example idea" \
  --description-file /path/to/body.md \
  --env-file /path/to/.env.local
```

Add one comment after verifying the target issue:

```bash
python3 linear-comment-issue/scripts/comment_issue.py LIN-123 \
  --body-file /path/to/comment.md \
  --env-file /path/to/.env.local
```

Ensure issue labels exist in a team:

```bash
python3 linear-label-setup/scripts/label_setup.py \
  --team LIN \
  --label "Example label" \
  --description "Issues for the example stream" \
  --env-file /path/to/.env.local \
  --dry-run
```

Update an existing issue after reading it:

```bash
python3 linear-update-issue/scripts/update_issue.py LIN-123 \
  --add-label "Example label" \
  --assignee "Example User" \
  --append-description-file /path/to/addition.md \
  --env-file /path/to/.env.local \
  --dry-run
```

Ensure a Custom View exists:

```bash
python3 linear-custom-view-setup/scripts/custom_view_setup.py \
  --team LIN \
  --project "Example Project" \
  --name "Example open work" \
  --label "Example label" \
  --open-only \
  --env-file /path/to/.env.local \
  --dry-run
```

Test a status transition without updating Linear:

```bash
python3 linear-change-status/scripts/change_status.py LIN-123 Done \
  --env-file /path/to/.env.local \
  --dry-run
```

Preview a batch of one-by-one status transitions:

```bash
python3 linear-change-status/scripts/change_status.py \
  --batch-file status_changes.tsv \
  --env-file /path/to/.env.local \
  --json
```

Use `--json` when another tool or agent should consume the output.

## Project-Specific Wrappers

These skills are low-level Linear helpers:

- `linear-custom-view` reads a Custom View queue and preserves manual order.
- `linear-change-status` performs a narrow status transition and verifies it.
- `linear-comment-issue` creates one issue comment after reading and verifying the target issue.
- `linear-read-issue` reads one issue and optional comments or relations without updating Linear.
- `linear-create-issue` creates one issue after resolving required metadata and verifying the created issue.
- `linear-label-setup` creates missing labels only when explicitly asked, with no-op behavior for existing labels.
- `linear-list-issues` reads scoped issue lists for metadata preflight without updating Linear.
- `linear-update-issue` updates one existing issue after read-before-write, then verifies the result.
- `linear-custom-view-setup` creates one missing Custom View after resolving metadata.

They do not decide which project issue should be implemented, whether delivery is complete, or whether `Done` is appropriate. Keep those decisions in a project-specific wrapper skill or process document. The wrapper can call these scripts through stable environment variables such as `LINEAR_API_KEY`, `LINEAR_ENV_FILE`, or `--env-file`.

## Codex Approvals

The scripts call the Linear API, so Codex may ask for network approval. To avoid repeated prompts while keeping the permission narrow, approve only these prefixes:

```text
python3 linear-change-status/scripts/change_status.py
python3 linear-comment-issue/scripts/comment_issue.py
python3 linear-create-issue/scripts/create_issue.py
python3 linear-custom-view/scripts/custom_view.py
python3 linear-custom-view-setup/scripts/custom_view_setup.py
python3 linear-label-setup/scripts/label_setup.py
python3 linear-list-issues/scripts/list_issues.py
python3 linear-read-issue/scripts/read_issue.py
python3 linear-update-issue/scripts/update_issue.py
```

Do not approve broad prefixes such as `python3`.

For complete setup guidance, including how to pre-seed rules before the first run, see [`docs/codex-approvals.md`](docs/codex-approvals.md).

## Safety Model

- The API key is read from environment variables or local env files only.
- The scripts never print the API key.
- `linear-change-status` reads the issue, resolves the target state in the issue's team, updates only when needed, then verifies.
- `linear-change-status --dry-run` resolves the transition without updating Linear.
- `linear-custom-view` resolves direct Custom View IDs or slug IDs through `customView(id:)` before falling back to workspace view listing.
- `linear-custom-view` preserves the view's manual order with Linear's `manual` sort.
- `linear-read-issue` sends only read queries and never GraphQL mutations.
- `linear-list-issues` sends only read queries and never GraphQL mutations.
- `linear-create-issue --dry-run` resolves team, status, project, and labels without creating an issue.
- `linear-comment-issue --dry-run` resolves the target issue without creating a comment.
- `linear-create-issue --optional-label` skips missing optional labels while preserving required-label failures.
- `linear-create-issue` can assign a user and parent issue after resolving both IDs; it does not create missing labels.
- `linear-label-setup --dry-run` resolves team and labels without creating labels.
- `linear-list-issues --without-labels` returns only issues whose `labels.nodes` list is empty.
- `linear-list-issues --missing-label` returns issues missing at least one requested label.
- `linear-update-issue` reads the issue before updating labels, assignee, parent, title, or description, then verifies the result.
- `linear-update-issue --dry-run` resolves the target update without updating Linear.
- `linear-custom-view-setup --dry-run` resolves team, project, labels, and existing view state without creating a Custom View.
- All scripts share one GraphQL client, API-key resolution, TLS setup through `certifi` when available, and token sanitization for error output.

## Development

CI runs on pull requests, pushes to `main`, and manual GitHub Actions dispatches. It does not call the live Linear API and does not require `LINEAR_API_KEY`; tests must use local mocks or fixtures.

Run syntax checks:

```bash
python3 -m py_compile \
  linear-change-status/scripts/change_status.py \
  linear-comment-issue/scripts/comment_issue.py \
  linear-create-issue/scripts/create_issue.py \
  linear-custom-view/scripts/custom_view.py \
  linear-custom-view-setup/scripts/custom_view_setup.py \
  linear-label-setup/scripts/label_setup.py \
  linear-list-issues/scripts/list_issues.py \
  linear-read-issue/scripts/read_issue.py \
  linear-update-issue/scripts/update_issue.py \
  linear_common/graphql.py
```

Run the local CI equivalent:

```bash
scripts/validate.sh
```

Run fixture tests only:

```bash
python3 -m unittest discover -s tests
```

Run a secret sanity check before pushing:

```bash
scripts/secret_scan.sh
```

`scripts/validate.sh` also blocks accidental project-specific or local-machine strings so this public repository stays portable.

Run the local release gate after committing and pushing:

```bash
scripts/release_check.sh
```

Release steps are documented in [`docs/release.md`](docs/release.md). Dependency updates are handled by Dependabot for GitHub Actions and Python requirements.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Changelog

See [`CHANGELOG.md`](CHANGELOG.md).

## Security

See [`SECURITY.md`](SECURITY.md).

## License

MIT. See [`LICENSE`](LICENSE).

## Disclaimer

This project is not affiliated with Linear. It uses Linear's public GraphQL API with a user-provided personal API key.
