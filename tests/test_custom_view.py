#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "linear-custom-view" / "scripts" / "custom_view.py"
SPEC = importlib.util.spec_from_file_location("custom_view", SCRIPT)
assert SPEC and SPEC.loader
custom_view = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = custom_view
SPEC.loader.exec_module(custom_view)


class FakeClient:
    def __init__(self, views):
        self.views = views

    def gql(self, query, variables=None):
        if "customView(id:" in query:
            lookup = (variables or {}).get("id")
            direct = next(
                (
                    view
                    for view in self.views
                    if view["id"] == lookup or view.get("slugId") == lookup
                ),
                None,
            )
            return {"customView": direct}
        return {"customViews": {"nodes": self.views}}


class CustomViewTest(unittest.TestCase):
    def test_first_actionable_preserves_manual_order(self) -> None:
        issues = [
            {
                "identifier": "LIN-1",
                "title": "Already done",
                "sortOrder": 100,
                "state": {"name": "Done", "type": "completed"},
            },
            {
                "identifier": "LIN-2",
                "title": "Next task",
                "sortOrder": 200,
                "state": {"name": "Todo", "type": "unstarted"},
            },
        ]
        first = custom_view.first_actionable_issue(issues, {"slugId": "queue-123"})
        self.assertEqual(first["row_index"], 2)
        self.assertEqual(first["identifier"], "LIN-2")
        self.assertEqual(first["manual_order"], 200)

    def test_ambiguous_view_lookup_lists_matches(self) -> None:
        client = FakeClient(
            [
                {"id": "1", "name": "Team Queue Alpha", "slugId": "alpha"},
                {"id": "2", "name": "Team Queue Beta", "slugId": "beta"},
            ]
        )
        with self.assertRaises(SystemExit) as error:
            custom_view.find_view(client, "Team Queue")
        self.assertIn("ambiguous", str(error.exception).casefold())

    def test_view_lookup_can_use_slug_directly(self) -> None:
        client = FakeClient(
            [
                {"id": "1", "name": "Team Queue Alpha", "slugId": "alpha"},
                {"id": "2", "name": "Team Queue Beta", "slugId": "beta"},
            ]
        )

        found = custom_view.find_view(client, "https://linear.app/example/view/beta")

        self.assertEqual(found["id"], "2")
        self.assertEqual(found["slugId"], "beta")

    def test_filter_explanation_includes_filter_data(self) -> None:
        explanation = custom_view.filter_explanation({"filterData": {"state": "not_completed"}})
        self.assertEqual(explanation["filter_data"], {"state": "not_completed"})
        self.assertIn("visible", explanation["note"])

    def test_first_matching_issue_reports_skipped_rows(self) -> None:
        issues = [
            {
                "identifier": "LIN-117",
                "title": "[Blocked] Check HTML prototypes",
                "sortOrder": -10,
                "state": {"name": "Backlog", "type": "backlog"},
                "labels": ["Blocked"],
            },
            {
                "identifier": "LIN-81",
                "title": "P1-01: Publish package metadata",
                "sortOrder": -9,
                "state": {"name": "Backlog", "type": "backlog"},
                "labels": ["Platform", "Publish"],
            },
        ]

        class Args:
            expect_label = ["Platform"]
            exclude_label = ["Blocked"]
            expect_title_regex = ["P1-"]
            skip_title_regex = [r"^\[Blocked\]"]

        selector = custom_view.build_issue_selector(Args)
        first, skipped = custom_view.first_matching_issue_with_skips(
            issues, {"slugId": "platform-queue"}, selector
        )

        self.assertEqual(first["row_index"], 2)
        self.assertEqual(first["identifier"], "LIN-81")
        self.assertEqual(skipped[0]["identifier"], "LIN-117")
        self.assertIn("excluded label", skipped[0]["reason"])


if __name__ == "__main__":
    unittest.main()
