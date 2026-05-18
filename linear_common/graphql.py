"""Shared Linear GraphQL client utilities."""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_URL = "https://api.linear.app/graphql"
ENV_KEY = "LINEAR_API_KEY"


class LinearApiError(Exception):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.message = message


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return values

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def candidate_env_files(env_file: str | None = None, cwd: Path | None = None) -> list[Path]:
    paths: list[Path] = []
    if env_file:
        paths.append(Path(env_file).expanduser())
    if os.environ.get("LINEAR_ENV_FILE"):
        paths.append(Path(os.environ["LINEAR_ENV_FILE"]).expanduser())

    search_root = cwd or Path.cwd()
    for base in [search_root, *search_root.parents]:
        paths.extend([base / ".env.local", base / ".env"])

    paths.append(search_root / "app" / ".env.local")

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve() if path.exists() else path
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(path)
    return deduped


def resolve_api_key(env_file: str | None = None) -> str:
    token = os.environ.get(ENV_KEY)
    if token:
        return token

    for path in candidate_env_files(env_file):
        values = parse_env_file(path)
        token = values.get(ENV_KEY)
        if token:
            return token

    raise LinearApiError(
        "missing_api_key",
        "LINEAR_API_KEY was not found in the environment, LINEAR_ENV_FILE, --env-file, "
        "or local .env files.",
    )


def build_ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore[import-not-found]

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def sanitize_text(value: str, token: str | None = None) -> str:
    sanitized = value
    if token:
        sanitized = sanitized.replace(token, "[redacted]")
    return sanitized


class LinearClient:
    def __init__(self, api_url: str, token: str) -> None:
        self.api_url = api_url
        self.token = token

    def gql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        request = urllib.request.Request(
            self.api_url,
            data=body,
            method="POST",
            headers={
                "Authorization": self.token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, context=build_ssl_context()) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = sanitize_text(exc.read().decode("utf-8", errors="replace"), self.token)
            category = "permission_denied" if exc.code in {401, 403} else "network"
            raise LinearApiError(category, f"Linear API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            reason = sanitize_text(str(exc.reason), self.token)
            raise LinearApiError("network", f"Linear API request failed: {reason}") from exc

        if payload.get("errors"):
            errors = sanitize_text(json.dumps(payload["errors"], ensure_ascii=False, indent=2), self.token)
            raise LinearApiError("network", errors)
        return payload["data"]

