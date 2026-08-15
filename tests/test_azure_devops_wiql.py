"""WIQL injection via the tenant-supplied project name (Factory#721).

``AzureDevOpsProvider.fetch_issues`` builds a WIQL query and there is nothing to
bind against: the REST endpoint takes one opaque ``query`` string, so the Azure
DevOps project name — tenant-supplied configuration under RFC-0020 — has to be
interpolated into a WHERE clause. Before the fix it was interpolated raw, so a
project name containing ``'`` closed the string literal and the remainder of the
name was parsed as query syntax.

What these tests assert is deliberately not "the output contains two quotes".
A quote-doubling that is off by one still contains two quotes. The check that
matters is a round trip: read the literal back out of the emitted query with a
reader that follows WIQL's own escaping rule, and require that (a) it decodes to
the project name byte for byte, and (b) nothing is left over after it. (b) is
the injection: any character of the project name that survives OUTSIDE the
literal is a character the tenant contributed to the query's structure.

OWASP: A03:2021 Injection.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

# httpx is an optional test-time dependency and is deliberately NOT imported by
# name: the ratchet's mypy runs without it installed, and `Any` here is honest
# about that rather than papering over it with an ignore that goes stale.
httpx = pytest.importorskip("httpx")

# `providers` is on sys.path courtesy of tests/conftest.py.
from providers.azure_devops_provider import (  # noqa: E402
    AzureDevOpsProvider,
    _wiql_literal,
)

# Not a credential: an opaque literal, so assertions stay meaningful.
_FAKE_PAT = "azure-pat-placeholder"

# Project names a tenant can legitimately configure, then the hostile ones. The
# benign entries matter as much as the attacks: an apostrophe is ordinary in a
# real project name, so any escaping that mangles "O'Brien Analytics" would be a
# fix that breaks paying tenants.
_PROJECTS = [
    "Contoso",
    "Contoso Web Platform",
    "O'Brien Analytics",
    "it's mine",
    "''",
    "' OR 1=1 --",
    "x' AND [System.State] = 'Closed",
    "' OR [System.AssignedTo] = @Me OR [System.TeamProject] <> '",
]


def _read_wiql_literal(text: str) -> tuple[str, str]:
    """Decode a leading WIQL single-quoted literal; return (value, remainder).

    This is the reader a WIQL parser would use, written independently of the
    escaping helper so that the test cannot pass by sharing its bug: an opening
    quote, then characters until a quote that is not doubled, with each doubled
    quote decoding to one literal quote.
    """
    if not text.startswith("'"):
        msg = f"not a quoted literal: {text!r}"
        raise AssertionError(msg)
    out: list[str] = []
    i = 1
    while i < len(text):
        char = text[i]
        if char != "'":
            out.append(char)
            i += 1
        elif text[i : i + 2] == "''":
            out.append("'")
            i += 2
        else:
            return "".join(out), text[i + 1 :]
        continue
    msg = f"unterminated literal: {text!r}"
    raise AssertionError(msg)


@pytest.mark.parametrize("project", _PROJECTS)
def test_wiql_literal_round_trips_and_consumes_everything(project: str) -> None:
    """The helper's output decodes back to the input with no leftover syntax."""
    value, remainder = _read_wiql_literal(_wiql_literal(project))
    assert value == project
    assert remainder == ""


def _query_for(project: str) -> str:
    """Drive ``fetch_issues`` against a mock transport and return the WIQL sent."""
    captured: list[str] = []

    def handler(request: Any) -> Any:
        if request.url.path.endswith("/_apis/wit/wiql"):
            captured.append(json.loads(request.content)["query"])
            return httpx.Response(200, json={"workItems": []})
        return httpx.Response(200, json={})

    provider = AzureDevOpsProvider(
        _repo="widgets",
        _pat=_FAKE_PAT,
        _organization="acme",
        _project=project,
    )
    transport = httpx.MockTransport(handler)
    provider._client = lambda: httpx.AsyncClient(transport=transport, timeout=30.0)

    asyncio.run(provider.fetch_issues())
    assert captured, "fetch_issues did not POST a WIQL query"
    return captured[0]


_MARKER = "[System.TeamProject] = "


def _split_at_project(query: str) -> tuple[str, str]:
    assert _MARKER in query, query
    return _read_wiql_literal(query.split(_MARKER, 1)[1])


@pytest.mark.parametrize("project", _PROJECTS)
def test_project_name_cannot_escape_the_where_clause(project: str) -> None:
    """No character of the project name reaches the query outside its literal.

    The remainder — everything after the project literal — is compared against
    the remainder produced by a benign project name. It has to be byte-identical:
    the tenant may fill the literal, and may contribute nothing at all to the
    query's structure. Without the fix, ``"' OR 1=1 --"`` leaves ``OR 1=1 --``
    sitting in the WHERE clause and the two remainders diverge.
    """
    value, remainder = _split_at_project(_query_for(project))
    _, benign_remainder = _split_at_project(_query_for("Contoso"))

    assert value == project
    assert remainder == benign_remainder


def test_state_filter_still_applies() -> None:
    """The escaping did not disturb the clause the provider appends after it."""
    query = _query_for("Contoso")
    assert "[System.TeamProject] = 'Contoso'" in query
    assert "SELECT [System.Id]" in query
