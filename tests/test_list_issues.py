#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from linear_common import graphql as linear_graphql


SCRIPT = Path(__file__).resolve().parents[1] / "linear-list-issues" / "scripts" / "list_issues.py"
SPEC = importlib.util.spec_from_file_location("list_issues", SCRIPT)
assert SPEC and SPEC.loader
list_issues = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = list_issues
SPEC.loader.exec_module(list_issues)


class FakeClient:
    def __init__(self, pages=None) -> None:
        self.pages = pages or [[self.issue("LIN-1", "Todo", "unstarted", ["Product"])]]
        self.queries: list[str] = []
        self.variables: list[dict] = []

    def gql(self, query, variables=None):
        self.queries.append(query)
        self.variables.append(variables or {})
        if "query Teams" in query:
            return {"teams": {"nodes": [{"id": "team-id", "key": "LIN", "name": "Example"}]}}
        if "query Projects" in query:
            return {"projects": {"nodes": [{"id": "project-id", "name": "Example Project"}]}}
        if "query States" in query:
            return {
                "workflowStates": {
                    "nodes": [
                        {"id": "todo", "name": "Todo", "type": "unstarted"},
                        {"id": "done", "name": "Done", "type": "completed"},
                    ]
                }
            }
        if "query Users" in query:
            return {
                "users": {
                    "nodes": [
                        {
                            "id": "user-id",
                            "name": "Alice",
                            "displayName": "Alice",
                            "email": "alice@example.com",
                        }
                    ]
                }
            }
        if "query ParentIssue" in query:
            return {
                "issue": {
                    "id": "parent-id",
                    "identifier": "LIN-9",
                    "title": "Parent",
                    "url": "https://linear.app/example/issue/LIN-9/parent",
                }
            }
        if "query Issues" in query:
            after = (variables or {}).get("after")
            page_index = int(after.removeprefix("cursor-")) if after else 0
            nodes = self.pages[page_index]
            next_index = page_index + 1
            return {
                "issues": {
                    "pageInfo": {
                        "hasNextPage": next_index < len(self.pages),
                        "endCursor": f"cursor-{next_index}",
                    },
                    "nodes": nodes,
                }
            }
        raise AssertionError(query)

    @staticmethod
    def issue(identifier: str, state_name: str, state_type: str, labels: list[str]):
        return {
            "id": f"{identifier.lower()}-id",
            "identifier": identifier,
            "title": f"{identifier} title",
            "url": f"https://linear.app/example/issue/{identifier}/fixture",
            "priority": 0,
            "updatedAt": "2026-05-18T00:00:00.000Z",
            "state": {"id": state_name.lower(), "name": state_name, "type": state_type},
            "team": {"id": "team-id", "key": "LIN", "name": "Example"},
            "project": {"id": "project-id", "name": "Example Project"},
            "assignee": None,
            "parent": None,
            "labels": {"nodes": [{"id": f"{label.lower()}-id", "name": label} for label in labels]},
        }


class ListIssuesTest(unittest.TestCase):
    def args(self, **overrides):
        defaults = {
            "team": "LIN",
            "project": "Example Project",
            "open_only": False,
            "status": None,
            "assignee": None,
            "parent": None,
            "label": [],
            "exclude_label": [],
            "missing_label": [],
            "without_labels": False,
            "limit": 100,
            "page_size": 50,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_lists_open_issues_by_team_and_project(self) -> None:
        client = FakeClient(
            [
                [
                    FakeClient.issue("LIN-1", "Todo", "unstarted", ["Product"]),
                    FakeClient.issue("LIN-2", "Done", "completed", ["Product"]),
                ]
            ]
        )

        result = list_issues.build_result(client, self.args(open_only=True))

        self.assertEqual([issue["identifier"] for issue in result["issues"]], ["LIN-1"])
        issues_variables = next(variables for query, variables in zip(client.queries, client.variables) if "query Issues" in query)
        self.assertEqual(issues_variables["filter"]["team"]["id"]["eq"], "team-id")
        self.assertEqual(issues_variables["filter"]["project"]["id"]["eq"], "project-id")

    def test_without_labels_returns_only_unlabelled_issues(self) -> None:
        client = FakeClient(
            [
                [
                    FakeClient.issue("LIN-1", "Todo", "unstarted", ["Product"]),
                    FakeClient.issue("LIN-2", "Todo", "unstarted", []),
                ]
            ]
        )

        result = list_issues.build_result(client, self.args(without_labels=True))

        self.assertEqual([issue["identifier"] for issue in result["issues"]], ["LIN-2"])

    def test_missing_label_returns_issues_missing_required_label(self) -> None:
        client = FakeClient(
            [
                [
                    FakeClient.issue("LIN-1", "Todo", "unstarted", ["Product"]),
                    FakeClient.issue("LIN-2", "Todo", "unstarted", ["Support"]),
                ]
            ]
        )

        result = list_issues.build_result(client, self.args(missing_label=["Product"]))

        self.assertEqual([issue["identifier"] for issue in result["issues"]], ["LIN-2"])

    def test_label_and_exclude_label_are_client_side_filters(self) -> None:
        client = FakeClient(
            [
                [
                    FakeClient.issue("LIN-1", "Todo", "unstarted", ["Product", "Blocked"]),
                    FakeClient.issue("LIN-2", "Todo", "unstarted", ["Product"]),
                    FakeClient.issue("LIN-3", "Todo", "unstarted", ["Support"]),
                ]
            ]
        )

        result = list_issues.build_result(client, self.args(label=["Product"], exclude_label=["Blocked"]))

        self.assertEqual([issue["identifier"] for issue in result["issues"]], ["LIN-2"])

    def test_limit_sets_has_more_when_more_matches_exist(self) -> None:
        client = FakeClient(
            [
                [
                    FakeClient.issue("LIN-1", "Todo", "unstarted", []),
                    FakeClient.issue("LIN-2", "Todo", "unstarted", []),
                ]
            ]
        )

        result = list_issues.build_result(client, self.args(limit=1))

        self.assertEqual([issue["identifier"] for issue in result["issues"]], ["LIN-1"])
        self.assertTrue(result["has_more"])
        self.assertEqual(result["counts"]["fetched"], 2)

    def test_resolves_status_assignee_and_parent_into_server_filter(self) -> None:
        client = FakeClient()

        result = list_issues.build_result(
            client,
            self.args(status="Todo", assignee="Alice", parent="LIN-9", limit=1),
        )

        server_filter = result["filters"]["server_filter"]
        self.assertEqual(server_filter["state"]["id"]["eq"], "todo")
        self.assertEqual(server_filter["assignee"]["id"]["eq"], "user-id")
        self.assertEqual(server_filter["parent"]["id"]["eq"], "parent-id")

    def test_source_is_read_only(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8").casefold()
        self.assertNotIn("mutation", source)

    def test_shared_client_redacts_token_from_errors(self) -> None:
        token = "secret-token-for-test"

        def failing_urlopen(_request, context=None):
            raise urllib.error.URLError(f"certificate failed for {token}")

        client = list_issues.LinearClient("https://api.example/graphql", token)
        with mock.patch.object(linear_graphql.urllib.request, "urlopen", side_effect=failing_urlopen):
            with self.assertRaises(list_issues.LinearApiError) as error:
                client.gql("query Test { viewer { id } }")

        self.assertNotIn(token, error.exception.message)
        self.assertIn("[redacted]", error.exception.message)


if __name__ == "__main__":
    unittest.main()
