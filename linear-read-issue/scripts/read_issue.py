#!/usr/bin/env python3
"""Read a Linear issue through the direct GraphQL API."""

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read a Linear issue by key, ID, or URL.")
    parser.add_argument("issue", help="Linear issue identifier, ID, or issue URL.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--include-comments", action="store_true", help="Include the first 50 comments.")
    parser.add_argument("--include-relations", action="store_true", help="Include the first 50 issue relations.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    return parser.parse_args()


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


def issue_query(include_comments: bool, include_relations: bool) -> str:
    comments = ""
    if include_comments:
        comments = """
            comments(first: 50) {
              pageInfo { hasNextPage }
              nodes {
                id
                body
                createdAt
                updatedAt
                user { name }
              }
            }
        """

    relations = ""
    if include_relations:
        relations = """
            relations(first: 50) {
              pageInfo { hasNextPage }
              nodes {
                id
                type
                relatedIssue {
                  id
                  identifier
                  title
                  state { name type }
                }
              }
            }
        """

    return f"""
        query IssueRead($id: String!) {{
          issue(id: $id) {{
            id
            identifier
            title
            description
            url
            priority
            createdAt
            updatedAt
            completedAt
            state {{ id name type }}
            team {{ id key name }}
            project {{ id name }}
            assignee {{ id name }}
            creator {{ id name }}
            labels {{ nodes {{ id name }} }}
            parent {{
              id
              identifier
              title
              state {{ name type }}
            }}
            children(first: 50) {{
              pageInfo {{ hasNextPage }}
              nodes {{
                id
                identifier
                title
                state {{ name type }}
              }}
            }}
            {comments}
            {relations}
          }}
        }}
    """


READ_ISSUE_QUERY = issue_query(include_comments=True, include_relations=True)


def summarize_connection(connection: dict[str, Any] | None) -> dict[str, Any]:
    connection = connection or {}
    nodes = connection.get("nodes") or []
    return {
        "visible_count": len(nodes),
        "has_more": bool((connection.get("pageInfo") or {}).get("hasNextPage")),
    }


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    labels = issue.pop("labels", None) or {}
    issue["labels"] = [node["name"] for node in labels.get("nodes", []) if node.get("name")]
    if "children" in issue:
        issue["children_summary"] = summarize_connection(issue["children"])
    if "comments" in issue:
        issue["comments_summary"] = summarize_connection(issue["comments"])
    if "relations" in issue:
        issue["relations_summary"] = summarize_connection(issue["relations"])
    return issue


def read_issue(
    client: LinearClient,
    issue_ref: str,
    include_comments: bool,
    include_relations: bool,
) -> dict[str, Any]:
    lookup = issue_lookup_key(issue_ref)
    data = client.gql(
        issue_query(include_comments=include_comments, include_relations=include_relations),
        {"id": lookup},
    )
    issue = data.get("issue")
    if not issue:
        raise LinearApiError("not_found", f"Issue '{lookup}' was not found.")
    return normalize_issue(issue)


def emit_text_result(result: dict[str, Any]) -> None:
    issue = result["issue"]
    state = issue.get("state") or {}
    team = issue.get("team") or {}
    project = issue.get("project") or {}
    labels = ", ".join(issue.get("labels") or []) or "-"
    print(f"issue={issue['identifier']} status={state.get('name')} type={state.get('type')}")
    print(f"title={issue['title']}")
    print(f"team={team.get('key') or '-'} project={project.get('name') or '-'}")
    print(f"labels={labels}")
    if "comments_summary" in issue:
        summary = issue["comments_summary"]
        print(f"comments={summary['visible_count']} has_more={str(summary['has_more']).lower()}")
    if "relations_summary" in issue:
        summary = issue["relations_summary"]
        print(f"relations={summary['visible_count']} has_more={str(summary['has_more']).lower()}")


def main() -> int:
    args = parse_args()
    try:
        client = LinearClient(args.api_url, resolve_api_key(args.env_file))
        issue = read_issue(
            client,
            args.issue,
            include_comments=args.include_comments,
            include_relations=args.include_relations,
        )
    except LinearApiError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": "linear-read-issue.error.v1",
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

    result = {
        "schema_version": "linear-read-issue.v1",
        "fetched_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "lookup": issue_lookup_key(args.issue),
        "issue": issue,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        emit_text_result(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())

