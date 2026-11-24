"""Guarded stage callables for the P1 and P5 campaign journeys.

The driver supplies service-specific operations. Unknown live routes are deliberately
left unbound rather than inferred from a similar portal's API.
"""

import time
from collections.abc import Callable
from typing import Any, Protocol

from scripts.e2e.guard import Guard
from scripts.e2e.journey import Journey

Stage = Callable[[float, Callable[..., None]], dict[str, Any]]


class Operations(Protocol):
    def create_repo(self, name: str) -> dict[str, Any]: ...
    def set_topics(self, full_name: str, topics: list[str]) -> object: ...
    def push_starter(self, project: str, full_name: str) -> object: ...
    def onboard(self, service: str, full_name: str, surface: str) -> dict[str, Any]: ...
    def submit(self, project: str, full_name: str, surface: str) -> dict[str, Any]: ...
    def task(self, identity: str) -> dict[str, Any]: ...
    def pull_request(self, full_name: str, task_id: str) -> dict[str, Any]: ...
    def test(self, full_name: str, sha: str, surface: str) -> dict[str, Any]: ...
    def hidden(self, project: str, full_name: str, sha: str) -> bool: ...
    def timeline(self, card_key: str) -> dict[str, Any]: ...
    def read_resource(self, service: str, kind: str, identity: str) -> dict[str, Any]: ...


def build(
    journey: Journey, guard: Guard, operations: Operations, repo_name: str
) -> dict[str, Stage]:
    if journey.project not in {"P1", "P5"} or journey.surface not in {"cli", "mcp"}:
        raise ValueError("step 2b supports only P1/P5 on CLI or MCP")
    state: dict[str, str] = {}

    def s1(_deadline: float, poll: Callable[..., None]) -> dict[str, Any]:
        poll()
        repo = guard.create_repo(
            repo_name,
            lambda: operations.create_repo(repo_name),
            operations.set_topics,
        )
        state["repo_node_id"] = repo["node_id"]
        state["full_name"] = repo["full_name"]
        guard.mutate(
            "github",
            "repo",
            repo["node_id"],
            lambda: operations.push_starter(journey.project, repo["full_name"]),
        )
        for service in ("aifactory", "pfactory", "tfactory"):

            def do_onboard(service: str = service) -> dict[str, Any]:
                return operations.onboard(service, repo["full_name"], journey.surface)

            project = guard.create_resource(
                "project",
                service,
                repo["node_id"],
                do_onboard,
            )
            state[f"{service}_project"] = str(project["id"])
        return {
            "registered": True,
            "projects": dict.fromkeys(("aifactory", "pfactory", "tfactory"), 1),
        }

    def s2(_deadline: float, poll: Callable[..., None]) -> dict[str, Any]:
        poll()
        # The submit handler ingests and emits; the PF project is the registered parent.
        result = guard.mutate(
            "pfactory",
            "project",
            state["pfactory_project"],
            lambda: operations.submit(journey.project, state["full_name"], journey.surface),
        )
        if not isinstance(result, dict):
            raise RuntimeError("submit returned no structured result")
        for service, kind, field in (
            ("pfactory", "session", "session_id"),
            ("aifactory", "task", "task_id"),
            ("cfactory", "card", "card_key"),
        ):
            if result.get(field):
                identity = str(result[field])

                def do_read(
                    service: str = service, kind: str = kind, identity: str = identity
                ) -> dict[str, Any]:
                    return operations.read_resource(service, kind, identity)

                guard.create_resource(
                    kind,
                    service,
                    state["repo_node_id"],
                    do_read,
                )
        task_id = result.get("task_id")
        if task_id:
            poll(task_id)
            state["task_id"] = str(task_id)
        if result.get("card_key"):
            state["card_key"] = str(result["card_key"])
        return result

    def s3(deadline: float, poll: Callable[..., None]) -> dict[str, Any]:
        task_id = state["task_id"]
        while True:
            poll(task_id)
            task = operations.task(task_id)
            if task.get("status") in {"completed", "failed", "cancelled", "stopped", "needs_you"}:
                return {**task, "task_id": task_id}
            if time.monotonic() >= deadline:
                poll(task_id)
                raise TimeoutError("AIF task deadline reached")
            time.sleep(1)

    def s4(_deadline: float, poll: Callable[..., None]) -> dict[str, Any]:
        poll(state.get("task_id"))
        return operations.pull_request(state["full_name"], state["task_id"])

    def s5(_deadline: float, poll: Callable[..., None]) -> dict[str, Any]:
        poll(state.get("task_id"))
        pr = operations.pull_request(state["full_name"], state["task_id"])
        sha = str(pr["merge_commit_sha"])
        result = guard.mutate(
            "tfactory",
            "project",
            state["tfactory_project"],
            lambda: operations.test(state["full_name"], sha, journey.surface),
        )
        if not isinstance(result, dict):
            raise RuntimeError("test returned no structured result")
        if result.get("verdict_sha") != sha:
            raise AssertionError("TF verdict is not for merge SHA")
        return {
            **result,
            "merge_sha": sha,
            "hidden_suite_sha": sha,
            "hidden_green": operations.hidden(journey.project, state["full_name"], sha),
        }

    def x(_deadline: float, poll: Callable[..., None]) -> dict[str, Any]:
        poll(state.get("task_id"))
        return operations.timeline(state["card_key"])

    return {"S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5, "X": x}
