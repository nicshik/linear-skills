#!/usr/bin/env python3
"""Create missing Linear issue labels through the direct GraphQL API."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from linear_common.graphql import API_URL, LinearApiError, LinearClient, resolve_api_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create missing Linear issue labels.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--team", required=True, help="Target team key, ID, or exact name.")
    parser.add_argument("--label", action="append", required=True, help="Label name to ensure. Can be repeated.")
    parser.add_argument("--description", help="Description to use for newly created labels.")
    parser.add_argument("--color", help="Color to use for newly created labels, for example #5E6AD2.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve labels without creating missing labels.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    return parser.parse_args()


def normalize(value: str) -> str:
    return value.casefold().strip()


def exact_match(items: list[dict[str, Any]], value: str, fields: tuple[str, ...], kind: str) -> dict[str, Any]:
    value_norm = normalize(value)
    matches = [
        item
        for item in items
        if any(normalize(str(item.get(field) or "")) == value_norm for field in fields)
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise LinearApiError("not_found", f"{kind} '{value}' was not found.")
    names = ", ".join(str(match.get("name") or match.get("key") or match.get("id")) for match in matches)
    raise LinearApiError("ambiguous_lookup", f"{kind} '{value}' is ambiguous: {names}")


def resolve_team(client: LinearClient, value: str) -> dict[str, Any]:
    data = client.gql(
        """
        query Teams {
          teams(first: 250) {
            nodes { id key name }
          }
        }
        """
    )
    return exact_match(data["teams"]["nodes"], value, ("id", "key", "name"), "Team")


def list_labels(client: LinearClient, team_id: str) -> list[dict[str, Any]]:
    data = client.gql(
        """
        query Labels($teamId: ID!) {
          issueLabels(first: 250, filter: { team: { id: { eq: $teamId } } }) {
            nodes { id name description color team { id key name } }
          }
        }
        """,
        {"teamId": team_id},
    )
    return data["issueLabels"]["nodes"]


def find_label(labels: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    matches = [label for label in labels if normalize(label.get("name") or "") == normalize(name)]
    if len(matches) > 1:
        names = ", ".join(str(label.get("id")) for label in matches)
        raise LinearApiError("ambiguous_lookup", f"Label '{name}' is ambiguous: {names}")
    return matches[0] if matches else None


def create_label(
    client: LinearClient,
    team: dict[str, Any],
    name: str,
    description: str | None,
    color: str | None,
) -> dict[str, Any]:
    input_data: dict[str, Any] = {
        "teamId": team["id"],
        "name": name,
    }
    if description:
        input_data["description"] = description
    if color:
        input_data["color"] = color

    data = client.gql(
        """
        mutation CreateLabel($input: IssueLabelCreateInput!) {
          issueLabelCreate(input: $input) {
            success
            issueLabel { id name description color team { id key name } }
          }
        }
        """,
        {"input": input_data},
    )
    return data["issueLabelCreate"]["issueLabel"]


def build_result(client: LinearClient, args: argparse.Namespace) -> dict[str, Any]:
    team = resolve_team(client, args.team)
    labels = list_labels(client, team["id"])
    results: list[dict[str, Any]] = []

    for name in args.label:
        existing = find_label(labels, name)
        if existing:
            results.append({"name": name, "action": "exists", "label": existing})
            continue

        if args.dry_run:
            results.append({"name": name, "action": "would_create", "label": None})
            continue

        created = create_label(client, team, name, args.description, args.color)
        labels.append(created)
        results.append({"name": name, "action": "created", "label": created})

    verified = list_labels(client, team["id"])
    return {
        "action": "dry_run" if args.dry_run else "ensured",
        "team": team,
        "labels": results,
        "verified_labels": [label for label in verified if normalize(label.get("name") or "") in {normalize(name) for name in args.label}],
        "schema_version": "linear-label-setup.v1",
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def emit_text_result(result: dict[str, Any]) -> None:
    team = result["team"]
    print(f"team={team.get('key') or '-'}:{team.get('name') or '-'}")
    for item in result["labels"]:
        print(f"label={item['name']} action={item['action']}")


def main() -> int:
    args = parse_args()
    try:
        client = LinearClient(args.api_url, resolve_api_key(args.env_file))
        result = build_result(client, args)
    except LinearApiError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": "linear-label-setup.error.v1",
                        "error_category": exc.category,
                        "error": exc.message,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                file=sys.stderr,
            )
        else:
            print(f"error_category={exc.category}", file=sys.stderr)
            print(exc.message, file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit_text_result(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
