#!/usr/bin/env python3
"""Create one Linear Custom View when it is missing."""

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


VIEW_FIELDS = """
  id
  name
  slugId
  shared
  modelName
  filterData
  team { id key name }
  creator { name }
  owner { name }
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create one Linear Custom View when missing.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--name", required=True, help="Custom View name.")
    parser.add_argument("--team", required=True, help="Target team key, ID, or exact name.")
    parser.add_argument("--project", help="Target project ID or exact name.")
    parser.add_argument("--label", action="append", default=[], help="Label name that should be visible in the view. Can be repeated.")
    parser.add_argument("--description", help="Custom View description.")
    parser.add_argument("--color", help="Custom View color.")
    parser.add_argument("--icon", help="Custom View icon.")
    parser.add_argument("--open-only", action="store_true", help="Filter out completed and canceled issues.")
    parser.add_argument("--private", action="store_true", help="Create a private view instead of a shared view.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve metadata without creating the view.")
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


def resolve_project(client: LinearClient, value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    data = client.gql(
        """
        query Projects {
          projects(first: 250, includeArchived: false) {
            nodes { id name }
          }
        }
        """
    )
    return exact_match(data["projects"]["nodes"], value, ("id", "name"), "Project")


def resolve_labels(client: LinearClient, team_id: str, values: list[str]) -> list[dict[str, Any]]:
    if not values:
        return []
    data = client.gql(
        """
        query Labels($teamId: ID!) {
          issueLabels(first: 250, filter: { team: { id: { eq: $teamId } } }) {
            nodes { id name }
          }
        }
        """,
        {"teamId": team_id},
    )
    labels = data["issueLabels"]["nodes"]
    return [exact_match(labels, value, ("id", "name"), "Label") for value in values]


def list_views(client: LinearClient) -> list[dict[str, Any]]:
    data = client.gql(
        f"""
        query Views {{
          customViews(first: 250, includeArchived: false) {{
            nodes {{
              {VIEW_FIELDS}
            }}
          }}
        }}
        """
    )
    return data["customViews"]["nodes"]


def find_existing_view(views: list[dict[str, Any]], name: str, team: dict[str, Any]) -> dict[str, Any] | None:
    matches = [
        view
        for view in views
        if normalize(view.get("name") or "") == normalize(name)
        and normalize(((view.get("team") or {}).get("id") or "")) == normalize(team["id"])
    ]
    if len(matches) > 1:
        names = ", ".join(str(view.get("id")) for view in matches)
        raise LinearApiError("ambiguous_lookup", f"Custom View '{name}' is ambiguous: {names}")
    return matches[0] if matches else None


def build_filter_data(labels: list[dict[str, Any]], open_only: bool) -> dict[str, Any]:
    filters: list[dict[str, Any]] = []
    if open_only:
        filters.append({"state": {"type": {"nin": ["completed", "canceled"]}}})
    if labels:
        label_options: list[dict[str, Any]] = []
        for label in labels:
            label_options.append({"name": {"eq": label["name"]}})
            label_options.append({"parent": {"name": {"eq": label["name"]}}})
        filters.append({"labels": {"and": [{"or": label_options}]}})
    return {"and": filters} if filters else {}


def create_view(
    client: LinearClient,
    args: argparse.Namespace,
    team: dict[str, Any],
    project: dict[str, Any] | None,
    labels: list[dict[str, Any]],
) -> dict[str, Any]:
    input_data: dict[str, Any] = {
        "name": args.name,
        "teamId": team["id"],
        "shared": not args.private,
    }
    if project:
        input_data["projectId"] = project["id"]
    if args.description:
        input_data["description"] = args.description
    if args.color:
        input_data["color"] = args.color
    if args.icon:
        input_data["icon"] = args.icon
    filter_data = build_filter_data(labels, args.open_only)
    if filter_data:
        input_data["filterData"] = filter_data

    data = client.gql(
        f"""
        mutation CreateCustomView($input: CustomViewCreateInput!) {{
          customViewCreate(input: $input) {{
            success
            customView {{
              {VIEW_FIELDS}
            }}
          }}
        }}
        """,
        {"input": input_data},
    )
    return data["customViewCreate"]["customView"]


def build_result(client: LinearClient, args: argparse.Namespace) -> dict[str, Any]:
    team = resolve_team(client, args.team)
    project = resolve_project(client, args.project)
    labels = resolve_labels(client, team["id"], args.label)
    existing = find_existing_view(list_views(client), args.name, team)
    target = {
        "name": args.name,
        "team": team,
        "project": project,
        "labels": labels,
        "shared": not args.private,
        "filterData": build_filter_data(labels, args.open_only),
    }

    if existing:
        action = "exists"
        created = None
        verified = existing
    elif args.dry_run:
        action = "dry_run"
        created = None
        verified = None
    else:
        action = "created"
        created = create_view(client, args, team, project, labels)
        verified = created

    return {
        "action": action,
        "target": target,
        "created": created,
        "verified": verified,
        "schema_version": "linear-custom-view-setup.v1",
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def emit_text_result(result: dict[str, Any]) -> None:
    target = result["target"]
    print(f"name={target['name']}")
    print(f"team={target['team'].get('key') or '-'}:{target['team'].get('name') or '-'}")
    if target.get("project"):
        print(f"project={target['project']['name']}")
    labels = ", ".join(label["name"] for label in target.get("labels") or []) or "-"
    print(f"labels={labels}")
    print(f"action={result['action']}")


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
                        "schema_version": "linear-custom-view-setup.error.v1",
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
