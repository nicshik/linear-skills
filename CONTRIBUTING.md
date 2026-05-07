# Contributing

Contributions are welcome if they keep the skills narrow, deterministic, and safe to run through Codex.

## Guidelines

- Keep each skill focused on one Linear workflow.
- Prefer small scripts with explicit arguments over broad shell snippets.
- Never commit API keys, `.env` files, workspace tokens, or command logs that contain secrets.
- Keep Codex approval guidance narrow. Do not recommend broad prefixes such as `python3`.
- Use `--dry-run` for examples that could otherwise mutate Linear state.
- Keep tests offline. Do not call the live Linear API from tests or CI; use mocks and fixtures.
- Keep `SKILL.md` concise and move longer setup guidance to `docs/`.

## Local Checks

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

These checks mirror the GitHub Actions CI and do not require a real `LINEAR_API_KEY`.

## Adding A New Skill

Follow the existing structure:

```text
linear-something/
  SKILL.md
  agents/openai.yaml
  scripts/something.py
```

The script should read `LINEAR_API_KEY` from the environment or `--env-file`, avoid printing secrets, and support `--json` when another agent may consume the output.
