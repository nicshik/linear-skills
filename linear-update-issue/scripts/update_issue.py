#!/usr/bin/env python3
"""Update one existing Linear issue through the direct GraphQL API."""

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


ISSUE_FIELDS = """
  id
  identifier
  title
  description
  url
  priority
  state { id name type }
  team { id key name }
  project { id name }
  assignee { id name displayName email }
  parent { id identifier title }
  labels { nodes { id name } }
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update one existing Linear issue.")
    parser.add_argument("issue", help="Linear issue identifier, ID, or issue URL.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--add-label", action="append", default=[], help="Label name or ID to add. Can be repeated.")
    parser.add_argument("--remove-label", action="append", default=[], help="Label name or ID to remove. Can be repeated.")
    parser.add_argument("--assignee", help="Assignee user ID, exact name, display name, or email.")
    parser.add_argument("--parent", help="Parent issue key, ID, or URL.")
    parser.add_argument("--title", help="Replacement issue title.")
    parser.add_argument("--priority", help="Replacement issue priority: none, urgent, high, medium/normal, low, or 0..4.")
    parser.add_argument("--sort-order", type=float, help="Replacement manual issue sort order.")
    parser.add_argument("--description-file", help="Path to a UTF-8 Markdown replacement description.")
    parser.add_argument("--append-description-file", help="Path to UTF-8 Markdown to append to the current description.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve the update without mutating Linear.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    args = parser.parse_args()
    if args.description_file and args.append_description_file:
        parser.error("--description-file and --append-description-file cannot be combined")
    return args


def normalize(value: str) -> str:
    return value.casefold().strip()


PRIORITY_VALUES = {
    "none": 0,
    "no-priority": 0,
    "no_priority": 0,
    "0": 0,
    "urgent": 1,
    "1": 1,
    "high": 2,
    "2": 2,
    "medium": 3,
    "normal": 3,
    "3": 3,
    "low": 4,
    "4": 4,
}


def parse_priority(value: str | None) -> int | None:
    if value is None:
        return None
    priority = PRIORITY_VALUES.get(normalize(value))
    if priority is None:
        allowed = "none/no-priority/no_priority/0, urgent/1, high/2, medium/normal/3, low/4"
        raise LinearApiError("validation", f"Priority must be one of: {allowed}.")
    return priority


def issue_lookup_key(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    text = urllib.parse.unquote(parsed.path if parsed.scheme and parsed.netloc else value)
    identifier_match = re.search(r"\b[A-Z][A-Z0-9]+-\d+\b", text, flags=re.IGNORECASE)
    if identifier_match:
        return identifier_match.group(0).upper()
    if parsed.scheme and parsed.netloc:
        path_parts = [part for part in text.split("/") if part]
        if path_parts:
            return path_parts[-1]
    return value.strip()


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
    names = ", ".join(str(match.get("name") or match.get("identifier") or match.get("id")) for match in matches)
    raise LinearApiError("ambiguous_lookup", f"{kind} '{value}' is ambiguous: {names}")


def read_text_file(path_value: str) -> str:
    path = Path(path_value).expanduser()
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LinearApiError("not_found", f"File cannot be read: {path}") from exc


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    labels = issue.get("labels") or {}
    compact = dict(issue)
    compact["labels"] = [node["name"] for node in labels.get("nodes", []) if node.get("name")]
    compact["label_nodes"] = labels.get("nodes", [])
    return compact


def read_issue(client: LinearClient, issue_ref: str) -> dict[str, Any]:
    lookup = issue_lookup_key(issue_ref)
    data = client.gql(
        f"""
        query Issue($id: String!) {{
          issue(id: $id) {{
            {ISSUE_FIELDS}
          }}
        }}
        """,
        {"id": lookup},
    )
    issue = data.get("issue")
    if not issue:
        raise LinearApiError("not_found", f"Issue '{lookup}' was not found.")
    return normalize_issue(issue)


def list_labels(client: LinearClient, team_id: str) -> list[dict[str, Any]]:
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
    return data["issueLabels"]["nodes"]


def resolve_labels(client: LinearClient, team_id: str, values: list[str]) -> list[dict[str, Any]]:
    if not values:
        return []
    labels = list_labels(client, team_id)
    return [exact_match(labels, value, ("id", "name"), "Label") for value in values]


def resolve_user(client: LinearClient, value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    data = client.gql(
        """
        query Users {
          users(first: 250) {
            nodes { id name displayName email }
          }
        }
        """
    )
    return exact_match(data["users"]["nodes"], value, ("id", "name", "displayName", "email"), "User")


def resolve_parent(client: LinearClient, value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    return read_issue(client, value)


def build_description(existing: str | None, args: argparse.Namespace) -> str | None:
    if args.description_file:
        return read_text_file(args.description_file)
    if args.append_description_file:
        addition = read_text_file(args.append_description_file)
        if existing:
            return existing.rstrip() + "\n\n" + addition.lstrip()
        return addition
    return None


def build_update_input(client: LinearClient, issue: dict[str, Any], args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    team_id = issue["team"]["id"]
    add_labels = resolve_labels(client, team_id, args.add_label)
    remove_labels = resolve_labels(client, team_id, args.remove_label)
    assignee = resolve_user(client, args.assignee)
    parent = resolve_parent(client, args.parent)
    priority = parse_priority(args.priority)
    description = build_description(issue.get("description"), args)

    input_data: dict[str, Any] = {}
    if add_labels:
        input_data["addedLabelIds"] = [label["id"] for label in add_labels]
    if remove_labels:
        input_data["removedLabelIds"] = [label["id"] for label in remove_labels]
    if assignee:
        input_data["assigneeId"] = assignee["id"]
    if parent:
        input_data["parentId"] = parent["id"]
    if args.title:
        input_data["title"] = args.title
    if priority is not None:
        input_data["priority"] = priority
    if args.sort_order is not None:
        input_data["sortOrder"] = args.sort_order
    if description is not None:
        input_data["description"] = description

    target = {
        "issue": issue,
        "add_labels": add_labels,
        "remove_labels": remove_labels,
        "assignee": assignee,
        "parent": parent,
        "title": args.title,
        "priority": priority,
        "sort_order": args.sort_order,
        "description_changed": description is not None,
    }
    return input_data, target


def update_issue(client: LinearClient, args: argparse.Namespace) -> dict[str, Any]:
    before = read_issue(client, args.issue)
    input_data, target = build_update_input(client, before, args)
    if not input_data:
        raise LinearApiError("validation", "No update fields were provided.")

    if args.dry_run:
        return {
            "action": "dry_run",
            "target": target,
            "input": input_data,
            "updated": None,
            "verified": before,
        }

    data = client.gql(
        f"""
        mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {{
          issueUpdate(id: $id, input: $input) {{
            success
            issue {{
              {ISSUE_FIELDS}
            }}
          }}
        }}
        """,
        {"id": before["id"], "input": input_data},
    )
    updated = normalize_issue(data["issueUpdate"]["issue"])
    verified = read_issue(client, before["identifier"])
    return {
        "action": "updated",
        "target": target,
        "input": input_data,
        "updated": updated,
        "verified": verified,
    }


def emit_text_result(result: dict[str, Any]) -> None:
    issue = result["target"]["issue"]
    print(f"issue={issue['identifier']} title={issue['title']}")
    print(f"action={result['action']}")
    add_labels = ", ".join(label["name"] for label in result["target"]["add_labels"]) or "-"
    remove_labels = ", ".join(label["name"] for label in result["target"]["remove_labels"]) or "-"
    print(f"add_labels={add_labels}")
    print(f"remove_labels={remove_labels}")
    if result["target"].get("assignee"):
        print(f"assignee={result['target']['assignee'].get('name')}")
    if result["target"].get("parent"):
        print(f"parent={result['target']['parent'].get('identifier')}")
    if result["target"].get("priority") is not None:
        print(f"priority={result['target']['priority']}")
    if result["target"].get("sort_order") is not None:
        print(f"sort_order={result['target']['sort_order']}")


def main() -> int:
    args = parse_args()
    try:
        client = LinearClient(args.api_url, resolve_api_key(args.env_file))
        result = update_issue(client, args)
        result["schema_version"] = "linear-update-issue.v1"
        result["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except LinearApiError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": "linear-update-issue.error.v1",
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
