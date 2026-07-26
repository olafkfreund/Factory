"""Guard: reading issue comments is normalised, incremental and never partial.

Factory#375. The shared provider protocol had ``add_comment`` (write) and no
read counterpart, so an imported card lost the entire discussion — which is
usually where the decision lives.

What these tests hold in place:

* **One shape for three providers.** ``fetch_comments`` returns the same
  :class:`IssueComment` fields whatever the provider is, so the board never
  branches on ``provider_type`` to render a thread.
* **``since`` narrows the request.** GitHub passes it to the API; GitLab and
  Azure DevOps have no ``since`` parameter, so they order newest-first and stop
  at the cutoff. Either way an incremental poll costs one page, not a full
  re-read. A client-side filter over a full download would pass a naive
  "correct results" test and still be the rate-limit failure this issue is
  about, so the assertions are on the REQUESTS, not only the results.
* **Pagination is followed.** A thread longer than one page comes back whole.
* **A provider error raises, never truncates.** ``ProviderCommentError`` is
  raised with nothing returned. The alternative — handing back the pages that
  did arrive — stores a partial thread that is indistinguishable from a short
  one, and "this issue has no discussion" is the exact data loss #375 reports.
* **Bulk uses the bulk endpoint.** GitHub's repository-wide issue-comments
  endpoint answers a 46-issue incremental poll in ONE call. The cold backfill
  fans out at one call per issue — bounded by the caller's list rather than by
  the repository's whole comment history.

No pytest-asyncio: the coroutines are driven with ``asyncio.run`` so the suite
runs on the same bare ``pytest + httpx`` install the contracts workflow uses.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

pytest.importorskip("httpx", reason="provider modules import httpx at module scope")

# The canonical tree lives under a hyphenated directory, so it cannot be a
# package path: it is imported via sys.path, exactly as the credential-repr
# guard does.
sys.path.insert(0, str(_REPO_ROOT / "shared" / "factory-github"))
try:
    from providers.azure_devops_provider import (  # type: ignore[import-not-found]
        AzureDevOpsProvider,
    )
    from providers.github_provider import (  # type: ignore[import-not-found]
        GitHubProvider,
    )
    from providers.gitlab_provider import (  # type: ignore[import-not-found]
        GitLabProvider,
    )
    from providers.protocol import (  # type: ignore[import-not-found]
        GitProvider,
        IssueComment,
        ProviderCommentError,
        ProviderType,
    )
finally:
    sys.path.pop(0)


NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeGHClient:
    """Stands in for GHClient, recording every endpoint ``api_get`` is asked for."""

    def __init__(self, pages: list[Any]):
        self._pages = list(pages)
        self.calls: list[str] = []

    async def api_get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,  # noqa: ARG002 - GHClient's signature
    ) -> Any:
        # `params` is deliberately ignored: the providers must build the query
        # string into the endpoint, because `gh api -f k=v` turns the request
        # into a POST. Recording only the endpoint is what proves they did.
        self.calls.append(endpoint)
        page = self._pages.pop(0) if self._pages else []
        if isinstance(page, Exception):
            raise page
        return page


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHTTPClient:
    """Async-context-manager stand-in for ``httpx.AsyncClient``."""

    def __init__(self, pages: list[Any], calls: list[tuple[str, dict[str, Any]]]):
        self._pages = list(pages)
        self.calls = calls

    async def __aenter__(self) -> FakeHTTPClient:
        return self

    async def __aexit__(self, *exc_info: object) -> bool:
        return False

    async def get(self, url: str, params: dict[str, Any] | None = None) -> FakeResponse:
        self.calls.append((url, dict(params or {})))
        page = self._pages.pop(0) if self._pages else []
        if isinstance(page, Exception):
            raise page
        return FakeResponse(page)


def _github(pages: list[Any]) -> tuple[GitHubProvider, FakeGHClient]:
    client = FakeGHClient(pages)
    return GitHubProvider(_repo="owner/repo", _gh_client=client), client


def _gitlab(pages: list[Any]) -> tuple[GitLabProvider, list[tuple[str, dict[str, Any]]]]:
    provider = GitLabProvider(_repo="group/repo", _token="glpat-fake")  # noqa: S106
    calls: list[tuple[str, dict[str, Any]]] = []
    provider._client = lambda: FakeHTTPClient(pages, calls)  # type: ignore[method-assign]
    return provider, calls


def _azure(pages: list[Any]) -> tuple[AzureDevOpsProvider, list[tuple[str, dict[str, Any]]]]:
    provider = AzureDevOpsProvider(
        _repo="repo", _pat="azdo-fake", _organization="org", _project="proj"
    )
    calls: list[tuple[str, dict[str, Any]]] = []
    provider._client = lambda: FakeHTTPClient(pages, calls)  # type: ignore[method-assign]
    return provider, calls


def _gh_comment(comment_id: int, issue_number: int = 7) -> dict[str, Any]:
    return {
        "id": comment_id,
        "user": {"login": "alice"},
        "body": "ship it",
        "created_at": "2026-07-20T09:00:00Z",
        "updated_at": "2026-07-21T09:00:00Z",
        "html_url": f"https://github.com/owner/repo/issues/{issue_number}#issuecomment-{comment_id}",
        "issue_url": f"https://api.github.com/repos/owner/repo/issues/{issue_number}",
    }


def _gl_note(
    note_id: int, *, system: bool = False, updated: str = "2026-07-21T09:00:00Z"
) -> dict[str, Any]:
    return {
        "id": note_id,
        "author": {"username": "alice"},
        "body": "ship it",
        "created_at": "2026-07-20T09:00:00Z",
        "updated_at": updated,
        "system": system,
    }


def _ado_comment(comment_id: int, modified: str = "2026-07-21T09:00:00Z") -> dict[str, Any]:
    return {
        "id": comment_id,
        "createdBy": {"uniqueName": "alice"},
        "text": "ship it",
        "createdDate": "2026-07-20T09:00:00Z",
        "modifiedDate": modified,
        "url": "https://dev.azure.com/org/proj/_apis/wit/workItems/7/comments/1",
    }


# ---------------------------------------------------------------------------
# One shape for three providers
# ---------------------------------------------------------------------------


def test_normalised_shape_is_identical_across_providers() -> None:
    """A caller reads author/body/timestamps/url/id without knowing the provider."""
    github, _ = _github([[_gh_comment(1)]])
    gitlab, _ = _gitlab([[_gl_note(1)]])
    azure, _ = _azure([{"comments": [_ado_comment(1)]}])

    results = {
        ProviderType.GITHUB: asyncio.run(github.fetch_comments(7)),
        ProviderType.GITLAB: asyncio.run(gitlab.fetch_comments(7)),
        ProviderType.AZURE_DEVOPS: asyncio.run(azure.fetch_comments(7)),
    }

    for provider_type, comments in results.items():
        assert len(comments) == 1, provider_type
        comment = comments[0]
        assert isinstance(comment, IssueComment)
        assert comment.provider is provider_type
        assert comment.id == "1"
        assert comment.issue_number == 7
        assert comment.author == "alice"
        assert comment.body == "ship it"
        assert comment.created_at == datetime(2026, 7, 20, 9, 0, tzinfo=UTC)
        assert comment.updated_at == datetime(2026, 7, 21, 9, 0, tzinfo=UTC)
        assert comment.url, "every provider must supply a link back to the comment"
        assert comment.raw_data, "raw provider payload is kept for debugging"


def test_empty_thread_is_an_empty_list_not_an_error() -> None:
    """No discussion is a normal answer; only a failed READ is an error."""
    github, _ = _github([[]])
    gitlab, _ = _gitlab([[]])
    azure, _ = _azure([{"comments": []}])

    assert asyncio.run(github.fetch_comments(7)) == []
    assert asyncio.run(gitlab.fetch_comments(7)) == []
    assert asyncio.run(azure.fetch_comments(7)) == []


# ---------------------------------------------------------------------------
# `since` narrows the REQUEST
# ---------------------------------------------------------------------------


def test_github_since_is_sent_to_the_api() -> None:
    """GitHub takes `since` server-side, so it must appear in the query string."""
    github, client = _github([[_gh_comment(1)]])
    asyncio.run(github.fetch_comments(7, since=NOW))

    query = parse_qs(urlparse(client.calls[0]).query)
    assert query["since"] == ["2026-07-26T12:00:00Z"]
    assert query["per_page"] == ["100"]


def test_gitlab_since_orders_newest_first_and_stops_at_the_cutoff() -> None:
    """GitLab has no `since`, so the narrowing is ordering plus an early stop."""
    fresh = _gl_note(2, updated="2026-07-26T18:00:00Z")
    stale = _gl_note(1, updated="2026-06-01T09:00:00Z")
    # A full page: a client-side filter would still have paged on.
    page = [fresh, stale] + [_gl_note(n, updated="2026-06-01T09:00:00Z") for n in range(3, 101)]
    gitlab, calls = _gitlab([page, [_gl_note(999)]])

    comments = asyncio.run(gitlab.fetch_comments(7, since=NOW))

    assert [c.id for c in comments] == ["2"], "only the comment newer than `since`"
    assert len(calls) == 1, "the walk stopped at the cutoff instead of paging on"
    assert calls[0][1]["order_by"] == "updated_at"
    assert calls[0][1]["sort"] == "desc"
    # Server-side noise removal where the instance supports it.
    assert calls[0][1]["activity_filter"] == "only_comments"


def test_azure_since_orders_newest_first_and_stops_at_the_cutoff() -> None:
    """Same lever for ADO: order=desc plus an early stop, not a full download."""
    fresh = _ado_comment(2, modified="2026-07-26T18:00:00Z")
    stale = _ado_comment(1, modified="2026-06-01T09:00:00Z")
    azure, calls = _azure(
        [
            {"comments": [fresh, stale], "continuationToken": "next-page"},
            {"comments": [_ado_comment(999)]},
        ]
    )

    comments = asyncio.run(azure.fetch_comments(7, since=NOW))

    assert [c.id for c in comments] == ["2"]
    assert len(calls) == 1, "a continuationToken was offered and correctly not followed"
    assert calls[0][1]["order"] == "desc"


def test_gitlab_drops_system_notes() -> None:
    """ "changed the description" is activity, not discussion.

    Covers the instances that ignore ``activity_filter`` and send them anyway.
    """
    gitlab, _ = _gitlab([[_gl_note(1), _gl_note(2, system=True)]])
    assert [c.id for c in asyncio.run(gitlab.fetch_comments(7))] == ["1"]


def test_azure_reads_the_commentid_the_live_payload_actually_sends() -> None:
    """The 7.1-preview.4 response keys it ``commentId``; the schema says ``id``."""
    live_shape, _ = _azure([{"comments": [{**_ado_comment(0), "id": None, "commentId": 45}]}])
    assert [c.id for c in asyncio.run(live_shape.fetch_comments(7))] == ["45"]

    schema_shape, _ = _azure([{"comments": [_ado_comment(45)]}])
    assert [c.id for c in asyncio.run(schema_shape.fetch_comments(7))] == ["45"]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_github_follows_every_page_of_a_long_thread() -> None:
    """A 250-comment issue comes back whole, not capped at the first page."""
    page_one = [_gh_comment(n) for n in range(100)]
    page_two = [_gh_comment(n) for n in range(100, 200)]
    page_three = [_gh_comment(n) for n in range(200, 250)]
    github, client = _github([page_one, page_two, page_three])

    comments = asyncio.run(github.fetch_comments(7))

    assert len(comments) == 250
    assert len(client.calls) == 3
    assert parse_qs(urlparse(client.calls[2]).query)["page"] == ["3"]


def test_gitlab_follows_every_page_of_a_long_thread() -> None:
    page_one = [_gl_note(n) for n in range(100)]
    page_two = [_gl_note(n) for n in range(100, 150)]
    gitlab, calls = _gitlab([page_one, page_two])

    assert len(asyncio.run(gitlab.fetch_comments(7))) == 150
    assert [call[1]["page"] for call in calls] == [1, 2]


def test_azure_follows_the_continuation_token() -> None:
    azure, calls = _azure(
        [
            {"comments": [_ado_comment(1)], "continuationToken": "page-2"},
            {"comments": [_ado_comment(2)]},
        ]
    )

    assert len(asyncio.run(azure.fetch_comments(7))) == 2
    assert calls[1][1]["continuationToken"] == "page-2"


# ---------------------------------------------------------------------------
# Failure never degrades to a silent partial
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "build"),
    [
        ("github", lambda: _github([[_gh_comment(n) for n in range(100)], RuntimeError("502")])[0]),
        ("gitlab", lambda: _gitlab([[_gl_note(n) for n in range(100)], RuntimeError("502")])[0]),
        (
            "azure",
            lambda: _azure(
                [
                    {"comments": [_ado_comment(1)], "continuationToken": "page-2"},
                    RuntimeError("502"),
                ]
            )[0],
        ),
    ],
)
def test_mid_thread_failure_raises_instead_of_returning_a_partial(name: str, build: Any) -> None:
    """The first page arrived; the second did not. Nothing is returned."""
    provider = build()
    with pytest.raises(ProviderCommentError) as excinfo:
        asyncio.run(provider.fetch_comments(7))
    assert "502" in str(excinfo.value), name


def test_github_page_cap_is_an_error_not_a_truncation() -> None:
    """An endless stream fails loudly rather than silently capping the thread."""
    github, _ = _github([[_gh_comment(n) for n in range(100)] for _ in range(60)])
    with pytest.raises(ProviderCommentError, match="exceeded"):
        asyncio.run(github.fetch_comments(7))


# ---------------------------------------------------------------------------
# Bulk: the rate-limit claim, asserted in calls
# ---------------------------------------------------------------------------


def test_github_incremental_backfill_of_46_issues_is_one_api_call() -> None:
    """The whole point of #375's rate-limit note.

    GitHub's repository-wide issue-comments endpoint honours `since`, so the
    poll that runs over and over reads all 46 cards in a single request instead
    of 46.
    """
    numbers = list(range(1, 47))
    github, client = _github([[_gh_comment(1, issue_number=3), _gh_comment(2, issue_number=9)]])

    grouped = asyncio.run(github.fetch_comments_bulk(numbers, since=NOW))

    assert len(client.calls) == 1, "one repository-wide call, not 46"
    assert client.calls[0].startswith("/repos/owner/repo/issues/comments?")
    assert parse_qs(urlparse(client.calls[0]).query)["since"] == ["2026-07-26T12:00:00Z"]
    assert set(grouped) == set(numbers), "every requested issue is present"
    assert [c.id for c in grouped[3]] == ["1"]
    assert [c.id for c in grouped[9]] == ["2"]
    assert grouped[4] == [], "an issue with no new comments maps to an empty list"


def test_github_cold_backfill_costs_one_call_per_issue_and_no_more() -> None:
    """No `since` means no window to narrow, so the cost is bounded by the ask.

    The repository-wide stream would page over the project's ENTIRE comment
    history to answer a question about 46 issues; per-issue is 46 calls whatever
    the repository's size.
    """
    numbers = list(range(1, 47))
    github, client = _github([[] for _ in numbers])

    grouped = asyncio.run(github.fetch_comments_bulk(numbers, since=None))

    assert len(client.calls) == 46
    assert set(grouped) == set(numbers)
    assert all(call.startswith("/repos/owner/repo/issues/") for call in client.calls)


def test_providers_without_a_bulk_endpoint_fan_out_one_call_per_issue() -> None:
    """GitLab and ADO have no batch comments API; the cost is explicit."""
    gitlab, gl_calls = _gitlab([[] for _ in range(3)])
    azure, ado_calls = _azure([{"comments": []} for _ in range(3)])

    assert set(asyncio.run(gitlab.fetch_comments_bulk([1, 2, 3], since=NOW))) == {1, 2, 3}
    assert set(asyncio.run(azure.fetch_comments_bulk([1, 2, 3], since=NOW))) == {1, 2, 3}
    assert len(gl_calls) == 3
    assert len(ado_calls) == 3


def test_bulk_of_nothing_makes_no_calls() -> None:
    github, client = _github([])
    assert asyncio.run(github.fetch_comments_bulk([], since=NOW)) == {}
    assert client.calls == []


# ---------------------------------------------------------------------------
# The protocol surface itself
# ---------------------------------------------------------------------------


def test_every_provider_satisfies_the_extended_protocol() -> None:
    """Adding methods to a runtime_checkable Protocol must not orphan a provider."""
    assert isinstance(GitHubProvider(_repo="owner/repo", _gh_client=FakeGHClient([])), GitProvider)
    assert isinstance(GitLabProvider(_repo="group/repo"), GitProvider)
    assert isinstance(AzureDevOpsProvider(_repo="repo"), GitProvider)


def test_add_comment_still_exists_unchanged() -> None:
    """This PR is additive: the vendored write surface other callers use stays put."""
    import inspect  # noqa: PLC0415

    signature = inspect.signature(GitHubProvider.add_comment)
    assert list(signature.parameters) == ["self", "issue_or_pr_number", "body"]
