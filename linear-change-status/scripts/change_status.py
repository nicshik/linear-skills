#!/usr/bin/env python3
"""Change a Linear issue status through the direct GraphQL API."""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.linear.app/graphql"
ENV_KEY = "LINEAR_API_KEY"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Change a Linear issue workflow state.")
    parser.add_argument("issue", help="Linear issue identifier or ID, for example FCT-9.")
    parser.add_argument("status", help="Target workflow state name or type, for example Done.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--dry-run", action="store_true", help="Read and resolve the transition without updating.")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON.")
    return parser.parse_args()


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return values

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def candidate_env_files(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    if args.env_file:
        paths.append(Path(args.env_file).expanduser())
    if os.environ.get("LINEAR_ENV_FILE"):
        paths.append(Path(os.environ["LINEAR_ENV_FILE"]).expanduser())

    cwd = Path.cwd()
    for base in [cwd, *cwd.parents]:
        paths.extend([base / ".env.local", base / ".env"])

    paths.extend(
        [
            cwd / "FactorixMarket" / "app" / ".env.local",
            cwd / "app" / ".env.local",
        ]
    )

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve() if path.exists() else path
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(path)
    return deduped


def resolve_api_key(args: argparse.Namespace) -> str:
    token = os.environ.get(ENV_KEY)
    if token:
        return token

    for path in candidate_env_files(args):
        values = parse_env_file(path)
        token = values.get(ENV_KEY)
        if token:
            return token

    raise SystemExit(
        "LINEAR_API_KEY was not found in the environment, LINEAR_ENV_FILE, --env-file, "
        "or local .env files."
    )


class LinearClient:
    def __init__(self, api_url: str, token: str) -> None:
        self.api_url = api_url
        self.token = token

    def gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        request = urllib.request.Request(
            self.api_url,
            data=body,
            method="POST",
            headers={
                "Authorization": self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, context=build_ssl_context()) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"Linear API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise SystemExit(f"Linear API request failed: {exc.reason}") from exc

        if payload.get("errors"):
            raise SystemExit(json.dumps(payload["errors"], ensure_ascii=False, indent=2))
        return payload["data"]


def build_ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore[import-not-found]

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def normalize(value: str) -> str:
    return value.casefold().strip()


def find_target_state(states: list[dict[str, Any]], requested: str) -> dict[str, Any]:
    requested_norm = normalize(requested)
    for state in states:
        if normalize(state["name"]) == requested_norm:
            return state
    for state in states:
        if normalize(state["type"]) == requested_norm:
            return state
    available = ", ".join(f"{state['name']} ({state['type']})" for state in states)
    raise SystemExit(f"Target state '{requested}' was not found. Available states: {available}")


def compact_state(state: dict[str, Any]) -> dict[str, str]:
    return {"id": state["id"], "name": state["name"], "type": state["type"]}


def main() -> int:
    args = parse_args()
    client = LinearClient(args.api_url, resolve_api_key(args))

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
        {"id": args.issue},
    )
    issue = issue_data.get("issue")
    if not issue:
        raise SystemExit(f"Issue '{args.issue}' was not found.")

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
    target_state = find_target_state(states_data["workflowStates"]["nodes"], args.status)
    before_state = issue["state"]

    changed = compact_state(before_state)["id"] != compact_state(target_state)["id"]
    action = "dry_run" if args.dry_run else "noop"
    updated_issue = issue

    if changed and not args.dry_run:
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
        {"id": args.issue},
    )
    verified_issue = verify_data["issue"]

    result = {
        "issue": {"id": issue["id"], "identifier": issue["identifier"], "title": issue["title"]},
        "before": compact_state(before_state),
        "target": compact_state(target_state),
        "changed": changed and not args.dry_run,
        "action": action,
        "updated": {
            "state": compact_state(updated_issue["state"]),
            "completed_at": updated_issue.get("completedAt"),
        },
        "verified": {
            "state": compact_state(verified_issue["state"]),
            "completed_at": verified_issue.get("completedAt"),
        },
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"before={issue['identifier']}:{before_state['name']}:{before_state['type']}")
        print(f"target={target_state['name']}:{target_state['type']}")
        if action == "updated":
            print(
                f"updated=true:{issue['identifier']}:{updated_issue['state']['name']}:"
                f"{updated_issue['state']['type']}:completedAt={updated_issue.get('completedAt') or 'null'}"
            )
        elif action == "dry_run":
            print(f"dry_run=true:{issue['identifier']}:{target_state['name']}:{target_state['type']}")
        else:
            print(f"noop=true:{issue['identifier']} is already {target_state['name']}")
        print(
            f"verify={verified_issue['identifier']}:{verified_issue['state']['name']}:"
            f"{verified_issue['state']['type']}:completedAt={verified_issue.get('completedAt') or 'null'}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
