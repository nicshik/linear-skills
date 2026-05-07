#!/usr/bin/env python3
"""Validate the local Linear skill metadata without Codex-only dependencies."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("linear-change-status", "linear-custom-view")
REQUIRED_AGENT_FIELDS = ("display_name", "short_description", "default_prompt")


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def parse_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing opening YAML frontmatter marker")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError("missing closing YAML frontmatter marker")

    frontmatter = text[4:end]
    data: dict[str, str] = {}
    for raw_line in frontmatter.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", line)
        if match:
            key, value = match.groups()
            data[key] = value.strip().strip('"').strip("'")
    return data


def validate_skill(skill: str) -> list[str]:
    errors: list[str] = []
    skill_dir = ROOT / skill
    skill_md = skill_dir / "SKILL.md"
    agent_yaml = skill_dir / "agents" / "openai.yaml"

    if not skill_md.is_file():
        return [f"{skill}: missing SKILL.md"]
    if not agent_yaml.is_file():
        errors.append(f"{skill}: missing agents/openai.yaml")

    text = skill_md.read_text(encoding="utf-8")
    if "TODO" in text:
        errors.append(f"{skill}: SKILL.md contains TODO")

    try:
        frontmatter = parse_frontmatter(skill_md)
    except ValueError as exc:
        errors.append(f"{skill}: {exc}")
        frontmatter = {}

    if frontmatter.get("name") != skill:
        errors.append(f"{skill}: frontmatter name must be {skill!r}")
    if not frontmatter.get("description"):
        errors.append(f"{skill}: frontmatter description is required")

    if agent_yaml.is_file():
        agent_text = agent_yaml.read_text(encoding="utf-8")
        for field in REQUIRED_AGENT_FIELDS:
            if not re.search(rf"^\s+{field}\s*:\s*.+$", agent_text, flags=re.MULTILINE):
                errors.append(f"{skill}: agents/openai.yaml missing interface.{field}")
    return errors


def main() -> int:
    errors: list[str] = []
    for skill in SKILLS:
        errors.extend(validate_skill(skill))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Skill metadata validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
