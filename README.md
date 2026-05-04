# Linear Skills

Codex skills for direct Linear GraphQL API workflows.

## Skills

- `linear-change-status` — change a Linear issue status and verify the result.
- `linear-custom-view` — read a Linear Custom View, including manually sorted issues.

## Setup

Set `LINEAR_API_KEY` in your shell, or pass a local env file to the bundled scripts:

```bash
python3 linear-change-status/scripts/change_status.py FCT-9 Done --env-file /path/to/.env.local
python3 linear-custom-view/scripts/custom_view.py "https://linear.app/.../view/..." --env-file /path/to/.env.local
```

The key must be a Linear personal API key with access to the workspace.

