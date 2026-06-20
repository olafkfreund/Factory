"""Tests for the stdlib HTTP/JSON client (factory_common.http).

No real network: urllib.request.urlopen is monkeypatched with a fake transport
that records the outgoing request and returns scripted responses, so the UA,
auth headers, retry behaviour and JSON parsing are all asserted offline.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

_PKG_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PKG_ROOT))

from factory_common import http  # noqa: E402


class _FakeResponse:
    """Minimal stand-in for the urlopen context-manager result."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self._body = body.encode()

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class _Transport:
    """Scripted urlopen replacement; records each Request it is handed."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[int | None] = []

    def __call__(self, req: urllib.request.Request, timeout: int | None = None) -> Any:
        self.requests.append(req)
        self.timeouts.append(timeout)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _install(monkeypatch: pytest.MonkeyPatch, transport: _Transport) -> None:
    monkeypatch.setattr(urllib.request, "urlopen", transport)


def _http_error(code: int, message: str = "err") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://x", code=code, msg=message, hdrs=Message(), fp=io.BytesIO(message.encode())
    )


def test_get_parses_json_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_FakeResponse(200, json.dumps({"ok": True}))])
    _install(monkeypatch, transport)
    client = http.HttpClient(base_url="https://api.example/")
    resp = client.get("/health")
    assert resp.status == 200
    assert resp.json == {"ok": True}
    assert transport.requests[0].full_url == "https://api.example/health"


def test_default_user_agent_is_cloudflare_friendly(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_FakeResponse(200, "{}")])
    _install(monkeypatch, transport)
    http.HttpClient(base_url="http://t").get("/x")
    ua = transport.requests[0].get_header("User-agent")
    assert ua is not None
    assert ua.startswith("Mozilla/5.0")


def test_bearer_auth_header(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_FakeResponse(200, "{}")])
    _install(monkeypatch, transport)
    http.HttpClient(base_url="http://t", auth=http.bearer_auth("tok123")).get("/x")
    assert transport.requests[0].get_header("Authorization") == "Bearer tok123"


def test_private_token_auth_header(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_FakeResponse(200, "{}")])
    _install(monkeypatch, transport)
    http.HttpClient(base_url="http://t", auth=http.private_token_auth("glpat-x")).get("/x")
    assert transport.requests[0].get_header("Private-token") == "glpat-x"


def test_basic_auth_header(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_FakeResponse(200, "{}")])
    _install(monkeypatch, transport)
    http.HttpClient(base_url="http://t", auth=http.basic_auth("", "pat")).get("/x")
    header = transport.requests[0].get_header("Authorization")
    assert header is not None and header.startswith("Basic ")


def test_post_sets_content_type_and_body(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_FakeResponse(201, json.dumps({"id": 7}))])
    _install(monkeypatch, transport)
    resp = http.HttpClient(base_url="http://t").post("/items", body={"name": "a"})
    req = transport.requests[0]
    assert req.get_header("Content-type") == "application/json"
    assert isinstance(req.data, bytes)
    assert json.loads(req.data.decode()) == {"name": "a"}
    assert resp.json == {"id": 7}


def test_4xx_returned_immediately_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_http_error(404, "missing")])
    _install(monkeypatch, transport)
    client = http.HttpClient(base_url="http://t", _sleep=lambda _s: None)
    resp = client.get("/nope")
    assert resp.status == 404
    assert "missing" in resp.json["error"]
    assert len(transport.requests) == 1  # not retried


def test_5xx_is_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_http_error(503), _FakeResponse(200, json.dumps({"ok": 1}))])
    _install(monkeypatch, transport)
    slept: list[float] = []
    client = http.HttpClient(base_url="http://t", _sleep=slept.append)
    resp = client.get("/flaky")
    assert resp.status == 200
    assert resp.json == {"ok": 1}
    assert len(transport.requests) == 2
    assert slept  # backed off once


def test_5xx_exhausts_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_http_error(500), _http_error(500), _http_error(500)])
    _install(monkeypatch, transport)
    client = http.HttpClient(base_url="http://t", _sleep=lambda _s: None)
    resp = client.get("/down")
    assert resp.status == 500
    assert len(transport.requests) == 3


def test_network_error_returns_status_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([urllib.error.URLError("dns"), urllib.error.URLError("dns")])
    _install(monkeypatch, transport)
    client = http.HttpClient(base_url="http://t", max_attempts=2, _sleep=lambda _s: None)
    resp = client.get("/unreachable")
    assert resp.status == 0
    assert "dns" in resp.json["error"]


def test_non_json_body_wrapped_as_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_FakeResponse(200, "plain text")])
    _install(monkeypatch, transport)
    resp = http.HttpClient(base_url="http://t").get("/text")
    assert resp.json == {"raw": "plain text"}


def test_json_array_body_wrapped_in_items(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_FakeResponse(200, json.dumps([1, 2, 3]))])
    _install(monkeypatch, transport)
    resp = http.HttpClient(base_url="http://t").get("/list")
    assert resp.json == {"items": [1, 2, 3]}


@pytest.mark.parametrize(
    ("status", "expected"),
    [(200, True), (201, True), (299, True), (300, False), (404, False), (500, False), (0, False)],
)
def test_is_success(status: int, expected: bool) -> None:
    assert http.is_success(status) is expected
