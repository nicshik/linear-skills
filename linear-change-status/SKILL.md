---
name: linear-change-status
description: Change Linear issue statuses through the direct Linear GraphQL API using a local LINEAR_API_KEY. Use when the user asks to move a Linear task or issue to Done, In Progress, Backlog, Todo, or another workflow state and the normal Linear MCP connector is unavailable, blocked, or insufficient.
metadata:
  category: productivity
  capability_taxonomy_ids:
    - cap.productivity.issue_tracking
    - cap.tools.api_automation
  compatibility:
    runtimes:
      - codex
      - claude_code
      - cursor
      - windsurf
  distribution_scope: internal
  invocation_strategy: explicit
  version: v0.1
  source_of_truth: https://github.com/nicshik/linear-skills
---

# Linear Change Status

Use this skill when the user explicitly asks to change a Linear issue status through the Linear API.

Prefer the official Linear MCP connector for read-only discovery. Use this skill when a direct API key is available and the task is a narrow status transition.

## Preconditions

- `LINEAR_API_KEY` is available in the shell, `LINEAR_ENV_FILE`, `--env-file`, or a local `.env.local`.
- The key belongs to a Linear user with permission to edit the target issue.
- Network access to `https://api.linear.app/graphql` is allowed.

## Non-Negotiable Rules

- Use `scripts/change_status.py`.
- Never print the API key.
- Do not store the API key in the skill directory.
- Read the issue first, find the target workflow state inside the issue team, update, then verify.
- If the issue is already in the target state, report a no-op instead of sending an update.
- For bulk changes, process issues one at a time and report each result.

## Codex Permission Rule

When Codex sandboxing asks for approval because the script needs network access, request a persistent command prefix:

- `sandbox_permissions`: `require_escalated`
- `prefix_rule`: `["python3", "linear-change-status/scripts/change_status.py"]`

Tell the user to choose the option like "Yes, and don't ask again for commands that start with this prefix". After that, the same status-change script can run without repeated prompts.

Keep the command prefix stable by running from the `linear-skills` repository root. Pass the API key only through the environment or `--env-file`; never pass the key as a command argument.

For full setup details and a ready-to-copy rules snippet, see `docs/codex-approvals.md` in the repository root.

## Default Flow

1. Identify the issue key or ID and target status from the user request.
2. If the key is only in a project `.env.local`, pass it via `--env-file`.
3. Run the script.
4. Report the previous status, target status, update result, and verified status.

## Recommended Commands

```bash
python3 scripts/change_status.py LIN-123 Done --env-file /path/to/.env.local
python3 scripts/change_status.py LIN-124 "In Progress" --json
python3 scripts/change_status.py LIN-125 Done --dry-run
```

## Output Shape

- Text output: `before`, `target`, `updated` or `noop`, and `verify`.
- `--json` output: structured fields for issue, before state, target state, changed flag, and verified state.
- On failure, show the API or validation error directly without guessing.
