#!/usr/bin/env python3
"""Update one existing Linear Custom View through the direct GraphQL API."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.parse
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
  description
  color
  icon
  filterData
  projectFilterData
  initiativeFilterData
  feedItemFilterData
  updatedAt
  team { id key name }
  creator { name }
  owner { name }
  projects(first: 20) { nodes { id name } }
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update one existing Linear Custom View.")
    parser.add_argument("view", help="Linear Custom View URL, ID, slugId, or exact name.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--team", help="Team key, ID, or exact name. Required for name lookup.")
    parser.add_argument("--project", help="Project ID or exact name for the view.")
    parser.add_argument("--label", action="append", default=[], help="Label name or ID for the view filter. Can be repeated.")
    parser.add_argument("--status", action="append", default=[], help="Workflow state name or ID for the view filter. Can be repeated.")
    parser.add_argument("--open-only", action="store_true", help="Filter out completed and canceled issues.")
    parser.add_argument("--name", help="Replacement Custom View name.")
    parser.add_argument("--description", help="Replacement Custom View description.")
    parser.add_argument("--color", help="Replacement Custom View color.")
    parser.add_argument("--icon", help="Replacement Custom View icon.")
    visibility = parser.add_mutually_exclusive_group()
    visibility.add_argument("--private", action="store_true", help="Make the view private.")
    visibility.add_argument("--shared", action="store_true", help="Make the view shared.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve the update without mutating Linear.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    return parser.parse_args()


def normalize(value: str) -> str:
    return value.casefold().strip()


def view_lookup_key(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    candidate = parsed.path.rsplit("/", 1)[-1] if parsed.scheme and parsed.netloc else value
    candidate = urllib.parse.unquote(candidate.strip())
    slug_match = re.search(r"([0-9a-f]{8,})$", candidate, flags=re.IGNORECASE)
    if slug_match:
        return slug_match.group(1)
    return candidate


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
    return [exact_match(data["issueLabels"]["nodes"], value, ("id", "name"), "Label") for value in values]


def resolve_statuses(client: LinearClient, team_id: str, values: list[str]) -> list[dict[str, Any]]:
    if not values:
        return []
    data = client.gql(
        """
        query WorkflowStates($teamId: ID!) {
          workflowStates(first: 250, filter: { team: { id: { eq: $teamId } } }) {
            nodes { id name type team { id key name } }
          }
        }
        """,
        {"teamId": team_id},
    )
    return [exact_match(data["workflowStates"]["nodes"], value, ("id", "name"), "Status") for value in values]


def get_view_by_id_or_slug(client: LinearClient, value: str) -> dict[str, Any] | None:
    data = client.gql(
        f"""
        query View($id: String!) {{
          customView(id: $id) {{
            {VIEW_FIELDS}
          }}
        }}
        """,
        {"id": value},
    )
    return data["customView"]


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


def find_view(client: LinearClient, value: str, team: dict[str, Any] | None) -> dict[str, Any]:
    lookup = view_lookup_key(value)
    direct = get_view_by_id_or_slug(client, lookup)
    if direct:
        return direct

    if not team:
        raise LinearApiError("validation", "--team is required when looking up a Custom View by name.")

    lookup_norm = normalize(lookup)
    matches = [
        view
        for view in list_views(client)
        if normalize(view.get("name") or "") == lookup_norm
        and normalize(((view.get("team") or {}).get("id") or "")) == normalize(team["id"])
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise LinearApiError("not_found", f"Custom View '{value}' was not found.")
    ids = ", ".join(str(view.get("id")) for view in matches)
    raise LinearApiError("ambiguous_lookup", f"Custom View '{value}' is ambiguous: {ids}")


def build_filter_data(labels: list[dict[str, Any]], statuses: list[dict[str, Any]], open_only: bool) -> dict[str, Any]:
    filters: list[dict[str, Any]] = []
    if open_only:
        filters.append({"state": {"type": {"nin": ["completed", "canceled"]}}})
    if statuses:
        filters.append({"state": {"name": {"in": [state["name"] for state in statuses]}}})
    if labels:
        label_options: list[dict[str, Any]] = []
        for label in labels:
            label_options.append({"name": {"eq": label["name"]}})
            label_options.append({"parent": {"name": {"eq": label["name"]}}})
        filters.append({"labels": {"and": [{"or": label_options}]}})
    return {"and": filters} if filters else {}


def filter_update_requested(args: argparse.Namespace) -> bool:
    return bool(args.label or args.status or args.open_only)


def build_update_input(
    client: LinearClient,
    args: argparse.Namespace,
    view: dict[str, Any],
    team: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    project = resolve_project(client, args.project)
    labels = resolve_labels(client, team["id"], args.label)
    statuses = resolve_statuses(client, team["id"], args.status)
    target_filter = build_filter_data(labels, statuses, args.open_only)

    input_data: dict[str, Any] = {}
    if project:
        input_data["projectId"] = project["id"]
    if args.name is not None:
        input_data["name"] = args.name
    if args.description is not None:
        input_data["description"] = args.description
    if args.color is not None:
        input_data["color"] = args.color
    if args.icon is not None:
        input_data["icon"] = args.icon
    if args.private:
        input_data["shared"] = False
    if args.shared:
        input_data["shared"] = True
    if filter_update_requested(args):
        input_data["filterData"] = target_filter

    target = {
        "view": view,
        "team": team,
        "project": project,
        "labels": labels,
        "statuses": statuses,
        "filterData": target_filter if filter_update_requested(args) else view.get("filterData"),
        "filter_changed": filter_update_requested(args),
        "name": input_data.get("name", view.get("name")),
        "shared": input_data.get("shared", view.get("shared")),
    }
    return input_data, target


def update_custom_view(client: LinearClient, args: argparse.Namespace) -> dict[str, Any]:
    resolved_team = resolve_team(client, args.team) if args.team else None
    before = find_view(client, args.view, resolved_team)
    team = resolved_team or (before.get("team") or {})
    if not team.get("id"):
        raise LinearApiError("validation", "The Custom View has no team; pass --team to resolve labels or statuses.")

    input_data, target = build_update_input(client, args, before, team)
    if not input_data:
        raise LinearApiError("validation", "No update fields were provided.")

    if args.dry_run:
        return {
            "action": "dry_run",
            "target": target,
            "before": before,
            "input": input_data,
            "updated": None,
            "verified": before,
        }

    data = client.gql(
        f"""
        mutation UpdateCustomView($id: String!, $input: CustomViewUpdateInput!) {{
          customViewUpdate(id: $id, input: $input) {{
            success
            customView {{
              {VIEW_FIELDS}
            }}
          }}
        }}
        """,
        {"id": before["id"], "input": input_data},
    )
    updated = data["customViewUpdate"]["customView"]
    verified = get_view_by_id_or_slug(client, before["id"])
    return {
        "action": "updated",
        "target": target,
        "before": before,
        "input": input_data,
        "updated": updated,
        "verified": verified,
    }


def emit_text_result(result: dict[str, Any]) -> None:
    view = result["target"]["view"]
    print(f"view={view['name']} slug={view.get('slugId') or '-'}")
    print(f"action={result['action']}")
    labels = ", ".join(label["name"] for label in result["target"].get("labels") or []) or "-"
    statuses = ", ".join(state["name"] for state in result["target"].get("statuses") or []) or "-"
    print(f"labels={labels}")
    print(f"statuses={statuses}")
    print(f"filter_changed={str(result['target'].get('filter_changed')).lower()}")


def main() -> int:
    args = parse_args()
    try:
        client = LinearClient(args.api_url, resolve_api_key(args.env_file))
        result = update_custom_view(client, args)
        result["schema_version"] = "linear-custom-view-update.v1"
        result["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except LinearApiError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": "linear-custom-view-update.error.v1",
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
