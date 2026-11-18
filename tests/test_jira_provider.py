"""Jira work-item provider contracts, exercised without a network."""

from __future__ import annotations

import base64
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

_SHARED = str(Path(__file__).resolve().parents[1] / "shared" / "factory-github")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

httpx = pytest.importorskip("httpx")

from providers.factory import get_provider, get_work_item_provider  # noqa: E402
from providers.jira_provider import (  # noqa: E402
    JiraError,
    JiraProvider,
    JiraTransitionError,
    adf_to_text,
    to_adf,
)
from providers.protocol import (  # noqa: E402
    CodeProvider,
    IssueFilters,
    LabelData,
    ProviderCommentError,
    ProviderType,
    WorkItemProvider,
)

_EMAIL = "secret-email@example.test"
_TOKEN = "secret-api-token"  # noqa: S105 - inert test marker
_BASE = "https://jira.example.test"
_ISSUE = "/rest/api/3/issue/PROJ-7"


def _provider(handler: Any) -> JiraProvider:
    return JiraProvider(
        _repo="PROJ",
        _email=_EMAIL,
        _api_token=_TOKEN,
        _base_url=_BASE,
        _transport=httpx.MockTransport(handler),
    )


def _transition_handler(
    transitions: list[dict[str, Any]], seen: list[Any], post: Any = None
) -> Any:
    """An issue that is not Done, its transition list, and the answer to the transition POST."""

    def handler(request: Any) -> Any:
        seen.append(request)
        if request.url.path == _ISSUE:
            return httpx.Response(200, json=_issue())
        if request.method == "GET":
            return httpx.Response(200, json={"transitions": transitions})
        return post or httpx.Response(204)

    return handler


def _issue(key: str = "PROJ-7", category: str | None = "new") -> dict[str, Any]:
    status = {} if category is None else {"statusCategory": {"key": category}}
    return {"key": key, "fields": {"summary": "A task", "status": status}}


def test_protocol_factory_and_redacted_repr():
    provider = _provider(lambda _: httpx.Response(200, json={}))
    assert isinstance(provider, WorkItemProvider)
    assert not isinstance(provider, CodeProvider)
    assert provider.provider_type is ProviderType.JIRA
    assert provider.repo == "PROJ"
    assert _EMAIL not in repr(provider) and _TOKEN not in repr(provider)
    assert isinstance(get_work_item_provider("jira", "PROJ", _base_url=_BASE), JiraProvider)
    with pytest.raises(ValueError, match="get_work_item_provider"):
        get_provider("jira", "PROJ")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("new", "open"),
        ("indeterminate", "open"),
        ("done", "closed"),
        ("custom", "open"),
        (None, "open"),
    ],
)
async def test_fetch_issue_keeps_string_key_and_maps_category(category, expected):
    seen = []

    def handler(request: Any) -> Any:
        seen.append(request)
        return httpx.Response(200, json=_issue(category=category))

    item = await _provider(handler).fetch_issue("PROJ-7")
    assert (item.number, item.state, item.provider) == ("PROJ-7", expected, ProviderType.JIRA)
    assert item.body == ""  # Jira's null or absent description is empty text.
    assert seen[0].url.path == _ISSUE
    assert "status" in seen[0].url.params["fields"]
    expected_auth = "Basic " + base64.b64encode(f"{_EMAIL}:{_TOKEN}".encode()).decode()
    assert seen[0].headers["Authorization"] == expected_auth


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["../x", "12"])
async def test_invalid_key_never_reaches_transport(key):
    def handler(_):
        pytest.fail("invalid key sent a request")

    with pytest.raises(ValueError, match="Jira issue key"):
        await _provider(handler).fetch_issue(key)


@pytest.mark.asyncio
async def test_search_fields_jql_token_pagination_and_limit():
    requests = []

    def handler(request: Any) -> Any:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(200, json={"issues": [_issue("PROJ-1")], "nextPageToken": "next"})
        return httpx.Response(200, json={"issues": [_issue("PROJ-2"), _issue("PROJ-3")]})

    items = await _provider(handler).fetch_issues(
        IssueFilters(state="closed", labels=['say "yes"'], limit=2)
    )
    assert [item.number for item in items] == ["PROJ-1", "PROJ-2"]
    assert [request.url.params.get("nextPageToken") for request in requests] == [None, "next"]
    assert all(request.url.path == "/rest/api/3/search/jql" for request in requests)
    assert all("description" in request.url.params["fields"] for request in requests)
    jql = requests[0].url.params["jql"]
    assert 'project = "PROJ"' in jql
    assert "statusCategory = Done" in jql
    assert 'labels = "say-\\"yes\\""' in jql
    assert requests[1].url.params["maxResults"] == "1"


@pytest.mark.asyncio
async def test_create_issue_reads_back_and_assigns_account_id():
    seen = []

    def handler(request: Any) -> Any:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"key": "PROJ-7"})
        return httpx.Response(200, json=_issue())

    item = await _provider(handler).create_issue(
        "Title", "line one\nline two", ["two words"], ["account-1"]
    )
    assert item.number == "PROJ-7"
    fields = json.loads(seen[0].content)["fields"]
    assert fields["project"] == {"key": "PROJ"}
    assert fields["description"] == to_adf("line one\nline two")
    assert fields["labels"] == ["two-words"]
    assert fields["assignee"] == {"accountId": "account-1"}
    assert seen[1].url.path == _ISSUE


@pytest.mark.asyncio
async def test_close_chooses_done_transition_and_sends_comment_in_same_post():
    seen: list[Any] = []

    handler = _transition_handler(
        [
            {"id": "1", "name": "Review", "to": {"statusCategory": {"key": "indeterminate"}}},
            {"id": "2", "name": "Finish", "to": {"statusCategory": {"key": "done"}}},
        ],
        seen,
    )

    assert await _provider(handler).close_issue("PROJ-7", "finished") is True
    assert [(r.method, r.url.path) for r in seen] == [
        ("GET", _ISSUE),
        ("GET", f"{_ISSUE}/transitions"),
        ("POST", f"{_ISSUE}/transitions"),
    ]
    payload = json.loads(seen[-1].content)
    assert payload["transition"] == {"id": "2"}
    assert payload["update"]["comment"][0]["add"]["body"] == to_adf("finished")


@pytest.mark.asyncio
async def test_already_done_needs_no_transition_post():
    seen = []

    def handler(request: Any) -> Any:
        seen.append(request)
        return httpx.Response(200, json=_issue(category="done"))

    assert await _provider(handler).close_issue("PROJ-7") is True
    assert [(r.method, r.url.path) for r in seen] == [("GET", _ISSUE)]


@pytest.mark.asyncio
async def test_no_done_transition_names_available_choices():
    def handler(request: Any) -> Any:
        if request.url.path == _ISSUE:
            return httpx.Response(200, json=_issue())
        return httpx.Response(200, json={"transitions": [{"id": "1", "name": "Review"}]})

    with pytest.raises(JiraTransitionError, match="Review"):
        await _provider(handler).close_issue("PROJ-7")


@pytest.mark.asyncio
async def test_required_transition_field_is_reported():
    handler = _transition_handler(
        [{"id": "2", "name": "Finish", "to": {"statusCategory": {"key": "done"}}}],
        [],
        post=httpx.Response(400, json={"errors": {"resolution": "required"}}),
    )

    with pytest.raises(JiraTransitionError, match="resolution"):
        await _provider(handler).close_issue("PROJ-7")


@pytest.mark.asyncio
async def test_comment_write_read_pages_since_and_bulk():
    seen = []

    def handler(request: Any) -> Any:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"id": "42"})
        start = int(request.url.params["startAt"])
        comments = [
            {"id": "1", "body": to_adf("old"), "updated": "2026-01-01T00:00:00+00:00"},
            {"id": "2", "body": to_adf("new"), "updated": "2026-02-01T00:00:00+00:00"},
        ]
        return httpx.Response(200, json={"comments": comments[start : start + 1], "total": 2})

    provider = _provider(handler)
    assert await provider.add_comment("PROJ-7", "hello") == 42
    assert json.loads(seen[0].content) == {"body": to_adf("hello")}
    comments = await provider.fetch_comments("PROJ-7", datetime(2026, 1, 15, tzinfo=UTC))
    assert [(c.id, c.issue_number, c.body) for c in comments] == [("2", "PROJ-7", "new")]
    assert [r.url.params["startAt"] for r in seen[1:]] == ["0", "1"]
    bulk = await provider.fetch_comments_bulk(["PROJ-7", "PROJ-7"])
    assert list(bulk) == ["PROJ-7"]
    assert [c.id for c in bulk["PROJ-7"]] == ["1", "2"]


@pytest.mark.asyncio
async def test_comment_page_failure_is_not_a_partial_thread():
    def handler(request: Any) -> Any:
        if request.url.params["startAt"] == "0":
            return httpx.Response(200, json={"comments": [{"id": "1"}], "total": 2})
        return httpx.Response(500, json={"errorMessages": ["failed"]})

    with pytest.raises(ProviderCommentError):
        await _provider(handler).fetch_comments("PROJ-7")


@pytest.mark.asyncio
async def test_assignment_label_members_and_project_info():
    seen = []

    def handler(request: Any) -> Any:
        seen.append(request)
        if request.url.path.endswith("/label"):
            return httpx.Response(200, json={"values": ["bug"], "isLast": True})
        if request.url.path.endswith("/project/PROJ"):
            return httpx.Response(200, json={"key": "PROJ"})
        return httpx.Response(204)

    provider = _provider(handler)
    await provider.assign_to_user("PROJ-7", ["account-1"])
    await provider.apply_labels("PROJ-7", ["good first issue"])
    await provider.remove_labels("PROJ-7", ["old label"])
    await provider.create_label(LabelData(name="new", color="ffffff"))
    assert await provider.list_labels() == [LabelData(name="bug", color="")]
    assert await provider.get_repository_info() == {"key": "PROJ"}
    assert [r.url.path for r in seen] == [
        f"{_ISSUE}/assignee",
        _ISSUE,
        _ISSUE,
        "/rest/api/3/label",
        "/rest/api/3/project/PROJ",
    ]
    assert json.loads(seen[0].content) == {"accountId": "account-1"}
    assert json.loads(seen[1].content) == {"update": {"labels": [{"add": "good-first-issue"}]}}
    assert json.loads(seen[2].content) == {"update": {"labels": [{"remove": "old-label"}]}}
    with pytest.raises(ValueError, match="one assignee"):
        await provider.assign_to_user("PROJ-7", ["a", "b"])
    with pytest.raises(NotImplementedError, match="Copilot"):
        await provider.assign_to_user("PROJ-7", ["Copilot"])


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 403])
async def test_apply_labels_degrades_on_locked_project(status, caplog):
    provider = _provider(lambda _: httpx.Response(status, json={"errorMessages": ["denied"]}))
    await provider.apply_labels("PROJ-7", ["label"])
    assert "labels not changed" in caplog.text
    assert _TOKEN not in caplog.text and _EMAIL not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 404, 429, 500])
async def test_apply_labels_propagates_other_errors(status):
    provider = _provider(lambda _: httpx.Response(status, json={"errorMessages": ["failed"]}))
    with pytest.raises(JiraError) as exc:
        await provider.apply_labels("PROJ-7", ["label"])
    assert exc.value.status == status


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 404, 429])
async def test_http_errors_are_redacted_and_keep_status(status, caplog):
    def handler(_):
        return httpx.Response(
            status, headers={"Retry-After": "17"}, json={"errorMessages": ["denied"]}
        )

    provider = _provider(handler)
    with pytest.raises(JiraError) as exc:
        await provider.fetch_issue("PROJ-7")
    assert isinstance(exc.value, httpx.HTTPStatusError)
    assert exc.value.status == status
    if status == 429:
        assert exc.value.retry_after == "17"
    for visible in (repr(provider), str(exc.value), caplog.text):
        assert _TOKEN not in visible and _EMAIL not in visible


@pytest.mark.asyncio
async def test_redirect_does_not_forward_basic_auth():
    seen = []

    def handler(request: Any) -> Any:
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://other.example.test/steal"})

    with pytest.raises(JiraError) as exc:
        await _provider(handler).fetch_issue("PROJ-7")
    assert exc.value.status == 302
    assert len(seen) == 1


def test_adf_flattens_nested_content_and_round_trips_multiline_text():
    node = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "hardBreak"},
                    {"type": "mention", "attrs": {"text": "@Ada"}},
                    {
                        "type": "text",
                        "text": " link",
                        "marks": [{"type": "link", "attrs": {"href": "https://example.test"}}],
                    },
                    {"type": "inlineCard", "attrs": {"url": "https://example.test/card"}},
                ],
            },
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "outer"}]},
                            {
                                "type": "bulletList",
                                "content": [
                                    {
                                        "type": "listItem",
                                        "content": [
                                            {
                                                "type": "paragraph",
                                                "content": [{"type": "text", "text": "inner"}],
                                            }
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            },
        ],
    }
    rendered = adf_to_text(node)
    assert "hello\n@Ada" in rendered
    assert "link (https://example.test)https://example.test/card" in rendered
    assert "- outer" in rendered and "- inner" in rendered
    assert adf_to_text(None) == ""
    assert adf_to_text(to_adf("first\nsecond")) == "first\nsecond\n"


def _list(*items: str) -> dict[str, Any]:
    return {
        "type": "bulletList",
        "content": [
            {
                "type": "listItem",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": i}]}],
            }
            for i in items
        ],
    }


def test_adf_sibling_list_items_stay_separate():
    assert adf_to_text(_list("alpha", "beta")) == "- alpha\n- beta\n"


@pytest.mark.asyncio
async def test_error_detail_reflecting_the_credential_is_redacted(caplog):
    echo = {"errorMessages": [f"bad auth {_EMAIL}:{_TOKEN}"], "errors": {"labels": _TOKEN}}

    def handler(request: Any) -> Any:
        return httpx.Response(403 if request.method == "PUT" else 401, json=echo)

    provider = _provider(handler)
    with pytest.raises(JiraError) as read:
        await provider.fetch_issue("PROJ-7")
    await provider.apply_labels("PROJ-7", ["x"])  # 403 degrades and logs
    for text in (str(read.value), caplog.text):
        assert _TOKEN not in text and _EMAIL not in text


@pytest.mark.asyncio
async def test_since_is_sent_as_epoch_millis_not_a_timezone_dependent_date():
    seen: list[str] = []

    def handler(request: Any) -> Any:
        seen.append(request.url.params["jql"])
        return httpx.Response(200, json={"issues": []})

    since = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    await _provider(handler).fetch_issues(IssueFilters(since=since))
    assert f"updated >= {int(since.timestamp() * 1000)}" in seen[0]
