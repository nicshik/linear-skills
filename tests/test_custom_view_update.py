#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "linear-custom-view-update" / "scripts" / "custom_view_update.py"
SPEC = importlib.util.spec_from_file_location("custom_view_update", SCRIPT)
assert SPEC and SPEC.loader
custom_view_update = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = custom_view_update
SPEC.loader.exec_module(custom_view_update)


class FakeClient:
    def __init__(self, views=None) -> None:
        self.views = list(views or [])
        self.queries: list[str] = []
        self.variables: list[dict] = []

    def gql(self, query, variables=None):
        self.queries.append(query)
        self.variables.append(variables or {})
        if "query View(" in query:
            lookup = variables["id"]
            return {
                "customView": next(
                    (
                        view
                        for view in self.views
                        if view["id"] == lookup or view.get("slugId") == lookup
                    ),
                    None,
                )
            }
        if "query Views" in query:
            return {"customViews": {"nodes": self.views}}
        if "query Teams" in query:
            return {"teams": {"nodes": [{"id": "team-id", "key": "LIN", "name": "Example"}]}}
        if "query Projects" in query:
            return {"projects": {"nodes": [{"id": "project-id", "name": "Example Project"}]}}
        if "query Labels" in query:
            return {"issueLabels": {"nodes": [{"id": "product-label", "name": "Product"}]}}
        if "query WorkflowStates" in query:
            return {
                "workflowStates": {
                    "nodes": [
                        {"id": "backlog-id", "name": "Backlog", "type": "backlog", "team": {"id": "team-id"}},
                        {"id": "todo-id", "name": "Todo", "type": "unstarted", "team": {"id": "team-id"}},
                    ]
                }
            }
        if "mutation UpdateCustomView" in query:
            input_data = variables["input"]
            view_id = variables["id"]
            view = next(view for view in self.views if view["id"] == view_id)
            updated = dict(view)
            if "projectId" in input_data:
                updated["projects"] = {"nodes": [{"id": input_data["projectId"], "name": "Example Project"}]}
            for key, value in input_data.items():
                if key == "projectId":
                    continue
                updated[key] = value
            self.views[self.views.index(view)] = updated
            return {"customViewUpdate": {"success": True, "customView": updated}}
        raise AssertionError(query)


class CustomViewUpdateTest(unittest.TestCase):
    def view(self, **overrides):
        defaults = {
            "id": "view-id",
            "name": "Product Queue",
            "slugId": "product-queue",
            "shared": True,
            "modelName": "Issue",
            "description": None,
            "color": None,
            "icon": None,
            "filterData": {},
            "projectFilterData": None,
            "initiativeFilterData": None,
            "feedItemFilterData": None,
            "updatedAt": "2026-05-18T00:00:00.000Z",
            "team": {"id": "team-id", "key": "LIN", "name": "Example"},
            "creator": {"name": "Tester"},
            "owner": {"name": "Tester"},
            "projects": {"nodes": []},
        }
        defaults.update(overrides)
        return defaults

    def args(self, **overrides):
        defaults = {
            "view": "Product Queue",
            "team": "LIN",
            "project": "Example Project",
            "label": ["Product"],
            "status": ["Backlog"],
            "open_only": True,
            "name": None,
            "description": None,
            "color": None,
            "icon": None,
            "private": False,
            "shared": False,
            "dry_run": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_dry_run_resolves_filter_without_mutation(self) -> None:
        client = FakeClient([self.view()])

        result = custom_view_update.update_custom_view(client, self.args(dry_run=True))

        self.assertEqual(result["action"], "dry_run")
        self.assertNotIn("mutation", "\n".join(client.queries).casefold())
        self.assertEqual(
            result["input"]["filterData"],
            {
                "and": [
                    {"state": {"type": {"nin": ["completed", "canceled"]}}},
                    {"state": {"name": {"in": ["Backlog"]}}},
                    {
                        "labels": {
                            "and": [
                                {
                                    "or": [
                                        {"name": {"eq": "Product"}},
                                        {"parent": {"name": {"eq": "Product"}}},
                                    ]
                                }
                            ]
                        }
                    },
                ]
            },
        )

    def test_update_sets_visibility_and_verifies(self) -> None:
        client = FakeClient([self.view()])

        result = custom_view_update.update_custom_view(
            client,
            self.args(label=[], status=[], open_only=False, project=None, private=True),
        )

        self.assertEqual(result["action"], "updated")
        update_variables = next(
            variables for query, variables in zip(client.queries, client.variables)
            if "mutation UpdateCustomView" in query
        )
        self.assertEqual(update_variables["input"], {"shared": False})
        self.assertFalse(result["verified"]["shared"])

    def test_update_sets_name_without_filter_change(self) -> None:
        client = FakeClient([self.view()])

        result = custom_view_update.update_custom_view(
            client,
            self.args(label=[], status=[], open_only=False, project=None, name="[Archive] Product Queue"),
        )

        self.assertEqual(result["action"], "updated")
        update_variables = next(
            variables for query, variables in zip(client.queries, client.variables)
            if "mutation UpdateCustomView" in query
        )
        self.assertEqual(update_variables["input"], {"name": "[Archive] Product Queue"})
        self.assertEqual(result["verified"]["name"], "[Archive] Product Queue")
        self.assertFalse(result["target"]["filter_changed"])

    def test_name_lookup_requires_team(self) -> None:
        client = FakeClient([self.view()])

        with self.assertRaises(custom_view_update.LinearApiError) as error:
            custom_view_update.update_custom_view(client, self.args(team=None, dry_run=True))

        self.assertEqual(error.exception.category, "validation")

    def test_missing_status_is_controlled_error(self) -> None:
        client = FakeClient([self.view()])

        with self.assertRaises(custom_view_update.LinearApiError) as error:
            custom_view_update.update_custom_view(client, self.args(status=["Missing"], dry_run=True))

        self.assertEqual(error.exception.category, "not_found")

    def test_ambiguous_view_is_controlled_error(self) -> None:
        client = FakeClient([self.view(id="a"), self.view(id="b")])

        with self.assertRaises(custom_view_update.LinearApiError) as error:
            custom_view_update.update_custom_view(client, self.args(dry_run=True))

        self.assertEqual(error.exception.category, "ambiguous_lookup")


if __name__ == "__main__":
    unittest.main()
