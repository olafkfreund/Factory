"""Bitbucket Cloud code seam, exercised with recorded-shape REST responses."""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime

import httpx
import pytest
from providers import bitbucket_provider as bitbucket_module
from providers.bitbucket_provider import BitbucketMergePending, BitbucketProvider
from providers.factory import (
    _PROVIDER_REGISTRY,
    get_code_provider,
    get_provider,
    is_provider_available,
    list_available_providers,
)
from providers.protocol import (
    CodeProvider,
    PRFilters,
    ProviderCommentError,
    ProviderType,
    ReviewData,
    ReviewFinding,
)

BASE = "https://api.bitbucket.org/2.0"
ROOT = "/repositories/acme/widgets"
TOKEN = "bitbucket-token-placeholder"  # noqa: S105 - test sentinel, not a credential


def _provider(handler, **kwargs) -> BitbucketProvider:
    return BitbucketProvider(
        _repo="acme/widgets", _token=TOKEN, _transport=httpx.MockTransport(handler), **kwargs
    )


def _pr(number: int, state: str = "OPEN", updated: str = "2026-11-18T12:00:00Z") -> dict:
    return {"id": number, "state": state, "updated_on": updated}


def test_list_follows_absolute_same_origin_next() -> None:
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json={"values": [_pr(2)]})
        return httpx.Response(
            200,
            json={"values": [_pr(1)], "next": f"{BASE}{ROOT}/pullrequests?page=2"},
        )

    result = asyncio.run(_provider(handler).fetch_prs())
    assert [pr.number for pr in result] == [1, 2]
    assert len(seen) == 2
    assert seen[1] == f"{BASE}{ROOT}/pullrequests?page=2"


def test_foreign_next_is_refused_without_request() -> None:
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(200, json={"values": [], "next": "https://evil.example/prs"})

    with pytest.raises(ValueError, match="foreign host"):
        asyncio.run(_provider(handler).fetch_prs())
    assert seen == ["api.bitbucket.org"]


@pytest.mark.parametrize(
    "target,allowed", [(f"{BASE}/diff/1", True), ("https://evil.example/diff", False)]
)
def test_diff_redirect_is_origin_checked(target: str, allowed: bool) -> None:
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.path.endswith("/diff"):
            return httpx.Response(302, headers={"Location": target})
        return httpx.Response(200, text="diff --git a/x b/x")

    provider = _provider(handler)
    if allowed:
        assert asyncio.run(provider.fetch_pr_diff(7)) == "diff --git a/x b/x"
        assert seen == [f"{BASE}{ROOT}/pullrequests/7/diff", target]
    else:
        with pytest.raises(ValueError, match="foreign host"):
            asyncio.run(provider.fetch_pr_diff(7))
        assert seen == [f"{BASE}{ROOT}/pullrequests/7/diff"]


@pytest.mark.parametrize("status", [401, 403, 404, 429])
def test_http_errors_raise_without_credential(status: int) -> None:
    provider = _provider(lambda _request: httpx.Response(status))
    with pytest.raises(httpx.HTTPStatusError) as error:
        asyncio.run(provider.get_repository_info())
    assert TOKEN not in str(error.value)
    assert provider._headers["Authorization"] not in str(error.value)


@pytest.mark.parametrize("status", [401, 429])
def test_permission_auth_and_rate_errors_raise(status: int) -> None:
    with pytest.raises(httpx.HTTPStatusError) as error:
        asyncio.run(_provider(lambda _request: httpx.Response(status)).check_permissions("alice"))
    assert TOKEN not in str(error.value)


@pytest.mark.parametrize("permission", ["admin", "write", "read", "owner", None])
def test_explicit_permissions(permission: str | None) -> None:
    provider = _provider(lambda _request: httpx.Response(200, json={"permission": permission}))
    expected = permission if permission in ("admin", "write", "read") else "none"
    assert asyncio.run(provider.check_permissions("alice")) == expected


@pytest.mark.parametrize("status", [403, 404])
def test_inaccessible_permission_endpoint_returns_none(status: int) -> None:
    # Group-only grants are not exposed by this explicit-grants endpoint.
    provider = _provider(lambda _request: httpx.Response(status))
    assert asyncio.run(provider.check_permissions("group-member")) == "none"


@pytest.mark.parametrize(
    "method,strategy",
    [("merge", "merge_commit"), ("squash", "squash"), ("rebase", "rebase_fast_forward")],
)
def test_merge_strategy_payload(method: str, strategy: str) -> None:
    payloads = []

    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={})

    assert asyncio.run(_provider(handler).merge_pr(7, method, "Release")) is True
    assert payloads == [{"type": "pullrequest", "merge_strategy": strategy, "message": "Release"}]


def test_unknown_merge_method_makes_no_request() -> None:
    def handler(_request):
        pytest.fail("unexpected network request")

    with pytest.raises(ValueError, match="Unsupported merge method"):
        asyncio.run(_provider(handler).merge_pr(7, "octopus"))


def test_merge_conflict_returns_false() -> None:
    assert asyncio.run(_provider(lambda _request: httpx.Response(409)).merge_pr(7)) is False


@pytest.mark.parametrize(
    "statuses,expected",
    [
        (["PENDING", "PENDING", "SUCCESS"], True),
        (["PENDING", "FAILED"], False),
        (["PENDING", "ERROR"], False),
    ],
)
def test_accepted_merge_polls_task(monkeypatch, statuses: list[str], expected: bool) -> None:
    monkeypatch.setattr(bitbucket_module, "_MERGE_POLL_DELAY", 0)
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.method == "POST":
            return httpx.Response(202, headers={"Location": f"{BASE}/tasks/7"})
        return httpx.Response(200, json={"task_status": statuses.pop(0)})

    assert asyncio.run(_provider(handler).merge_pr(7)) is expected
    assert seen[1:] == [f"{BASE}/tasks/7"] * (len(seen) - 1)
    assert statuses == []


def test_accepted_merge_still_pending_after_five_polls(monkeypatch) -> None:
    monkeypatch.setattr(bitbucket_module, "_MERGE_POLL_DELAY", 0)
    polls = []

    def handler(request):
        if request.method == "POST":
            return httpx.Response(202, headers={"Location": f"{BASE}/tasks/7"})
        polls.append(str(request.url))
        return httpx.Response(200, json={"task_status": "PENDING"})

    with pytest.raises(BitbucketMergePending):
        asyncio.run(_provider(handler).merge_pr(7))
    assert polls == [f"{BASE}/tasks/7"] * 5


def test_accepted_merge_foreign_task_is_never_requested() -> None:
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(202, headers={"Location": "https://evil.example/task"})

    with pytest.raises(BitbucketMergePending):
        asyncio.run(_provider(handler).merge_pr(7))
    assert seen == ["api.bitbucket.org"]


@pytest.mark.parametrize(
    "raw,mapped",
    [
        ("OPEN", "open"),
        ("MERGED", "merged"),
        ("DECLINED", "closed"),
        ("SUPERSEDED", "closed"),
        ("FUTURE", "unknown"),
    ],
)
def test_pr_state_mapping(raw: str, mapped: str) -> None:
    assert _provider(lambda _request: httpx.Response(200))._parse_pr(_pr(7, raw)).state == mapped


def test_fetch_pr_joins_details_diffstat_and_diff() -> None:
    raw = {
        **_pr(7),
        "title": "Fix",
        "description": "Body",
        "draft": True,
        "author": {"nickname": "alice"},
        "participants": [{"role": "REVIEWER", "user": {"display_name": "Bob"}}],
        "source": {"branch": {"name": "feature"}},
        "destination": {"branch": {"name": "main"}},
        "links": {"html": {"href": "https://bitbucket.org/acme/widgets/pull-requests/7"}},
        "created_on": "2026-11-17T12:00:00Z",
    }

    def handler(request):
        if request.url.path.endswith("/diffstat"):
            return httpx.Response(
                200,
                json={
                    "values": [
                        {
                            "new": {"path": "a.py"},
                            "lines_added": 3,
                            "lines_removed": 1,
                            "status": "modified",
                        },
                        {
                            "old": {"path": "b.py"},
                            "lines_added": 0,
                            "lines_removed": 2,
                            "status": "removed",
                        },
                    ]
                },
            )
        if request.url.path.endswith("/diff"):
            return httpx.Response(200, text="diff text")
        return httpx.Response(200, json=raw)

    pr = asyncio.run(_provider(handler).fetch_pr(7))
    assert (pr.number, pr.title, pr.body, pr.author, pr.state) == (
        7,
        "Fix",
        "Body",
        "alice",
        "open",
    )
    assert (pr.source_branch, pr.target_branch, pr.reviewers, pr.is_draft) == (
        "feature",
        "main",
        ["Bob"],
        True,
    )
    assert (pr.additions, pr.deletions, pr.changed_files, pr.diff) == (3, 3, 2, "diff text")
    assert [item["path"] for item in pr.files] == ["a.py", "b.py"]
    assert pr.url == raw["links"]["html"]["href"]
    assert pr.created_at == datetime(2026, 11, 17, 12, tzinfo=UTC)
    assert pr.updated_at == datetime(2026, 11, 18, 12, tzinfo=UTC)
    assert pr.provider is ProviderType.BITBUCKET and pr.raw_data == raw


def test_fetch_prs_filters_query_since_and_limit() -> None:
    queries = []

    def handler(request):
        queries.append(request.url.params)
        return httpx.Response(
            200,
            json={
                "values": [
                    _pr(3, updated="2026-11-19T12:00:00Z"),
                    _pr(2, updated="2026-11-18T12:00:00Z"),
                    _pr(1, updated="2026-11-17T12:00:00Z"),
                ]
            },
        )

    filters = PRFilters(
        state="merged",
        author='a"b',
        base_branch="main",
        head_branch="feature",
        since=datetime(2026, 11, 18, tzinfo=UTC),
        limit=1,
    )
    result = asyncio.run(_provider(handler).fetch_prs(filters))
    assert [pr.number for pr in result] == [3]
    assert queries[0].get_list("state") == ["MERGED"]
    assert queries[0]["q"] == (
        'author.nickname="a\\"b" AND destination.branch.name="main" '
        'AND source.branch.name="feature"'
    )
    assert queries[0]["sort"] == "-updated_on"


def test_fetch_prs_since_stops_at_cutoff() -> None:
    provider = _provider(
        lambda _request: httpx.Response(
            200,
            json={
                "values": [
                    _pr(3, updated="2026-11-19T12:00:00Z"),
                    _pr(2, updated="2026-11-18T00:00:00Z"),
                ]
            },
        )
    )
    result = asyncio.run(provider.fetch_prs(PRFilters(since=datetime(2026, 11, 18, tzinfo=UTC))))
    assert [pr.number for pr in result] == [3]


def test_labels_return_empty_without_request() -> None:
    def handler(_request):
        pytest.fail("unexpected network request")

    assert asyncio.run(_provider(handler).fetch_prs(PRFilters(labels=["bug"]))) == []


def test_comments_are_filtered_sorted_and_keep_avatar() -> None:
    def comment(number, date, deleted=False):
        return {
            "id": number,
            "deleted": deleted,
            "created_on": date,
            "updated_on": date,
            "content": {"raw": str(number)},
            "user": {
                "nickname": "alice",
                "links": {"avatar": {"href": "https://avatar.example/a"}},
            },
        }

    def handler(request):
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json={"values": [comment(2, "2026-11-19T10:00:00Z")]})
        return httpx.Response(
            200,
            json={
                "values": [
                    comment(3, "2026-11-20T10:00:00Z"),
                    comment(4, "2026-11-21T10:00:00Z", True),
                    comment(1, "2026-11-17T10:00:00Z"),
                ],
                "next": f"{BASE}{ROOT}/pullrequests/7/comments?page=2",
            },
        )

    comments = asyncio.run(
        _provider(handler).fetch_pr_comments(7, datetime(2026, 11, 18, tzinfo=UTC))
    )
    assert [c.id for c in comments] == ["2", "3"]
    assert comments[0].avatar_url == "https://avatar.example/a"
    assert comments[0].body == "2" and comments[0].provider is ProviderType.BITBUCKET


def test_comment_page_failure_is_wrapped() -> None:
    def handler(request):
        if request.url.params.get("page") == "2":
            return httpx.Response(429)
        return httpx.Response(
            200,
            json={"values": [{"id": 1}], "next": f"{BASE}{ROOT}/pullrequests/7/comments?page=2"},
        )

    with pytest.raises(ProviderCommentError, match="comment read failed"):
        asyncio.run(_provider(handler).fetch_pr_comments(7))


def test_comment_page_cap_is_an_error() -> None:
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "values": [],
                "next": f"{BASE}{ROOT}/pullrequests/7/comments?page={len(seen) + 1}",
            },
        )

    with pytest.raises(ProviderCommentError, match="exceeded 20 pages"):
        asyncio.run(_provider(handler).fetch_pr_comments(7))
    assert len(seen) == 20


@pytest.mark.parametrize(
    "event,action",
    [("comment", None), ("approve", "approve"), ("request_changes", "request-changes")],
)
def test_post_review_body_inline_and_action(event: str, action: str | None) -> None:
    seen = []

    def handler(request):
        seen.append(
            (
                request.url.path,
                json.loads(request.content) if request.content else None,
            )
        )
        return httpx.Response(200, json={"id": 42})

    finding = ReviewFinding(
        id="f",
        severity="high",
        category="bug",
        title="Issue",
        description="Details",
        file="a.py",
        line=8,
    )
    review = ReviewData(pr_number=7, event=event, body="Summary", findings=[finding])
    assert asyncio.run(_provider(handler).post_review(7, review)) == 42
    assert seen[0][1] == {"content": {"raw": "Summary"}}
    assert seen[1][1]["inline"] == {"path": "a.py", "to": 8}
    assert [path.rsplit("/", 1)[-1] for path, _ in seen] == ["comments", "comments"] + (
        [action] if action else []
    )


def test_rejected_inline_finding_falls_back_to_plain_comment() -> None:
    payloads = []

    def handler(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        if "inline" in payload:
            return httpx.Response(400)
        return httpx.Response(200, json={"id": len(payloads)})

    finding = ReviewFinding(
        id="f",
        severity="low",
        category="style",
        title="Style",
        description="Details",
        file="a.py",
        line=8,
    )
    review = ReviewData(pr_number=7, event="comment", body="Summary", findings=[finding])
    assert asyncio.run(_provider(handler).post_review(7, review)) == 1
    assert "inline" not in payloads[2]
    assert "a.py:L8" in payloads[2]["content"]["raw"]


def test_close_pr_comments_before_decline() -> None:
    seen = []

    def handler(request):
        seen.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"id": 1})

    assert asyncio.run(_provider(handler).close_pr(7, "Closing")) is True
    assert seen == ["comments", "decline"]


def test_auto_merge_is_unavailable() -> None:
    with pytest.raises(NotImplementedError):
        asyncio.run(
            _provider(lambda _request: pytest.fail("unexpected request")).enable_auto_merge(7)
        )


@pytest.mark.parametrize(
    "username,expected",
    [
        (None, f"Bearer {TOKEN}"),
        (
            "user@example.com",
            "Basic " + base64.b64encode(f"user@example.com:{TOKEN}".encode()).decode(),
        ),
    ],
)
def test_auth_header_and_repr_hide_credential(username: str | None, expected: str) -> None:
    seen = []

    def handler(request):
        seen.append(request.headers["Authorization"])
        return httpx.Response(200, json={})

    provider = _provider(handler, _username=username)
    asyncio.run(provider.get_repository_info())
    assert seen == [expected]
    assert TOKEN not in repr(provider) + str(provider)
    assert expected not in repr(provider) + str(provider)
    assert isinstance(provider, CodeProvider)


@pytest.mark.parametrize("repo", ["", "acme", "/widgets", "acme/", "acme/widgets/extra"])
def test_invalid_repo_is_rejected(repo: str) -> None:
    with pytest.raises(ValueError, match="workspace/repo_slug"):
        BitbucketProvider(_repo=repo)


def test_factory_flag_and_registry(monkeypatch) -> None:
    registry = dict(_PROVIDER_REGISTRY)
    monkeypatch.delenv("FACTORY_BITBUCKET_ENABLED", raising=False)
    with pytest.raises(NotImplementedError, match="FACTORY_BITBUCKET_ENABLED"):
        get_code_provider("bitbucket", "acme/widgets")
    with pytest.raises(NotImplementedError, match="get_code_provider"):
        get_provider("bitbucket", "acme/widgets")
    with pytest.raises(NotImplementedError):
        get_code_provider("github", "acme/widgets", token=TOKEN)
    assert ProviderType.BITBUCKET not in list_available_providers()
    assert not is_provider_available("bitbucket")
    for enabled in ("1", "true", "yes"):
        monkeypatch.setenv("FACTORY_BITBUCKET_ENABLED", enabled)
        assert isinstance(get_code_provider("bitbucket", "acme/widgets"), BitbucketProvider)
        assert ProviderType.BITBUCKET in list_available_providers()
        assert is_provider_available("bitbucket")
    assert registry == _PROVIDER_REGISTRY
