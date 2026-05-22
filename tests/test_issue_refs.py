#!/usr/bin/env python3
from __future__ import annotations

import unittest

from linear_common.issue_refs import parse_issue_reference


class IssueReferenceTest(unittest.TestCase):
    def test_identifier_is_stable_lookup(self) -> None:
        reference = parse_issue_reference("lin-123")

        self.assertEqual(reference.lookup, "LIN-123")
        self.assertEqual(reference.input_kind, "issue_identifier")

    def test_url_with_identifier_is_stable_lookup(self) -> None:
        reference = parse_issue_reference("https://linear.app/example/issue/LIN-123/fixture")

        self.assertEqual(reference.lookup, "LIN-123")
        self.assertEqual(reference.input_kind, "url_with_identifier")

    def test_uuid_is_raw_entity_lookup_with_hint(self) -> None:
        reference = parse_issue_reference("123e4567-e89b-12d3-a456-426614174000")

        self.assertEqual(reference.lookup, "123e4567-e89b-12d3-a456-426614174000")
        self.assertEqual(reference.input_kind, "uuid_or_raw")
        self.assertIn("another Linear entity UUID", reference.hint)

    def test_url_without_identifier_is_reported(self) -> None:
        reference = parse_issue_reference("https://linear.app/example/comment/123e4567-e89b-12d3-a456-426614174000")

        self.assertEqual(reference.lookup, "123e4567-e89b-12d3-a456-426614174000")
        self.assertEqual(reference.input_kind, "url_without_identifier")
        self.assertIn("does not contain an issue key", reference.hint)


if __name__ == "__main__":
    unittest.main()
