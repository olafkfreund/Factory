"""``assign_to_user`` behaves identically on both GitHub transports (Factory#3773).

The GraphQL assignment algorithm (resolve suggested actors, translate the
``Copilot`` alias to ``copilot-swe-agent``, replace the issue's actors) used to
live only in ``GitHubProvider``. ``HttpGitHubProvider`` needs it too, so it is
one shared helper; these cases are ported from AIFactory's
``tests/test_git_providers_assign.py`` and run against BOTH providers through
their one transport seam, ``_graphql(query, variables)``, so the Copilot
semantics cannot drift between the gh-CLI and the token transport.

Held in place: the alias is case-insensitive, a disabled Copilot agent is a
silent no-op (the caller verifies by re-reading the issue), and nothing is
mutated when no actor resolves.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

_SHARED = Path(__file__).resolve().parents[1] / "shared" / "factory-github"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

pytest.importorskip("httpx", reason="provider modules import httpx at module scope")

from providers.github_provider import GitHubProvider  # noqa: E402
from providers.http_github_provider import HttpGitHubProvider  # noqa: E402

_BOT = {"login": "copilot-swe-agent", "__typename": "Bot", "id": "BOT_ID"}
_ALICE = {"login": "alice", "__typename": "User", "id": "ALICE_ID"}


def _actors(*nodes: dict[str, Any]) -> dict[str, Any]:
    return {"data": {"repository": {"id": "R", "suggestedActors": {"nodes": list(nodes)}}}}


_ISSUE = {"data": {"repository": {"issue": {"id": "ISSUE_ID"}}}}
_MUTATION = {"data": {"replaceActorsForAssignable": {"assignable": {"number": 42}}}}


def _provider(kind: str, responses: list[dict[str, Any]]) -> tuple[Any, list[dict[str, Any]]]:
    """A provider whose ``_graphql`` replays ``responses`` and records variables."""
    seen: list[dict[str, Any]] = []
    queue = list(responses)

    async def fake_graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
        seen.append({"query": query, **variables})
        return queue.pop(0)

    if kind == "gh":
        provider: Any = GitHubProvider(_repo="acme/widgets", _gh_client=object())
    else:
        provider = HttpGitHubProvider(_repo="acme/widgets", _token="t")  # noqa: S106
    provider._graphql = fake_graphql
    return provider, seen


@pytest.fixture(params=["gh", "http"])
def kind(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def test_copilot_alias_assigns_the_agent(kind: str) -> None:
    provider, seen = _provider(kind, [_actors(_BOT, _ALICE), _ISSUE, _MUTATION])

    asyncio.run(provider.assign_to_user(42, ["Copilot"]))

    assert len(seen) == 3, "actor lookup, issue lookup, mutation"
    assert "replaceActorsForAssignable" in seen[2]["query"]
    assert seen[2]["assignableId"] == "ISSUE_ID"
    assert seen[2]["actorIds"] == ["BOT_ID"]
    assert seen[1]["number"] == 42
    assert (seen[0]["owner"], seen[0]["name"]) == ("acme", "widgets")


def test_disabled_copilot_is_a_silent_noop(kind: str) -> None:
    provider, seen = _provider(kind, [_actors(_ALICE)])

    asyncio.run(provider.assign_to_user(42, ["Copilot"]))

    assert len(seen) == 1, "only the actor lookup fires; no issue lookup, no mutation"


def test_alias_is_case_insensitive_and_mixes_with_real_logins(kind: str) -> None:
    provider, seen = _provider(kind, [_actors(_BOT, _ALICE), _ISSUE, _MUTATION])

    asyncio.run(provider.assign_to_user(42, ["COPILOT", "alice", "nobody"]))

    assert seen[2]["actorIds"] == ["BOT_ID", "ALICE_ID"], "unknown login dropped, order kept"


def test_unresolvable_logins_mutate_nothing(kind: str) -> None:
    provider, seen = _provider(kind, [_actors(_ALICE)])

    asyncio.run(provider.assign_to_user(42, ["nobody"]))

    assert len(seen) == 1


def test_empty_assignees_make_no_calls(kind: str) -> None:
    provider, seen = _provider(kind, [])

    asyncio.run(provider.assign_to_user(42, []))

    assert seen == []


def test_missing_issue_node_skips_the_mutation(kind: str) -> None:
    provider, seen = _provider(kind, [_actors(_BOT), {"data": {"repository": {"issue": None}}}])

    asyncio.run(provider.assign_to_user(42, ["Copilot"]))

    assert len(seen) == 2
