#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "linear-update-issue" / "scripts" / "update_issue.py"
SPEC = importlib.util.spec_from_file_location("update_issue", SCRIPT)
assert SPEC and SPEC.loader
update_issue = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = update_issue
SPEC.loader.exec_module(update_issue)


class FakeClient:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.variables: list[dict] = []
        self.updated_description = "Initial body"

    def gql(self, query, variables=None):
        self.queries.append(query)
        self.variables.append(variables or {})
        if "query Issue" in query:
            lookup = (variables or {}).get("id")
            if lookup in {"LIN-9", "parent-id"}:
                return {"issue": self.issue("parent-id", "LIN-9", "Parent", "Parent body")}
            return {"issue": self.issue("issue-id", "LIN-123", "Fixture issue", self.updated_description)}
        if "query Labels" in query:
            return {
                "issueLabels": {
                    "nodes": [
                        {"id": "idea-label", "name": "Idea"},
                        {"id": "product-label", "name": "Product"},
                    ]
                }
            }
        if "query Users" in query:
            return {
                "users": {
                    "nodes": [
                        {
                            "id": "user-id",
                            "name": "Nick",
                            "displayName": "Nick",
                            "email": "nick@example.com",
                        }
                    ]
                }
            }
        if "mutation UpdateIssue" in query:
            self.updated_description = variables["input"].get("description", self.updated_description)
            return {
                "issueUpdate": {
                    "success": True,
                    "issue": self.issue("issue-id", "LIN-123", variables["input"].get("title", "Fixture issue"), self.updated_description),
                }
            }
        raise AssertionError(query)

    @staticmethod
    def issue(issue_id: str, identifier: str, title: str, description: str):
        return {
            "id": issue_id,
            "identifier": identifier,
            "title": title,
            "description": description,
            "url": f"https://linear.app/example/issue/{identifier}/fixture",
            "state": {"id": "todo", "name": "Todo", "type": "unstarted"},
            "team": {"id": "team-id", "key": "LIN", "name": "Example"},
            "project": {"id": "project-id", "name": "Example Project"},
            "assignee": None,
            "parent": None,
            "labels": {"nodes": [{"id": "idea-label", "name": "Idea"}]},
        }


class UpdateIssueTest(unittest.TestCase):
    def args(self, **overrides):
        defaults = {
            "issue": "LIN-123",
            "add_label": [],
            "remove_label": [],
            "assignee": None,
            "parent": None,
            "title": None,
            "description_file": None,
            "append_description_file": None,
            "dry_run": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_dry_run_resolves_update_without_mutation(self) -> None:
        client = FakeClient()

        result = update_issue.update_issue(
            client,
            self.args(
                add_label=["Product"],
                remove_label=["Idea"],
                assignee="Nick",
                parent="LIN-9",
                title="Updated title",
                dry_run=True,
            ),
        )

        self.assertEqual(result["action"], "dry_run")
        self.assertEqual(result["input"]["addedLabelIds"], ["product-label"])
        self.assertEqual(result["input"]["removedLabelIds"], ["idea-label"])
        self.assertEqual(result["input"]["assigneeId"], "user-id")
        self.assertEqual(result["input"]["parentId"], "parent-id")
        self.assertEqual(result["input"]["title"], "Updated title")
        self.assertNotIn("mutation", "\n".join(client.queries).casefold())

    def test_update_appends_description_and_verifies(self) -> None:
        client = FakeClient()
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as body:
            body.write("Additional body")
            body.flush()

            result = update_issue.update_issue(
                client,
                self.args(append_description_file=body.name),
            )

        self.assertEqual(result["action"], "updated")
        self.assertEqual(result["verified"]["description"], "Initial body\n\nAdditional body")
        update_variables = next(
            variables for query, variables in zip(client.queries, client.variables)
            if "mutation UpdateIssue" in query
        )
        self.assertEqual(update_variables["input"]["description"], "Initial body\n\nAdditional body")

    def test_missing_label_is_controlled_error(self) -> None:
        client = FakeClient()

        with self.assertRaises(update_issue.LinearApiError) as error:
            update_issue.update_issue(client, self.args(add_label=["Missing"], dry_run=True))

        self.assertEqual(error.exception.category, "not_found")

    def test_no_update_fields_is_controlled_error(self) -> None:
        client = FakeClient()

        with self.assertRaises(update_issue.LinearApiError) as error:
            update_issue.update_issue(client, self.args())

        self.assertEqual(error.exception.category, "validation")


if __name__ == "__main__":
    unittest.main()
