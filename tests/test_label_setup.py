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


SCRIPT = Path(__file__).resolve().parents[1] / "linear-label-setup" / "scripts" / "label_setup.py"
SPEC = importlib.util.spec_from_file_location("label_setup", SCRIPT)
assert SPEC and SPEC.loader
label_setup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = label_setup
SPEC.loader.exec_module(label_setup)


class FakeClient:
    def __init__(self, labels=None) -> None:
        self.labels = list(labels or [])
        self.queries: list[str] = []
        self.variables: list[dict] = []

    def gql(self, query, variables=None):
        self.queries.append(query)
        self.variables.append(variables or {})
        if "query Teams" in query:
            return {"teams": {"nodes": [{"id": "team-id", "key": "LIN", "name": "Example"}]}}
        if "query Labels" in query:
            return {"issueLabels": {"nodes": self.labels}}
        if "mutation CreateLabel" in query:
            input_data = variables["input"]
            created = {
                "id": f"label-{len(self.labels) + 1}",
                "name": input_data["name"],
                "description": input_data.get("description"),
                "color": input_data.get("color"),
                "team": {"id": "team-id", "key": "LIN", "name": "Example"},
            }
            self.labels.append(created)
            return {"issueLabelCreate": {"success": True, "issueLabel": created}}
        raise AssertionError(query)


class LabelSetupTest(unittest.TestCase):
    def args(self, **overrides):
        defaults = {
            "team": "LIN",
            "label": ["Bug"],
            "description": None,
            "color": None,
            "dry_run": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_existing_label_is_noop(self) -> None:
        client = FakeClient([{"id": "bug-label", "name": "Bug", "description": None, "color": None}])

        result = label_setup.build_result(client, self.args())

        self.assertEqual(result["labels"][0]["action"], "exists")
        self.assertNotIn("mutation", "\n".join(client.queries).casefold())

    def test_missing_label_is_created(self) -> None:
        client = FakeClient()

        result = label_setup.build_result(
            client,
            self.args(description="Defects", color="#ff0000"),
        )

        self.assertEqual(result["labels"][0]["action"], "created")
        create_variables = next(
            variables for query, variables in zip(client.queries, client.variables)
            if "mutation CreateLabel" in query
        )
        self.assertEqual(create_variables["input"]["teamId"], "team-id")
        self.assertEqual(create_variables["input"]["name"], "Bug")
        self.assertEqual(create_variables["input"]["description"], "Defects")
        self.assertEqual(create_variables["input"]["color"], "#ff0000")

    def test_dry_run_does_not_create_missing_label(self) -> None:
        client = FakeClient()

        result = label_setup.build_result(client, self.args(dry_run=True))

        self.assertEqual(result["labels"][0]["action"], "would_create")
        self.assertNotIn("mutation", "\n".join(client.queries).casefold())

    def test_duplicate_label_is_controlled_error(self) -> None:
        client = FakeClient(
            [
                {"id": "bug-label-1", "name": "Bug"},
                {"id": "bug-label-2", "name": "Bug"},
            ]
        )

        with self.assertRaises(label_setup.LinearApiError) as error:
            label_setup.build_result(client, self.args())

        self.assertEqual(error.exception.category, "ambiguous_lookup")

    def test_shared_client_redacts_token_from_errors(self) -> None:
        token = "secret-token-for-test"

        def failing_urlopen(_request, context=None):
            raise urllib.error.URLError(f"certificate failed for {token}")

        client = label_setup.LinearClient("https://api.example/graphql", token)
        with mock.patch.object(linear_graphql.urllib.request, "urlopen", side_effect=failing_urlopen):
            with self.assertRaises(label_setup.LinearApiError) as error:
                client.gql("query Test { viewer { id } }")

        self.assertNotIn(token, error.exception.message)
        self.assertIn("[redacted]", error.exception.message)


if __name__ == "__main__":
    unittest.main()
