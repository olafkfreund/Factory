"""Offline safety and oracle tests for the campaign harness."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from scripts.e2e.cleanup import sweep
from scripts.e2e.config import HOSTS
from scripts.e2e.cost import Budget, StopUnconfirmedError, poll_usage, registry_costs
from scripts.e2e.guard import Guard, GuardRefusalError
from scripts.e2e.journey import Journey, matrix, validate, write_meta
from scripts.e2e.probes import PROBES, matches, verify
from scripts.e2e.readback import Readback, SurfaceMismatchError, pinned_rest
from scripts.e2e.registry import Registry
from scripts.e2e.report import summarize
from scripts.e2e.surfaces.cli import CLI
from scripts.e2e.surfaces.mcp import MCP


def repo(name="e2e-20261124-P1-1", owner="Freundcloud", topics=None):
    return {
        "id": 42,
        "node_id": "R_42",
        "full_name": f"{owner}/{name}",
        "name": name,
        "owner": {"login": owner},
        "topics": ["factory-e2e"] if topics is None else topics,
    }


@pytest.fixture
def guarded(tmp_path):
    registry = Registry("campaign", tmp_path)
    registry.append("repo", "R_42", "R_42", repo_id=42, full_name=repo()["full_name"])
    for kind, identity in (
        ("project", "aif-1"),
        ("session", "pf-1"),
        ("task", "task-1"),
        ("spec", "tf-1"),
        ("card", "card-1"),
    ):
        registry.append(kind, identity, "R_42")
    live = {"repo": repo(), "resource": {"repo_node_id": "R_42"}}
    guard = Guard(
        registry,
        lambda _name: live["repo"],
        lambda kind, identity: {"key" if kind == "card" else "id": identity, **live["resource"]},
    )
    return registry, guard, live


@pytest.mark.parametrize(
    "kind,identity",
    [
        ("repo", "R_42"),
        ("project", "aif-1"),
        ("session", "pf-1"),
        ("task", "task-1"),
        ("spec", "tf-1"),
        ("card", "card-1"),
    ],
)
def test_guard_accepts_registered_live_resource(guarded, kind, identity):
    _, guard, _ = guarded
    assert guard.check(kind, identity)["id"] == identity


@pytest.mark.parametrize(
    "change",
    [
        {"owner": {"login": "Other"}},
        {"topics": []},
        {"name": "e2e-bad"},
        {"node_id": "R_other"},
        {"full_name": "Freundcloud/e2e-20261124-P1-2"},
    ],
)
@pytest.mark.parametrize(
    "kind,identity",
    [
        ("repo", "R_42"),
        ("project", "aif-1"),
        ("session", "pf-1"),
        ("task", "task-1"),
        ("spec", "tf-1"),
        ("card", "card-1"),
    ],
)
def test_guard_refuses_unsafe_repo_for_every_service(guarded, change, kind, identity):
    _, guard, live = guarded
    live["repo"] = {**live["repo"], **change}
    with pytest.raises(GuardRefusalError):
        guard.check(kind, identity)


def test_guard_refuses_unregistered_and_resource_mismatch(guarded):
    _, guard, live = guarded
    with pytest.raises(GuardRefusalError):
        guard.check("task", "unknown")
    live["resource"]["repo_node_id"] = "R_other"
    with pytest.raises(GuardRefusalError):
        guard.check("task", "task-1")


def test_created_identity_is_durable_before_return(tmp_path):
    registry = Registry("campaign", tmp_path)
    guard = Guard(registry, lambda _: repo(), lambda _kind, _id: None)
    created = guard.create_repo(repo()["name"], lambda: repo())
    assert registry.find("repo", created["node_id"])["repo_id"] == created["id"]
    project = guard.create_resource(
        "project", "aifactory", created["node_id"], lambda: {"id": "aif-1", "repo_node_id": "R_42"}
    )
    assert registry.find("project", project["id"])["service"] == "aifactory"


def test_surface_mutations_always_use_guard(guarded):
    _, guard, _ = guarded
    cli = CLI(
        guard, lambda *_args, **_kwargs: __import__("subprocess").CompletedProcess([], 0, "{}")
    )
    mcp = MCP(guard, lambda _method, _params: {"result": {"ok": True}})
    assert cli.call("task", "task-1", "retry") == {}
    assert mcp.call("card", "card-1", "card.move")["ok"]
    with pytest.raises(GuardRefusalError):
        cli.call("task", "unknown", "retry")
    with pytest.raises(GuardRefusalError):
        mcp.call("card", "unknown", "card.move")


def test_cap_requires_confirmed_remote_stop(guarded):
    budget = Budget(guarded[1])
    budget.reserve("lane", 15)
    stopped = []
    budget.cap("lane", "task-1", stopped.append, lambda _: {"is_running": False})
    assert stopped == ["task-1"]
    with pytest.raises(StopUnconfirmedError):
        budget.cap(
            "lane", "task-1", stopped.append, lambda _: {"is_running": True}, wait=lambda _: None
        )
    assert "lane" in budget.blocked


def test_cap_cannot_stop_unregistered_task(guarded):
    stopped = []
    with pytest.raises(GuardRefusalError):
        Budget(guarded[1]).cap(
            "lane", "other-task", stopped.append, lambda _: {"is_running": False}
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
    called = []
    stages = {
        "S1": lambda: {
            "registered": True,
            "branch_protection": True,
            "projects": {"aifactory": 1, "pfactory": 1, "tfactory": 1},
            "cards": 1,
        },
        "S2": lambda: {
            "ingested": True,
            "approved": True,
            "emitted": True,
            "from_plan": True,
            "task_id": "task-1",
            "cost_usd": 15,
        },
        "S3": lambda: called.append("S3"),
    }
    with pytest.raises(ValueError, match="remote stop confirmed"):
        Journey("P1", "cli", "Claude", 1).run(
            stages,
            Budget(guarded[1]),
            "lane",
            remote=(called.append, lambda _: {"is_running": False}),
        )
    assert called == ["task-1"]


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
    assert matches(probe, 409, reason)
    for status in (302, 401, 403, 404, 500, 503):
        assert not matches(probe, status, reason)
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
        validate("S1", result, "P1")


def test_p5_requires_review_finding_to_stop():
    with pytest.raises(AssertionError, match="review finding"):
        validate("S2", {"needs_you": True}, "P5")
    validate("S2", {"needs_you": True, "review_findings": 1}, "P5")


def test_sweeper_dry_run_only_old_registered(guarded):
    registry, guard, _ = guarded
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    rows = registry.entries()
    registry.path.write_text(
        "".join(__import__("json").dumps({**row, "at": old}) + "\n" for row in rows)
    )

    class FakeDelete:
        def delete(self, _kind, _identity):
            raise AssertionError("dry run mutated")

        def close_session(self, _identity):
            raise AssertionError("dry run mutated")

        def exists(self, _kind, _identity):
            return True

    actions = sweep(registry, guard, FakeDelete())
    assert len(actions) == len(rows)
    assert any(action["action"] == "retain" for action in actions)


def test_sweeper_live_confirms_absence(guarded):
    registry, guard, _ = guarded
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    registry.path.write_text(
        "".join(json.dumps({**row, "at": old}) + "\n" for row in registry.entries())
    )

    class FakeDelete:
        def __init__(self):
            self.deleted = set()
            self.closed = []

        def delete(self, kind, identity):
            self.deleted.add((kind, identity))

        def close_session(self, identity):
            self.closed.append(identity)

        def exists(self, kind, identity):
            return (kind, identity) not in self.deleted

    client = FakeDelete()
    sweep(registry, guard, client, dry_run=False)
    assert client.closed == ["pf-1"]
    assert not registry.active()
