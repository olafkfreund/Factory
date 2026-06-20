"""Behaviour-lock for the shared-HTTP refactor of the two hub consumers.

Epic Factory#154 / issue Factory#161: scripts/parr_regression.py::_call and
scripts/sync_labels.py::_http_json each hand-rolled the same urllib JSON helper
and were refactored onto factory_common.http.HttpClient. These tests lock that
the consumers still behave as before (the proof-of-consumption), driving the
shared client via a stubbed urlopen rather than real network.
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

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import parr_regression  # noqa: E402
import sync_labels  # noqa: E402


class _FakeResponse:
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


def test_parr_call_returns_status_and_json(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_FakeResponse(200, json.dumps({"status": "ok"}))])
    _install(monkeypatch, transport)
    code, body = parr_regression._call("pfactory", "GET", "/api/health")
    assert code == 200
    assert body == {"status": "ok"}
    # Cloudflare-friendly UA + bearer auth preserved through the shared client.
    assert transport.requests[0].get_header("User-agent", "").startswith("Mozilla/5.0")


def test_parr_call_network_failure_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([urllib.error.URLError("boom")] * 3)
    _install(monkeypatch, transport)
    monkeypatch.setattr("factory_common.http.time.sleep", lambda _s: None)
    code, body = parr_regression._call("pfactory", "GET", "/api/health")
    assert code == 0
    assert "boom" in body["error"]


def test_sync_http_json_unwraps_array(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_FakeResponse(200, json.dumps([{"name": "a"}]))])
    _install(monkeypatch, transport)
    out = sync_labels._http_json("GET", "https://gitlab.com/x", {"PRIVATE-TOKEN": "t"})
    assert out == [{"name": "a"}]
    assert transport.requests[0].get_header("Private-token") == "t"


def test_sync_http_json_raises_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport(
        [
            urllib.error.HTTPError(
                url="https://x", code=403, msg="forbidden", hdrs=Message(), fp=io.BytesIO(b"nope")
            )
        ]
    )
    _install(monkeypatch, transport)
    with pytest.raises(RuntimeError, match="403"):
        sync_labels._http_json("GET", "https://x", {"PRIVATE-TOKEN": "t"})


def test_sync_http_json_returns_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = _Transport([_FakeResponse(200, json.dumps({"value": [1, 2]}))])
    _install(monkeypatch, transport)
    out = sync_labels._http_json("GET", "https://dev.azure.com/x", {"Authorization": "Basic z"})
    assert out == {"value": [1, 2]}
