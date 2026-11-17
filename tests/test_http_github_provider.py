"""Token-authenticated GitHub provider (Factory#370).

The defect: the canonical ``GitHubProvider`` drives the ``gh`` CLI, so it cannot
serve a caller that must supply its own credential. Two things follow, and the
second is the dangerous one:

* a server image has no ``gh`` binary at all;
* ``gh`` uses whatever credential is AMBIENT. CFactory found during RFC-0019
  Phase 6 that an ambient login silently switched issue-writing on and the board
  filed real issues. A per-tenant credential cannot come from a process-wide
  login — there is one ``gh`` session per process and many tenants.

The guard that matters is therefore not "a REST provider exists" but "supplying
a token can never yield an ambient-auth provider".
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_SHARED = Path(__file__).resolve().parents[1] / "shared" / "factory-github"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

httpx = pytest.importorskip("httpx")

from providers.factory import get_provider  # noqa: E402
from providers.github_provider import GitHubProvider  # noqa: E402
from providers.http_github_provider import HttpGitHubProvider  # noqa: E402
from providers.protocol import (  # noqa: E402
    IssueFilters,
    LabelData,
    ProviderCommentError,
    ProviderType,
    WorkItemProvider,
)

# Not a credential: an opaque literal so assertions about where it does and does
# not appear are meaningful.
_FAKE_TOKEN = "github-token-placeholder"  # noqa: S105 - a literal, not a credential
_REPO = "acme/widgets"


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


# ── the guard: an explicit token must never become ambient auth ──────────────


def test_a_token_selects_the_rest_provider_not_the_gh_cli():
    """MUTATION GUARD: the reported bug.

    Handing the factory a credential must not produce a provider that ignores it
    and uses whatever ``gh`` is logged in as. That substitution is not a degraded
    result — it is a request made as the WRONG IDENTITY.
    """
    provider = get_provider("github", _REPO, token=_FAKE_TOKEN)

    assert isinstance(provider, HttpGitHubProvider)
    assert not isinstance(provider, GitHubProvider)


def test_an_empty_token_still_refuses_the_ambient_provider():
    """MUTATION GUARD: `token=None` is not the same as "no token given".

    A caller resolving a per-tenant credential that came back empty is the case
    most likely to fall through to ambient auth, and the one where doing so is
    worst: the tenant's own credential is missing, so ``gh``'s login is
    guaranteed to be someone else's. The branch turns on whether the key was
    PASSED, not on whether it is truthy.
    """
    provider = get_provider("github", _REPO, token=None)

    assert isinstance(provider, HttpGitHubProvider)


def test_no_token_keeps_the_gh_cli_provider_unchanged():
    """The existing default must not move — every runner depends on it."""
    provider = get_provider("github", _REPO)

    assert isinstance(provider, GitHubProvider)


def test_the_token_is_not_rendered_in_repr():
    """Factory#372's rule, applied to the new credential-bearing provider.

    A dataclass renders every field by default, so this is one `logger.debug(
    "provider=%s", provider)` away from a leaked token.
    """
    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN)

    assert _FAKE_TOKEN not in repr(provider)


# ── it actually talks to GitHub ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_token_is_sent_as_a_bearer_credential():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("Authorization", "")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"number": 7, "title": "t", "state": "open"})

    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=_transport(handler))
    issue = await provider.fetch_issue(7)

    assert issue.number == 7
    assert seen["auth"] == f"Bearer {_FAKE_TOKEN}"
    assert seen["url"].endswith("/repos/acme/widgets/issues/7")


@pytest.mark.asyncio
async def test_a_github_enterprise_base_url_is_honoured():
    """A self-hosted host is the reason `_base_url` is configurable at all."""
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        return httpx.Response(200, json={"number": 1})

    provider = HttpGitHubProvider(
        _repo=_REPO,
        _token=_FAKE_TOKEN,
        _base_url="https://github.acme.internal/api/v3",
        _transport=_transport(handler),
    )
    await provider.fetch_issue(1)

    assert seen["host"] == "github.acme.internal"


@pytest.mark.asyncio
async def test_issue_listing_pages_to_completion():
    """MUTATION GUARD: stopping after page one silently imports a third of a backlog.

    That failure looks like success — the caller gets issues, just not all of
    them — so it is the one worth pinning.
    """
    pages = {
        1: [{"number": n} for n in range(1, 101)],
        2: [{"number": n} for n in range(101, 151)],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", 1))
        return httpx.Response(200, json=pages.get(page, []))

    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=_transport(handler))
    # `limit` must be raised explicitly: IssueFilters defaults it to 100, which is
    # also GitHub's page size, so the default can never page by construction and
    # a paging test written without this passes against a one-page implementation.
    issues = await provider.fetch_issues(IssueFilters(limit=500))

    assert len(issues) == 150


@pytest.mark.asyncio
async def test_pull_requests_are_dropped_from_the_issue_list():
    """`/issues` returns PRs too. A PR is not a work item."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"number": 1},
                {"number": 2, "pull_request": {"url": "..."}},
                {"number": 3},
            ],
        )

    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=_transport(handler))
    issues = await provider.fetch_issues()

    assert [i.number for i in issues] == [1, 3]


@pytest.mark.asyncio
async def test_a_response_without_an_issue_number_is_an_error():
    """The one field with no safe default — a card pointing at nothing is worse."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"title": "no number here"})

    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=_transport(handler))
    with pytest.raises(ValueError, match="no issue number"):
        await provider.create_issue("t", "b")


# ── the seam it deliberately does not cross ──────────────────────────────────


@pytest.mark.asyncio
async def test_the_vcs_half_says_which_provider_to_use_instead():
    """Absent on purpose, and it must say so.

    An AttributeError from deep inside a sync tells the caller nothing. The
    work-item/VCS split is Factory#380's premise too.
    """
    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN)

    for op in ("fetch_pr", "post_review", "merge_pr", "enable_auto_merge"):
        with pytest.raises(NotImplementedError, match="GitHubProvider"):
            await getattr(provider, op)(1)


def test_it_still_reports_itself_as_github():
    """Callers switch on provider_type; a second GitHub class must not look new."""
    assert HttpGitHubProvider(_repo=_REPO).provider_type is ProviderType.GITHUB


# ── the shared comment walk (providers/_github_json.collect_comment_pages) ────


@pytest.mark.asyncio
async def test_comment_paging_walks_every_page():
    pages = {
        1: [{"id": n, "user": {"login": "a"}, "issue_url": ".../1"} for n in range(100)],
        2: [{"id": 100, "user": {"login": "a"}, "issue_url": ".../1"}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=pages.get(int(request.url.params.get("page", 1)), []))

    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=_transport(handler))
    comments = await provider.fetch_comments(1)

    assert len(comments) == 101


@pytest.mark.asyncio
async def test_a_non_list_comment_page_raises_rather_than_truncating():
    """MUTATION GUARD: a truncated thread stored as a whole one is
    indistinguishable from a short one, so this must never return partial data."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": "not a list"})

    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=_transport(handler))
    with pytest.raises(ProviderCommentError, match="non-list"):
        await provider.fetch_comments(1)


@pytest.mark.asyncio
async def test_a_failing_comment_page_raises_rather_than_truncating():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=_transport(handler))
    with pytest.raises(ProviderCommentError, match="comment read failed"):
        await provider.fetch_comments(1)


# ── the rest of the work-item protocol (Factory#3773) ────────────────────────


def _recording(responses: dict[tuple[str, str], Any] | None = None):
    """A transport that records (method, path, body, auth) and replays canned answers."""
    seen: list[tuple[str, str, bytes, str]] = []
    canned = responses or {}

    def handler(request: Any) -> Any:
        seen.append(
            (request.method, request.url.path, request.content, request.headers["Authorization"])
        )
        return canned.get((request.method, request.url.path), httpx.Response(200, json={}))

    return seen, _transport(handler)


def test_it_is_now_a_complete_work_item_provider():
    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN)
    assert isinstance(provider, WorkItemProvider)


@pytest.mark.asyncio
async def test_add_comment_posts_to_the_issues_endpoint_and_returns_the_id():
    seen, transport = _recording(
        {("POST", "/repos/acme/widgets/issues/7/comments"): httpx.Response(201, json={"id": 99})}
    )
    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=transport)

    assert await provider.add_comment(7, "hello") == 99
    method, path, body, auth = seen[0]
    assert (method, path) == ("POST", "/repos/acme/widgets/issues/7/comments")
    assert b'"body":"hello"' in body.replace(b" ", b"")
    assert auth == f"Bearer {_FAKE_TOKEN}"


@pytest.mark.asyncio
async def test_close_issue_comments_first_then_patches_state():
    seen, transport = _recording(
        {("POST", "/repos/acme/widgets/issues/7/comments"): httpx.Response(201, json={"id": 1})}
    )
    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=transport)

    assert await provider.close_issue(7, comment="done") is True
    assert [(m, p) for m, p, _, _ in seen] == [
        ("POST", "/repos/acme/widgets/issues/7/comments"),
        ("PATCH", "/repos/acme/widgets/issues/7"),
    ]
    assert b"closed" in seen[1][2]


@pytest.mark.asyncio
async def test_close_issue_answers_false_on_a_server_error_like_the_gh_provider():
    _, transport = _recording({("PATCH", "/repos/acme/widgets/issues/7"): httpx.Response(500)})
    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=transport)

    assert await provider.close_issue(7) is False


@pytest.mark.asyncio
async def test_apply_labels_posts_the_whole_list():
    seen, transport = _recording()
    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=transport)

    await provider.apply_labels(7, ["bug", "p1"])

    assert seen[0][:2] == ("POST", "/repos/acme/widgets/issues/7/labels")
    assert b'"labels"' in seen[0][2] and b'"p1"' in seen[0][2]


@pytest.mark.asyncio
async def test_remove_labels_deletes_each_quoted_and_tolerates_a_missing_one():
    seen, transport = _recording(
        {("DELETE", "/repos/acme/widgets/issues/7/labels/gone"): httpx.Response(404)}
    )
    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=transport)

    await provider.remove_labels(7, ["good first issue", "gone"])

    assert [(m, p) for m, p, _, _ in seen] == [
        ("DELETE", "/repos/acme/widgets/issues/7/labels/good first issue"),
        ("DELETE", "/repos/acme/widgets/issues/7/labels/gone"),
    ]


@pytest.mark.asyncio
async def test_remove_labels_still_raises_on_a_real_error():
    _, transport = _recording(
        {("DELETE", "/repos/acme/widgets/issues/7/labels/x"): httpx.Response(403)}
    )
    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=transport)

    with pytest.raises(httpx.HTTPStatusError):
        await provider.remove_labels(7, ["x"])


@pytest.mark.asyncio
async def test_create_label_updates_when_it_already_exists():
    exists = httpx.Response(422, json={"errors": [{"code": "already_exists"}]})
    seen, transport = _recording({("POST", "/repos/acme/widgets/labels"): exists})
    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=transport)

    await provider.create_label(LabelData(name="bug", color="d73a4a", description="broken"))

    assert [(m, p) for m, p, _, _ in seen] == [
        ("POST", "/repos/acme/widgets/labels"),
        ("PATCH", "/repos/acme/widgets/labels/bug"),
    ]


@pytest.mark.asyncio
async def test_create_label_does_not_treat_any_422_as_already_existing():
    """MUTATION GUARD: only `already_exists` may fall through to an update."""
    invalid = httpx.Response(422, json={"errors": [{"code": "invalid", "field": "color"}]})
    seen, transport = _recording({("POST", "/repos/acme/widgets/labels"): invalid})
    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=transport)

    with pytest.raises(httpx.HTTPStatusError):
        await provider.create_label(LabelData(name="bug", color="zzz"))
    assert len(seen) == 1, "no PATCH was attempted"


@pytest.mark.asyncio
async def test_list_labels_pages_to_completion():
    def handler(request: Any) -> Any:
        page = int(request.url.params["page"])
        if page == 1:
            return httpx.Response(200, json=[{"name": f"l{i}", "color": "fff"} for i in range(100)])
        return httpx.Response(200, json=[{"name": "last", "color": "000", "description": "d"}])

    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=_transport(handler))

    labels = await provider.list_labels()

    assert len(labels) == 101
    assert labels[-1] == LabelData(name="last", color="000", description="d")


@pytest.mark.asyncio
async def test_assign_to_user_posts_graphql_to_the_api_host():
    urls: list[str] = []

    def handler(request: Any) -> Any:
        urls.append(str(request.url))
        return httpx.Response(
            200, json={"data": {"repository": {"suggestedActors": {"nodes": []}}}}
        )

    provider = HttpGitHubProvider(_repo=_REPO, _token=_FAKE_TOKEN, _transport=_transport(handler))
    await provider.assign_to_user(7, ["Copilot"])

    assert urls == ["https://api.github.com/graphql"]


@pytest.mark.asyncio
async def test_graphql_on_github_enterprise_drops_the_v3_segment():
    urls: list[str] = []

    def handler(request: Any) -> Any:
        urls.append(str(request.url))
        return httpx.Response(200, json={"data": {}})

    provider = HttpGitHubProvider(
        _repo=_REPO,
        _token=_FAKE_TOKEN,
        _base_url="https://github.acme.internal/api/v3",
        _transport=_transport(handler),
    )
    await provider.assign_to_user(7, ["alice"])

    assert urls == ["https://github.acme.internal/api/graphql"]
