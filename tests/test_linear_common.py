#!/usr/bin/env python3
from __future__ import annotations

import builtins
import sys
import unittest
import urllib.error
from types import SimpleNamespace
from unittest import mock

from linear_common import graphql as linear_graphql


class LinearCommonTest(unittest.TestCase):
    def test_build_ssl_context_uses_certifi_when_available(self) -> None:
        sentinel = object()
        fake_certifi = SimpleNamespace(where=lambda: "/tmp/certifi.pem")

        with mock.patch.dict(sys.modules, {"certifi": fake_certifi}):
            with mock.patch.object(linear_graphql.ssl, "create_default_context", return_value=sentinel) as create:
                result = linear_graphql.build_ssl_context()

        self.assertIs(result, sentinel)
        create.assert_called_once_with(cafile="/tmp/certifi.pem")

    def test_build_ssl_context_falls_back_when_certifi_missing(self) -> None:
        sentinel = object()
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "certifi":
                raise ImportError("missing certifi")
            return original_import(name, *args, **kwargs)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            with mock.patch.object(linear_graphql.ssl, "create_default_context", return_value=sentinel) as create:
                result = linear_graphql.build_ssl_context()

        self.assertIs(result, sentinel)
        create.assert_called_once_with()

    def test_client_error_sanitizes_api_key(self) -> None:
        token = "secret-token-for-test"

        def failing_urlopen(_request, context=None):
            raise urllib.error.URLError(f"certificate failed for {token}")

        client = linear_graphql.LinearClient("https://api.example/graphql", token)
        with mock.patch.object(linear_graphql.urllib.request, "urlopen", side_effect=failing_urlopen):
            with self.assertRaises(linear_graphql.LinearApiError) as error:
                client.gql("query Test { viewer { id } }")

        self.assertNotIn(token, error.exception.message)
        self.assertIn("[redacted]", error.exception.message)


if __name__ == "__main__":
    unittest.main()
