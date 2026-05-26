#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "linear-delete-issue" / "scripts" / "delete_issue.py"
SPEC = importlib.util.spec_from_file_location("delete_issue", SCRIPT)
assert SPEC and SPEC.loader
delete_issue = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = delete_issue
SPEC.loader.exec_module(delete_issue)


class FakeClient:
    def __init__(
        self,
        *,
        status: str = "Done",
        labels: list[str] | None = None,
        children: int = 0,
        relations: int = 0,
        comments: int = 0,
        trashed: bool = False,
    ) -> None:
        self.queries: list[str] = []
        self.variables: list[dict] = []
        self.status = status
        self.labels = labels or ["Product"]
        self.children = children
        self.relations = relations
        self.comments = comments
        self.trashed = trashed
        self.delete_calls = 0

    def gql(self, query, variables=None):
        self.queries.append(query)
        self.variables.append(variables or {})
        if "query IssueDeleteRead" in query:
            return {"issue": self.issue()}
        if "mutation DeleteIssue" in query:
            self.delete_calls += 1
            self.trashed = True
            return {
                "issueDelete": {
                    "success": True,
                    "lastSyncId": 123,
                    "entity": {
                        "id": "issue-id",
                        "identifier": "LIN-123",
                        "title": "Fixture issue",
                        "url": "https://linear.app/example/issue/LIN-123/fixture",
                        "trashed": True,
                        "archivedAt": None,
                        "state": {"id": "done", "name": self.status, "type": "completed"},
                    },
                }
            }
        raise AssertionError(query)

    def connection(self, count: int, kind: str):
        if kind == "children":
            nodes = [
                {
                    "id": f"child-{idx}",
                    "identifier": f"LIN-{idx}",
                    "title": f"Child {idx}",
                    "state": {"name": "Todo", "type": "unstarted"},
                }
                for idx in range(count)
            ]
        elif kind == "relations":
            nodes = [
                {
                    "id": f"relation-{idx}",
                    "type": "related",
                    "relatedIssue": {
                        "id": f"related-{idx}",
                        "identifier": f"LIN-{idx}",
                        "title": f"Related {idx}",
                        "state": {"name": "Todo", "type": "unstarted"},
                    },
                }
                for idx in range(count)
            ]
        else:
            nodes = [
                {
                    "id": f"comment-{idx}",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "updatedAt": "2026-01-01T00:00:00Z",
                    "user": {"name": "User"},
                }
                for idx in range(count)
            ]
        return {"pageInfo": {"hasNextPage": False}, "nodes": nodes}

    def issue(self):
        return {
            "id": "issue-id",
            "identifier": "LIN-123",
            "title": "Fixture issue",
            "url": "https://linear.app/example/issue/LIN-123/fixture",
            "priority": 0,
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
            "completedAt": "2026-01-02T00:00:00Z",
            "archivedAt": None,
            "trashed": self.trashed,
            "state": {"id": "done", "name": self.status, "type": "completed"},
            "team": {"id": "team-id", "key": "LIN", "name": "Example"},
            "project": {"id": "project-id", "name": "Example Project"},
            "assignee": None,
            "parent": None,
            "labels": {"nodes": [{"id": f"label-{label}", "name": label} for label in self.labels]},
            "children": self.connection(self.children, "children"),
            "comments": self.connection(self.comments, "comments"),
            "relations": self.connection(self.relations, "relations"),
        }


class DeleteIssueTest(unittest.TestCase):
    def args(self, **overrides):
        defaults = {
            "issue": "LIN-123",
            "confirm": None,
            "expect_status": [],
            "forbid_label": [],
            "require_no_children": False,
            "require_no_relations": False,
            "require_no_comments": False,
            "dry_run": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_dry_run_does_not_mutate(self) -> None:
        client = FakeClient()

        result = delete_issue.delete_issue(
            client,
            self.args(
                dry_run=True,
                expect_status=["Done"],
                forbid_label=["Idea"],
                require_no_children=True,
                require_no_relations=True,
                require_no_comments=True,
            ),
        )

        self.assertEqual(result["action"], "dry_run")
        self.assertEqual(client.delete_calls, 0)
        self.assertNotIn("mutation DeleteIssue", "\n".join(client.queries))

    def test_live_deletion_requires_confirm(self) -> None:
        client = FakeClient()

        with self.assertRaises(delete_issue.LinearApiError) as error:
            delete_issue.delete_issue(client, self.args())

        self.assertEqual(error.exception.category, "validation")
        self.assertEqual(client.delete_calls, 0)

    def test_live_deletion_requires_matching_confirm(self) -> None:
        client = FakeClient()

        with self.assertRaises(delete_issue.LinearApiError) as error:
            delete_issue.delete_issue(client, self.args(confirm="LIN-999"))

        self.assertEqual(error.exception.category, "validation")
        self.assertEqual(client.delete_calls, 0)

    def test_expect_status_blocks_wrong_status(self) -> None:
        client = FakeClient(status="Todo")

        with self.assertRaises(delete_issue.LinearApiError) as error:
            delete_issue.delete_issue(client, self.args(dry_run=True, expect_status=["Done"]))

        self.assertEqual(error.exception.category, "validation")
        self.assertEqual(error.exception.details["failed_checks"][0]["name"], "expect_status")

    def test_forbid_label_blocks_deletion(self) -> None:
        client = FakeClient(labels=["Idea"])

        with self.assertRaises(delete_issue.LinearApiError) as error:
            delete_issue.delete_issue(client, self.args(dry_run=True, forbid_label=["Idea"]))

        self.assertEqual(error.exception.category, "validation")
        self.assertEqual(error.exception.details["failed_checks"][0]["name"], "forbid_label")

    def test_require_empty_connections_block_deletion(self) -> None:
        cases = [
            ("children", {"children": 1}, {"require_no_children": True}, "require_no_children"),
            ("relations", {"relations": 1}, {"require_no_relations": True}, "require_no_relations"),
            ("comments", {"comments": 1}, {"require_no_comments": True}, "require_no_comments"),
        ]

        for name, client_kwargs, arg_kwargs, check_name in cases:
            with self.subTest(name=name):
                client = FakeClient(**client_kwargs)
                with self.assertRaises(delete_issue.LinearApiError) as error:
                    delete_issue.delete_issue(client, self.args(dry_run=True, **arg_kwargs))
                self.assertEqual(error.exception.category, "validation")
                self.assertEqual(error.exception.details["failed_checks"][0]["name"], check_name)

    def test_successful_live_deletion_calls_issue_delete_once(self) -> None:
        client = FakeClient()

        result = delete_issue.delete_issue(client, self.args(confirm="LIN-123", expect_status=["Done"]))

        self.assertEqual(result["action"], "deleted")
        self.assertEqual(client.delete_calls, 1)
        mutation_variables = next(
            variables for query, variables in zip(client.queries, client.variables)
            if "mutation DeleteIssue" in query
        )
        self.assertEqual(mutation_variables, {"id": "issue-id", "permanentlyDelete": False})
        self.assertTrue(result["deleted"]["entity"]["trashed"])
        self.assertEqual(result["verification_status"], "read_back")

    def test_already_trashed_issue_does_not_mutate(self) -> None:
        client = FakeClient(trashed=True)

        result = delete_issue.delete_issue(client, self.args(confirm="LIN-123"))

        self.assertEqual(result["action"], "already_deleted")
        self.assertEqual(client.delete_calls, 0)


if __name__ == "__main__":
    unittest.main()
