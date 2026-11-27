"""Offline checks for the step 2b adapters and entry point."""

import base64
import json
import socket
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from scripts.e2e import github, run, services, stages
from scripts.e2e.config import HOSTS
from scripts.e2e.guard import Guard
from scripts.e2e.journey import Journey
from scripts.e2e.registry import Registry
from scripts.e2e.surfaces import mcp


def _registry_with_repo(root: Path) -> Registry:
    registry = Registry("campaign", root)
    registry.append(
        "repo", "R1", "R1", service="github", repo_id=1, full_name="olafkfreund/e2e-20261124-P1-1"
    )
    return registry


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


def test_live_writes_results_from_injected_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(socket.socket, "connect", lambda *_: pytest.fail("network call"))
    seen: list[Journey] = []

    def fake_live(
        runs: list[Journey], _campaign: str, _root: Path, _cap: float
    ) -> list[dict[str, Any]]:
        seen.extend(runs)
        return [
            {"status": "failed", "probes": {"c": {"status": "skipped", "reason": "no safe seam"}}}
        ]

    monkeypatch.setattr(run, "run_live", fake_live)
    assert run.main(["--slice", "mvr", "--live", "--evidence-root", str(tmp_path)]) == 1
    assert len(seen) == 5
    meta = next(tmp_path.glob("*/run.meta.json"))
    assert json.loads(meta.read_text())["journeys"][0]["probes"]["c"]["status"] == "skipped"


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
            body: object = [] if _path == "/api/mcp-stdio/projects" else {"id": "task-1"}
            return SimpleNamespace(status=200, json=body)

    monkeypatch.setattr(services, "HttpClient", FakeHttpClient)
    client = services.Services({"aifactory": key})
    assert client.read_resource("aifactory", "task", "task-1") == {
        "id": "task-1",
        "repo_node_id": None,
        "org": "default",
    }
    key.write_text("secret-two")
    assert client.read_resource("aifactory", "task", "task-1") == {
        "id": "task-1",
        "repo_node_id": None,
        "org": "default",
    }
    assert seen == ["Bearer secret-one"] * 2 + ["Bearer secret-two"] * 2
    captured = capsys.readouterr()
    assert "secret-" not in captured.out + captured.err


def test_unknown_mutation_route_never_sends_request(monkeypatch: pytest.MonkeyPatch) -> None:
    client = services.Services({})
    monkeypatch.setattr(client, "_request", lambda *_: pytest.fail("unguarded request"))
    with pytest.raises(NotImplementedError, match="delete route"):
        client.delete("pfactory", "task", "task-1")


def test_service_ownership_fields_and_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry_with_repo(tmp_path)
    client = services.Services({}, registry)
    responses: dict[tuple[str, str], object] = {
        ("aifactory", "/api/mcp-stdio/projects"): [
            {"id": "a1", "repoIdentity": "github.com/olafkfreund/e2e-20261124-p1-1"}
        ],
        ("pfactory", "/api/mcp-stdio/projects"): [{"id": "p1", "repo": None}],
        ("tfactory", "/api/mcp-stdio/projects"): [
            {"id": "t1", "repoLabel": "olafkfreund/e2e-20261124-P1-1"}
        ],
        ("pfactory", "/api/mcp-stdio/plan/sessions/s1"): {
            "session_id": "s1",
            "repo": "olafkfreund/e2e-20261124-P1-1",
            "org_id": "o1",
        },
        ("aifactory", "/api/mcp-stdio/tasks/a1%3Aspec"): {"id": "a1:spec"},
        ("tfactory", "/api/tfactory/tasks/spec?project_id=t1"): {
            "task_id": "spec",
            "project_id": "t1",
        },
        ("tfactory", "/api/tfactory/tasks/orphan?project_id=t9"): {
            "task_id": "orphan",
            "project_id": "t9",
        },
        ("tfactory", "/api/tfactory/tasks/other?project_id=t1"): {
            "task_id": "other",
            "project_id": "t2",
        },
        ("cfactory", "/api/cards/C-1"): {
            "card_key": "C-1",
            "tenant_id": "default",
            "repository_id": 7,
        },
        ("cfactory", "/api/tenants/default/git-repositories"): {
            "repositories": [{"id": 7, "project": "olafkfreund/e2e-20261124-P1-1"}]
        },
    }

    def fake_request(service: str, method: str, path: str, _body: object = None) -> Any:
        assert method == "GET"
        return responses[service, path]

    monkeypatch.setattr(client, "_request", fake_request)
    for service, kind, identity, field, expected in (
        ("aifactory", "project", "a1", "repo_node_id", "R1"),
        ("pfactory", "project", "p1", "org", "default"),
        ("tfactory", "project", "t1", "repo_node_id", "R1"),
        ("pfactory", "session", "s1", "org", "o1"),
        ("aifactory", "task", "a1:spec", "repo_node_id", "R1"),
        ("tfactory", "spec", "t1:spec", "repo_node_id", "R1"),
        ("cfactory", "card", "C-1", "repo_node_id", "R1"),
    ):
        resource = client.read_resource(service, kind, identity)
        assert resource is not None and resource[field] == expected
    # #3937: a TF spec echoing another project is not ours.
    assert client.read_resource("tfactory", "spec", "t1:other") is None
    orphan = client.read_resource("tfactory", "spec", "t9:orphan")
    assert orphan is not None and orphan["repo_node_id"] is None


@pytest.mark.parametrize(  # type: ignore[untyped-decorator, unused-ignore]
    "case",
    [
        ("DELETE", "aifactory", "project", "a1", "/api/projects/a1", None),
        ("DELETE", "pfactory", "project", "p1", "/api/projects/p1", None),
        ("DELETE", "tfactory", "project", "t1", "/api/projects/t1", None),
        ("DELETE", "cfactory", "card", "C-1", "/api/cards/C-1", None),
        ("DELETE", "cfactory", "repository", "7", "/api/tenants/default/git-repositories/7", None),
        (
            "POST",
            "tfactory",
            "spec",
            "t1:s1",
            "/api/mcp-stdio/projects/t1/tasks/archive",
            {"taskIds": ["t1:s1"]},
        ),
        (
            "POST",
            "aifactory",
            "task",
            "a1:s1",
            "/api/mcp-stdio/projects/a1/tasks/archive",
            {"taskIds": ["a1:s1"]},
        ),
    ],
)
def test_cleanup_routes(
    monkeypatch: pytest.MonkeyPatch,
    case: tuple[str, str, str, str, str, object],
) -> None:
    method, service, kind, identity, path, body = case
    client = services.Services({})
    seen: list[object] = []
    monkeypatch.setattr(client, "_request", lambda *args: seen.append(args))
    client.delete(service, kind, identity)
    expected = (service, method, path, body) if body is not None else (service, method, path)
    assert seen == [expected]


def test_github_create_and_push_keep_token_out_of_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = tmp_path / "token"
    token.write_text("test-secret")
    client = github.GitHub(token)
    requested: list[object] = []

    def fake_request(*args: object) -> dict[str, str]:
        requested.append(args)
        return {"name": "repo"}

    monkeypatch.setattr(client, "request", fake_request)
    assert client.create_repo("repo") == {"name": "repo"}
    assert requested == [
        ("POST", "/user/repos", {"name": "repo", "private": False, "auto_init": False})
    ]
    starter = tmp_path / "starter"
    triple = tmp_path / "triple"
    starter.mkdir()
    triple.mkdir()
    (starter / "a.txt").write_text("a")
    for stage in ("intent", "spec", "plan"):
        folder = triple / stage
        folder.mkdir()
        (folder / "test.md").write_text("---\nstatus: approved\n---\n")
    (triple / "execution.json").write_text("{}")
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> None:
        calls.append((argv, kwargs["env"]))

    monkeypatch.setattr("scripts.e2e.github.subprocess.run", fake_run)
    client.push_starter(starter, triple, "olafkfreund/repo", tmp_path / "work")
    assert len(calls) == 20  # push, then origin remote and origin/main for factory submit
    assert all("test-secret" not in str(argv) for argv, _ in calls)
    basic = base64.b64encode(b"x-access-token:test-secret").decode()
    assert all(env["GIT_CONFIG_VALUE_0"] == f"Authorization: basic {basic}" for _, env in calls)
    assert all(env["GIT_CONFIG_KEY_1"] == "credential.helper" for _, env in calls)
    assert all(
        env["GIT_CONFIG_VALUE_1"] == "" and env["GIT_TERMINAL_PROMPT"] == "0" for _, env in calls
    )
    assert (tmp_path / "work" / "a.txt").read_text() == "a"
    assert (tmp_path / "work" / "execution.json").read_text() == "{}"
    assert (tmp_path / "work" / "plan" / "test.md").read_text() == ("---\nstatus: approved\n---\n")


def test_mcp_surface_uses_isolated_stdio_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[list[str], dict[str, Any]]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        seen.append((argv, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "error": False,
                    "content": [json.dumps({"outcome": "ok", "result": {"id": "p1"}})],
                }
            ),
        )

    monkeypatch.setattr("scripts.e2e.surfaces.cli.shutil.which", lambda _: "/bin/uv")
    assert (
        mcp.invoke(
            "factory_project_add", {"portal": "pfactory"}, cwd=tmp_path, key_files={}, run=fake_run
        )["result"]["id"]
        == "p1"
    )
    argv, kwargs = seen[0]
    assert argv[:4] == ["/bin/uv", "run", "--no-project", "--with-editable"]
    assert json.loads(kwargs["input"])["tool"] == "factory_project_add"
    assert kwargs["env"]["HOME"] != str(Path.home())


def test_aif_usage_maps_wire_cost_for_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    client = services.Services({})
    monkeypatch.setattr(
        client,
        "_request",
        lambda *_: {
            "totalTokens": 42,
            "totalCostUsd": 1.25,
        },
    )
    assert client.usage("a1:s1")["cost_usd"] == 1.25
    assert client.usage("a1:s1")["total_tokens"] == 42


def test_status_readback_and_session_close_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    client = services.Services({})
    calls: list[tuple[object, ...]] = []

    def fake_request(*args: object) -> Any:
        calls.append(args)
        path = str(args[2])
        if path.endswith("/status"):
            return {"is_running": False, "queued": False}
        if path.endswith("/tasks?project_id=a1"):
            return {"tasks": [{"id": "a1:s1"}]}
        if path.endswith("/verdicts.json?project_id=t1"):
            return {"verdicts": []}
        if path.endswith("/api/tokens"):
            return {"by_work_item": []}
        if path.endswith("/api/anomalies"):
            return {"anomalies": []}
        return {"source_sha": "a" * 40}

    monkeypatch.setattr(client, "_request", fake_request)
    assert client.task_ids("a1") == {"a1:s1"}
    assert client.stop_status("a1:s1") == {"status": "stopped"}
    verdict = client.verdict("t1:s1")
    assert verdict is not None and verdict["verdict_sha"] == "a" * 40
    assert client.qa_report("a1:s1") is not None
    assert client.timeline("card") is not None
    assert client.workitem("card") is not None
    assert client.tokens() == {"by_work_item": []}
    assert client.anomalies() == []
    client.stop("a1:s1")
    client.close_session("s1")
    paths = {str(call[2]) for call in calls}
    assert {
        "/api/mcp-stdio/tasks?project_id=a1",
        "/api/mcp-stdio/tasks/a1%3As1/status",
        "/api/tfactory/tasks/s1?project_id=t1",
        "/api/tfactory/tasks/s1/verdicts.json?project_id=t1",
        "/api/mcp-stdio/tasks/a1%3As1/qa-report",
        "/api/workitems/card/timeline",
        "/api/workitems/card",
        "/api/tokens",
        "/api/anomalies",
        "/api/tasks/a1%3As1/stop",
        "/api/plan/sessions/s1/discard",
    } <= paths


def test_emitted_pf_session_is_retained_without_discard(monkeypatch: pytest.MonkeyPatch) -> None:
    client = services.Services({})
    monkeypatch.setattr(
        client,
        "read_resource",
        lambda *_: {"id": "s1", "status": "emitted", "org": "default"},
    )
    monkeypatch.setattr(client, "_request", lambda *_: pytest.fail("emitted session discarded"))
    assert client.close_session("s1") == {"retained": True}


def test_enable_pr_endgame_turns_on_auto_pr_and_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    client = services.Services({})
    calls: list[tuple[object, ...]] = []

    def fake_request(*args: object) -> dict[str, Any]:
        calls.append(args)
        return {}

    monkeypatch.setattr(client, "_request", fake_request)
    client.enable_pr_endgame("a1")
    assert calls == [
        ("aifactory", "PATCH", "/api/projects/a1/settings", {"autoPr": True, "autoMerge": True})
    ]


def test_cf_repository_and_card_creation_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _registry_with_repo(tmp_path)
    client = services.Services({}, registry)
    calls: list[tuple[object, ...]] = []

    def fake_request(service: str, method: str, path: str, body: object = None) -> Any:
        calls.append((service, method, path, body))
        if path.endswith("/git-connections"):
            return {"connections": [{"id": 2, "provider": "github", "status": "verified"}]}
        if path.endswith("/repositories") and method == "POST":
            return {"id": 7}
        if path.endswith("/git-repositories"):
            return {"repositories": [{"id": 7, "project": "olafkfreund/e2e-20261124-P1-1"}]}
        if path == "/api/cards":
            return {"card_key": "C-1"}
        if path == "/api/cards/C-1":
            return {"card_key": "C-1", "repository_id": 7, "tenant_id": "default"}
        return None

    monkeypatch.setattr(client, "_request", fake_request)
    repo = client.register_cf_repository("olafkfreund/e2e-20261124-P1-1", "a1")
    assert repo["repo_node_id"] == "R1"
    card = client.create_card("C-1", "olafkfreund/e2e-20261124-P1-1", 1)
    assert card["repo_node_id"] == "R1"
    assert (
        "cfactory",
        "POST",
        "/api/cards",
        {
            "card_key": "C-1",
            "title": "C-1",
            "repository_id": 7,
            "correlation_key": "1",
            "issue_ref": "olafkfreund/e2e-20261124-P1-1#1",
        },
    ) in calls


def test_github_pr_issue_protection_and_delete_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    client = github.GitHub()
    calls: list[tuple[object, ...]] = []

    def fake_request(*args: object) -> Any:
        calls.append(args)
        if str(args[1]).endswith("/pulls?state=all"):
            return [{"number": 3}]
        return {"number": 3}

    monkeypatch.setattr(client, "request", fake_request)
    full = "olafkfreund/e2e-20261124-P1-1"
    client.pull_request(full)
    client.pull_files(full, 3)
    client.check_runs(full, "a" * 40)
    client.protect_main(full)
    client.main_protection(full)
    client.create_issue(full, "test")
    client.delete_repo(full)
    assert ("GET", f"/repos/{full}/pulls/3") in calls
    assert ("DELETE", f"/repos/{full}") in calls
    assert ("POST", f"/repos/{full}/issues", {"title": "test"}) in calls


def test_probe_request_keeps_rejection_status_and_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = tmp_path / "token"
    token.write_text("test-secret")
    seen: list[object] = []

    class FakeHttpClient:
        def __init__(self, **kwargs: Any) -> None:
            seen.append(kwargs["auth"]()["Authorization"])

        def request(self, method: str, path: str, body: object) -> Any:
            seen.append((method, path, body))
            return SimpleNamespace(status=422, json={"detail": "intent blob SHA mismatch"})

    monkeypatch.setattr(services, "HttpClient", FakeHttpClient)
    response = services.Services({"pfactory": token}).probe_request(
        "pfactory", "POST", "/api/mcp-stdio/plan/sessions/ingest-approved", {"x": 1}
    )
    assert response == {
        "status": 422,
        "reason": "intent blob SHA mismatch",
        "body": {"detail": "intent blob SHA mismatch"},
    }
    assert seen[0] == "Bearer test-secret"


def test_stages_use_guard_for_every_mutation() -> None:
    calls: list[tuple[str, str]] = []
    recorded: list[tuple[tuple[object, ...], dict[str, object]]] = []

    class FakeGuard:
        registry = SimpleNamespace(append=lambda *args, **kwargs: recorded.append((args, kwargs)))

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
            return {"node_id": "R1", "full_name": f"olafkfreund/{name}"}

        def set_topics(self, *_: object) -> None:
            return None

        def push_starter(self, *_: object) -> None:
            return None

        def protect_main(self, *_: object) -> None:
            return None

        def create_issue(self, *_: object) -> dict[str, Any]:
            return {"number": 1}

        def create_card(self, *_: object) -> dict[str, Any]:
            return {"key": "c1"}

        def register_cf_repository(self, *_: object) -> dict[str, Any]:
            return {"id": 7}

        def enable_pr_endgame(self, *_: object) -> None:
            return None

        def onboard(self, service: str, *_: object) -> dict[str, Any]:
            return {"id": service + "-1"}

        def submit(self, *_: object) -> dict[str, Any]:
            return {"session_id": "s1", "task_id": "t1"}

        def probe_c(self, *_: object) -> dict[str, Any]:
            return {"status": 422, "reason": "intent blob SHA mismatch"}

        def probe_e(self, *_: object) -> dict[str, Any]:
            return {"status": 200, "reason": "deduplicated", "before": 1, "after": 1}

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
        ("github", "repo"),
        ("github", "repo"),
        ("aifactory", "project"),
        ("pfactory", "project"),
        ("tfactory", "project"),
        ("aifactory", "project"),
        ("cfactory", "repository"),
        ("cfactory", "card"),
        ("pfactory", "project"),
        ("pfactory", "session"),
        ("aifactory", "task"),
    ]
    assert [row[0][0:2] for row in recorded] == [("session", "s1"), ("task", "t1")]


def _fake_guard() -> Any:
    class FakeGuard:
        def __init__(self) -> None:
            self.registry = SimpleNamespace(
                append=lambda *_, **__: None,
                active=lambda: [{"kind": "repo", "id": "R1", "full_name": "olafkfreund/repo"}],
            )

        def create_repo(
            self,
            _name: str,
            create: Callable[[], dict[str, Any]],
            set_topics: Callable[[str, list[str]], object],
        ) -> dict[str, Any]:
            repo = create()
            set_topics(repo["full_name"], ["factory-e2e"])
            return repo

        def create_resource(
            self, _kind: str, _service: str, _repo: str, create: Callable[[], dict[str, Any]]
        ) -> dict[str, Any]:
            return create()

        def mutate(self, _service: str, _kind: str, _identity: str, action: Any) -> Any:
            return action()

    return FakeGuard()


def test_live_operations_test_passes_correlation_key_per_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "spec").mkdir()
    (tmp_path / "spec" / "2026-11-27-1-demo.md").write_text("---\nstatus: approved\n---\n")
    cli_calls: list[list[str]] = []
    mcp_calls: list[tuple[str, dict[str, object]]] = []

    def fake_cli(command: list[str], **_kwargs: Any) -> dict[str, Any]:
        cli_calls.append(command)
        return {"tf_id": "tf:t1/s1", "tfactory_source_sha": "a" * 40}

    def fake_mcp(tool: str, arguments: dict[str, object], **_kwargs: Any) -> dict[str, Any]:
        mcp_calls.append((tool, arguments))
        return {"tf_id": "tf:t1/s1", "tfactory_source_sha": "a" * 40}

    monkeypatch.setattr(stages, "invoke", fake_mcp)
    fake_github = SimpleNamespace(fetch_commit=lambda *_: None)
    fake_services = SimpleNamespace()

    for surface in ("cli", "mcp"):
        ops = stages.LiveOperations(
            Journey("P1", surface, "Claude", 1),
            cast(Guard, _fake_guard()),
            cast(services.Services, fake_services),
            cast(github.GitHub, fake_github),
            tmp_path,
        )
        ops.projects["tfactory"] = "t1"
        monkeypatch.setattr(ops.cli, "execute", fake_cli)
        ops.test("olafkfreund/repo", "a" * 40, surface, "pf-337-x")
        ops.test("olafkfreund/repo", "a" * 40, surface, None)

    assert cli_calls[0][-2:] == ["--correlation-key", "pf-337-x"]
    assert "--correlation-key" not in cli_calls[1]
    assert mcp_calls[0] == (
        "factory_test",
        {
            "project_id": "t1",
            "criteria": "spec/2026-11-27-1-demo.md",
            "branch": "a" * 40,
            "correlation_key": "pf-337-x",
        },
    )
    assert mcp_calls[1][0] == "factory_test"
    assert "correlation_key" not in mcp_calls[1][1]


@pytest.mark.parametrize(  # type: ignore[untyped-decorator, unused-ignore]
    "submit_key",
    ["pf-337-x", None],
)
def test_s5_passes_state_correlation_key_to_test(submit_key: str | None) -> None:
    seen_keys: list[str | None] = []

    class FakeOperations:
        def create_repo(self, name: str) -> dict[str, Any]:
            return {"node_id": "R1", "full_name": f"olafkfreund/{name}"}

        def set_topics(self, *_: object) -> None:
            return None

        def push_starter(self, *_: object) -> None:
            return None

        def protect_main(self, *_: object) -> None:
            return None

        def create_issue(self, *_: object) -> dict[str, Any]:
            return {"number": 1}

        def create_card(self, *_: object) -> dict[str, Any]:
            return {"key": "c1"}

        def register_cf_repository(self, *_: object) -> dict[str, Any]:
            return {"id": 7}

        def enable_pr_endgame(self, *_: object) -> None:
            return None

        def onboard(self, service: str, *_: object) -> dict[str, Any]:
            return {"id": service + "-1"}

        def submit(self, *_: object) -> dict[str, Any]:
            out: dict[str, Any] = {"session_id": "s1", "task_id": "t1"}
            if submit_key is not None:
                out["correlation_key"] = submit_key
            return out

        def pull_request(self, *_: object) -> dict[str, Any]:
            return {"merged": True, "merge_commit_sha": "a" * 40}

        def test(
            self,
            _full_name: str,
            _sha: str,
            _surface: str,
            correlation_key: str | None = None,
        ) -> dict[str, Any]:
            seen_keys.append(correlation_key)
            return {"spec_id": "t1:s1", "verdict_sha": "a" * 40}

        def verdict(self, _identity: str) -> dict[str, Any]:
            return {"verdict_sha": "a" * 40}

        def hidden(self, *_: object) -> bool:
            return True

        def read_resource(self, _service: str, kind: str, identity: str) -> dict[str, Any]:
            return {"key" if kind == "card" else "id": identity}

    built = stages.build(
        Journey("P1", "cli", "Claude", 1),
        cast(Guard, _fake_guard()),
        cast(stages.Operations, FakeOperations()),
        "repo",
    )
    built["S1"](999, lambda *_: None)
    built["S2"](999, lambda *_: None)
    built["S5"](999, lambda *_: None)
    assert seen_keys == [submit_key]


@pytest.mark.parametrize(  # type: ignore[untyped-decorator, unused-ignore]
    "surface",
    ["cli", "mcp"],
)
def test_submit_to_test_handoff_preserves_correlation_key_per_surface(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, surface: str
) -> None:
    (tmp_path / "plan").mkdir()
    (tmp_path / "spec").mkdir()
    (tmp_path / "plan" / "2026-11-27-1-demo.md").write_text("---\nstatus: approved\n---\n")
    (tmp_path / "spec" / "2026-11-27-1-demo.md").write_text("---\nstatus: approved\n---\n")

    cli_calls: list[list[str]] = []
    mcp_calls: list[tuple[str, dict[str, object]]] = []

    def handle_surface(kind: str) -> dict[str, Any]:
        if kind == "project_add":
            return {"result": {"id": "proj-1"}}
        if kind == "submit":
            return {
                "session_id": "pf:s1",
                "aifactory_task_id": "af:t1",
                "correlation_key": "pf-337-x",
                "outcome": "ok",
            }
        return {"tf_id": "tf:t1/s1", "tfactory_source_sha": "a" * 40}

    def fake_cli(command: list[str], **_kwargs: Any) -> dict[str, Any]:
        cli_calls.append(command)
        if command[:2] == ["project", "add"]:
            return handle_surface("project_add")
        if command[0] == "submit":
            return handle_surface("submit")
        return handle_surface("test")

    def fake_mcp(tool: str, arguments: dict[str, object], **_kwargs: Any) -> dict[str, Any]:
        mcp_calls.append((tool, arguments))
        if tool == "factory_project_add":
            return handle_surface("project_add")
        if tool == "factory_submit":
            return handle_surface("submit")
        return handle_surface("test")

    fake_github = SimpleNamespace(
        create_repo=lambda name: {"node_id": "R1", "full_name": f"olafkfreund/{name}"},
        set_topics=lambda *_: None,
        push_starter=lambda *_: None,
        protect_main=lambda *_: None,
        create_issue=lambda *_: {"number": 1},
        pull_request=lambda *_: {"merged": True, "merge_commit_sha": "a" * 40},
        fetch_commit=lambda *_: None,
    )
    fake_services = SimpleNamespace(
        read_resource=lambda _service, kind, identity: {
            "key" if kind == "card" else "id": identity
        },
        enable_pr_endgame=lambda *_: None,
        register_cf_repository=lambda *_: {"id": 7},
        create_card=lambda *_: {"key": "c1"},
        verdict=lambda *_: {"verdict_sha": "a" * 40},
    )

    monkeypatch.setattr(stages, "invoke", fake_mcp)
    ops = stages.LiveOperations(
        Journey("P1", surface, "Claude", 1),
        cast(Guard, _fake_guard()),
        cast(services.Services, fake_services),
        cast(github.GitHub, fake_github),
        tmp_path,
    )
    monkeypatch.setattr(ops.cli, "execute", fake_cli)
    monkeypatch.setattr(ops, "hidden", lambda *_: True)

    built = stages.build(
        Journey("P1", surface, "Claude", 1),
        cast(Guard, _fake_guard()),
        cast(stages.Operations, ops),
        "repo",
    )
    built["S1"](999, lambda *_: None)
    built["S2"](999, lambda *_: None)
    built["S5"](999, lambda *_: None)

    if surface == "cli":
        test_argv = next(cmd for cmd in cli_calls if cmd[0] == "test")
        assert test_argv[-2:] == ["--correlation-key", "pf-337-x"]
    else:
        _, test_args = next(call for call in mcp_calls if call[0] == "factory_test")
        assert test_args["correlation_key"] == "pf-337-x"
