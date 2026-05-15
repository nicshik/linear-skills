#!/usr/bin/env python3
"""Read a Linear Custom View and its manually sorted issues."""

from __future__ import annotations

import argparse
import datetime as dt
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
    parser.add_argument("--limit", type=int, default=250, help="Max issues to return.")
    parser.add_argument(
        "--order",
        choices=("Ascending", "Descending"),
        default="Ascending",
        help="Manual sort order.",
    )
    parser.add_argument(
        "--first",
        action="store_true",
        help="Include the first actionable issue in a stable first_issue field.",
    )
    parser.add_argument(
        "--explain-filter",
        action="store_true",
        help="Include the Custom View filterData and a short note about view-controlled visibility.",
    )
    parser.add_argument(
        "--include-relations-summary",
        action="store_true",
        help="Fetch read-only relation/comment counts and labels for issue rows.",
    )
    parser.add_argument(
        "--expect-label",
        action="append",
        default=[],
        help="Require the first matching issue to have this label. Can be repeated.",
    )
    parser.add_argument(
        "--exclude-label",
        action="append",
        default=[],
        help="Skip issues with this label when selecting first_matching_issue. Can be repeated.",
    )
    parser.add_argument(
        "--expect-title-regex",
        action="append",
        default=[],
        help="Require the first matching issue title to match this regular expression. Can be repeated.",
    )
    parser.add_argument(
        "--skip-title-regex",
        action="append",
        default=[],
        help="Skip issues whose title matches this regular expression. Can be repeated.",
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


def get_view_by_id_or_slug(client: LinearClient, value: str) -> dict[str, Any] | None:
    data = client.gql(
        """
        query View($id: String!) {
          customView(id: $id) {
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
        """,
        {"id": value},
    )
    return data["customView"]


def find_view(client: LinearClient, value: str) -> dict[str, Any]:
    lookup = view_lookup_key(value)
    lookup_norm = normalize(lookup)

    direct = get_view_by_id_or_slug(client, lookup)
    if direct:
        return direct

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


def issue_fields(include_relations_summary: bool, include_labels: bool = False) -> str:
    base = """
                    id
                    identifier
                    title
                    priority
                    sortOrder
                    updatedAt
                    state { name type }
                    parent { identifier title }
                    project { name }
                    assignee { name }
    """
    if include_labels and not include_relations_summary:
        return (
            base
            + """
                    labels { nodes { name } }
        """
        )
    if not include_relations_summary:
        return base
    return (
        base
        + """
                    labels { nodes { name } }
                    comments(first: 50) { pageInfo { hasNextPage } nodes { id } }
                    relations(first: 50) {
                      pageInfo { hasNextPage }
                      nodes {
                        id
                        type
                        relatedIssue { identifier title state { name type } }
                      }
                    }
        """
    )


def add_relation_summaries(issues: list[dict[str, Any]]) -> None:
    for issue in issues:
        labels = issue.pop("labels", None) or {}
        comments = issue.pop("comments", None) or {}
        relations = issue.pop("relations", None) or {}
        if not labels and not comments and not relations:
            continue
        issue["labels"] = [node["name"] for node in labels.get("nodes", []) if node.get("name")]
        relation_nodes = relations.get("nodes", [])
        issue["relations_summary"] = {
            "visible_count": len(relation_nodes),
            "has_more": bool((relations.get("pageInfo") or {}).get("hasNextPage")),
            "items": [
                {
                    "type": node.get("type"),
                    "identifier": (node.get("relatedIssue") or {}).get("identifier"),
                    "title": (node.get("relatedIssue") or {}).get("title"),
                    "status": ((node.get("relatedIssue") or {}).get("state") or {}).get("name"),
                }
                for node in relation_nodes
            ],
        }
        issue["comments_summary"] = {
            "visible_count": len(comments.get("nodes", [])),
            "has_more": bool((comments.get("pageInfo") or {}).get("hasNextPage")),
        }


def fetch_issues(
    client: LinearClient,
    view_id: str,
    limit: int,
    order: str,
    include_relations_summary: bool,
    include_labels: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if limit < 1:
        raise SystemExit("--limit must be greater than zero.")

    issues: list[dict[str, Any]] = []
    after: str | None = None
    view_payload: dict[str, Any] | None = None

    while len(issues) < limit:
        first = min(250, limit - len(issues))
        fields = issue_fields(include_relations_summary, include_labels)
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
                    {fields}
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

    if include_relations_summary or include_labels:
        add_relation_summaries(issues)
    return view_payload or {}, issues


def issue_labels(issue: dict[str, Any]) -> set[str]:
    labels = issue.get("labels")
    if isinstance(labels, list):
        return {str(label).casefold() for label in labels if str(label).strip()}
    return set()


def compile_regexes(patterns: list[str], option_name: str) -> list[re.Pattern[str]]:
    regexes: list[re.Pattern[str]] = []
    for pattern in patterns:
        try:
            regexes.append(re.compile(pattern, flags=re.IGNORECASE))
        except re.error as exc:
            raise SystemExit(f"{option_name} is not a valid regular expression: {pattern}: {exc}") from exc
    return regexes


def selection_filters_active(args: argparse.Namespace) -> bool:
    return bool(args.expect_label or args.exclude_label or args.expect_title_regex or args.skip_title_regex)


def build_issue_selector(args: argparse.Namespace):
    expected_labels = {label.casefold() for label in args.expect_label}
    excluded_labels = {label.casefold() for label in args.exclude_label}
    expected_title_regexes = compile_regexes(args.expect_title_regex, "--expect-title-regex")
    skipped_title_regexes = compile_regexes(args.skip_title_regex, "--skip-title-regex")

    def selector(issue: dict[str, Any]) -> tuple[bool, str | None]:
        labels = issue_labels(issue)
        title = str(issue.get("title") or "")
        missing_labels = sorted(expected_labels - labels)
        blocked_labels = sorted(excluded_labels & labels)
        missing_title_regexes = [regex.pattern for regex in expected_title_regexes if not regex.search(title)]
        matched_skip_regexes = [regex.pattern for regex in skipped_title_regexes if regex.search(title)]
        reasons: list[str] = []
        if missing_labels:
            reasons.append("missing expected label(s): " + ", ".join(missing_labels))
        if blocked_labels:
            reasons.append("excluded label(s): " + ", ".join(blocked_labels))
        if missing_title_regexes:
            reasons.append("title did not match expected regex: " + ", ".join(missing_title_regexes))
        if matched_skip_regexes:
            reasons.append("title matched skip regex: " + ", ".join(matched_skip_regexes))
        if reasons:
            return False, "; ".join(reasons)
        return True, None

    return selector


def first_actionable_issue(
    issues: list[dict[str, Any]],
    view: dict[str, Any],
    issue_selector=None,
) -> dict[str, Any] | None:
    for index, issue in enumerate(issues, start=1):
        state = issue.get("state") or {}
        state_type = (state.get("type") or "").casefold()
        if state_type in {"completed", "canceled"}:
            continue
        if issue_selector:
            matched, _reason = issue_selector(issue)
            if not matched:
                continue
        return {
            "row_index": index,
            "identifier": issue.get("identifier"),
            "title": issue.get("title"),
            "status": state.get("name"),
            "status_type": state.get("type"),
            "manual_order": issue.get("sortOrder"),
            "view_slug": view.get("slugId"),
            "issue": issue,
        }
    return None


def first_matching_issue_with_skips(
    issues: list[dict[str, Any]],
    view: dict[str, Any],
    issue_selector,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    skipped: list[dict[str, Any]] = []
    for index, issue in enumerate(issues, start=1):
        state = issue.get("state") or {}
        state_type = (state.get("type") or "").casefold()
        if state_type in {"completed", "canceled"}:
            skipped.append({
                "row_index": index,
                "identifier": issue.get("identifier"),
                "title": issue.get("title"),
                "reason": f"state type is {state_type}",
            })
            continue
        matched, reason = issue_selector(issue)
        if not matched:
            skipped.append({
                "row_index": index,
                "identifier": issue.get("identifier"),
                "title": issue.get("title"),
                "reason": reason,
            })
            continue
        return {
            "row_index": index,
            "identifier": issue.get("identifier"),
            "title": issue.get("title"),
            "status": state.get("name"),
            "status_type": state.get("type"),
            "manual_order": issue.get("sortOrder"),
            "view_slug": view.get("slugId"),
            "issue": issue,
        }, skipped
    return None, skipped


def filter_explanation(view: dict[str, Any]) -> dict[str, Any]:
    return {
        "filter_data": view.get("filterData"),
        "note": "Custom View filterData controls which issues are visible; completed issues can disappear when the view filter excludes them.",
    }


def main() -> int:
    args = parse_args()
    client = LinearClient(args.api_url, resolve_api_key(args))
    view = find_view(client, args.view)
    filters_active = selection_filters_active(args)
    full_view, issues = fetch_issues(
        client,
        view["id"],
        args.limit,
        args.order,
        args.include_relations_summary,
        include_labels=filters_active,
    )
    fetched_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    result = {
        "schema_version": "linear-custom-view.v1",
        "fetched_at": fetched_at,
        "queue_order": "manual",
        "view": full_view,
        "issue_count": len(issues),
        "issues": issues,
    }
    if args.first:
        result["first_issue"] = first_actionable_issue(issues, full_view)
    if filters_active:
        selector = build_issue_selector(args)
        first_matching_issue, skipped_issues = first_matching_issue_with_skips(issues, full_view, selector)
        result["selection_filters"] = {
            "expect_labels": args.expect_label,
            "exclude_labels": args.exclude_label,
            "expect_title_regexes": args.expect_title_regex,
            "skip_title_regexes": args.skip_title_regex,
        }
        result["first_matching_issue"] = first_matching_issue
        result["skipped_issues"] = skipped_issues
    if args.explain_filter:
        result["filter_explanation"] = filter_explanation(full_view)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"view={full_view['name']} slug={full_view.get('slugId') or '-'} issues={len(issues)}")
        if args.explain_filter:
            print("filterData=" + json.dumps(full_view.get("filterData"), ensure_ascii=False, sort_keys=True))
            print("filter_note=Custom View filterData controls visibility; completed issues can disappear when excluded by the view.")
        if args.first:
            first_issue = result["first_issue"]
            if first_issue:
                print(
                    f"first={first_issue['row_index']}\t{first_issue['identifier']}\t"
                    f"{first_issue['status']}\tsort={first_issue.get('manual_order')}\t{first_issue['title']}"
                )
            else:
                print("first=none")
        if filters_active:
            first_matching_issue = result["first_matching_issue"]
            if first_matching_issue:
                print(
                    f"first_matching={first_matching_issue['row_index']}\t{first_matching_issue['identifier']}\t"
                    f"{first_matching_issue['status']}\tsort={first_matching_issue.get('manual_order')}\t"
                    f"{first_matching_issue['title']}"
                )
            else:
                print("first_matching=none")
            for skipped in result["skipped_issues"]:
                print(
                    f"skipped={skipped['row_index']}\t{skipped.get('identifier')}\t"
                    f"{skipped.get('reason')}\t{skipped.get('title')}"
                )
        for issue in issues:
            print(
                f"{issue['identifier']}\t{issue['state']['name']}\t"
                f"sort={issue.get('sortOrder')}\t{issue['title']}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
