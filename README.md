# Linear Skills

Codex skills and small Python scripts for direct Linear GraphQL API workflows.

This repository is useful when the standard Linear connector is read-only, unavailable, or blocked by a tool guard, but you still need a narrow, auditable way to automate Linear actions with your own personal API key.

## Included Skills

| Skill | Purpose |
| --- | --- |
| `linear-change-status` | Change a Linear issue workflow state and verify the result. |
| `linear-custom-view` | Read a Linear Custom View and return its issues in manual order. |

## Repository Layout

```text
linear-change-status/
  SKILL.md
  agents/openai.yaml
  scripts/change_status.py
linear-custom-view/
  SKILL.md
  agents/openai.yaml
  scripts/custom_view.py
docs/
  codex-approvals.md
examples/
  default.rules.snippet
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

## Codex Approvals

The scripts call the Linear API, so Codex may ask for network approval. To avoid repeated prompts while keeping the permission narrow, approve only these prefixes:

```text
python3 linear-change-status/scripts/change_status.py
python3 linear-custom-view/scripts/custom_view.py
```

Do not approve broad prefixes such as `python3`.

For complete setup guidance, including how to pre-seed rules before the first run, see [`docs/codex-approvals.md`](docs/codex-approvals.md).

## Safety Model

- The API key is read from environment variables or local env files only.
- The scripts never print the API key.
- `linear-change-status` reads the issue, resolves the target state in the issue's team, updates only when needed, then verifies.
- `linear-change-status --dry-run` resolves the transition without updating Linear.
- `linear-custom-view` preserves the view's manual order with Linear's `manual` sort.

## Development

CI runs on pull requests, pushes to `main`, and manual GitHub Actions dispatches. It does not call the live Linear API and does not require `LINEAR_API_KEY`; tests must use local mocks or fixtures.

Run syntax checks:

```bash
python3 -m py_compile \
  linear-change-status/scripts/change_status.py \
  linear-custom-view/scripts/custom_view.py
```

Run the local CI equivalent:

```bash
python3 -m compileall linear-change-status linear-custom-view tests
python3 -m py_compile \
  linear-change-status/scripts/change_status.py \
  linear-custom-view/scripts/custom_view.py
python3 -m unittest discover -s tests
python3 scripts/validate_skill_files.py
python3 linear-custom-view/scripts/custom_view.py --help
python3 linear-change-status/scripts/change_status.py --help
```

Run fixture tests:

```bash
python3 -m unittest discover -s tests
```

Run a secret sanity check before pushing:

```bash
rg -n -I --hidden --glob '!.git/**' \
  -e 'LINEAR_API_KEY=[A-Za-z0-9_./+=:-]{20,}' \
  -e 'lin_api_[A-Za-z0-9_]{20,}' \
  -e 'sk-[A-Za-z0-9_-]{20,}' \
  -e 'gh[pousr]_[A-Za-z0-9_]{20,}' \
  -e 'BEGIN [A-Z ]*PRIVATE KEY' \
  -e 'Bearer [A-Za-z0-9._~+/=-]{20,}' \
  .
```

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Security

See [`SECURITY.md`](SECURITY.md).

## License

MIT. See [`LICENSE`](LICENSE).

## Disclaimer

This project is not affiliated with Linear. It uses Linear's public GraphQL API with a user-provided personal API key.
