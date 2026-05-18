#!/usr/bin/env python3
"""Ensure one Linear issue relation exists through the direct GraphQL API."""

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
  state { id name type }
  team { id key name }
  project { id name }
"""

RELATION_FIELDS = """
  id
  type
  issue { id identifier title }
  relatedIssue { id identifier title }
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ensure one Linear issue relation exists.")
    parser.add_argument("issue", help="Source issue identifier, ID, or URL.")
    parser.add_argument("related_issue", help="Related issue identifier, ID, or URL.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--type", required=True, choices=("related", "blocks", "blocked-by"), help="Relation to ensure.")
    parser.add_argument("--dry-run", action="store_true", help="Resolve the relation without mutating Linear.")
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


def normalize_relation_type(kind: str, issue: dict[str, Any], related_issue: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if kind == "blocked-by":
        return "blocks", related_issue, issue
    return kind, issue, related_issue


def read_issue(client: LinearClient, issue_ref: str) -> dict[str, Any]:
    lookup = issue_lookup_key(issue_ref)
    data = client.gql(
        f"""
        query IssueWithRelations($id: String!) {{
          issue(id: $id) {{
            {ISSUE_FIELDS}
            relations(first: 50) {{
              pageInfo {{ hasNextPage }}
              nodes {{
                {RELATION_FIELDS}
              }}
            }}
          }}
        }}
        """,
        {"id": lookup},
    )
    issue = data.get("issue")
    if not issue:
        raise LinearApiError("not_found", f"Issue '{lookup}' was not found.")
    return issue


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


def relation_matches(relation: dict[str, Any], relation_type: str, source_id: str, target_id: str) -> bool:
    issue_id = ((relation.get("issue") or {}).get("id") or "")
    related_id = ((relation.get("relatedIssue") or {}).get("id") or "")
    if relation.get("type") != relation_type:
        return False
    if relation_type == "related":
        return {issue_id, related_id} == {source_id, target_id}
    return issue_id == source_id and related_id == target_id


def find_relation(issues: list[dict[str, Any]], relation_type: str, source_id: str, target_id: str) -> dict[str, Any] | None:
    for issue in issues:
        relations = ((issue.get("relations") or {}).get("nodes") or [])
        for relation in relations:
            if relation_matches(relation, relation_type, source_id, target_id):
                return relation
    return None


def create_relation(client: LinearClient, input_data: dict[str, Any]) -> dict[str, Any]:
    data = client.gql(
        f"""
        mutation CreateIssueRelation($input: IssueRelationCreateInput!) {{
          issueRelationCreate(input: $input) {{
            success
            issueRelation {{
              {RELATION_FIELDS}
            }}
          }}
        }}
        """,
        {"input": input_data},
    )
    return data["issueRelationCreate"]["issueRelation"]


def setup_relation(client: LinearClient, args: argparse.Namespace) -> dict[str, Any]:
    left = read_issue(client, args.issue)
    right = read_issue(client, args.related_issue)
    relation_type, source, target = normalize_relation_type(args.type, left, right)
    existing = find_relation([left, right], relation_type, source["id"], target["id"])
    input_data = {
        "type": relation_type,
        "issueId": source["id"],
        "relatedIssueId": target["id"],
    }
    target_data = {
        "requested_type": args.type,
        "type": relation_type,
        "issue": compact_issue(left),
        "related_issue": compact_issue(right),
        "source": compact_issue(source),
        "target": compact_issue(target),
    }
    before = {
        "issue": left,
        "related_issue": right,
        "existing_relation": existing,
    }

    if existing:
        return {
            "action": "exists",
            "target": target_data,
            "before": before,
            "input": input_data,
            "created": None,
            "verified": existing,
        }

    if args.dry_run:
        return {
            "action": "dry_run",
            "target": target_data,
            "before": before,
            "input": input_data,
            "created": None,
            "verified": None,
        }

    created = create_relation(client, input_data)
    verified_left = read_issue(client, left["identifier"])
    verified_right = read_issue(client, right["identifier"])
    verified = find_relation([verified_left, verified_right], relation_type, source["id"], target["id"])
    if not verified:
        raise LinearApiError("validation", "Created relation was not found after mutation.")
    return {
        "action": "created",
        "target": target_data,
        "before": before,
        "input": input_data,
        "created": created,
        "verified": verified,
    }


def emit_text_result(result: dict[str, Any]) -> None:
    target = result["target"]
    print(f"issue={target['issue']['identifier']} related_issue={target['related_issue']['identifier']}")
    print(f"requested_type={target['requested_type']} type={target['type']}")
    print(f"action={result['action']}")
    print(f"source={target['source']['identifier']} target={target['target']['identifier']}")


def main() -> int:
    args = parse_args()
    try:
        client = LinearClient(args.api_url, resolve_api_key(args.env_file))
        result = setup_relation(client, args)
        result["schema_version"] = "linear-relation-setup.v1"
        result["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except LinearApiError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": "linear-relation-setup.error.v1",
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
