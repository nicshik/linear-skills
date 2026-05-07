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
scripts/validate.sh
```

```bash
scripts/secret_scan.sh
```

These checks mirror the GitHub Actions CI and do not require a real `LINEAR_API_KEY`.
They also block accidental project-specific or local-machine strings. Keep project-specific queue URLs, issue prefixes, delivery rules, and private workspace names outside this public repository.

## Adding A New Skill

Follow the existing structure:

```text
linear-something/
  SKILL.md
  agents/openai.yaml
  scripts/something.py
```

The script should read `LINEAR_API_KEY` from the environment or `--env-file`, avoid printing secrets, and support `--json` when another agent may consume the output.
