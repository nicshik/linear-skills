#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "linear-custom-view-setup" / "scripts" / "custom_view_setup.py"
SPEC = importlib.util.spec_from_file_location("custom_view_setup", SCRIPT)
assert SPEC and SPEC.loader
custom_view_setup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = custom_view_setup
SPEC.loader.exec_module(custom_view_setup)


class FakeClient:
    def __init__(self, views=None) -> None:
        self.views = list(views or [])
        self.queries: list[str] = []
        self.variables: list[dict] = []

    def gql(self, query, variables=None):
        self.queries.append(query)
        self.variables.append(variables or {})
        if "query Teams" in query:
            return {"teams": {"nodes": [{"id": "team-id", "key": "LIN", "name": "Example"}]}}
        if "query Projects" in query:
            return {"projects": {"nodes": [{"id": "project-id", "name": "Example Project"}]}}
        if "query Labels" in query:
            return {
                "issueLabels": {
                    "nodes": [
                        {"id": "bug-label", "name": "Bug"},
                        {"id": "product-label", "name": "Product"},
                    ]
                }
            }
        if "query Views" in query:
            return {"customViews": {"nodes": self.views}}
        if "mutation CreateCustomView" in query:
            input_data = variables["input"]
            created = {
                "id": "view-id",
                "name": input_data["name"],
                "slugId": "example-view",
                "shared": input_data["shared"],
                "modelName": "Issue",
                "filterData": input_data.get("filterData"),
                "team": {"id": input_data["teamId"], "key": "LIN", "name": "Example"},
                "creator": {"name": "Tester"},
                "owner": {"name": "Tester"},
            }
            self.views.append(created)
            return {"customViewCreate": {"success": True, "customView": created}}
        raise AssertionError(query)


class CustomViewSetupTest(unittest.TestCase):
    def args(self, **overrides):
        defaults = {
            "name": "Bug Queue",
            "team": "LIN",
            "project": "Example Project",
            "label": ["Bug"],
            "description": None,
            "color": None,
            "icon": None,
            "open_only": True,
            "private": False,
            "dry_run": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_existing_view_is_noop(self) -> None:
        client = FakeClient(
            [
                {
                    "id": "view-id",
                    "name": "Bug Queue",
                    "slugId": "bug-queue",
                    "shared": True,
                    "modelName": "Issue",
                    "filterData": {},
                    "team": {"id": "team-id", "key": "LIN", "name": "Example"},
                    "creator": {"name": "Tester"},
                    "owner": {"name": "Tester"},
                }
            ]
        )

        result = custom_view_setup.build_result(client, self.args())

        self.assertEqual(result["action"], "exists")
        self.assertNotIn("mutation", "\n".join(client.queries).casefold())

    def test_missing_view_is_created_with_expected_payload(self) -> None:
        client = FakeClient()

        result = custom_view_setup.build_result(client, self.args(label=["Bug", "Product"]))

        self.assertEqual(result["action"], "created")
        create_variables = next(
            variables for query, variables in zip(client.queries, client.variables)
            if "mutation CreateCustomView" in query
        )
        self.assertEqual(create_variables["input"]["teamId"], "team-id")
        self.assertEqual(create_variables["input"]["projectId"], "project-id")
        self.assertTrue(create_variables["input"]["shared"])
        self.assertEqual(create_variables["input"]["filterData"], result["target"]["filterData"])

    def test_dry_run_does_not_create_missing_view(self) -> None:
        client = FakeClient()

        result = custom_view_setup.build_result(client, self.args(dry_run=True))

        self.assertEqual(result["action"], "dry_run")
        self.assertNotIn("mutation", "\n".join(client.queries).casefold())

    def test_filter_payload_combines_open_state_and_labels(self) -> None:
        payload = custom_view_setup.build_filter_data(
            [{"id": "bug-label", "name": "Bug"}],
            open_only=True,
        )

        self.assertEqual(
            payload,
            {
                "and": [
                    {"state": {"type": {"nin": ["completed", "canceled"]}}},
                    {
                        "labels": {
                            "and": [
                                {
                                    "or": [
                                        {"name": {"eq": "Bug"}},
                                        {"parent": {"name": {"eq": "Bug"}}},
                                    ]
                                }
                            ]
                        }
                    },
                ]
            },
        )

    def test_missing_label_is_controlled_error(self) -> None:
        client = FakeClient()

        with self.assertRaises(custom_view_setup.LinearApiError) as error:
            custom_view_setup.build_result(client, self.args(label=["Missing"], dry_run=True))

        self.assertEqual(error.exception.category, "not_found")


if __name__ == "__main__":
    unittest.main()
