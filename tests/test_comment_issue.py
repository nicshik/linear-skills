#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "linear-comment-issue" / "scripts" / "comment_issue.py"
SPEC = importlib.util.spec_from_file_location("comment_issue", SCRIPT)
assert SPEC and SPEC.loader
comment_issue = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = comment_issue
SPEC.loader.exec_module(comment_issue)


class FakeClient:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.variables: list[dict] = []

    def gql(self, query, variables=None):
        self.queries.append(query)
        self.variables.append(variables or {})
        if "query Issue" in query:
            return {"issue": self.issue("LIN-123")}
        if "mutation CreateComment" in query:
            return {
                "commentCreate": {
                    "success": True,
                    "comment": {
                        "id": "comment-id",
                        "body": variables["input"]["body"],
                        "createdAt": "2026-05-18T00:00:00.000Z",
                        "updatedAt": "2026-05-18T00:00:00.000Z",
                        "user": {"id": "user-id", "name": "Tester"},
                        "issue": {
                            "id": "issue-id",
                            "identifier": "LIN-123",
                            "title": "Fixture issue",
                            "url": "https://linear.app/example/issue/LIN-123/fixture",
                        },
                    },
                }
            }
        raise AssertionError(query)

    @staticmethod
    def issue(identifier: str):
        return {
            "id": "issue-id",
            "identifier": identifier,
            "title": "Fixture issue",
            "url": "https://linear.app/example/issue/LIN-123/fixture",
            "state": {"id": "todo", "name": "Todo", "type": "unstarted"},
            "team": {"id": "team-id", "key": "LIN", "name": "Example"},
            "project": {"id": "project-id", "name": "Example Project"},
        }


class CommentIssueTest(unittest.TestCase):
    def test_issue_lookup_extracts_identifier_from_url(self) -> None:
        lookup = comment_issue.issue_lookup_key("https://linear.app/example/issue/LIN-123/fixture")
        self.assertEqual(lookup, "LIN-123")

    def test_dry_run_reads_issue_without_mutation(self) -> None:
        client = FakeClient()

        result = comment_issue.comment_issue(client, "LIN-123", "Body", dry_run=True)

        self.assertEqual(result["action"], "dry_run")
        self.assertEqual(result["target"]["identifier"], "LIN-123")
        self.assertNotIn("mutation", "\n".join(client.queries).casefold())

    def test_comment_issue_creates_comment_and_verifies_issue(self) -> None:
        client = FakeClient()

        result = comment_issue.comment_issue(client, "LIN-123", "Body", dry_run=False)

        self.assertEqual(result["action"], "commented")
        self.assertEqual(result["comment"]["body"], "Body")
        self.assertEqual(result["verified"]["identifier"], "LIN-123")
        create_variables = next(
            variables for query, variables in zip(client.queries, client.variables)
            if "mutation CreateComment" in query
        )
        self.assertEqual(create_variables["input"]["issueId"], "issue-id")
        self.assertEqual(create_variables["input"]["body"], "Body")


if __name__ == "__main__":
    unittest.main()

