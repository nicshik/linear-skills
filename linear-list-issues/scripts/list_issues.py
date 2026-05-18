#!/usr/bin/env python3
"""Read Linear issues with checked filters through the direct GraphQL API."""

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
  url
  priority
  updatedAt
  state { id name type }
  team { id key name }
  project { id name }
  assignee { id name displayName }
  parent { id identifier title }
  labels { nodes { id name } }
"""

OPEN_STATE_TYPES = {"backlog", "unstarted", "started", "triage"}
CLOSED_STATE_TYPES = {"completed", "canceled", "cancelled"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read Linear issues with checked filters.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--team", help="Target team key, ID, or exact name.")
    parser.add_argument("--project", help="Target project ID or exact name.")
    parser.add_argument("--open-only", action="store_true", help="Return only non-completed issues.")
    parser.add_argument("--status", help="Workflow state ID, exact name, or type.")
    parser.add_argument("--assignee", help="Assignee user ID, exact name, display name, or email.")
    parser.add_argument("--parent", help="Parent issue key, ID, or URL.")
    parser.add_argument("--label", action="append", default=[], help="Require this label. Can be repeated.")
    parser.add_argument("--exclude-label", action="append", default=[], help="Exclude this label. Can be repeated.")
    parser.add_argument("--missing-label", action="append", default=[], help="Require at least one listed label to be missing. Can be repeated.")
    parser.add_argument("--without-labels", action="store_true", help="Return only issues with no labels.")
    parser.add_argument("--limit", type=int, default=100, help="Max matching issues to return.")
    parser.add_argument("--page-size", type=int, default=50, help="Linear API page size, max 250.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.page_size < 1:
        parser.error("--page-size must be at least 1")
    return args


def normalize(value: str) -> str:
    return value.casefold().strip()


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
    names = ", ".join(str(match.get("name") or match.get("key") or match.get("identifier") or match.get("id")) for match in matches)
    raise LinearApiError("ambiguous_lookup", f"{kind} '{value}' is ambiguous: {names}")


def resolve_team(client: LinearClient, value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
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


def resolve_state(client: LinearClient, team_id: str | None, value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    if team_id:
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
    else:
        data = client.gql(
            """
            query States {
              workflowStates(first: 250) {
                nodes { id name type }
              }
            }
            """
        )
    return exact_match(data["workflowStates"]["nodes"], value, ("id", "name", "type"), "Workflow state")


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


def resolve_issue(client: LinearClient, value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    lookup = issue_lookup_key(value)
    data = client.gql(
        """
        query ParentIssue($id: String!) {
          issue(id: $id) {
            id
            identifier
            title
            url
          }
        }
        """,
        {"id": lookup},
    )
    issue = data.get("issue")
    if not issue:
        raise LinearApiError("not_found", f"Parent issue '{lookup}' was not found.")
    return issue


def compact_issue(issue: dict[str, Any]) -> dict[str, Any]:
    labels = issue.get("labels") or {}
    return {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "url": issue.get("url"),
        "priority": issue.get("priority"),
        "updatedAt": issue.get("updatedAt"),
        "state": issue.get("state"),
        "team": issue.get("team"),
        "project": issue.get("project"),
        "assignee": issue.get("assignee"),
        "parent": issue.get("parent"),
        "labels": [node["name"] for node in labels.get("nodes", []) if node.get("name")],
    }


def compact_user(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user:
        return None
    return {
        "id": user.get("id"),
        "name": user.get("name"),
        "displayName": user.get("displayName"),
    }


def build_server_filter(
    team: dict[str, Any] | None,
    project: dict[str, Any] | None,
    state: dict[str, Any] | None,
    assignee: dict[str, Any] | None,
    parent: dict[str, Any] | None,
) -> dict[str, Any]:
    filter_data: dict[str, Any] = {}
    if team:
        filter_data["team"] = {"id": {"eq": team["id"]}}
    if project:
        filter_data["project"] = {"id": {"eq": project["id"]}}
    if state:
        filter_data["state"] = {"id": {"eq": state["id"]}}
    if assignee:
        filter_data["assignee"] = {"id": {"eq": assignee["id"]}}
    if parent:
        filter_data["parent"] = {"id": {"eq": parent["id"]}}
    return filter_data


def label_set(issue: dict[str, Any]) -> set[str]:
    return {normalize(label) for label in issue.get("labels", [])}


def is_open_issue(issue: dict[str, Any]) -> bool:
    state_type = normalize(((issue.get("state") or {}).get("type") or ""))
    if state_type in CLOSED_STATE_TYPES:
        return False
    if state_type in OPEN_STATE_TYPES:
        return True
    return state_type not in CLOSED_STATE_TYPES


def passes_client_filters(issue: dict[str, Any], args: argparse.Namespace) -> bool:
    labels = label_set(issue)
    required_labels = {normalize(label) for label in args.label}
    excluded_labels = {normalize(label) for label in args.exclude_label}
    missing_labels = {normalize(label) for label in args.missing_label}

    if args.open_only and not is_open_issue(issue):
        return False
    if args.without_labels and labels:
        return False
    if required_labels and not required_labels.issubset(labels):
        return False
    if excluded_labels and excluded_labels.intersection(labels):
        return False
    if missing_labels and missing_labels.issubset(labels):
        return False
    return True


def fetch_matching_issues(
    client: LinearClient,
    args: argparse.Namespace,
    server_filter: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int], bool]:
    matched: list[dict[str, Any]] = []
    fetched = 0
    skipped = 0
    has_more = False
    after: str | None = None
    page_size = min(args.page_size, 250)

    while len(matched) < args.limit:
        data = client.gql(
            f"""
            query Issues($first: Int!, $after: String, $filter: IssueFilter) {{
              issues(first: $first, after: $after, filter: $filter) {{
                pageInfo {{
                  hasNextPage
                  endCursor
                }}
                nodes {{
                  {ISSUE_FIELDS}
                }}
              }}
            }}
            """,
            {"first": page_size, "after": after, "filter": server_filter or None},
        )
        connection = data["issues"]
        nodes = connection["nodes"]
        fetched += len(nodes)

        for node in nodes:
            compacted = compact_issue(node)
            if passes_client_filters(compacted, args):
                matched.append(compacted)
                if len(matched) >= args.limit:
                    has_more = connection["pageInfo"]["hasNextPage"] or node is not nodes[-1]
                    break
            else:
                skipped += 1

        if len(matched) >= args.limit:
            break
        if not connection["pageInfo"]["hasNextPage"]:
            break
        after = connection["pageInfo"]["endCursor"]

    counts = {"fetched": fetched, "matched": len(matched), "skipped": skipped}
    return matched, counts, has_more


def build_result(client: LinearClient, args: argparse.Namespace) -> dict[str, Any]:
    team = resolve_team(client, args.team)
    project = resolve_project(client, args.project)
    state = resolve_state(client, team["id"] if team else None, args.status)
    assignee = resolve_user(client, args.assignee)
    parent = resolve_issue(client, args.parent)
    server_filter = build_server_filter(team, project, state, assignee, parent)
    issues, counts, has_more = fetch_matching_issues(client, args, server_filter)

    return {
        "schema_version": "linear-list-issues.v1",
        "target": {
            "team": team,
            "project": project,
            "status": state,
            "assignee": compact_user(assignee),
            "parent": parent,
        },
        "filters": {
            "open_only": args.open_only,
            "labels": args.label,
            "exclude_labels": args.exclude_label,
            "missing_labels": args.missing_label,
            "without_labels": args.without_labels,
            "limit": args.limit,
            "page_size": min(args.page_size, 250),
            "server_filter": server_filter,
        },
        "issues": issues,
        "counts": counts,
        "has_more": has_more,
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def emit_text_result(result: dict[str, Any]) -> None:
    counts = result["counts"]
    print(f"matched={counts['matched']} fetched={counts['fetched']} skipped={counts['skipped']} has_more={str(result['has_more']).lower()}")
    for issue in result["issues"]:
        labels = ", ".join(issue.get("labels") or []) or "-"
        state = issue.get("state") or {}
        project = issue.get("project") or {}
        print(
            f"{issue['identifier']} state={state.get('name') or '-'} "
            f"project={project.get('name') or '-'} labels={labels} title={issue['title']}"
        )


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
                        "schema_version": "linear-list-issues.error.v1",
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
