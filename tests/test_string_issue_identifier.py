"""Guard: the work-item identifier is a string everywhere it is typed (Factory#3774).

An all-digit string behaves exactly like today's integer; a non-numeric key
(Jira's ``PROJ-123``) round-trips through the contract and is refused, with a
clear error, by providers whose API needs an integer.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import contract_schema as cs
import pytest

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "shared" / "factory-github"))
sys.path.insert(0, str(_ROOT / "shared" / "factory-contracts" / "python"))
pytest.importorskip("httpx", reason="provider modules import httpx at module scope")
fc = pytest.importorskip("factory_contracts")
from providers import as_issue_int, fanout_comments  # noqa: E402
from providers._github_json import (  # noqa: E402
    group_bulk_comments,
    issue_number_from_url,
)
from providers.github_provider import GitHubProvider  # noqa: E402


def _provenance_errors(issue_number: Any) -> list[str]:
    schema = cs.schema("task-contract.schema.json")
    sub = dict(schema["properties"]["provenance"])
    sub["$defs"] = schema["$defs"]
    return cs.error_messages(sub, {"issue_number": issue_number})


@pytest.mark.parametrize("value", [5, "5", "PROJ-1"])
def test_schema_accepts_integer_and_string(value: Any) -> None:
    assert _provenance_errors(value) == []


def test_schema_still_rejects_other_types() -> None:
    assert _provenance_errors(1.5) != []


@pytest.mark.parametrize("value", [5, "5"])
def test_contract_model_normalises_to_the_decimal_string(value: Any) -> None:
    assert fc.CorrelationBlock(issue_number=value).issue_number == "5"
    assert fc.CorrelationBlock(issue_number="PROJ-1").issue_number == "PROJ-1"
    assert fc.CorrelationBlock().issue_number is None


def test_as_issue_int() -> None:
    assert as_issue_int("42") == 42
    assert as_issue_int(42) == 42
    for bad in ("PROJ-1", "", "-3", "4.2", "٣"):
        with pytest.raises(ValueError, match="not numeric for GitLab"):
            as_issue_int(bad, "GitLab")


def test_issue_url_yields_a_string_and_grouping_keys_by_string() -> None:
    assert issue_number_from_url("https://api.github.com/repos/o/r/issues/7") == "7"
    assert issue_number_from_url("https://api.github.com/repos/o/r/issues/x") is None
    grouped = group_bulk_comments([{"issue_url": "https://x/issues/7", "id": 1}], ["7", "8"])
    assert set(grouped) == {"7", "8"} and len(grouped["7"]) == 1 and grouped["8"] == []


class _NoCalls:
    """A gh client that fails the test if the provider reaches it."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"gh client reached: {name}")


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("fetch_issue", ()),
        ("fetch_comments", ()),
        ("add_comment", ("x",)),
        ("assign_to_user", (["bob"],)),
    ],
)
def test_github_refuses_a_non_numeric_key_before_any_call(
    method: str, args: tuple[Any, ...]
) -> None:
    provider = GitHubProvider.__new__(GitHubProvider)
    provider._repo = "o/r"
    provider._gh_client = _NoCalls()
    with pytest.raises(ValueError, match="not numeric for GitHub"):
        asyncio.run(getattr(provider, method)("PROJ-1", *args))


def test_fanout_keys_are_canonical_decimal_strings() -> None:
    class _P:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def fetch_comments(self, ref: str, **_: Any) -> list[Any]:
            self.calls.append(ref)
            return []

    p = _P()
    assert asyncio.run(fanout_comments(p, ["007", "7", 7, "PROJ-1"])) == {"7": [], "PROJ-1": []}
    assert p.calls == ["7", "PROJ-1"]
