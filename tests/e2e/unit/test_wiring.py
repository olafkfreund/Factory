"""Offline checks for the step 2b adapters and entry point."""

import json
import socket
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from scripts.e2e import run, services, stages
from scripts.e2e.config import HOSTS
from scripts.e2e.guard import Guard
from scripts.e2e.journey import Journey


def test_mvr_dry_run_never_opens_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[object] = []

    def forbidden(*args: object, **kwargs: object) -> None:
        calls.append((args, kwargs))
        raise AssertionError("network call")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    assert run.main(["--slice", "mvr", "--evidence-root", str(tmp_path)]) == 0
    assert calls == []
    output = capsys.readouterr().out
    assert output.count(": S1") == 5
    meta = next(tmp_path.glob("*/run.meta.json"))
    assert len(json.loads(meta.read_text())["journeys"]) == 5


def test_live_fails_before_network_or_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("network call"))
    with pytest.raises(NotImplementedError, match="ownership"):
        run.main(["--slice", "mvr", "--live", "--evidence-root", str(tmp_path)])
    assert list(tmp_path.iterdir()) == []


def test_service_reads_key_at_each_call_without_printing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key = tmp_path / ".token"
    key.write_text("secret-one")
    seen: list[str] = []

    class FakeHttpClient:
        def __init__(self, **kwargs: Any) -> None:
            self.auth = kwargs["auth"]
            assert kwargs["base_url"] == HOSTS["aifactory"]
            assert kwargs["follow_redirects"] is False

        def request(self, _method: str, _path: str, _body: object) -> Any:
            seen.append(self.auth()["Authorization"])
            return SimpleNamespace(status=200, json={"id": "task-1"})

    monkeypatch.setattr(services, "HttpClient", FakeHttpClient)
    client = services.Services({"aifactory": key})
    assert client.read_resource("aifactory", "task", "task-1") == {"id": "task-1"}
    key.write_text("secret-two")
    assert client.read_resource("aifactory", "task", "task-1") == {"id": "task-1"}
    assert seen == ["Bearer secret-one", "Bearer secret-two"]
    captured = capsys.readouterr()
    assert "secret-" not in captured.out + captured.err


def test_unknown_mutation_route_never_sends_request(monkeypatch: pytest.MonkeyPatch) -> None:
    client = services.Services({})
    monkeypatch.setattr(client, "_request", lambda *_: pytest.fail("unguarded request"))
    with pytest.raises(NotImplementedError, match="delete route"):
        client.delete("tfactory", "project", "project-1")


def test_stages_use_guard_for_every_mutation() -> None:
    calls: list[tuple[str, str]] = []

    class FakeGuard:
        def create_repo(
            self,
            _name: str,
            create: Callable[[], dict[str, Any]],
            set_topics: Callable[[str, list[str]], object],
        ) -> dict[str, Any]:
            calls.append(("github", "create"))
            repo = create()
            set_topics(repo["full_name"], ["factory-e2e"])
            return repo

        def create_resource(
            self, kind: str, service: str, _repo: str, create: Callable[[], dict[str, Any]]
        ) -> dict[str, Any]:
            calls.append((service, kind))
            return create()

        def mutate(self, service: str, kind: str, _identity: str, action: Any) -> Any:
            calls.append((service, kind))
            return action()

    class FakeOperations:
        def create_repo(self, name: str) -> dict[str, Any]:
            return {"node_id": "R1", "full_name": f"Freundcloud/{name}"}

        def set_topics(self, *_: object) -> None:
            return None

        def push_starter(self, *_: object) -> None:
            return None

        def onboard(self, service: str, *_: object) -> dict[str, Any]:
            return {"id": service + "-1"}

        def submit(self, *_: object) -> dict[str, Any]:
            return {"session_id": "s1", "task_id": "t1", "card_key": "c1"}

        def read_resource(self, _service: str, kind: str, identity: str) -> dict[str, Any]:
            return {"key" if kind == "card" else "id": identity}

    built = stages.build(
        Journey("P1", "cli", "Claude", 1),
        cast(Guard, FakeGuard()),
        cast(stages.Operations, FakeOperations()),
        "e2e-20261124-P1-1",
    )
    built["S1"](999, lambda *_: None)
    built["S2"](999, lambda *_: None)
    assert calls == [
        ("github", "create"),
        ("github", "repo"),
        ("aifactory", "project"),
        ("pfactory", "project"),
        ("tfactory", "project"),
        ("pfactory", "project"),
        ("pfactory", "session"),
        ("aifactory", "task"),
        ("cfactory", "card"),
    ]
