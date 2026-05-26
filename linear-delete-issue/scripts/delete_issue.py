#!/usr/bin/env python3
"""Soft-delete one Linear issue through the direct GraphQL API."""

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
from linear_common.issue_refs import is_issue_entity_not_found_message, issue_not_found_details, parse_issue_reference


ISSUE_FIELDS = """
  id
  identifier
  title
  url
  priority
  createdAt
  updatedAt
  completedAt
  archivedAt
  trashed
  state { id name type }
  team { id key name }
  project { id name }
  assignee { id name displayName email }
  parent { id identifier title state { name type } }
  labels { nodes { id name } }
  children(first: 50) {
    pageInfo { hasNextPage }
    nodes { id identifier title state { name type } }
  }
  comments(first: 50) {
    pageInfo { hasNextPage }
    nodes { id createdAt updatedAt user { name } }
  }
  relations(first: 50) {
    pageInfo { hasNextPage }
    nodes {
      id
      type
      relatedIssue { id identifier title state { name type } }
    }
  }
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Soft-delete one Linear issue after checked guards.")
    parser.add_argument("issue", help="Linear issue identifier, ID, or issue URL.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--confirm", help="Required for live deletion; must equal the resolved issue identifier.")
    parser.add_argument("--expect-status", action="append", default=[], help="Allowed status name. Can be repeated.")
    parser.add_argument("--forbid-label", action="append", default=[], help="Label name that blocks deletion. Can be repeated.")
    parser.add_argument("--require-no-children", action="store_true", help="Block deletion if visible child issues exist.")
    parser.add_argument("--require-no-relations", action="store_true", help="Block deletion if visible issue relations exist.")
    parser.add_argument("--require-no-comments", action="store_true", help="Block deletion if visible comments exist.")
    parser.add_argument("--dry-run", action="store_true", help="Read and validate without mutating Linear.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    return parser.parse_args()


def issue_lookup_key(value: str) -> str:
    return parse_issue_reference(value).lookup


def normalize(value: str | None) -> str:
    return (value or "").casefold().strip()


def summarize_connection(connection: dict[str, Any] | None) -> dict[str, Any]:
    connection = connection or {}
    nodes = connection.get("nodes") or []
    return {
        "visible_count": len(nodes),
        "has_more": bool((connection.get("pageInfo") or {}).get("hasNextPage")),
    }


def normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    compact = dict(issue)
    labels = compact.pop("labels", None) or {}
    compact["labels"] = [node["name"] for node in labels.get("nodes", []) if node.get("name")]
    compact["label_nodes"] = labels.get("nodes", [])
    compact["children_summary"] = summarize_connection(compact.get("children"))
    compact["comments_summary"] = summarize_connection(compact.get("comments"))
    compact["relations_summary"] = summarize_connection(compact.get("relations"))
    return compact


def read_issue(client: LinearClient, issue_ref: str) -> dict[str, Any]:
    reference = parse_issue_reference(issue_ref)
    try:
        data = client.gql(
            f"""
            query IssueDeleteRead($id: String!) {{
              issue(id: $id) {{
                {ISSUE_FIELDS}
              }}
            }}
            """,
            {"id": reference.lookup},
        )
    except LinearApiError as exc:
        if is_issue_entity_not_found_message(exc.message):
            raise LinearApiError(
                "not_found",
                f"Issue '{reference.lookup}' was not found.",
                issue_not_found_details(reference),
            ) from exc
        raise

    issue = data.get("issue")
    if not issue:
        raise LinearApiError(
            "not_found",
            f"Issue '{reference.lookup}' was not found.",
            issue_not_found_details(reference),
        )
    return normalize_issue(issue)


def status_name(issue: dict[str, Any]) -> str:
    return str((issue.get("state") or {}).get("name") or "")


def visible_count(issue: dict[str, Any], key: str) -> int:
    return int((issue.get(f"{key}_summary") or {}).get("visible_count") or 0)


def has_more(issue: dict[str, Any], key: str) -> bool:
    return bool((issue.get(f"{key}_summary") or {}).get("has_more"))


def check_zero_connection(issue: dict[str, Any], key: str, enabled: bool) -> dict[str, Any]:
    count = visible_count(issue, key)
    more = has_more(issue, key)
    return {
        "name": f"require_no_{key}",
        "enabled": enabled,
        "ok": (not enabled) or (count == 0 and not more),
        "visible_count": count,
        "has_more": more,
    }


def build_guard_checks(issue: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    labels = set(issue.get("labels") or [])
    label_norms = {normalize(label): label for label in labels}
    expected_statuses = [value for value in args.expect_status if value]
    forbidden_labels = [value for value in args.forbid_label if value]

    checks: list[dict[str, Any]] = []
    if expected_statuses:
        checks.append(
            {
                "name": "expect_status",
                "enabled": True,
                "ok": normalize(status_name(issue)) in {normalize(value) for value in expected_statuses},
                "actual": status_name(issue),
                "expected": expected_statuses,
            }
        )

    for label in forbidden_labels:
        checks.append(
            {
                "name": "forbid_label",
                "enabled": True,
                "ok": normalize(label) not in label_norms,
                "label": label,
                "matched": label_norms.get(normalize(label)),
            }
        )

    checks.append(check_zero_connection(issue, "children", args.require_no_children))
    checks.append(check_zero_connection(issue, "relations", args.require_no_relations))
    checks.append(check_zero_connection(issue, "comments", args.require_no_comments))
    return checks


def validate_before_delete(issue: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    checks = build_guard_checks(issue, args)
    failed = [check for check in checks if check.get("enabled") and not check.get("ok")]
    if failed:
        names = ", ".join(str(check["name"]) for check in failed)
        raise LinearApiError("validation", f"Deletion guard failed: {names}.", {"failed_checks": failed})
    return checks


def validate_confirm(issue: dict[str, Any], confirm: str | None) -> None:
    identifier = str(issue.get("identifier") or "")
    if not confirm:
        raise LinearApiError("validation", f"Live deletion requires --confirm {identifier}.")
    if normalize(confirm) != normalize(identifier):
        raise LinearApiError(
            "validation",
            f"--confirm must match resolved issue identifier '{identifier}', got '{confirm}'.",
        )


def delete_mutation(client: LinearClient, issue_id: str) -> dict[str, Any]:
    data = client.gql(
        """
        mutation DeleteIssue($id: String!, $permanentlyDelete: Boolean) {
          issueDelete(id: $id, permanentlyDelete: $permanentlyDelete) {
            success
            lastSyncId
            entity {
              id
              identifier
              title
              url
              trashed
              archivedAt
              state { id name type }
            }
          }
        }
        """,
        {"id": issue_id, "permanentlyDelete": False},
    )
    payload = data.get("issueDelete") or {}
    if not payload.get("success"):
        raise LinearApiError("network", "Linear issueDelete mutation did not report success.", {"payload": payload})
    return payload


def verify_after_delete(client: LinearClient, before: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return read_issue(client, str(before["id"]))
    except LinearApiError as exc:
        if exc.category == "not_found" or is_issue_entity_not_found_message(exc.message):
            return None
        raise


def delete_issue(client: LinearClient, args: argparse.Namespace) -> dict[str, Any]:
    before = read_issue(client, args.issue)
    if before.get("trashed"):
        return {
            "action": "already_deleted",
            "before": before,
            "guard_checks": build_guard_checks(before, args),
            "deleted": None,
            "verified": before,
            "verification_status": "already_trashed",
        }

    guard_checks = validate_before_delete(before, args)
    if args.dry_run:
        return {
            "action": "dry_run",
            "before": before,
            "guard_checks": guard_checks,
            "deleted": None,
            "verified": before,
            "verification_status": "not_mutated",
        }

    validate_confirm(before, args.confirm)
    deleted = delete_mutation(client, str(before["id"]))
    verified = verify_after_delete(client, before)
    return {
        "action": "deleted",
        "before": before,
        "guard_checks": guard_checks,
        "deleted": deleted,
        "verified": verified,
        "verification_status": "read_back" if verified else "not_found_after_delete",
    }


def emit_text_result(result: dict[str, Any]) -> None:
    before = result["before"]
    print(f"issue={before['identifier']} title={before['title']}")
    print(f"action={result['action']}")
    print(f"status={status_name(before)}")
    print(f"labels={', '.join(before.get('labels') or []) or '-'}")
    print(f"verification_status={result.get('verification_status')}")


def main() -> int:
    args = parse_args()
    try:
        client = LinearClient(args.api_url, resolve_api_key(args.env_file))
        result = delete_issue(client, args)
        result["schema_version"] = "linear-delete-issue.v1"
        result["fetched_at"] = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except LinearApiError as exc:
        payload = {
            "schema_version": "linear-delete-issue.error.v1",
            "error_category": exc.category,
            "error": exc.message,
        }
        payload.update(exc.details)
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
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
