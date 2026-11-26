"""Offline safety and oracle tests for the campaign harness."""

import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.message import Message
from io import BytesIO
from typing import Any, cast
from urllib.error import HTTPError

import pytest

from scripts.e2e.cleanup import sweep, unregistered_repos
from scripts.e2e.config import HOSTS
from scripts.e2e.cost import Budget, StopUnconfirmedError, poll_usage, reconcile, registry_costs
from scripts.e2e.evidence import redact, safe_fields
from scripts.e2e.github import GitHub, NoRedirect
from scripts.e2e.guard import Guard, GuardRefusalError
from scripts.e2e.journey import Journey, matrix, validate, write_meta
from scripts.e2e.probes import PROBES, matches, verify
from scripts.e2e.readback import Readback, SurfaceMismatchError, absent, pinned_rest
from scripts.e2e.registry import Registry
from scripts.e2e.report import summarize
from scripts.e2e.run import s3_models
from scripts.e2e.surfaces.cli import CLI
from scripts.e2e.surfaces.mcp import MCP

KINDS = [
    ("repo", "R_42"),
    ("project", "aif-1"),
    ("session", "pf-1"),
    ("task", "task-1"),
    ("spec", "tf-1"),
    ("card", "card-1"),
]
SERVICES = {
    "repo": "github",
    "project": "aifactory",
    "session": "pfactory",
    "task": "aifactory",
    "spec": "tfactory",
    "card": "cfactory",
}


def repo(
    name: str = "e2e-20261124-P1-1", owner: str = "olafkfreund", topics: list[str] | None = None
) -> dict[str, Any]:
    return {
        "id": 42,
        "node_id": "R_42",
        "full_name": f"{owner}/{name}",
        "name": name,
        "owner": {"login": owner},
        "topics": ["factory-e2e"] if topics is None else topics,
    }


def age_registry(registry: Registry) -> None:
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    registry.path.write_text(
        "".join(json.dumps({**row, "at": old}) + "\n" for row in registry.entries())
    )


def record(items: list[Any], value: Any, result: Any) -> Any:
    items.append(value)
    return result


@pytest.fixture
def guarded(tmp_path):
    registry = Registry("campaign", tmp_path)
    registry.append(
        "repo", "R_42", "R_42", service="github", repo_id=42, full_name=repo()["full_name"]
    )
    for kind, identity in (
        ("project", "aif-1"),
        ("session", "pf-1"),
        ("task", "task-1"),
        ("spec", "tf-1"),
        ("card", "card-1"),
    ):
        registry.append(
            kind,
            identity,
            "R_42",
            service={
                "project": "aifactory",
                "session": "pfactory",
                "task": "aifactory",
                "spec": "tfactory",
                "card": "cfactory",
            }[kind],
            org="factory-e2e",
        )
    live = {"repo": repo(), "resource": {"repo_node_id": "R_42", "org": "factory-e2e"}}
    guard = Guard(
        registry,
        lambda _name: live["repo"],
        lambda _service, kind, identity: {
            "key" if kind == "card" else "id": identity,
            **live["resource"],
        },
    )
    return registry, guard, live


@pytest.mark.parametrize(
    "kind,identity",
    KINDS,
)
def test_guard_accepts_registered_live_resource(guarded, kind, identity):
    _, guard, _ = guarded
    assert (
        guard.check(
            SERVICES[kind],
            kind,
            identity,
        )["id"]
        == identity
    )


@pytest.mark.parametrize(
    "change",
    [
        {"owner": {"login": "Other"}},
        {"topics": []},
        {"name": "e2e-bad"},
        {"node_id": "R_other"},
        {"full_name": "olafkfreund/e2e-20261124-P1-2"},
    ],
)
@pytest.mark.parametrize(
    "kind,identity",
    KINDS,
)
def test_guard_refuses_unsafe_repo_for_every_service(guarded, change, kind, identity):
    _, guard, live = guarded
    live["repo"] = {**live["repo"], **change}
    with pytest.raises(GuardRefusalError):
        guard.check(
            SERVICES[kind],
            kind,
            identity,
        )


def test_guard_refuses_unregistered_and_resource_mismatch(guarded):
    _, guard, live = guarded
    with pytest.raises(GuardRefusalError):
        guard.check("aifactory", "task", "unknown")
    live["resource"]["repo_node_id"] = "R_other"
    with pytest.raises(GuardRefusalError):
        guard.check("aifactory", "task", "task-1")


def test_created_identity_is_durable_before_return(tmp_path):
    registry = Registry("campaign", tmp_path)
    guard = Guard(registry, lambda _: repo(), lambda _service, _kind, _id: None)
    created = guard.create_repo(
        repo()["name"], lambda: {**repo(), "topics": []}, lambda _name, _topics: None
    )
    saved_repo = registry.find("github", "repo", created["node_id"])
    assert saved_repo is not None and saved_repo["repo_id"] == created["id"]
    project = guard.create_resource(
        "project",
        "aifactory",
        created["node_id"],
        lambda: {"id": "aif-1", "repo_node_id": "R_42", "org": "factory-e2e"},
    )
    saved_project = registry.find("aifactory", "project", project["id"])
    assert saved_project is not None and saved_project["service"] == "aifactory"


def test_surface_mutations_always_use_guard(guarded):
    _, guard, _ = guarded
    cli = CLI(
        guard,
        lambda *_args, **_kwargs: __import__("subprocess").CompletedProcess([], 0, "{}"),
        uv="uv",
    )
    mcp = MCP(guard, lambda _method, _params: {"result": {"ok": True}})
    assert cli.call("aifactory", "task", "task-1", "retry") == {}
    assert mcp.call("cfactory", "card", "card-1", "card.move")["ok"]
    with pytest.raises(GuardRefusalError):
        cli.call("aifactory", "task", "unknown", "retry")
    with pytest.raises(GuardRefusalError):
        mcp.call("cfactory", "card", "unknown", "card.move")


def test_cap_requires_confirmed_remote_stop(guarded):
    budget = Budget(guarded[1])
    budget.reserve("lane", 15)
    stopped: list[str] = []
    budget.cap("lane", "task-1", stopped.append, lambda _: {"status": "stopped"})
    assert stopped == ["task-1"]
    with pytest.raises(StopUnconfirmedError):
        budget.cap(
            "lane",
            "task-1",
            stopped.append,
            lambda _: {"status": "queued"},
            timeout=0,
            wait=lambda _: None,
        )
    assert "lane" in budget.blocked


def test_cap_accepts_stop_error_on_finished_task(guarded):
    budget = Budget(guarded[1])
    budget.reserve("lane", 15)

    def gone(_task: str) -> object:
        raise RuntimeError("aifactory HTTP 404")

    budget.cap("lane", "task-1", gone, lambda _: {"status": "stopped"})
    with pytest.raises(RuntimeError):
        budget.cap("lane", "task-1", gone, lambda _: {"status": "running"})


def test_cap_cannot_stop_unregistered_task(guarded):
    stopped: list[str] = []
    with pytest.raises(GuardRefusalError):
        Budget(guarded[1]).cap(
            "lane", "other-task", stopped.append, lambda _: {"status": "stopped"}
        )
    assert stopped == []


def test_usage_deadline_and_registry_filter():
    assert poll_usage("task-1", lambda _: {"total_tokens": 0}, 0, now=lambda: 1)[1] == [
        "missing usage"
    ]
    rows = [{"task_id": "task-1", "cost_usd": 1.5}, {"task_id": "other", "cost_usd": 99}]
    assert registry_costs(rows, {"task-1"}) == 1.5


def test_matrix_and_hidden_suite_cost():
    assert len(matrix()) == 19
    assert (
        len({(run.project, run.surface, run.model, run.repeat, run.ablation) for run in matrix()})
        == 19
    )
    rows = [
        {"status": "completed", "hidden_green": True, "cost_usd": 2},
        {"status": "completed", "hidden_green": True, "cost_usd": 4},
        {"status": "completed", "hidden_green": False, "cost_usd": 100},
        {
            "status": "completed",
            "hidden_green": True,
            "cost_usd": None,
            "billing_mode": "subscription",
        },
    ]
    assert summarize(rows)["median_cost_per_accepted_build_usd"] == 3


def test_run_meta_records_pinned_hosts(tmp_path):
    path = tmp_path / "run.meta.json"
    write_meta(path, {"project": "P1"})
    assert json.loads(path.read_text())["hosts"] == HOSTS


def test_journey_cap_stops_before_next_stage(guarded):
    called: list[str] = []
    stages = {
        "S1": lambda _deadline, _poll: {
            "registered": True,
            "branch_protection": True,
            "projects": {"aifactory": 1, "pfactory": 1, "tfactory": 1},
            "cards": 1,
        },
        "S2": lambda _deadline, _poll: {
            "ingested": True,
            "approved": True,
            "emitted": True,
            "from_plan": True,
            "task_id": "task-1",
            "cost_usd": 15,
        },
        "S3": lambda _deadline, _poll: record(called, "S3", None),
    }
    with pytest.raises(ValueError, match="remote stop confirmed") as err:
        Journey("P1", "cli", "Claude", 1).run(
            stages,
            Budget(guarded[1]),
            "lane",
            readback=lambda _stage, row: row,
            remote=(called.append, lambda _: {"status": "stopped"}),
        )
    assert called == ["task-1"]
    assert getattr(err.value, "e2e_stage", None) == "S2"
    assert set(getattr(err.value, "e2e_stage_results", {})) == {"S1"}
    assert getattr(err.value, "e2e_cost_usd", None) == 15


def test_independent_readback_disagreement():
    readback = Readback(lambda _service, _path: {"status": "red"}, lambda _: repo())
    with pytest.raises(SurfaceMismatchError):
        readback.compare("aifactory", "/api/tasks/1", {"status": "green"}, ("status",))


def test_rest_readback_pins_hosts(monkeypatch):
    monkeypatch.setenv("AIFACTORY_API", "https://wrong.invalid")
    seen = []

    class FakeClient:
        def __init__(self, **kwargs):
            seen.append(kwargs["base_url"])

        def get(self, _path):
            return type("Response", (), {"status": 200, "json": {"ok": True}})()

    read = pinned_rest(dict.fromkeys(HOSTS, "fake"), FakeClient)
    assert read("aifactory", "/api/health") == {"ok": True}
    assert set(seen) == set(HOSTS.values())


@pytest.mark.parametrize(
    "probe,reason",
    [
        ("a", "already exists"),
        ("b", "repository access denied"),
        ("c", "artifact integrity mismatch"),
        ("d", "signed-plan invalid"),
        ("e", "deduplicated"),
        ("f", "empty diff"),
        ("g", "missing usage"),
        ("h", "stale verdict"),
        ("i", "0 tests"),
        ("j", "verdict sha mismatch"),
        ("k", "mutant behaviour failed"),
        ("l", "duplicate event"),
        ("m", "distinct repos isolated"),
    ],
)
def test_every_probe_specific_reason(probe, reason):
    assert matches(
        probe,
        409,
        reason,
        after={"total_tokens": 0, "deadline_reached": True}
        if probe == "g"
        else ({"left"}, {"right"})
        if probe == "m"
        else None,
        before=("left", "right") if probe == "m" else None,
    )
    for status in (302, 401, 403, 404, 405, 407, 408, 429, 500, 503):
        assert not matches(probe, status, reason)
    if probe not in {"g", "m"}:
        assert not matches(probe, 409, "unexpected infrastructure failure")
    assert set(PROBES) == set("abcdefghijklm")


def test_replay_and_isolation_need_state_evidence():
    with pytest.raises(AssertionError):
        verify("e", 409, "deduplicated", before=1, after=2)
    with pytest.raises(AssertionError):
        verify("m", 200, "distinct repos isolated", after=("same", "same"))


def test_stage_rejects_auth_error_in_negative_probe():
    result = {
        "registered": True,
        "branch_protection": True,
        "projects": {"aifactory": 1, "pfactory": 1, "tfactory": 1},
        "cards": 1,
        "probes": {"b": {"status": 401, "reason": "repository access denied"}},
    }
    with pytest.raises(AssertionError, match="expected repo access denied"):
        validate("S1", result, "P1", result)


def test_p5_requires_review_finding_to_stop():
    with pytest.raises(AssertionError, match="review finding"):
        validate("S2", {"needs_you": True}, "P5", {"needs_you": True})
    validate(
        "S2",
        {"needs_you": True, "review_findings": 1},
        "P5",
        {"needs_you": True, "review_findings": 1},
    )


def test_sweeper_dry_run_only_old_registered(guarded):
    registry, guard, _ = guarded
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    rows = registry.entries()
    registry.path.write_text(
        "".join(__import__("json").dumps({**row, "at": old}) + "\n" for row in rows)
    )

    class FakeDelete:
        def delete(self, _service, _kind, _identity):
            raise AssertionError("dry run mutated")

        def close_session(self, _identity):
            raise AssertionError("dry run mutated")

        def exists(self, _service, _kind, _identity):
            return True

    actions = sweep(registry, guard, FakeDelete())
    assert len(actions) == len(rows)
    assert any(action["action"] == "retain" for action in actions)


def test_sweeper_live_confirms_absence(guarded):
    registry, guard, _ = guarded
    age_registry(registry)

    class FakeDelete:
        def __init__(self) -> None:
            self.deleted: set[tuple[str, str, str]] = set()
            self.closed: list[str] = []

        def delete(self, service, kind, identity):
            self.deleted.add((service, kind, identity))

        def close_session(self, identity):
            self.closed.append(identity)

        def exists(self, service, kind, identity):
            return (service, kind, identity) not in self.deleted

    client = FakeDelete()
    sweep(registry, guard, client, dry_run=False)
    assert client.closed == ["pf-1"]
    assert not registry.active()


def test_surface_target_is_constructed_and_other_ids_refused(guarded, tmp_path):
    seen: list[Any] = []
    cli = CLI(
        guarded[1],
        lambda argv, **kw: record(
            seen, (argv, kw), __import__("subprocess").CompletedProcess(argv, 0, "{}")
        ),
        key_files={"aifactory": tmp_path / "key"},
        uv="uv",
    )
    cli.call("aifactory", "task", "task-1", "retry")
    assert seen[0][0][-5:] == ["python", "-m", "factory_cli", "retry", "task-1"]
    with pytest.raises(GuardRefusalError):
        cli.call("aifactory", "task", "task-1", "retry", "af:other")
    seen_mcp: list[Any] = []
    mcp = MCP(guarded[1], lambda _method, params: record(seen_mcp, params, {"result": {}}))
    mcp.call("cfactory", "card", "card-1", "card.move", column="Done")
    assert seen_mcp == [{"column": "Done", "key": "card-1"}]
    with pytest.raises(GuardRefusalError):
        mcp.call("cfactory", "card", "card-1", "card.move", key="card-other")


def test_cli_environment_is_pinned_and_isolated(guarded, tmp_path, monkeypatch):
    monkeypatch.setenv("AIFACTORY_API_URL", "https://wrong.invalid")
    monkeypatch.setenv("AIFACTORY_API_TOKEN_FILE", "/secret/parent")
    monkeypatch.setenv("HOME", "/secret/home")
    token = tmp_path / "token"
    token.write_text("temp-test-token")
    seen: list[Any] = []
    CLI(
        guarded[1],
        lambda argv, **kw: record(
            seen, kw["env"], __import__("subprocess").CompletedProcess(argv, 0, "{}")
        ),
        {"aifactory": token},
        uv="uv",
    ).call("aifactory", "task", "task-1", "retry")
    env = seen[0]
    assert env["AIFACTORY_API_URL"] == HOSTS["aifactory"]
    assert env["AIFACTORY_API_TOKEN_FILE"] == str(token)
    assert env["HOME"] != "/secret/home" and env["XDG_CONFIG_HOME"] == env["HOME"]
    assert "PFACTORY_API_TOKEN_FILE" not in env


def test_registry_service_key_validation_and_redaction(guarded):
    registry = guarded[0]
    registry.append("project", "same", "R_42", service="aifactory", note="acw_secret")
    registry.append("project", "same", "R_42", service="pfactory")
    assert registry.find("aifactory", "project", "same")["service"] == "aifactory"
    assert "note" not in registry.entries()[-2]
    for fields in ({"service": "wrong"}, {"service": "aifactory", "target_kind": "bogus"}):
        with pytest.raises(ValueError):
            registry.append("deleted", "same", "R_42", **fields)
    assert "acw_secret" not in str(
        redact({"x": "Bearer acw_secret cfk_secret ghp_secret github_pat_secret"})
    )


def test_guard_refuses_resource_without_recorded_org(tmp_path):
    registry = Registry("c", tmp_path)
    registry.append(
        "repo", "R_42", "R_42", service="github", repo_id=42, full_name=repo()["full_name"]
    )
    registry.append("task", "task-1", "R_42", service="aifactory")
    guard = Guard(
        registry,
        read_repo=lambda _name: repo(),
        read_resource=lambda *_a: {"id": "task-1", "repo_node_id": "R_42", "org": "any"},
    )
    with pytest.raises(GuardRefusalError):
        guard.check("aifactory", "task", "task-1")


def test_guard_requires_org_and_active_repo(guarded):
    registry, guard, live = guarded
    live["resource"]["org"] = "another-org"
    with pytest.raises(GuardRefusalError):
        guard.check("aifactory", "task", "task-1")
    with pytest.raises(GuardRefusalError):
        guard.check("cfactory", "card", "card-1")
    live["resource"]["org"] = "factory-e2e"
    registry.append("deleted", "R_42", "R_42", service="github", target_kind="repo")
    with pytest.raises(GuardRefusalError):
        guard.check("aifactory", "task", "task-1")


def test_repo_create_records_intent_before_create_and_sets_topic(tmp_path):
    registry = Registry("c", tmp_path)
    guard = Guard(registry, lambda _: repo(), lambda *_: None)
    order = []

    def create():
        assert registry.find("github", "intent", repo()["name"])
        order.append("create")
        return {**repo(), "topics": []}

    def set_topics(name, topics):
        order.append("topics")
        assert name == repo()["full_name"] and topics == ["factory-e2e"]

    guard.create_repo(repo()["name"], create, set_topics)
    assert order == ["create", "topics"]


def test_github_client_never_exposes_token(tmp_path):
    token = tmp_path / "token"
    token.write_text("github_pat_topsecret")
    client = GitHub(
        token,
        lambda request, **_kwargs: (_ for _ in ()).throw(
            ValueError(f"bad {request.get_header('Authorization')}")
        ),
    )
    assert "github_pat_topsecret" not in repr(client) + str(client)
    with pytest.raises(RuntimeError) as caught:
        client.request("GET", "/repos/olafkfreund/e2e-20261124-P1-1")
    assert "github_pat_topsecret" not in repr(caught.value) + str(caught.value)


def test_stop_exception_blocks_lane_and_queued_is_not_terminal(guarded):
    budget = Budget(guarded[1])
    with pytest.raises(RuntimeError):
        budget.cap(
            "lane",
            "task-1",
            lambda _: (_ for _ in ()).throw(RuntimeError("stop failed")),
            lambda _: {"status": "stopped"},
        )
    assert "lane" in budget.blocked
    clock = iter([0, 1, 1])
    with pytest.raises(StopUnconfirmedError):
        budget.cap(
            "next",
            "task-1",
            lambda _: None,
            lambda _: {"status": "queued"},
            timeout=1,
            now=lambda: next(clock),
            wait=lambda _: None,
        )
    assert "next" in budget.blocked


def test_readback_requires_present_nonempty_keys_and_validate_uses_observation():
    rb = Readback(lambda *_: {}, lambda _: repo())
    with pytest.raises(SurfaceMismatchError):
        rb.compare("aifactory", "/task", {}, ())
    with pytest.raises(SurfaceMismatchError):
        rb.compare("aifactory", "/task", {}, ("status",))
    with pytest.raises(AssertionError):
        validate("S1", {"registered": True}, "P1", {})


def test_absence_requires_positive_read_then_404():
    seen = iter([{"id": "task-1"}, SurfaceMismatchError("aifactory read-back returned HTTP 404")])

    def read(*_):
        item = next(seen)
        if isinstance(item, Exception):
            raise item
        return item

    deleted = []
    absent(read, lambda: deleted.append(True), "aifactory", "/task", "id", "task-1")
    assert deleted
    with pytest.raises(SurfaceMismatchError):
        absent(lambda *_: {}, lambda: None, "aifactory", "/task", "id", "task-1")


@pytest.mark.parametrize("status", [404, 401, 403, 500])
def test_github_absence_accepts_only_404(status):
    calls: list[str] = []

    def read(*_):
        if not calls:
            calls.append("read")
            return {"id": 42}
        raise HTTPError("", status, "", cast(Message, {}), None)

    if status == 404:
        absent(read, lambda: calls.append("delete"), "github", "/repos/x", "id", 42)
        assert calls == ["read", "delete"]
    else:
        with pytest.raises(HTTPError) as caught:
            absent(read, lambda: calls.append("delete"), "github", "/repos/x", "id", 42)
        assert caught.value.code == status


def test_probe_statuses_codes_and_state():
    for probe in "cdj":
        assert not matches(probe, 200, PROBES[probe].reason)
    assert not matches("h", 200, "stale verdict")
    assert not matches("d", 409, "signed-plan invalid auth error")
    assert not matches("i", 409, "10 tests")
    assert not matches("i", 409, "no tests failed")
    assert not matches("c", 409, "artifact integrity mismatch", code="auth_denied")
    assert not matches("g", 200, "missing usage")
    assert not matches("m", 200, "distinct repos isolated")
    with pytest.raises(AssertionError):
        verify("g", 200, "missing usage", after={"total_tokens": 10, "deadline_reached": True})
    with pytest.raises(AssertionError):
        verify("m", 200, "distinct repos isolated", after=("same", "same"))


def test_sweeper_repo_last_includes_young_child(guarded):
    registry, guard, _ = guarded
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    rows = registry.entries()
    registry.path.write_text(
        "".join(
            json.dumps(
                {**row, "at": old if row["kind"] == "repo" else datetime.now(UTC).isoformat()}
            )
            + "\n"
            for row in rows
        )
    )

    class Client:
        def __init__(self) -> None:
            self.order: list[str] = []

        def delete(self, _service, kind, _identity):
            self.order.append(kind)

        def exists(self, _service, _kind, _identity):
            return False

        def close_session(self, _identity):
            self.order.append("session")

    client = Client()
    sweep(registry, guard, client, dry_run=False)
    assert client.order[-1] == "repo" and "task" in client.order


def test_unregistered_repos_reports_only_unknown(guarded):
    known = repo()
    unknown = {**repo("e2e-20261124-P1-2"), "full_name": "olafkfreund/e2e-20261124-P1-2"}
    assert unregistered_repos(guarded[0], lambda: [known, unknown]) == [unknown["full_name"]]


def test_budget_reservation_limits_and_blocked_lanes(guarded):
    budget = Budget(guarded[1])
    for lane in ("a", "b", "c"):
        budget.reserve(lane, 1)
    with pytest.raises(ValueError):
        budget.reserve("d", 1)
    with pytest.raises(ValueError):
        budget.reserve("a", 450)
    budget.blocked.add("a")
    with pytest.raises(ValueError):
        budget.reserve("a", 1)


def test_reconcile_findings():
    assert reconcile([1, 2], 3, {"cf": 3}) == []
    assert len(reconcile([1, 2], 4, {"cf": 3})) == 2


def test_journey_run_happy_deadline_and_p5(guarded):
    budget = Budget(guarded[1])

    def stages(
        p5: bool = False,
    ) -> dict[str, Callable[[float, Callable[..., None]], dict[str, Any]]]:
        def stage(name: str) -> Callable[[float, Callable[..., None]], dict[str, Any]]:
            def run(_deadline: float, poll: Callable[..., None]) -> dict[str, Any]:
                poll()
                if name == "S2" and p5:
                    return {"needs_you": True, "review_findings": 1}
                return {}

            return run

        return {name: stage(name) for name in ("S1", "S2", "S3", "S4", "S5", "X")}

    observations: dict[str, dict[str, Any]] = {
        "S1": {
            "registered": True,
            "branch_protection": True,
            "projects": {"aifactory": 1, "pfactory": 1, "tfactory": 1},
            "cards": 1,
        },
        "S2": {"ingested": True, "approved": True, "emitted": True, "from_plan": True},
        "S3": {
            "terminal": True,
            "green": True,
            "code_diff": True,
            "plan_files_only": True,
            "review_recorded": True,
            "reviewer_model": "A",
            "coder_model": "B",
            "runtime_models": True,
        },
        "S4": {
            "merged_by_service": True,
            "checks_green": True,
            "triple_linked": True,
            "merged_head": "sha",
            "checked_head": "sha",
        },
        "S5": {
            "verdict_sha": "sha",
            "merge_sha": "sha",
            "hidden_suite_sha": "sha",
            "signals": 5,
            "hidden_green": True,
        },
        "X": {
            "events_ordered": True,
            "registry_filtered": True,
            "cost_reconciled": True,
            "no_card_anomaly": True,
        },
    }
    assert (
        len(
            Journey("P1", "cli", "Claude", 1).run(
                stages(), budget, "ok", readback=lambda stage, _: observations[stage]
            )["stage_results"]
        )
        == 6
    )
    p5 = Journey("P5", "cli", "Claude", 1).run(
        stages(True),
        budget,
        "p5",
        readback=lambda stage, row: row if stage == "S2" else observations[stage],
    )
    assert p5["expected_stop"] and set(p5["stage_results"]) == {"S1", "S2", "X"}
    with pytest.raises(TimeoutError):
        Journey("P1", "cli", "Claude", 1).run(
            stages(),
            budget,
            "late",
            now=iter([0, 3601]).__next__,
            readback=lambda stage, _: observations[stage],
        )
    assert "late" in budget.blocked


def test_stage_poll_caps_while_stage_runs(guarded):
    called = []
    budget = Budget(guarded[1])

    def stage(_deadline, poll):
        poll("task-1")
        called.append("after poll")
        return {}

    with pytest.raises(ValueError, match="remote stop confirmed"):
        Journey("P1", "cli", "Claude", 1).run(
            {"S1": stage},
            budget,
            "lane",
            readback=lambda *_: {},
            usage=lambda _: {"cost_usd": 15},
            remote=(lambda _: called.append("stop"), lambda _: {"status": "stopped"}),
        )
    assert called == ["stop"]


def test_orphan_repo_requires_created_at_and_topic(tmp_path):
    registry = Registry("c", tmp_path)
    name = repo()["name"]
    registry.append(
        "intent",
        name,
        name,
        service="github",
        target_kind="repo",
        name=name,
        full_name=repo()["full_name"],
    )
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    registry.path.write_text(json.dumps({**registry.entries()[0], "at": old}) + "\n")
    live = {**repo(), "created_at": (datetime.now(UTC) - timedelta(days=9)).isoformat()}
    guard = Guard(registry, lambda _: live, lambda *_: None)

    class Client:
        def __init__(self) -> None:
            self.deleted: list[tuple[str, str, str]] = []

        def delete(self, service, kind, identity):
            self.deleted.append((service, kind, identity))

        def exists(self, _service, _kind, _identity):
            return False

        def close_session(self, _identity):
            raise AssertionError("unexpected")

    client = Client()
    sweep(registry, guard, client, dry_run=False)
    assert client.deleted == []
    live["created_at"] = (datetime.now(UTC) - timedelta(days=7)).isoformat()
    live["topics"] = []
    sweep(registry, guard, client, dry_run=False)
    assert client.deleted == []
    live["topics"] = ["factory-e2e"]
    sweep(registry, guard, client, dry_run=False)
    assert client.deleted == [("github", "repo", repo()["full_name"])]
    sweep(registry, guard, client, dry_run=False)
    assert len(client.deleted) == 1


def test_evidence_allowlist_in_meta_and_report(tmp_path):
    path = tmp_path / "meta.json"
    write_meta(
        path,
        {
            "project": "P1",
            "secret": "acw_hidden",
            "stage_results": {"S1": {"registered": True, "secret": "cfk_hidden"}},
        },
    )
    saved = path.read_text()
    assert "secret" not in saved and "hidden" not in saved
    record = {
        "instance_id": "x",
        "status": "completed",
        "hidden_green": True,
        "cost_usd": 1,
        "stage_results": {"S1": {"secret": "ghp_hidden"}},
    }
    assert "ghp_hidden" not in str(summarize([record]))


def test_registry_costs_handles_null_cost():
    assert registry_costs([{"task_id": "task-1", "cost_usd": None}], {"task-1"}) == 0


def test_probe_rejection_code_and_field():
    assert not matches("f", 200, "empty diff")
    assert matches("c", 409, "generic message", code="artifact_integrity_mismatch")
    assert matches("d", 422, "generic message", code="signed_plan_invalid")


def test_failed_create_closes_intent(tmp_path):
    registry = Registry("c", tmp_path)
    guard = Guard(registry, lambda _: repo(), lambda *_: None)
    with pytest.raises(HTTPError):
        guard.create_repo(
            repo()["name"],
            lambda: (_ for _ in ()).throw(HTTPError("", 422, "", cast(Message, {}), None)),
            lambda *_: None,
        )
    assert registry.find("github", "create_failed", repo()["name"])


def assert_failed_stage_stops(
    guarded: Any,
    stage: Any,
    error: type[Exception],
    stopped: list[str],
    match: str | None = None,
) -> None:
    with pytest.raises(error, match=match):
        Journey("P1", "cli", "Claude", 1).run(
            {"S1": stage},
            Budget(guarded[1]),
            "lane",
            readback=lambda *_: {},
            remote=(stopped.append, lambda _: {"status": "stopped"}),
        )


def test_stage_exception_stops_dispatched_service_resource(guarded):
    registry, _, _ = guarded
    registry.append("session", "pf-2", "R_42", service="pfactory", org="factory-e2e")
    stopped: list[str] = []

    def stage(_deadline, poll):
        poll(("pfactory", "session", "pf-2"))
        raise RuntimeError("stage failed")

    assert_failed_stage_stops(guarded, stage, RuntimeError, stopped, "stage failed")
    assert stopped == ["pf-2"]


def test_validation_failure_stops_result_dispatched_resource(guarded):
    registry, _, _ = guarded
    registry.append("session", "pf-2", "R_42", service="pfactory", org="factory-e2e")
    stopped: list[str] = []
    assert_failed_stage_stops(
        guarded,
        lambda *_: {"dispatched": ("pfactory", "session", "pf-2")},
        AssertionError,
        stopped,
    )
    assert stopped == ["pf-2"]


@pytest.mark.parametrize("arg", ["550e8400-e29b-41d4-a716-446655440000", "123", "CARD-12"])
def test_cli_refuses_extra_ids(guarded, arg):
    with pytest.raises(GuardRefusalError):
        CLI(guarded[1]).call("aifactory", "task", "task-1", "retry", arg)


@pytest.mark.parametrize(
    "key", ["taskId", "cardKey", "TASK_ID", "sessionId", "specId", "projectId"]
)
def test_mcp_refuses_id_keys(guarded, key):
    with pytest.raises(GuardRefusalError):
        MCP(guarded[1], lambda *_: {"result": {}}).call(
            "aifactory", "task", "task-1", "retry", **{key: "other"}
        )


def test_probe_m_requires_only_own_cards():
    assert matches("m", 200, "", after=({"a"}, {"b"}), before=("a", "b"))
    assert not matches("m", 200, "", after=({"a", "c"}, {"b"}), before=("a", "b"))
    assert not matches("m", 200, "", after=({"a", "b"}, {"b"}), before=("a", "b"))


def test_github_preserves_status_and_accepts_empty_204(tmp_path):
    token = tmp_path / "token"
    token.write_text("secret")
    with pytest.raises(HTTPError) as caught:
        GitHub(
            token,
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                HTTPError("", 404, "", cast(Message, {}), None)
            ),
        ).request("GET", "/repos/olafkfreund/x")
    assert caught.value.code == 404

    response = BytesIO(b"")
    cast(Any, response).status = 204
    assert (
        GitHub(token, lambda *_args, **_kwargs: response).request("DELETE", "/repos/olafkfreund/x")
        == {}
    )
    assert NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere") is None


def test_sweep_records_failure_and_continues(guarded):
    registry, guard, _ = guarded
    age_registry(registry)

    class Client:
        def delete(self, _service, kind, _identity):
            if kind == "task":
                raise RuntimeError("failed")

        def exists(self, *_):
            return False

        def close_session(self, *_):
            pass

    sweep(registry, guard, Client(), dry_run=False)
    assert registry.find("aifactory", "failed", "task-1")
    assert registry.find("github", "deleted", "R_42")


def test_sweep_404_is_absent_and_401_is_failure(guarded):
    registry, guard, _ = guarded
    age_registry(registry)

    class Client:
        def delete(self, *_):
            pass

        def exists(self, _service, kind, _identity):
            raise HTTPError("", 404 if kind == "task" else 401, "", cast(Message, {}), None)

        def close_session(self, *_):
            pass

    sweep(registry, guard, Client(), dry_run=False)
    assert registry.find("aifactory", "deleted", "task-1")
    assert registry.find("github", "failed", "R_42")


def test_redaction_includes_github_token_families():
    for prefix in ("gho_", "ghs_", "ghu_", "ghr_"):
        assert prefix + "secret" not in str(redact(prefix + "secret"))
    assert "secret" not in str(redact("Authorization: token secret"))
    assert safe_fields(
        {"probes": {"ab": {"reason": "leak"}, "a": {"reason": "kept"}}}, {"probes"}
    ) == {"probes": {"a": {"reason": "kept"}}}


HEAD = "a" * 40


def usage_payload(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "phaseModels": {
            "coding": ["claude-sonnet-5-5"],
            "planning": ["claude-sonnet-5-5"],
            "qa_fixer": ["claude-sonnet-5-5"],
            "qa": ["claude-opus-5-5"],
        },
        "qaEvidence": {
            "status": "approved",
            "reviewer": {
                "model": "claude-opus-5-5",
                "provider": "claude",
                "served_model": "claude-opus-5-5",
            },
            "reviewed_head": HEAD,
            "report_sha256": "b" * 64,
            "qa_cycle": 1,
            "override": False,
            "at": "2026-11-25T10:00:00Z",
        },
    }
    return {**payload, **over}


def test_s3_models_pass():
    got = s3_models(usage_payload(), HEAD)
    assert got == {
        "runtime_models": True,
        "coder_model": "claude-sonnet-5-5",
        "reviewer_model": "claude-opus-5-5",
        "qa_approved": True,
    }


def test_s3_models_alias_equals_coder():
    evidence = usage_payload()["qaEvidence"] | {"reviewer": {"model": "sonnet"}}
    got = s3_models(usage_payload(qaEvidence=evidence), HEAD)
    assert got["reviewer_model"] == got["coder_model"] == "claude-sonnet-5-5"


def test_s3_models_without_evidence_or_phases():
    got = s3_models(usage_payload(qaEvidence=None), HEAD)
    assert not got["runtime_models"]
    assert not got["qa_approved"]
    got = s3_models({"qaEvidence": usage_payload()["qaEvidence"]}, HEAD)
    assert not got["runtime_models"]
    assert got["coder_model"] is None


def test_s3_models_stale_head():
    assert not s3_models(usage_payload(), "c" * 40)["qa_approved"]


def test_s3_models_ignores_planning_identity() -> None:
    usage = usage_payload(
        phaseModels={
            "planning": ["claude-opus-5-5"],
            "coding": ["claude-sonnet-5-5"],
        }
    )
    models = s3_models(usage, HEAD)
    assert models["reviewer_model"] == "claude-opus-5-5"
    assert models["coder_model"] == "claude-sonnet-5-5"
    assert models["qa_approved"]


def test_github_waits_for_rate_limit_reset_then_retries(tmp_path):
    token = tmp_path / "t"
    token.write_text("x")
    limited = cast(
        Message,
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(time.time()) + 30)},
    )
    calls: list[str] = []

    def open_url(request, *_args, **_kw):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise HTTPError("", 403, "", limited, None)
        return BytesIO(b'{"ok": true}')

    client = GitHub(token_file=token, open_url=open_url)
    slept: list[float] = []
    client.sleep = slept.append
    assert client.request("GET", "/repos/olafkfreund/x") == {"ok": True}
    assert len(calls) == 2
    assert 1 <= slept[0] <= 31


def test_github_plain_403_is_not_retried(tmp_path):
    token = tmp_path / "t"
    token.write_text("x")
    calls: list[int] = []

    def open_url(*_args, **_kw):
        calls.append(1)
        raise HTTPError("", 403, "", cast(Message, {}), None)

    with pytest.raises(HTTPError):
        GitHub(token_file=token, open_url=open_url).request("GET", "/repos/olafkfreund/x")
    assert calls == [1]
