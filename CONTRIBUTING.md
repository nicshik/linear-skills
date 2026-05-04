# Contributing

Contributions are welcome if they keep the skills narrow, deterministic, and safe to run through Codex.

## Guidelines

- Keep each skill focused on one Linear workflow.
- Prefer small scripts with explicit arguments over broad shell snippets.
- Never commit API keys, `.env` files, workspace tokens, or command logs that contain secrets.
- Keep Codex approval guidance narrow. Do not recommend broad prefixes such as `python3`.
- Use `--dry-run` for examples that could otherwise mutate Linear state.
- Keep `SKILL.md` concise and move longer setup guidance to `docs/`.

## Local Checks

```bash
python3 -m py_compile \
  linear-change-status/scripts/change_status.py \
  linear-custom-view/scripts/custom_view.py
```

```bash
rg -n 'LINEAR_API_KEY=.*[A-Za-z0-9]{20,}' .
```

## Adding A New Skill

Follow the existing structure:

```text
linear-something/
  SKILL.md
  agents/openai.yaml
  scripts/something.py
```

The script should read `LINEAR_API_KEY` from the environment or `--env-file`, avoid printing secrets, and support `--json` when another agent may consume the output.
