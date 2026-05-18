#!/usr/bin/env python3
"""Change a Linear issue status through the direct GraphQL API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from linear_common.graphql import API_URL, LinearApiError, LinearClient, resolve_api_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Change a Linear issue workflow state.")
    parser.add_argument("issue", nargs="?", help="Linear issue identifier or ID, for example LIN-123.")
    parser.add_argument("status", nargs="?", help="Target workflow state name or type, for example Done.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--dry-run", action="store_true", help="Read and resolve the transition without updating.")
    parser.add_argument(
        "--batch-file",
        help="Process one issue per line. Lines can be JSON objects or tab-separated issue/status pairs.",
    )
    parser.add_argument(
        "--apply-batch",
        action="store_true",
        help="Allow --batch-file to update Linear. Without this flag, batch mode is dry-run only.",
    )
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    args = parser.parse_args()
    if args.batch_file:
        if args.issue or args.status:
            parser.error("--batch-file cannot be combined with positional issue/status arguments")
    elif not args.issue or not args.status:
        parser.error("issue and status are required unless --batch-file is used")
    return args


class LinearToolError(LinearApiError):
    pass


def normalize(value: str) -> str:
    return value.casefold().strip()


def find_target_state(states: list[dict[str, Any]], requested: str) -> dict[str, Any]:
    requested_norm = normalize(requested)
    exact_name = [state for state in states if normalize(state["name"]) == requested_norm]
    if len(exact_name) == 1:
        return exact_name[0]
    if len(exact_name) > 1:
        names = ", ".join(f"{state['name']} ({state['type']})" for state in exact_name)
        raise LinearToolError("ambiguous_status", f"Target state '{requested}' is ambiguous: {names}")

    exact_type = [state for state in states if normalize(state["type"]) == requested_norm]
    if len(exact_type) == 1:
        return exact_type[0]
    if len(exact_type) > 1:
        names = ", ".join(f"{state['name']} ({state['type']})" for state in exact_type)
        raise LinearToolError("ambiguous_status", f"Target status type '{requested}' is ambiguous: {names}")

    available = ", ".join(f"{state['name']} ({state['type']})" for state in states)
    raise LinearToolError("ambiguous_status", f"Target state '{requested}' was not found. Available states: {available}")


def compact_state(state: dict[str, Any]) -> dict[str, str]:
    return {"id": state["id"], "name": state["name"], "type": state["type"]}


def change_issue_status(client: LinearClient, issue_id: str, requested_status: str, dry_run: bool) -> dict[str, Any]:
    issue_data = client.gql(
        """
        query Issue($id: String!) {
          issue(id: $id) {
            id
            identifier
            title
            completedAt
            state { id name type }
            team { id key name }
          }
        }
        """,
        {"id": issue_id},
    )
    issue = issue_data.get("issue")
    if not issue:
        raise LinearToolError("not_found", f"Issue '{issue_id}' was not found.")

    states_data = client.gql(
        """
        query States($teamId: ID!) {
          workflowStates(filter: { team: { id: { eq: $teamId } } }) {
            nodes { id name type }
          }
        }
        """,
        {"teamId": issue["team"]["id"]},
    )
    target_state = find_target_state(states_data["workflowStates"]["nodes"], requested_status)
    before_state = issue["state"]

    changed = compact_state(before_state)["id"] != compact_state(target_state)["id"]
    action = "dry_run" if dry_run else "noop"
    updated_issue = issue

    if changed and not dry_run:
        update_data = client.gql(
            """
            mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
              issueUpdate(id: $id, input: $input) {
                success
                issue {
                  id
                  identifier
                  title
                  completedAt
                  state { id name type }
                }
              }
            }
            """,
            {"id": issue["id"], "input": {"stateId": target_state["id"]}},
        )
        updated_issue = update_data["issueUpdate"]["issue"]
        action = "updated"

    verify_data = client.gql(
        """
        query Verify($id: String!) {
          issue(id: $id) {
            id
            identifier
            title
            completedAt
            state { id name type }
          }
        }
        """,
        {"id": issue_id},
    )
    verified_issue = verify_data["issue"]

    return {
        "issue": {"id": issue["id"], "identifier": issue["identifier"], "title": issue["title"]},
        "before": compact_state(before_state),
        "target": compact_state(target_state),
        "changed": changed and not dry_run,
        "action": action,
        "error_category": "already_in_target" if action == "noop" else None,
        "updated": {
            "state": compact_state(updated_issue["state"]),
            "completed_at": updated_issue.get("completedAt"),
        },
        "verified": {
            "state": compact_state(verified_issue["state"]),
            "completed_at": verified_issue.get("completedAt"),
        },
    }


def parse_batch_file(path: Path) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LinearToolError("not_found", f"Batch file cannot be read: {path}") from exc

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LinearToolError("ambiguous_status", f"Invalid JSON on batch line {line_number}: {exc}") from exc
            issue = str(payload.get("issue") or payload.get("identifier") or "").strip()
            status = str(payload.get("status") or "").strip()
        else:
            parts = line.split("\t", 1)
            if len(parts) != 2:
                raise LinearToolError(
                    "ambiguous_status",
                    f"Batch line {line_number} must be JSON or tab-separated issue/status",
                )
            issue, status = parts[0].strip(), parts[1].strip()
        if not issue or not status:
            raise LinearToolError("ambiguous_status", f"Batch line {line_number} is missing issue or status")
        pairs.append((issue, status))
    return pairs


def emit_text_result(result: dict[str, Any]) -> None:
    issue = result["issue"]
    before_state = result["before"]
    target_state = result["target"]
    updated = result["updated"]
    verified = result["verified"]
    action = result["action"]

    print(f"before={issue['identifier']}:{before_state['name']}:{before_state['type']}")
    print(f"target={target_state['name']}:{target_state['type']}")
    if action == "updated":
        print(
            f"updated=true:{issue['identifier']}:{updated['state']['name']}:"
            f"{updated['state']['type']}:completedAt={updated.get('completed_at') or 'null'}"
        )
    elif action == "dry_run":
        print(f"dry_run=true:{issue['identifier']}:{target_state['name']}:{target_state['type']}")
    else:
        print(f"noop=true:{issue['identifier']} is already {target_state['name']}")
    print(
        f"verify={issue['identifier']}:{verified['state']['name']}:"
        f"{verified['state']['type']}:completedAt={verified.get('completed_at') or 'null'}"
    )


def main() -> int:
    args = parse_args()
    try:
        client = LinearClient(args.api_url, resolve_api_key(args.env_file))
        if args.batch_file:
            pairs = parse_batch_file(Path(args.batch_file).expanduser())
            dry_run = args.dry_run or not args.apply_batch
            results = [
                change_issue_status(client, issue, status, dry_run=dry_run)
                for issue, status in pairs
            ]
            payload = {
                "schema_version": "linear-change-status.batch.v1",
                "dry_run": dry_run,
                "apply_batch": args.apply_batch,
                "results": results,
            }
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                mode = "dry-run" if dry_run else "apply"
                print(f"batch={mode} count={len(results)}")
                for result in results:
                    print(f"- {result['issue']['identifier']} {result['before']['name']} -> {result['target']['name']} action={result['action']}")
            return 0

        result = change_issue_status(client, args.issue, args.status, dry_run=args.dry_run)
    except LinearApiError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "schema_version": "linear-change-status.error.v1",
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
