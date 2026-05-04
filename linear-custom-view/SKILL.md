---
name: linear-custom-view
description: Read Linear Custom Views through the direct Linear GraphQL API using a local LINEAR_API_KEY. Use when the user asks to inspect a Linear view URL, extract the live issue queue, preserve manual order, or use a Custom View as a source of task priority.
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

# Linear Custom View

Use this skill when the user gives a Linear Custom View URL, slug, ID, or view name and wants the live ordered issue list.

This skill is useful when Linear MCP cannot read custom views or when the view's manual order is the source of implementation priority.

## Preconditions

- `LINEAR_API_KEY` is available in the shell, `LINEAR_ENV_FILE`, `--env-file`, or a local `.env.local`.
- The key belongs to a Linear user with access to the workspace and the Custom View.
- Network access to `https://api.linear.app/graphql` is allowed.

## Non-Negotiable Rules

- Use `scripts/custom_view.py`.
- Preserve manual order with `sort: [{ manual: { order: Ascending } }]` unless the user asks otherwise.
- Never print the API key.
- Treat the Custom View filter as the source of truth. Do not add hidden filters unless the user asks.
- If a completed issue disappears from the view, explain that the view filter controls visibility.

## Codex Permission Rule

When Codex sandboxing asks for approval because the script needs network access, request a persistent command prefix:

- `sandbox_permissions`: `require_escalated`
- `prefix_rule`: `["python3", "linear-custom-view/scripts/custom_view.py"]`

Tell the user to choose the option like "Yes, and don't ask again for commands that start with this prefix". After that, the same Custom View script can run without repeated prompts.

Keep the command prefix stable by running from the `linear-skills` repository root. Pass the API key only through the environment or `--env-file`; never pass the key as a command argument.

## Default Flow

1. Pass the Linear view URL, slug, ID, or exact name to the script.
2. Use `--json` when the result will drive automation.
3. Read the returned `filter_data`, issue count, and ordered issues.
4. Use the returned order as the queue order.

## Recommended Commands

```bash
python3 scripts/custom_view.py "https://linear.app/shihini/view/ochered-realizacii-agent-creator-ea68e703fad4" --env-file FactorixMarket/app/.env.local
python3 scripts/custom_view.py ea68e703fad4 --json
python3 scripts/custom_view.py "Очередь реализации [Agent_Creator]" --limit 50
```

## Output Shape

- Text output: view name, slug, issue count, then one issue per line in manual order.
- `--json` output: view metadata, `filter_data`, and ordered issue objects.
- On ambiguity, the script lists matching views and exits without guessing.
