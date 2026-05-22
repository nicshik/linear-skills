#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "linear-read-issue" / "scripts" / "read_issue.py"
SPEC = importlib.util.spec_from_file_location("read_issue", SCRIPT)
assert SPEC and SPEC.loader
read_issue = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = read_issue
SPEC.loader.exec_module(read_issue)


class FakeClient:
    def __init__(self, issue_exists: bool = True, entity_error: bool = False) -> None:
        self.queries: list[str] = []
        self.issue_exists = issue_exists
        self.entity_error = entity_error

    def gql(self, query, variables=None):
        self.queries.append(query)
        self.variables = variables
        if self.entity_error:
            raise read_issue.LinearApiError("network", "Entity not found: Issue")
        if not self.issue_exists:
            return {"issue": None}
        return {
            "issue": {
                "id": "issue-id",
                "identifier": "LIN-123",
                "title": "Fixture issue",
                "description": "Fixture description",
                "url": "https://linear.app/example/issue/LIN-123/fixture-issue",
                "priority": 1,
                "createdAt": "2026-05-01T00:00:00.000Z",
                "updatedAt": "2026-05-02T00:00:00.000Z",
                "completedAt": None,
                "state": {"id": "todo", "name": "Todo", "type": "unstarted"},
                "team": {"id": "team-id", "key": "LIN", "name": "Example"},
                "project": {"id": "project-id", "name": "Example Project"},
                "assignee": None,
                "creator": {"id": "user-id", "name": "Creator"},
                "labels": {"nodes": [{"id": "label-id", "name": "Bug"}]},
                "parent": None,
                "children": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                "comments": {"pageInfo": {"hasNextPage": False}, "nodes": []},
                "relations": {"pageInfo": {"hasNextPage": False}, "nodes": []},
            }
        }


class ReadIssueTest(unittest.TestCase):
    def test_issue_lookup_extracts_identifier_from_url(self) -> None:
        lookup = read_issue.issue_lookup_key("https://linear.app/example/issue/LIN-123/fixture-issue")
        self.assertEqual(lookup, "LIN-123")

    def test_read_query_contains_no_mutation(self) -> None:
        self.assertNotIn("mutation", read_issue.READ_ISSUE_QUERY.casefold())

    def test_read_issue_normalizes_labels_and_summaries(self) -> None:
        client = FakeClient()
        issue = read_issue.read_issue(client, "LIN-123", include_comments=True, include_relations=True)

        self.assertEqual(client.variables, {"id": "LIN-123"})
        self.assertNotIn("mutation", client.queries[0].casefold())
        self.assertEqual(issue["labels"], ["Bug"])
        self.assertEqual(issue["comments_summary"]["visible_count"], 0)
        self.assertEqual(issue["relations_summary"]["visible_count"], 0)

    def test_not_found_error_includes_safe_issue_diagnostics(self) -> None:
        client = FakeClient(issue_exists=False)

        with self.assertRaises(read_issue.LinearApiError) as error:
            read_issue.read_issue(
                client,
                "https://linear.app/example/comment/123e4567-e89b-12d3-a456-426614174000",
                include_comments=True,
                include_relations=True,
            )

        self.assertEqual(error.exception.category, "not_found")
        self.assertEqual(error.exception.details["error_code"], "issue_not_found")
        self.assertEqual(error.exception.details["input_kind"], "url_without_identifier")
        self.assertEqual(error.exception.details["lookup"], "123e4567-e89b-12d3-a456-426614174000")
        self.assertIn("issue key", error.exception.details["hint"])

    def test_graphql_entity_not_found_error_is_issue_not_found(self) -> None:
        client = FakeClient(entity_error=True)

        with self.assertRaises(read_issue.LinearApiError) as error:
            read_issue.read_issue(
                client,
                "https://linear.app/example/issue/LIN-123/fixture-issue",
                include_comments=True,
                include_relations=True,
            )

        self.assertEqual(error.exception.category, "not_found")
        self.assertEqual(error.exception.details["error_code"], "issue_not_found")
        self.assertEqual(error.exception.details["input_kind"], "url_with_identifier")


if __name__ == "__main__":
    unittest.main()
