#!/usr/bin/env python3
"""Add one comment to a Linear issue through the direct GraphQL API."""

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
    parser = argparse.ArgumentParser(description="Add one comment to a Linear issue.")
    parser.add_argument("issue", help="Linear issue identifier, ID, or issue URL.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--body", help="Comment body.")
    parser.add_argument("--body-file", help="Path to a UTF-8 Markdown comment body file.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve the issue without creating a comment.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    args = parser.parse_args()
    if bool(args.body) == bool(args.body_file):
        parser.error("exactly one of --body or --body-file is required")
    return args


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


def read_body(args: argparse.Namespace) -> str:
    if args.body is not None:
        body = args.body
    else:
        path = Path(args.body_file).expanduser()
        try:
            body = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise LinearApiError("not_found", f"Comment body file cannot be read: {path}") from exc
    if not body.strip():
        raise LinearApiError("validation", "Comment body must not be empty.")
    return body


ISSUE_FIELDS = """
  id
  identifier
  title
  url
  state { id name type }
  team { id key name }
  project { id name }
"""


COMMENT_FIELDS = """
  id
  body
  createdAt
  updatedAt
  user { id name }
  issue {
    id
    identifier
    title
    url
  }
"""


def compact_issue(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": issue.get("id"),
        "identifier": issue.get("identifier"),
        "title": issue.get("title"),
        "url": issue.get("url"),
        "state": issue.get("state"),
        "team": issue.get("team"),
        "project": issue.get("project"),
    }


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
    return compact_issue(issue)


def comment_issue(client: LinearClient, issue_ref: str, body: str, dry_run: bool) -> dict[str, Any]:
    issue = read_issue(client, issue_ref)
    if dry_run:
        return {
            "action": "dry_run",
            "target": issue,
            "comment": None,
            "verified": issue,
        }

    data = client.gql(
        f"""
        mutation CreateComment($input: CommentCreateInput!) {{
          commentCreate(input: $input) {{
            success
            comment {{
              {COMMENT_FIELDS}
            }}
          }}
        }}
        """,
        {"input": {"issueId": issue["id"], "body": body}},
    )
    comment = data["commentCreate"]["comment"]
    verified = read_issue(client, issue["id"])
    return {
        "action": "commented",
        "target": issue,
        "comment": comment,
        "verified": verified,
    }


def build_result(client: LinearClient, args: argparse.Namespace) -> dict[str, Any]:
    body = read_body(args)
    result = comment_issue(client, args.issue, body, dry_run=args.dry_run)
    result["schema_version"] = "linear-comment-issue.v1"
    result["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return result


def emit_text_result(result: dict[str, Any]) -> None:
    target = result["target"]
    print(f"issue={target['identifier']} status={(target.get('state') or {}).get('name')}")
    print(f"title={target['title']}")
    if result["action"] == "dry_run":
        print("dry_run=true")
        return
    comment = result["comment"]
    print(f"commented=true comment={comment['id']}")


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
                        "schema_version": "linear-comment-issue.error.v1",
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

