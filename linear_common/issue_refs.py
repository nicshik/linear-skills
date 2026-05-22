"""Shared Linear issue reference parsing utilities."""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass


ISSUE_IDENTIFIER_RE = re.compile(r"(?<![A-Z0-9-])[A-Z][A-Z0-9]+-\d+(?![A-Z0-9-])", flags=re.IGNORECASE)
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class IssueReference:
    raw: str
    lookup: str
    input_kind: str
    hint: str


def parse_issue_reference(value: str) -> IssueReference:
    raw = value.strip()
    if not raw:
        return IssueReference(
            raw=value,
            lookup="",
            input_kind="empty",
            hint="Issue reference is empty. Pass a stable issue key such as LIN-123.",
        )

    parsed = urllib.parse.urlparse(raw)
    is_url = bool(parsed.scheme and parsed.netloc)
    text = urllib.parse.unquote(parsed.path if is_url else raw)
    identifier_match = ISSUE_IDENTIFIER_RE.search(text)
    if identifier_match:
        return IssueReference(
            raw=value,
            lookup=identifier_match.group(0).upper(),
            input_kind="url_with_identifier" if is_url else "issue_identifier",
            hint="Verify that the issue key belongs to the expected Linear workspace and is visible to the token.",
        )

    lookup = raw
    input_kind = "uuid_or_raw"
    if is_url:
        path_parts = [part for part in text.split("/") if part]
        lookup = path_parts[-1] if path_parts else raw
        input_kind = "url_without_identifier"
    elif UUID_RE.match(raw):
        input_kind = "uuid_or_raw"

    if input_kind == "url_without_identifier":
        hint = "The URL does not contain an issue key such as LIN-123. Retry with a Linear issue URL or stable issue key."
    else:
        hint = (
            "The value is not a stable issue key. It may be another Linear entity UUID or raw id; "
            "retry with an issue key such as LIN-123 and verify workspace access."
        )

    return IssueReference(raw=value, lookup=lookup, input_kind=input_kind, hint=hint)


def issue_not_found_details(reference: IssueReference) -> dict[str, str]:
    return {
        "error_code": "issue_not_found",
        "lookup": reference.lookup,
        "input_kind": reference.input_kind,
        "hint": reference.hint,
    }


def is_issue_entity_not_found_message(value: str) -> bool:
    normalized = value.casefold()
    return "entity not found" in normalized and "issue" in normalized
