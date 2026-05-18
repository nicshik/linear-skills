#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "linear-create-issue" / "scripts" / "create_issue.py"
SPEC = importlib.util.spec_from_file_location("create_issue", SCRIPT)
assert SPEC and SPEC.loader
create_issue = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = create_issue
SPEC.loader.exec_module(create_issue)


class FakeClient:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.variables: list[dict] = []

    def gql(self, query, variables=None):
        self.queries.append(query)
        self.variables.append(variables or {})
        if "query Teams" in query:
            return {"teams": {"nodes": [{"id": "team-id", "key": "LIN", "name": "Example"}]}}
        if "query States" in query:
            return {
                "workflowStates": {
                    "nodes": [
                        {"id": "backlog", "name": "Backlog", "type": "backlog"},
                        {"id": "todo", "name": "Todo", "type": "unstarted"},
                    ]
                }
            }
        if "query Projects" in query:
            return {"projects": {"nodes": [{"id": "project-id", "name": "Example Project"}]}}
        if "query Labels" in query:
            return {
                "issueLabels": {
                    "nodes": [
                        {"id": "idea-label", "name": "Idea"},
                        {"id": "product-label", "name": "Product"},
                    ]
                }
            }
        if "mutation CreateIssue" in query:
            return {"issueCreate": {"success": True, "issue": self.issue("LIN-123")}}
        if "query Verify" in query:
            return {"issue": self.issue("LIN-123")}
        raise AssertionError(query)

    @staticmethod
    def issue(identifier: str):
        return {
            "id": "issue-id",
            "identifier": identifier,
            "title": "Example idea",
            "url": "https://linear.app/example/issue/LIN-123/example-idea",
            "state": {"id": "backlog", "name": "Backlog", "type": "backlog"},
            "team": {"id": "team-id", "key": "LIN", "name": "Example"},
            "project": {"id": "project-id", "name": "Example Project"},
            "labels": {"nodes": [{"id": "idea-label", "name": "Idea"}]},
        }


class CreateIssueTest(unittest.TestCase):
    def test_dry_run_resolves_metadata_without_mutation(self) -> None:
        client = FakeClient()
        team = create_issue.resolve_team(client, "LIN")
        state = create_issue.resolve_state(client, team["id"], "Backlog")
        project = create_issue.resolve_project(client, "Example Project")
        labels, skipped_labels = create_issue.resolve_labels(client, team["id"], ["Idea"])

        self.assertEqual(skipped_labels, [])
        result = create_issue.create_issue(
            client,
            "Example idea",
            "Body",
            team,
            state,
            project,
            labels,
            dry_run=True,
        )

        self.assertEqual(result["action"], "dry_run")
        self.assertNotIn("mutation", "\n".join(client.queries).casefold())

    def test_create_issue_sends_expected_input_and_verifies(self) -> None:
        client = FakeClient()
        team = create_issue.resolve_team(client, "LIN")
        state = create_issue.resolve_state(client, team["id"], "Backlog")
        project = create_issue.resolve_project(client, "Example Project")
        labels, _skipped_labels = create_issue.resolve_labels(client, team["id"], ["Idea"])

        result = create_issue.create_issue(
            client,
            "Example idea",
            "Body",
            team,
            state,
            project,
            labels,
            dry_run=False,
        )

        self.assertEqual(result["action"], "created")
        self.assertEqual(result["verified"]["identifier"], "LIN-123")
        create_variables = next(variables for query, variables in zip(client.queries, client.variables) if "mutation CreateIssue" in query)
        self.assertEqual(create_variables["input"]["teamId"], "team-id")
        self.assertEqual(create_variables["input"]["stateId"], "backlog")
        self.assertEqual(create_variables["input"]["projectId"], "project-id")
        self.assertEqual(create_variables["input"]["labelIds"], ["idea-label"])

    def test_missing_label_is_controlled_error(self) -> None:
        with self.assertRaises(create_issue.LinearApiError) as error:
            create_issue.resolve_labels(FakeClient(), "team-id", ["Missing"])
        self.assertEqual(error.exception.category, "not_found")

    def test_missing_optional_label_is_reported_and_skipped(self) -> None:
        labels, skipped = create_issue.resolve_labels(
            FakeClient(),
            "team-id",
            ["Idea", "Missing"],
            optional=True,
        )

        self.assertEqual([label["name"] for label in labels], ["Idea"])
        self.assertEqual(skipped, ["Missing"])


if __name__ == "__main__":
    unittest.main()
