"""Regression cases for the live campaign safety boundaries."""

import base64
import importlib
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from scripts.e2e import cleanup, github, run, services, stages
from scripts.e2e.cost import Budget
from scripts.e2e.evidence import safe_fields
from scripts.e2e.guard import Guard
from scripts.e2e.journey import Journey
from scripts.e2e.registry import Registry


def test_projects_accept_real_http_array_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = tmp_path / "key"
    key.write_text("test-token")

    class Client:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        def request(self, _method: str, _path: str, _body: object) -> Any:
            parse = importlib.import_module("factory_common.http")._parse_body
            return SimpleNamespace(status=200, json=parse(json.dumps([{"id": "p1"}])))

    monkeypatch.setattr(services, "HttpClient", Client)
    assert services.Services({"pfactory": key}).read_resource("pfactory", "project", "p1") == {
        "id": "p1",
        "repo_node_id": None,
        "org": "default",
    }


def test_other_array_reads_accept_http_items_wrapper(monkeypatch: pytest.MonkeyPatch) -> None:
    client = services.Services({})
    parse = importlib.import_module("factory_common.http")._parse_body
    monkeypatch.setattr(client, "_request", lambda *_: parse('[{"id":"a1:t1"}]'))
    assert client.task_ids("a1") == {"a1:t1"}
    assert client.anomalies() == [{"id": "a1:t1"}]


def test_onboard_records_intent_and_unverified_id_before_failed_readback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = Registry("campaign", tmp_path)
    full_name = "olafkfreund/e2e-20261124-P1-1"
    registry.append("repo", "R1", "R1", service="github", repo_id=1, full_name=full_name)
    guard = Guard(registry, lambda _: None, lambda *_: None)
    ops = stages.LiveOperations(
        Journey("P1", "cli", "Claude", 1), guard, services.Services({}), github.GitHub(), tmp_path
    )

    def surface(*_args: object, **_kwargs: object) -> dict[str, Any]:
        assert registry.find("pfactory", "resource_intent", full_name)
        return {"result": {"id": "p1"}}

    monkeypatch.setattr(ops, "_surface", surface)
    monkeypatch.setattr(
        ops.services, "read_resource", lambda *_: (_ for _ in ()).throw(RuntimeError("read failed"))
    )
    with pytest.raises(RuntimeError, match="read failed"):
        ops.onboard("pfactory", full_name, "cli")
    row = registry.find("pfactory", "project", "p1")
    assert row is not None and row["unverified"] is True


def test_hidden_suite_uses_minimal_bwrap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class Git:
        def fetch_commit(self, *_: object) -> None:
            pass

    ops = stages.LiveOperations(
        Journey("P1", "cli", "Claude", 1),
        cast(Guard, None),
        cast(services.Services, None),
        cast(github.GitHub, Git()),
        tmp_path,
    )
    monkeypatch.setattr(
        "scripts.e2e.stages.shutil.which", lambda name: f"/nix/store/test/bin/{name}"
    )
    seen: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        seen.append((argv, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("scripts.e2e.stages.subprocess.run", fake_run)
    assert ops.hidden("P1", "olafkfreund/test", "a" * 40)
    argv, kwargs = seen[-1]
    assert argv[0].endswith("bwrap")
    assert "--unshare-all" in argv and "--clearenv" in argv
    assert [argv[i + 1] for i, item in enumerate(argv[:-1]) if item == "--bind"] == [str(tmp_path)]
    hidden_source = Path(argv[argv.index("/suite") - 1])
    assert hidden_source.parent.parent == Path(tempfile.gettempdir())
    assert hidden_source.parent.name.startswith("factory-e2e-hidden-")
    assert not any("agenix" in item or "/home/olafkfreund" in item for item in argv)
    assert kwargs["env"] == {"PATH": "/nix/store", "PYTHONDONTWRITEBYTECODE": "1"}


def test_missing_bwrap_skips_hidden_suite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ops = stages.LiveOperations(
        Journey("P1", "cli", "Claude", 1),
        cast(Guard, None),
        cast(services.Services, None),
        cast(github.GitHub, None),
        tmp_path,
    )
    monkeypatch.setattr("scripts.e2e.stages.shutil.which", lambda _: None)
    monkeypatch.setattr(
        "scripts.e2e.stages.subprocess.run", lambda *_a, **_k: pytest.fail("unsandboxed run")
    )
    assert ops.hidden("P1", "olafkfreund/test", "a" * 40) is False
    assert ops.hidden_skip_reason == "bubblewrap unavailable"


def test_repo_delete_resolves_node_id_from_registry(tmp_path: Path) -> None:
    registry = Registry("campaign", tmp_path)
    full_name = "olafkfreund/e2e-20261124-P1-1"
    registry.append("repo", "R1", "R1", service="github", repo_id=1, full_name=full_name)
    seen: list[str] = []
    github = SimpleNamespace(delete_repo=seen.append, read_repo=lambda name: {"full_name": name})
    deleter = cleanup.LiveDelete(None, github, registry)  # type: ignore[arg-type]
    deleter.delete("github", "repo", "R1")
    assert seen == [full_name]
    assert deleter.exists("github", "repo", "R1")


def test_sweep_deletes_registered_repo_by_node_through_guard(tmp_path: Path) -> None:
    registry = Registry("campaign", tmp_path)
    full_name = "olafkfreund/e2e-20261124-P1-1"
    registry.append("repo", "R1", "R1", service="github", repo_id=1, full_name=full_name)
    deleted: list[str] = []

    def read_repo(name: str) -> dict[str, Any] | None:
        if deleted:
            return None
        return {
            "node_id": "R1",
            "id": 1,
            "full_name": name,
            "name": "e2e-20261124-P1-1",
            "owner": {"login": "olafkfreund"},
            "topics": ["factory-e2e"],
        }

    github_client = SimpleNamespace(read_repo=read_repo, delete_repo=deleted.append)
    guard = Guard(registry, read_repo, lambda *_: None)
    actions = cleanup.sweep(
        registry,
        guard,
        cleanup.LiveDelete(None, github_client, registry),  # type: ignore[arg-type]
        dry_run=False,
        now=datetime.now(UTC) + timedelta(days=8),
    )
    assert {row["action"] for row in actions} == {"delete"}
    assert deleted == [full_name]
    assert registry.find("github", "deleted", "R1")


def test_campaign_cap_and_lane_release() -> None:
    budget = Budget(None, 0.01)  # type: ignore[arg-type]
    for lane in ("a", "b", "c", "d", "e"):
        budget.reserve(lane, 0.001)
        budget.release(lane, 0.0005)
    assert budget.lanes == set()
    assert budget.spent == pytest.approx(0.0025)
    with pytest.raises(ValueError):
        budget.reserve("too-much", 0.01)
    with pytest.raises(ValueError, match="finite"):
        Budget(None, float("inf"))  # type: ignore[arg-type]


def test_nonfinite_cli_cap_rejected_before_any_journey(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        run.main(["--slice", "mvr", "--cap-usd", "nan", "--evidence-root", str(tmp_path)])
    assert "--cap-usd must be finite and positive" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_one_cent_cap_confirms_remote_stop(tmp_path: Path) -> None:
    registry = Registry("campaign", tmp_path)
    full_name = "olafkfreund/e2e-20261124-P1-1"
    registry.append("repo", "R1", "R1", service="github", repo_id=1, full_name=full_name)
    registry.append("task", "a1:t1", "R1", service="aifactory", org="default")
    guard = Guard(
        registry,
        lambda _: {
            "node_id": "R1",
            "id": 1,
            "full_name": full_name,
            "name": "e2e-20261124-P1-1",
            "owner": {"login": "olafkfreund"},
            "topics": ["factory-e2e"],
        },
        lambda _service, _kind, identity: {"id": identity, "repo_node_id": "R1", "org": "default"},
    )
    stopped: list[str] = []

    def s2(_deadline: float, poll: Any) -> dict[str, Any]:
        poll("a1:t1", 0.01)
        raise AssertionError("cap did not stop the stage")

    stages_by_name: dict[str, Any] = {"S1": lambda *_: {}}
    stages_by_name["S2"] = s2
    with pytest.raises(ValueError, match="remote stop confirmed"):
        Journey("P1", "cli", "Claude", 1).run(
            stages_by_name,
            Budget(guard, 0.01),
            "lane",
            readback=lambda *_: {
                "registered": True,
                "branch_protection": True,
                "projects": {"aifactory": 1, "pfactory": 1, "tfactory": 1},
                "cards": 1,
            },
            remote=(stopped.append, lambda _: {"status": "stopped"}),
        )
    assert stopped == ["a1:t1"]


def test_sweep_cli_is_dry_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[bool] = []

    def fake_sweep(*_args: object, **kwargs: Any) -> list[dict[str, Any]]:
        seen.append(kwargs["dry_run"])
        return []

    monkeypatch.setattr(run, "sweep", fake_sweep)
    assert run.main(["sweep", "--evidence-root", str(tmp_path)]) == 0
    assert seen == [True]


def test_live_preflight_aborts_before_first_journey(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def request(_self: object, service: str, _method: str, _path: str) -> object:
        seen.append(service)
        if service == "tfactory":
            raise RuntimeError("tfactory HTTP 401")
        return {"items": []}

    monkeypatch.setattr(services.Services, "_request", request)
    monkeypatch.setattr(run, "build", lambda *_: pytest.fail("journey began"))
    with pytest.raises(RuntimeError, match="HTTP 401"):
        run.run_live([Journey("P1", "cli", "Claude", 1)], "campaign", tmp_path)
    assert seen == ["aifactory", "pfactory", "tfactory"]


def test_missing_sandbox_records_s5_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(services.Services, "_request", lambda *_: {"items": []})
    monkeypatch.setattr(
        run,
        "LiveOperations",
        lambda *_: SimpleNamespace(hidden_skip_reason="bubblewrap unavailable", probes={}),
    )
    monkeypatch.setattr(run, "build", lambda *_: {})
    monkeypatch.setattr(
        Journey, "run", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("S5"))
    )
    rows = run.run_live([Journey("P1", "cli", "Claude", 1)], "campaign", tmp_path)
    assert rows[0]["status"] == "skipped"
    assert rows[0]["stage_results"]["S5"] == {
        "status": "skipped",
        "reason": "bubblewrap unavailable",
    }
    assert safe_fields(rows[0], {"stage_results"})["stage_results"]["S5"] == {
        "status": "skipped",
        "reason": "bubblewrap unavailable",
    }


def test_cap_test_runs_one_p1_with_one_cent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[list[Journey], float]] = []

    def live(runs: list[Journey], _campaign: str, _root: Path, cap: float) -> list[dict[str, Any]]:
        seen.append((runs, cap))
        return [{"status": "cap_confirmed"}]

    monkeypatch.setattr(run, "run_live", live)
    assert run.main(["--cap-test", "--live", "--evidence-root", str(tmp_path)]) == 0
    assert seen == [([Journey("P1", "cli", "Claude", 1)], 0.01)]


def test_s2_tracks_dispatched_task_before_ownership_read_fails(tmp_path: Path) -> None:
    registry = Registry("campaign", tmp_path)
    repo_node_id = "R1"
    name = "e2e-20261124-P1-1"

    class GuardStub:
        def __init__(self) -> None:
            self.registry = registry

        def create_repo(self, _name: str, create: Any, topics: Any) -> dict[str, Any]:
            result = create()
            topics(result["full_name"], ["factory-e2e"])
            return cast(dict[str, Any], result)

        def mutate(self, _service: str, _kind: str, _id: str, action: Any) -> Any:
            return action()

        def create_resource(self, kind: str, _service: str, _repo: str, create: Any) -> Any:
            if kind == "task":
                raise RuntimeError("task read-back failed")
            return create()

    class Ops:
        def create_repo(self, _name: str) -> dict[str, Any]:
            return {"node_id": repo_node_id, "full_name": f"olafkfreund/{name}"}

        def set_topics(self, *_: object) -> None: ...
        def push_starter(self, *_: object) -> None: ...
        def protect_main(self, *_: object) -> None: ...
        def create_issue(self, *_: object) -> dict[str, int]:
            return {"number": 1}

        def onboard(self, service: str, *_: object) -> dict[str, str]:
            return {"id": service}

        def register_cf_repository(self, *_: object) -> dict[str, str]:
            return {"id": "cf"}

        def create_card(self, *_: object) -> dict[str, str]:
            return {"key": name}

        def submit(self, *_: object) -> dict[str, str]:
            return {"session_id": "s1", "task_id": "aifactory:t1"}

        def read_resource(self, _service: str, _kind: str, identity: str) -> dict[str, str]:
            return {"id": identity}

    built = stages.build(Journey("P1", "cli", "Claude", 1), GuardStub(), Ops(), name)  # type: ignore[arg-type]
    built["S1"](999, lambda *_: None)
    seen: list[str] = []
    with pytest.raises(RuntimeError, match="task read-back failed"):
        built["S2"](999, lambda task=None: seen.append(task) if task else None)
    assert seen == ["aifactory:t1"]
    row = registry.find("aifactory", "task", "aifactory:t1")
    assert row is not None and row["unverified"] is True
    assert any(
        row["kind"] == "session" and row["id"] == "s1" and row.get("unverified")
        for row in registry.entries()
    )


def test_probe_c_stops_accepted_tampered_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = Registry("campaign", tmp_path)
    full_name = "olafkfreund/e2e-20261124-P1-1"
    live_repo = {
        "node_id": "R1",
        "id": 1,
        "full_name": full_name,
        "name": full_name.split("/")[1],
        "owner": {"login": "olafkfreund"},
        "topics": ["factory-e2e"],
    }
    registry.append("repo", "R1", "R1", service="github", repo_id=1, full_name=full_name)
    registry.append("project", "a1", "R1", service="aifactory", org="default")
    registry.append("project", "p1", "R1", service="pfactory", org="default")
    guard = Guard(
        registry,
        lambda _: live_repo,
        lambda _service, _kind, identity: {"id": identity, "repo_node_id": "R1", "org": "default"},
    )
    client = services.Services({})
    stopped: list[str] = []
    monkeypatch.setattr(
        client,
        "probe_request",
        lambda *_: {
            "status": 200,
            "reason": "accepted",
            "body": {"session_id": "s1", "aifactory_task_id": "af:a1:t1"},
        },
    )
    monkeypatch.setattr(client, "stop", stopped.append)
    monkeypatch.setattr(client, "stop_status", lambda _: {"status": "stopped"})
    monkeypatch.setattr(
        client,
        "read_resource",
        lambda _service, _kind, identity: {"id": identity, "repo_node_id": "R1", "org": "default"},
    )
    ops = stages.LiveOperations(
        Journey("P1", "cli", "Claude", 1), guard, client, github.GitHub(), tmp_path
    )
    ops.projects = {"aifactory": "a1", "pfactory": "p1"}
    monkeypatch.setattr(ops, "_approved_payload", lambda _: {"artifacts": [{"content": "old"}]})
    with pytest.raises(AssertionError, match="probe c"):
        ops.probe_c(full_name)
    assert stopped == ["a1:t1"]
    row = registry.find("aifactory", "task", "a1:t1")
    assert row is not None and row["unverified"] is True
    assert any(
        row["kind"] == "session" and row["id"] == "s1" and row.get("unverified")
        for row in registry.entries()
    )


def test_git_fetch_uses_basic_header_and_no_credential_helper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("classic-pat")
    seen: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr("scripts.e2e.github.shutil.which", lambda _: "/bin/git")
    monkeypatch.setattr(
        "scripts.e2e.github.subprocess.run", lambda argv, **kwargs: seen.append((argv, kwargs))
    )
    github.GitHub(token_file).fetch_commit("olafkfreund/e2e-20261124-P1-1", "a" * 40, tmp_path)
    argv, kwargs = seen[0]
    env = kwargs["env"]
    assert "classic-pat" not in str(argv)
    assert (
        env["GIT_CONFIG_VALUE_0"]
        == "Authorization: basic " + base64.b64encode(b"x-access-token:classic-pat").decode()
    )
    assert env["GIT_CONFIG_KEY_1"] == "credential.helper"
    assert env["GIT_CONFIG_VALUE_1"] == "" and env["GIT_TERMINAL_PROMPT"] == "0"
