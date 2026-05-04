#!/usr/bin/env python3
"""Read a Linear Custom View and its manually sorted issues."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.linear.app/graphql"
ENV_KEY = "LINEAR_API_KEY"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read a Linear Custom View issue queue.")
    parser.add_argument("view", help="Linear Custom View URL, slugId, ID, or name.")
    parser.add_argument("--env-file", help="Path to a .env file containing LINEAR_API_KEY.")
    parser.add_argument("--api-url", default=API_URL, help="Linear GraphQL API URL.")
    parser.add_argument("--limit", type=int, default=250, help="Maximum issues to return.")
    parser.add_argument(
        "--order",
        choices=("Ascending", "Descending"),
        default="Ascending",
        help="Manual sort order.",
    )
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
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
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

    paths.append(cwd / "app" / ".env.local")

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


def view_lookup_key(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    candidate = parsed.path.rsplit("/", 1)[-1] if parsed.scheme and parsed.netloc else value
    candidate = urllib.parse.unquote(candidate.strip())
    slug_match = re.search(r"([0-9a-f]{8,})$", candidate, flags=re.IGNORECASE)
    if slug_match:
        return slug_match.group(1)
    return candidate


def list_views(client: LinearClient) -> list[dict[str, Any]]:
    data = client.gql(
        """
        query Views {
          customViews(first: 250, includeArchived: false) {
            nodes {
              id
              name
              slugId
              shared
              modelName
              filterData
              team { key name }
              creator { name }
              owner { name }
            }
          }
        }
        """
    )
    return data["customViews"]["nodes"]


def find_view(client: LinearClient, value: str) -> dict[str, Any]:
    lookup = view_lookup_key(value)
    lookup_norm = normalize(lookup)
    views = list_views(client)

    exact = [
        view
        for view in views
        if normalize(view["id"]) == lookup_norm
        or normalize(view.get("slugId") or "") == lookup_norm
        or normalize(view["name"]) == lookup_norm
    ]
    if len(exact) == 1:
        return exact[0]

    partial = [view for view in views if lookup_norm in normalize(view["name"])]
    matches = exact or partial
    if len(matches) == 1:
        return matches[0]

    if not matches:
        raise SystemExit(f"Custom View '{value}' was not found.")

    lines = ["Custom View lookup is ambiguous:"]
    for view in matches:
        lines.append(f"- {view['name']} slug={view.get('slugId') or '-'} id={view['id']}")
    raise SystemExit("\n".join(lines))


def fetch_issues(client: LinearClient, view_id: str, limit: int, order: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if limit < 1:
        raise SystemExit("--limit must be greater than zero.")

    issues: list[dict[str, Any]] = []
    after: str | None = None
    view_payload: dict[str, Any] | None = None

    while len(issues) < limit:
        first = min(250, limit - len(issues))
        data = client.gql(
            f"""
            query ViewIssues($id: String!, $first: Int!, $after: String) {{
              customView(id: $id) {{
                id
                name
                slugId
                shared
                modelName
                filterData
                team {{ key name }}
                creator {{ name }}
                owner {{ name }}
                issues(first: $first, after: $after, sort: [{{ manual: {{ order: {order} }} }}]) {{
                  pageInfo {{ hasNextPage endCursor }}
                  nodes {{
                    id
                    identifier
                    title
                    priority
                    sortOrder
                    updatedAt
                    state {{ name type }}
                    parent {{ identifier title }}
                    project {{ name }}
                    assignee {{ name }}
                  }}
                }}
              }}
            }}
            """,
            {"id": view_id, "first": first, "after": after},
        )
        view = data["customView"]
        if not view:
            raise SystemExit(f"Custom View ID '{view_id}' was not found.")
        view_payload = {key: value for key, value in view.items() if key != "issues"}
        connection = view["issues"]
        issues.extend(connection["nodes"])
        if not connection["pageInfo"]["hasNextPage"]:
            break
        after = connection["pageInfo"]["endCursor"]

    return view_payload or {}, issues


def main() -> int:
    args = parse_args()
    client = LinearClient(args.api_url, resolve_api_key(args))
    view = find_view(client, args.view)
    full_view, issues = fetch_issues(client, view["id"], args.limit, args.order)

    result = {
        "view": full_view,
        "issue_count": len(issues),
        "issues": issues,
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"view={full_view['name']} slug={full_view.get('slugId') or '-'} issues={len(issues)}")
        for issue in issues:
            print(
                f"{issue['identifier']}\t{issue['state']['name']}\t"
                f"sort={issue.get('sortOrder')}\t{issue['title']}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
