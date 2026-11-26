"""Question journey checks use the planned API and MCP payload shapes."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from scripts.e2e.github import GitHub
from scripts.e2e.journey import Journey
from scripts.e2e.run import main, selected
from scripts.e2e.services import Services
from scripts.e2e.stages import LiveOperations, Operations, build
from scripts.e2e.surfaces import mcp

CONTRACT = json.loads((Path(__file__).parent / "fixtures/questions_api.json").read_text())


@pytest.fixture(autouse=True)
def no_stage_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.e2e.stages.time.sleep", lambda _seconds: None)


def test_question_route_uses_task_scoped_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Services({})
    calls: list[tuple[object, ...]] = []

    def request(*args: object) -> object:
        calls.append(args)
        if args[1] == "GET":
            return CONTRACT["list"]["response"]["body"]
        return {"dry_run": False, "results": [], "counts": {}}

    monkeypatch.setattr(client, "_request", request)
    assert client.questions("042-export-csv")[0]["id"] == "q-3f9a1c7e20b4"
    assert client.merger_tick()["dry_run"] is False
    assert calls == [
        ("aifactory", "GET", "/api/tasks/042-export-csv/questions"),
        ("aifactory", "POST", "/api/maintenance/merger/run?dry_run=false"),
    ]


@pytest.mark.parametrize(
    "response", [[], {}, {"items": []}, {"questions": None}, {"questions": [], "extra": 1}]
)
def test_question_route_rejects_other_shapes(
    monkeypatch: pytest.MonkeyPatch, response: object
) -> None:
    client = Services({})
    monkeypatch.setattr(client, "_request", lambda *_args: response)
    with pytest.raises(RuntimeError, match="unknown shape"):
        client.questions("042-export-csv")


def test_question_variant_creates_quick_coder_task(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Services({})
    calls: list[tuple[object, ...]] = []

    def request(*args: object) -> dict[str, str]:
        calls.append(args)
        return {"id": "a1:spec"}

    monkeypatch.setattr(client, "_request", request)
    assert (
        client.create_question_task("a1", "Question", "Contradictory criteria")["id"] == "a1:spec"
    )
    assert client.start_task("a1:spec")["id"] == "a1:spec"
    assert calls == [
        (
            "aifactory",
            "POST",
            "/api/projects/a1/tasks",
            {
                "title": "Question",
                "description": "Contradictory criteria",
                "metadata": {"mode": "quick", "requireReviewBeforeCoding": False},
            },
        ),
        (
            "aifactory",
            "POST",
            "/api/tasks/a1%3Aspec/start",
            {"mode": "quick", "auto_handover_tfactory": True},
        ),
    ]


def test_wip_lookup_uses_task_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    github = GitHub()
    paths: list[str] = []

    def request(_method: str, path: str) -> dict[str, Any]:
        paths.append(path)
        return {"commit": {"message": "wip: paused for question q1"}}

    monkeypatch.setattr(github, "request", request)
    assert github.branch_commit("olafkfreund/e2e", "aifactory/spec")["commit"]["message"]
    assert paths == ["/repos/olafkfreund/e2e/commits/aifactory%2Fspec"]


def test_default_branch_commit_scan_is_owner_guarded(monkeypatch: pytest.MonkeyPatch) -> None:
    github = GitHub()
    paths: list[str] = []
    monkeypatch.setattr(github, "request", lambda _method, path: paths.append(path) or [])
    assert github.default_branch_commits("olafkfreund/e2e") == []
    assert paths == ["/repos/olafkfreund/e2e/commits?sha=main&per_page=100&page=1"]
    with pytest.raises(ValueError, match="unsafe owner"):
        github.default_branch_commits("someone/e2e")


def test_mcp_answer_uses_aifactory_tool_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = tmp_path / "key"
    key.write_text("unused-test-key")
    seen: list[dict[str, Any]] = []
    result = CONTRACT["mcp"]["answer_question"]["result"]

    def fake_run(_argv: list[str], **kwargs: Any) -> Any:
        seen.append(json.loads(kwargs["input"]))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"error": False, "content": [json.dumps(result)]}),
        )

    monkeypatch.setattr(mcp, "resolve_uv", lambda: "/bin/uv")
    assert (
        mcp.answer_question(
            CONTRACT["mcp"]["answer_question"]["arguments"]["task_id"],
            CONTRACT["mcp"]["answer_question"]["arguments"]["qid"],
            CONTRACT["mcp"]["answer_question"]["arguments"]["answer"],
            cwd=tmp_path,
            key_files={"aifactory": key},
            run=fake_run,
        )
        == result
    )
    assert seen[0]["arguments"] == CONTRACT["mcp"]["answer_question"]["arguments"]
    assert seen[0]["url"].endswith("/api/mcp-remote/sse")
    assert "unused-test-key" not in json.dumps(seen)


def test_mcp_approval_refusal_uses_contract_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key = tmp_path / "key"
    key.write_text("unused-test-key")
    refusal = CONTRACT["mcp"]["answer_question"]["refusal_approval"]
    monkeypatch.setattr(mcp, "resolve_uv", lambda: "/bin/uv")

    def fake_run(_argv: list[str], **_kwargs: Any) -> Any:
        return SimpleNamespace(
            returncode=0, stdout=json.dumps({"error": False, "content": [json.dumps(refusal)]})
        )

    with pytest.raises(RuntimeError, match="rejected"):
        mcp.answer_question(
            "042-export-csv",
            "q-c4d81f3360ae",
            "yes",
            cwd=tmp_path,
            key_files={"aifactory": key},
            run=fake_run,
        )


class _Guard:
    class _Registry:
        def append(self, *_args: object, **_kwargs: object) -> None:
            pass

    registry = _Registry()

    def create_repo(self, _name: str, create: Any, _topics: Any) -> dict[str, str]:
        return cast(dict[str, str], create())

    def create_resource(self, _kind: str, _service: str, _repo: str, create: Any) -> Any:
        return create()

    def mutate(self, _service: str, _kind: str, _identity: str, action: Any) -> Any:
        return action()


class _Operations:
    def __init__(
        self, project: str, needs_approval: bool | None = False, wrong_log: bool = False
    ) -> None:
        self.project = project
        self.needs_approval = needs_approval
        self.wrong_log = wrong_log
        self.answered = False
        self.answer = ""
        self.ticks = 0

    def create_repo(self, name: str) -> dict[str, str]:
        return {"node_id": "R1", "full_name": f"olafkfreund/{name}"}

    def onboard(self, service: str, *_args: object) -> dict[str, str]:
        return {"id": f"{service}-1"}

    def create_issue(self, *_args: object) -> dict[str, int]:
        return {"number": 1}

    def create_card(self, *_args: object) -> dict[str, str]:
        return {"key": "card"}

    def register_cf_repository(self, *_args: object) -> dict[str, int]:
        return {"id": 1}

    def submit(self, *_args: object) -> dict[str, str]:
        return {"session_id": "s1", "task_id": "aifactory-1:spec", "correlation_key": "c1"}

    def create_question_task(self, *_args: object) -> dict[str, str]:
        return {"id": "aifactory-1:spec"}

    def start_task(self, _task_id: str) -> dict[str, bool]:
        return {"started": True}

    def read_resource(self, *_args: object) -> dict[str, str]:
        return {"id": "ok"}

    def task(self, _identity: str) -> dict[str, str]:
        return {"status": "completed" if self.answered else "needs_input"}

    def questions(self, _task_id: str) -> list[dict[str, Any]]:
        question = CONTRACT["list"]["response"]["body"]["questions"][
            1 if self.project == "P1" else 0
        ].copy()
        question["task_id"] = "aifactory-1:spec"
        question["status"] = "open"
        if self.project == "P5":
            question["question"] = (
                "The additive total is 11.75, but the criterion says 11.76. Which wins?"
            )
        if self.needs_approval is None:
            question.pop("needs_approval")
        else:
            question["needs_approval"] = self.needs_approval
        return [question]

    def answer_question(self, _task_id: str, _qid: str, answer: str) -> dict[str, str]:
        assert answer.startswith("e2e-answer-") and len(answer) == 23
        self.answer = answer
        self.answered = True
        result = CONTRACT["mcp"]["answer_question"]["result"].copy()
        result["question"] = {**result["question"], "answer": answer}
        return result

    def task_logs(self, _task_id: str) -> dict[str, str]:
        return {
            "inbox_drain": "Question answered: "
            + ("e2e-answer-badbadbadbad" if self.wrong_log else self.answer)
        }

    def merger_tick(self) -> dict[str, Any]:
        self.ticks += 1
        return {"dry_run": False, "results": [], "counts": {}}

    def pull_requests(self, _full_name: str) -> list[dict[str, Any]]:
        return []

    def tf_task_ids(self, _project_id: str) -> set[str]:
        return set()

    def branch_commit(self, _full_name: str, _branch: str) -> dict[str, Any]:
        return {"commit": {"message": f"wip: paused for question {self.questions('')[0]['id']}"}}

    def __getattr__(self, _name: str) -> Any:
        return lambda *_args: None


def _stage3(
    project: str, needs_approval: bool | None = False, wrong_log: bool = False
) -> tuple[dict[str, Any], _Operations]:
    operations = _Operations(project, needs_approval, wrong_log)
    stages = build(
        Journey(project, "cli", "Claude", 1, ask_human=True),
        cast(Any, _Guard()),
        cast(Operations, operations),
        "fixture",
    )
    for stage in ("S1", "S2"):
        stages[stage](1e12, lambda *_args: None)
    return stages["S3"](1e12, lambda *_args: None), operations


def test_p5_pause_survives_write_merger_tick() -> None:
    result, operations = _stage3("P5")
    assert result["status"] == "needs_input"
    assert result["expected_stop"] is True
    assert operations.ticks == 1


def test_p1_answers_and_proves_exact_inbox_delivery() -> None:
    result, operations = _stage3("P1")
    assert result["status"] == "completed"
    assert result["answer"] == operations.answer
    assert operations.answered
    assert operations.answer in str(operations.task_logs(""))


def test_p1_rejects_log_with_different_answer() -> None:
    with pytest.raises(AssertionError, match="exact answer absent"):
        _stage3("P1", wrong_log=True)


def test_harness_never_answers_approval_question() -> None:
    with pytest.raises(AssertionError, match="human portal"):
        _stage3("P1", needs_approval=True)
    with pytest.raises(AssertionError, match="human portal"):
        _stage3("P1", needs_approval=None)


def test_live_answer_guard_reads_question(monkeypatch: pytest.MonkeyPatch) -> None:
    operations = LiveOperations.__new__(LiveOperations)
    approval = CONTRACT["list"]["response"]["body"]["questions"][3].copy()
    monkeypatch.setattr(operations, "questions", lambda _task_id: [approval])
    with pytest.raises(AssertionError, match="human portal"):
        operations.answer_question(approval["task_id"], approval["id"], "yes")
    approval.pop("needs_approval")
    with pytest.raises(AssertionError, match="human portal"):
        operations.answer_question(approval["task_id"], approval["id"], "yes")


def test_answer_resume_wait_respects_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("scripts.e2e.stages.time.monotonic", lambda: 1e12)
    monkeypatch.setattr(_Operations, "task", lambda _self, _task_id: {"status": "needs_input"})
    with pytest.raises(TimeoutError, match="resume deadline"):
        _stage3("P1")


def test_question_variants_are_opt_in() -> None:
    ordinary, factual, paused = selected(
        ["P1:cli:1", "P1:cli:1:ask-human", "P5:cli:1:ask-human"], None
    )
    assert not ordinary.ask_human
    assert factual.ask_human and paused.ask_human


def test_p5_question_variant_requires_its_own_campaign(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit, match="2"):
        main(
            [
                "--journey",
                "P5:cli:1:ask-human",
                "--journey",
                "P1:cli:1",
                "--evidence-root",
                str(tmp_path),
            ]
        )
    assert "only that journey" in capsys.readouterr().err
