#!/usr/bin/env python3
"""Create one Linear issue through the direct GraphQL API."""

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
    parser = argparse.ArgumentParser(description="Create one Linear issue.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--team", required=True, help="Target team key, ID, or exact name.")
    parser.add_argument("--title", required=True, help="Issue title.")
    parser.add_argument("--description", help="Issue description.")
    parser.add_argument("--description-file", help="Path to a UTF-8 Markdown description file.")
    parser.add_argument("--project", help="Target project ID or exact name.")
    parser.add_argument("--status", help="Target workflow state name or type.")
    parser.add_argument("--label", action="append", default=[], help="Required label name. Can be repeated.")
    parser.add_argument("--optional-label", action="append", default=[], help="Optional label name. Missing optional labels are reported and skipped. Can be repeated.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve metadata without creating the issue.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    args = parser.parse_args()
    if args.description and args.description_file:
        parser.error("--description and --description-file cannot be combined")
    return args


def normalize(value: str) -> str:
    return value.casefold().strip()


def read_description(args: argparse.Namespace) -> str | None:
    if args.description is not None:
        return args.description
    if not args.description_file:
        return None
    path = Path(args.description_file).expanduser()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LinearApiError("not_found", f"Description file cannot be read: {path}") from exc


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


def resolve_state(client: LinearClient, team_id: str, value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    data = client.gql(
        """
        query States($teamId: ID!) {
          workflowStates(filter: { team: { id: { eq: $teamId } } }) {
            nodes { id name type }
          }
        }
        """,
        {"teamId": team_id},
    )
    return exact_match(data["workflowStates"]["nodes"], value, ("id", "name", "type"), "Workflow state")


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


def resolve_labels(
    client: LinearClient,
    team_id: str,
    values: list[str],
    optional: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not values:
        return [], []
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
    resolved: list[dict[str, Any]] = []
    skipped: list[str] = []
    for value in values:
        try:
            resolved.append(exact_match(labels, value, ("id", "name"), "Label"))
        except LinearApiError as exc:
            if optional and exc.category == "not_found":
                skipped.append(value)
                continue
            raise
    return resolved, skipped


def compact_issue(issue: dict[str, Any]) -> dict[str, Any]:
    labels = issue.get("labels") or {}
    compacted = {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "url": issue.get("url"),
        "state": issue.get("state"),
        "team": issue.get("team"),
        "project": issue.get("project"),
        "labels": [node["name"] for node in labels.get("nodes", []) if node.get("name")],
    }
    return compacted


ISSUE_FIELDS = """
  id
  identifier
  title
  url
  state { id name type }
  team { id key name }
  project { id name }
  labels { nodes { id name } }
"""


def create_issue(
    client: LinearClient,
    title: str,
    description: str | None,
    team: dict[str, Any],
    state: dict[str, Any] | None,
    project: dict[str, Any] | None,
    labels: list[dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    target = {
        "team": team,
        "state": state,
        "project": project,
        "labels": labels,
        "title": title,
    }
    if dry_run:
        return {
            "action": "dry_run",
            "target": target,
            "created": None,
            "verified": None,
        }

    input_data: dict[str, Any] = {
        "teamId": team["id"],
        "title": title,
    }
    if description:
        input_data["description"] = description
    if state:
        input_data["stateId"] = state["id"]
    if project:
        input_data["projectId"] = project["id"]
    if labels:
        input_data["labelIds"] = [label["id"] for label in labels]

    create_data = client.gql(
        f"""
        mutation CreateIssue($input: IssueCreateInput!) {{
          issueCreate(input: $input) {{
            success
            issue {{
              {ISSUE_FIELDS}
            }}
          }}
        }}
        """,
        {"input": input_data},
    )
    created = create_data["issueCreate"]["issue"]
    verify_data = client.gql(
        f"""
        query Verify($id: String!) {{
          issue(id: $id) {{
            {ISSUE_FIELDS}
          }}
        }}
        """,
        {"id": created["id"]},
    )
    return {
        "action": "created",
        "target": target,
        "created": compact_issue(created),
        "verified": compact_issue(verify_data["issue"]),
    }


def build_result(client: LinearClient, args: argparse.Namespace) -> dict[str, Any]:
    description = read_description(args)
    team = resolve_team(client, args.team)
    state = resolve_state(client, team["id"], args.status)
    project = resolve_project(client, args.project)
    required_labels, _skipped_required_labels = resolve_labels(client, team["id"], args.label)
    optional_labels, skipped_optional_labels = resolve_labels(
        client,
        team["id"],
        args.optional_label,
        optional=True,
    )
    labels = required_labels + optional_labels
    result = create_issue(
        client,
        args.title,
        description,
        team,
        state,
        project,
        labels,
        dry_run=args.dry_run,
    )
    result["skipped_optional_labels"] = skipped_optional_labels
    result["schema_version"] = "linear-create-issue.v1"
    result["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return result


def emit_text_result(result: dict[str, Any]) -> None:
    target = result["target"]
    labels = ", ".join(label["name"] for label in target["labels"]) or "-"
    skipped_optional_labels = ", ".join(result.get("skipped_optional_labels") or []) or "-"
    print(f"team={target['team']['key']}:{target['team']['name']}")
    if target["project"]:
        print(f"project={target['project']['name']}")
    if target["state"]:
        print(f"status={target['state']['name']}:{target['state']['type']}")
    print(f"labels={labels}")
    print(f"skipped_optional_labels={skipped_optional_labels}")
    if result["action"] == "dry_run":
        print("dry_run=true")
        return
    verified = result["verified"]
    print(f"created={verified['identifier']} url={verified.get('url') or '-'}")


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
                        "schema_version": "linear-create-issue.error.v1",
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
