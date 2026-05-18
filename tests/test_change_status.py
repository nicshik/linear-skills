#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path

from linear_common import graphql as linear_graphql


SCRIPT = Path(__file__).resolve().parents[1] / "linear-change-status" / "scripts" / "change_status.py"
SPEC = importlib.util.spec_from_file_location("change_status", SCRIPT)
assert SPEC and SPEC.loader
change_status = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = change_status
SPEC.loader.exec_module(change_status)


class FakeClient:
    def __init__(self, initial_state_id: str = "done") -> None:
        self.initial_state_id = initial_state_id

    def gql(self, query, variables=None):
        if "query Issue" in query:
            return {
                "issue": {
                    "id": "issue-id",
                    "identifier": "LIN-1",
                    "title": "Fixture",
                    "completedAt": "2026-05-07T00:00:00.000Z",
                    "state": {"id": self.initial_state_id, "name": "Done", "type": "completed"},
                    "team": {"id": "team-id", "key": "LIN", "name": "Example"},
                }
            }
        if "query States" in query:
            return {
                "workflowStates": {
                    "nodes": [
                        {"id": "todo", "name": "Todo", "type": "unstarted"},
                        {"id": "done", "name": "Done", "type": "completed"},
                    ]
                }
            }
        if "mutation UpdateIssue" in query:
            return {
                "issueUpdate": {
                    "success": True,
                    "issue": {
                        "id": "issue-id",
                        "identifier": "LIN-1",
                        "title": "Fixture",
                        "completedAt": "2026-05-07T00:00:00.000Z",
                        "state": {"id": variables["input"]["stateId"], "name": "Done", "type": "completed"},
                    },
                }
            }
        if "query Verify" in query:
            return {
                "issue": {
                    "id": "issue-id",
                    "identifier": "LIN-1",
                    "title": "Fixture",
                    "completedAt": "2026-05-07T00:00:00.000Z",
                    "state": {"id": "done", "name": "Done", "type": "completed"},
                }
            }
        raise AssertionError(query)


class ChangeStatusTest(unittest.TestCase):
    def test_noop_reports_already_in_target(self) -> None:
        result = change_status.change_issue_status(FakeClient(), "LIN-1", "Done", dry_run=False)
        self.assertEqual(result["action"], "noop")
        self.assertEqual(result["error_category"], "already_in_target")

    def test_unknown_target_status_has_error_category(self) -> None:
        with self.assertRaises(change_status.LinearToolError) as error:
            change_status.find_target_state(
                [{"id": "todo", "name": "Todo", "type": "unstarted"}],
                "Not A Real Status",
            )
        self.assertEqual(error.exception.category, "ambiguous_status")

    def test_missing_key_error_uses_controlled_message(self) -> None:
        old = os.environ.pop("LINEAR_API_KEY", None)
        old_env_file = os.environ.pop("LINEAR_ENV_FILE", None)
        original_candidate_env_files = linear_graphql.candidate_env_files
        linear_graphql.candidate_env_files = lambda env_file=None: []
        try:
            with self.assertRaises(change_status.LinearApiError) as error:
                change_status.resolve_api_key(None)
            self.assertIn("LINEAR_API_KEY was not found", str(error.exception))
        finally:
            linear_graphql.candidate_env_files = original_candidate_env_files
            if old is not None:
                os.environ["LINEAR_API_KEY"] = old
            if old_env_file is not None:
                os.environ["LINEAR_ENV_FILE"] = old_env_file


if __name__ == "__main__":
    unittest.main()
