#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "linear-relation-setup" / "scripts" / "relation_setup.py"
SPEC = importlib.util.spec_from_file_location("relation_setup", SCRIPT)
assert SPEC and SPEC.loader
relation_setup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = relation_setup
SPEC.loader.exec_module(relation_setup)


class FakeClient:
    def __init__(self, relations=None) -> None:
        self.relations = list(relations or [])
        self.queries: list[str] = []
        self.variables: list[dict] = []

    def issue(self, issue_id: str, identifier: str):
        return {
            "id": issue_id,
            "identifier": identifier,
            "title": f"{identifier} title",
            "url": f"https://linear.app/example/issue/{identifier}/fixture",
            "state": {"id": "todo", "name": "Todo", "type": "unstarted"},
            "team": {"id": "team-id", "key": "LIN", "name": "Example"},
            "project": {"id": "project-id", "name": "Example Project"},
            "relations": {
                "pageInfo": {"hasNextPage": False},
                "nodes": [
                    relation
                    for relation in self.relations
                    if relation["issue"]["id"] == issue_id or relation["relatedIssue"]["id"] == issue_id
                ],
            },
        }

    def gql(self, query, variables=None):
        self.queries.append(query)
        self.variables.append(variables or {})
        if "query IssueWithRelations" in query:
            lookup = variables["id"]
            if lookup in {"LIN-123", "issue-123"}:
                return {"issue": self.issue("issue-123", "LIN-123")}
            if lookup in {"LIN-100", "issue-100"}:
                return {"issue": self.issue("issue-100", "LIN-100")}
            return {"issue": None}
        if "mutation CreateIssueRelation" in query:
            input_data = variables["input"]
            relation = {
                "id": "relation-id",
                "type": input_data["type"],
                "issue": {"id": input_data["issueId"], "identifier": "LIN-123" if input_data["issueId"] == "issue-123" else "LIN-100", "title": "source"},
                "relatedIssue": {"id": input_data["relatedIssueId"], "identifier": "LIN-123" if input_data["relatedIssueId"] == "issue-123" else "LIN-100", "title": "target"},
            }
            self.relations.append(relation)
            return {"issueRelationCreate": {"success": True, "issueRelation": relation}}
        raise AssertionError(query)


class RelationSetupTest(unittest.TestCase):
    def args(self, **overrides):
        defaults = {
            "issue": "LIN-123",
            "related_issue": "LIN-100",
            "type": "related",
            "dry_run": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_existing_relation_is_noop(self) -> None:
        existing = {
            "id": "relation-id",
            "type": "related",
            "issue": {"id": "issue-100", "identifier": "LIN-100", "title": "target"},
            "relatedIssue": {"id": "issue-123", "identifier": "LIN-123", "title": "source"},
        }
        client = FakeClient([existing])

        result = relation_setup.setup_relation(client, self.args())

        self.assertEqual(result["action"], "exists")
        self.assertNotIn("mutation", "\n".join(client.queries).casefold())

    def test_dry_run_does_not_mutate(self) -> None:
        client = FakeClient()

        result = relation_setup.setup_relation(client, self.args(type="blocks", dry_run=True))

        self.assertEqual(result["action"], "dry_run")
        self.assertEqual(result["input"]["type"], "blocks")
        self.assertEqual(result["input"]["issueId"], "issue-123")
        self.assertEqual(result["input"]["relatedIssueId"], "issue-100")
        self.assertNotIn("mutation", "\n".join(client.queries).casefold())

    def test_blocked_by_reverses_blocks_direction(self) -> None:
        client = FakeClient()

        result = relation_setup.setup_relation(client, self.args(type="blocked-by", dry_run=True))

        self.assertEqual(result["target"]["type"], "blocks")
        self.assertEqual(result["target"]["source"]["identifier"], "LIN-100")
        self.assertEqual(result["target"]["target"]["identifier"], "LIN-123")
        self.assertEqual(result["input"]["issueId"], "issue-100")
        self.assertEqual(result["input"]["relatedIssueId"], "issue-123")

    def test_create_relation_and_verify(self) -> None:
        client = FakeClient()

        result = relation_setup.setup_relation(client, self.args(type="blocks"))

        self.assertEqual(result["action"], "created")
        self.assertEqual(result["created"]["type"], "blocks")
        self.assertEqual(result["verified"]["type"], "blocks")

    def test_missing_issue_is_controlled_error(self) -> None:
        client = FakeClient()

        with self.assertRaises(relation_setup.LinearApiError) as error:
            relation_setup.setup_relation(client, self.args(issue="LIN-999", dry_run=True))

        self.assertEqual(error.exception.category, "not_found")


if __name__ == "__main__":
    unittest.main()
