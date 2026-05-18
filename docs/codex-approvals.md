# Codex Approvals For Linear Skills

This guide explains how to make the Linear skills run without repeated Codex approval prompts while keeping the permission scope narrow.

It is based on the setup used for:

- `linear-change-status`
- `linear-custom-view`
- `linear-read-issue`

## Why Prompts Appear

The scripts call the Linear GraphQL API at `https://api.linear.app/graphql`.

In Codex, network access from shell commands normally requires elevated sandbox permission. If no matching approved command prefix exists, Codex asks before running the command.

The goal is not to disable safety globally. The goal is to approve only the exact skill entrypoints.

## Recommended Approved Prefixes

Add these prefixes:

```text
prefix_rule(pattern=["python3", "linear-change-status/scripts/change_status.py"], decision="allow")
prefix_rule(pattern=["python3", "linear-custom-view/scripts/custom_view.py"], decision="allow")
prefix_rule(pattern=["python3", "linear-read-issue/scripts/read_issue.py"], decision="allow")
```

These rules allow commands that start with the exact script path, for example:

```bash
python3 linear-change-status/scripts/change_status.py LIN-123 Done --env-file /path/to/.env.local
python3 linear-custom-view/scripts/custom_view.py https://linear.app/example/view/example-123 --limit 10
python3 linear-read-issue/scripts/read_issue.py LIN-123 --include-comments
```

They do not allow arbitrary Python commands such as:

```bash
python3 -c "..."
python3 other_script.py
```

## Option A: Let Codex Save The Rule

When Codex asks for approval, choose the option like:

```text
Yes, and do not ask again for commands that start with this prefix
```

The approval request should use one of these `prefix_rule` values:

```json
["python3", "linear-change-status/scripts/change_status.py"]
["python3", "linear-custom-view/scripts/custom_view.py"]
["python3", "linear-read-issue/scripts/read_issue.py"]
```

If Codex asks for a broader prefix such as `["python3"]`, do not approve it. Re-run the command with a narrower `prefix_rule`.

## Option B: Pre-Seed The Rules

To avoid even the first prompt, add the rules to the Codex rules file before running the skills.

The common location is:

```text
~/.codex/rules/default.rules
```

Append:

```text
prefix_rule(pattern=["python3", "linear-change-status/scripts/change_status.py"], decision="allow")
prefix_rule(pattern=["python3", "linear-custom-view/scripts/custom_view.py"], decision="allow")
prefix_rule(pattern=["python3", "linear-read-issue/scripts/read_issue.py"], decision="allow")
```

Then restart the Codex session so the rules are loaded.

The same content is available as [`examples/default.rules.snippet`](../examples/default.rules.snippet).

## Stable Working Directory

Run the scripts from the repository root:

```bash
cd /path/to/linear-skills
python3 linear-custom-view/scripts/custom_view.py ...
```

This keeps the command prefix stable. If you run the script by an absolute path, Codex may treat it as a different prefix and ask again.

## API Key Handling

Store the Linear key outside this repository.

Recommended options:

```bash
export LINEAR_API_KEY=<linear-api-key>
```

or:

```bash
python3 linear-custom-view/scripts/custom_view.py ... --env-file /path/to/.env.local
```

The `.env.local` file should contain:

```text
LINEAR_API_KEY=<linear-api-key>
```

Do not commit `.env`, `.env.local`, or any file containing a real Linear API key.

## What Not To Approve

Avoid broad rules:

```text
prefix_rule(pattern=["python3"], decision="allow")
prefix_rule(pattern=["python3", "-c"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc"], decision="allow")
```

Those rules are too wide for skills that only need deterministic script entrypoints.

## Verification

After adding the rules and restarting Codex, these commands should run without approval prompts:

```bash
python3 linear-custom-view/scripts/custom_view.py https://linear.app/example/view/example-123 --env-file /path/to/.env.local --limit 1
python3 linear-change-status/scripts/change_status.py LIN-123 Done --env-file /path/to/.env.local --dry-run
python3 linear-read-issue/scripts/read_issue.py LIN-123 --env-file /path/to/.env.local
```

Use `--dry-run` for status changes when testing. It reads the issue and resolves the target status without updating Linear. `linear-read-issue` is read-only by design.

## Troubleshooting

If Codex still asks:

- confirm the rules are in `~/.codex/rules/default.rules`;
- restart the Codex session;
- run from the `linear-skills` repository root;
- make sure the command starts with the same prefix as the rule;
- avoid shell wrappers like `/bin/zsh -lc "python3 ..."` unless you also approve that exact wrapper prefix.

If the command fails with a DNS or sandbox network error, the prefix was not applied in the current session or the command did not match the rule.
