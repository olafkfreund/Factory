"""Guarded stage callables for the P1 and P5 campaign journeys.

The driver supplies service-specific operations. Unknown live routes are deliberately
left unbound rather than inferred from a similar portal's API.
"""

import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from scripts.e2e.github import GitHub
from scripts.e2e.guard import Guard
from scripts.e2e.journey import Journey
from scripts.e2e.probes import verify
from scripts.e2e.services import Services
from scripts.e2e.surfaces.cli import CLI, CLI_ROOT
from scripts.e2e.surfaces.mcp import invoke

Stage = Callable[[float, Callable[..., None]], dict[str, Any]]


class LiveOperations:
    def __init__(
        self,
        journey: Journey,
        guard: Guard,
        services: Services,
        github: GitHub,
        workspace: Path,
    ) -> None:
        self.journey = journey
        self.services = services
        self.github = github
        self.workspace = workspace
        self.cli = CLI(guard)
        self.projects: dict[str, str] = {}
        self.probes: dict[str, dict[str, Any]] = {}
        self.hidden_skip_reason: str | None = None

    def _surface(
        self,
        command: list[str],
        tool: str,
        arguments: dict[str, object],
        *,
        allow_rejected: bool = False,
    ) -> dict[str, Any]:
        if self.journey.surface == "cli":
            return self.cli.execute(command, cwd=self.workspace, allow_rejected=allow_rejected)
        return invoke(tool, arguments, cwd=self.workspace, allow_rejected=allow_rejected)

    def create_repo(self, name: str) -> dict[str, Any]:
        return self.github.create_repo(name)

    def set_topics(self, full_name: str, topics: list[str]) -> object:
        return self.github.set_topics(full_name, topics)

    def push_starter(self, project: str, full_name: str) -> None:
        fixture = Path(__file__).resolve().parents[2] / "tests" / "e2e" / "fixtures" / project
        self.github.push_starter(fixture / "starter", fixture / "triple", full_name, self.workspace)

    def protect_main(self, full_name: str) -> object:
        return self.github.protect_main(full_name)

    def create_issue(self, full_name: str, title: str) -> dict[str, Any]:
        return self.github.create_issue(full_name, title)

    def create_card(self, full_name: str, card_key: str, issue_number: int) -> dict[str, Any]:
        return self.services.create_card(card_key, full_name, issue_number)

    def register_cf_repository(self, full_name: str, aif_project_id: str) -> dict[str, Any]:
        return self.services.register_cf_repository(full_name, aif_project_id)

    def enable_pr_endgame(self, aif_project_id: str) -> object:
        return self.services.enable_pr_endgame(aif_project_id)

    def onboard(self, service: str, full_name: str, _surface: str) -> dict[str, Any]:
        url = f"https://github.com/{full_name}.git"
        registry = self.cli.guard.registry
        repo = next(
            row
            for row in registry.active()
            if row["kind"] == "repo" and row["full_name"] == full_name
        )
        registry.append(
            "resource_intent", full_name, repo["id"], service=service, target_kind="project"
        )
        output = self._surface(
            ["project", "add", service, url],
            "factory_project_add",
            {"portal": service, "git_url": url},
        )
        row = output.get("result", output)
        if not isinstance(row, dict) or not row.get("id"):
            raise RuntimeError(f"{service} project add returned no ID")
        identity = str(row["id"])
        self.projects[service] = identity
        registry.append("project", identity, repo["id"], service=service, unverified=True)
        return self.services.read_resource(service, "project", identity) or {}

    def submit(self, project: str, _full_name: str, _surface: str) -> dict[str, Any]:
        slug = next((self.workspace / "plan").glob("*.md")).stem
        output = self._surface(
            ["submit", slug, "--project", self.projects["pfactory"]],
            "factory_submit",
            {"slug": slug, "project_id": self.projects["pfactory"], "dry_run": False},
            allow_rejected=project == "P5",
        )
        session_id = str(output.get("session_id") or "").removeprefix("pf:")
        task_id = str(output.get("aifactory_task_id") or "").removeprefix("af:")
        return {
            "session_id": session_id,
            "task_id": task_id,
            "correlation_key": output.get("correlation_key"),
            "outcome": output.get("outcome", "ok"),
        }

    def _approved_payload(self, full_name: str) -> dict[str, Any]:
        # PF mcp_stdio/router.py:559-567,598-608,719-748.
        sys.path.insert(0, str(CLI_ROOT))
        from factory_cli.gitartifacts import verify_and_load_artifacts  # noqa: PLC0415

        slug = next((self.workspace / "plan").glob("*.md")).stem
        artifacts = [item.to_payload() for item in verify_and_load_artifacts(self.workspace, slug)]
        git = shutil.which("git")
        if git is None:
            raise RuntimeError("git unavailable")
        head = subprocess.run(  # noqa: S603
            [git, "rev-parse", "HEAD"],
            cwd=self.workspace,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        return {
            "slug": slug,
            "provider": "github",
            "repo": full_name,
            "base_ref": "main",
            "branch": "main",
            "head_sha": head,
            "project_id": self.projects["pfactory"],
            "artifacts": artifacts,
        }

    def probe_c(self, full_name: str) -> dict[str, Any]:
        # PF mcp_stdio/router.py:741-748 verifies the original blob SHA.
        payload = self._approved_payload(full_name)
        payload["artifacts"][0]["content"] += "\n"
        outcome = self.services.probe_request(
            "pfactory",
            "POST",
            "/api/mcp-stdio/plan/sessions/ingest-approved",
            payload,
        )
        body = outcome["body"]
        created = body.get("session_id")
        if created:
            project = self.cli.guard.registry.find("pfactory", "project", self.projects["pfactory"])
            if project is None:
                raise RuntimeError("PFactory project missing from registry")
            self.cli.guard.registry.append(
                "session",
                str(created),
                project["repo_node_id"],
                service="pfactory",
                unverified=True,
            )
        contract = body.get("contract_result") or {}
        task_id = str(
            body.get("aifactory_task_id")
            or body.get("task_id")
            or (contract.get("correlation") or {}).get("task_id")
            or ""
        ).removeprefix("af:")
        if task_id:
            project = self.cli.guard.registry.find(
                "aifactory", "project", self.projects["aifactory"]
            )
            if project is None:
                raise RuntimeError("AIFactory project missing from registry")
            self.cli.guard.registry.append(
                "task", task_id, project["repo_node_id"], service="aifactory", unverified=True
            )
            self.cli.guard.mutate("aifactory", "task", task_id, lambda: self.services.stop(task_id))
            if self.services.stop_status(task_id).get("status") != "stopped":
                raise RuntimeError("probe c dispatched task stop unconfirmed")
        if created:
            project = self.cli.guard.registry.find("pfactory", "project", self.projects["pfactory"])
            if project is None:
                raise RuntimeError("PFactory project missing from registry")
            self.cli.guard.create_resource(
                "session",
                "pfactory",
                project["repo_node_id"],
                lambda: self.read_resource("pfactory", "session", str(created)),
            )
        result = {"status": outcome["status"], "reason": outcome["reason"]}
        self.probes["c"] = result
        verify("c", **result)
        return result

    def probe_e(self, full_name: str) -> dict[str, Any]:
        # PF mcp_stdio/router.py:750-777 returns deduped for replay.
        before = self.services.task_ids(self.projects["aifactory"])
        outcome = self.services.probe_request(
            "pfactory",
            "POST",
            "/api/mcp-stdio/plan/sessions/ingest-approved",
            self._approved_payload(full_name),
        )
        after = self.services.task_ids(self.projects["aifactory"])
        for identity in after - before:
            repo = self.cli.guard.registry.find("aifactory", "project", self.projects["aifactory"])
            if repo is None:
                raise RuntimeError("AIFactory project missing from registry")

            def read_task(identity: str = identity) -> dict[str, Any]:
                return self.read_resource("aifactory", "task", identity)

            self.cli.guard.create_resource(
                "task",
                "aifactory",
                repo["repo_node_id"],
                read_task,
            )
        result = {
            "status": outcome["status"],
            "reason": "deduplicated" if outcome["body"].get("deduped") else outcome["reason"],
            "before": len(before),
            "after": len(after),
        }
        self.probes["e"] = result
        verify("e", **result)
        return result

    def task(self, identity: str) -> dict[str, Any]:
        detail = self.services.read_resource("aifactory", "task", identity) or {}
        execution = self.services.task_status(identity)
        if not execution.get("is_running") and not execution.get("queued"):
            if detail.get("status") in {"done", "human_review"}:
                return {**detail, "status": "completed"}
            if detail.get("status") == "backlog":
                return {**detail, "status": "cancelled"}
        return detail

    def pull_request(self, full_name: str, _task_id: str) -> dict[str, Any]:
        return self.github.pull_request(full_name)

    def checks_green(self, full_name: str, sha: str) -> bool:
        runs = self.github.check_runs(full_name, sha).get("check_runs", [])
        return any(
            row.get("name") == "tests"
            and row.get("conclusion") == "success"
            and row.get("head_sha") == sha
            for row in runs
        )

    def test(self, full_name: str, sha: str, _surface: str) -> dict[str, Any]:
        self.github.fetch_commit(full_name, sha, self.workspace)
        slug = next((self.workspace / "spec").glob("*.md")).name
        output = self._surface(
            [
                "test",
                "--project",
                self.projects["tfactory"],
                "--criteria",
                f"spec/{slug}",
                "--branch",
                sha,
            ],
            "factory_test",
            {"project_id": self.projects["tfactory"], "criteria": f"spec/{slug}", "branch": sha},
        )
        identity = str(output.get("tf_id") or "").removeprefix("tf:").replace("/", ":", 1)
        if not identity:
            raise RuntimeError("factory test returned no TF spec")
        return {"spec_id": identity, "verdict_sha": output.get("tfactory_source_sha")}

    def verdict(self, identity: str) -> dict[str, Any] | None:
        return self.services.verdict(identity)

    def hidden(self, project: str, full_name: str, sha: str) -> bool:
        bwrap = shutil.which("bwrap")
        if bwrap is None:
            self.hidden_skip_reason = "bubblewrap unavailable"
            return False
        self.github.fetch_commit(full_name, sha, self.workspace)
        git = shutil.which("git")
        if git is None:
            raise RuntimeError("git unavailable")
        subprocess.run(  # noqa: S603
            [git, "checkout", "--detach", sha],
            cwd=self.workspace,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        suite = Path(__file__).resolve().parents[2] / "tests" / "e2e" / "hidden" / project
        python = shutil.which("python3")
        if python is None:
            self.hidden_skip_reason = "sandbox interpreter unavailable"
            return False
        with tempfile.TemporaryDirectory(prefix="factory-e2e-hidden-") as isolated:
            hidden = Path(isolated) / "suite"
            shutil.copytree(suite, hidden)
            result = subprocess.run(  # noqa: S603
                [
                    bwrap,
                    "--unshare-all",
                    "--die-with-parent",
                    "--clearenv",
                    "--ro-bind",
                    "/nix/store",
                    "/nix/store",
                    "--bind",
                    str(self.workspace),
                    "/work",
                    "--ro-bind",
                    str(hidden),
                    "/suite",
                    "--tmpfs",
                    "/tmp",  # noqa: S108 - private sandbox tmpfs
                    "--tmpfs",
                    "/home",
                    "--dir",
                    "/home/sandbox",
                    "--dev",
                    "/dev",
                    "--proc",
                    "/proc",
                    "--chdir",
                    "/work",
                    "--setenv",
                    "HOME",
                    "/home/sandbox",
                    Path(python).resolve().as_posix(),
                    "-c",
                    (
                        "import glob, sys; "
                        + "v = f'{sys.version_info.major}.{sys.version_info.minor}'; "
                        + "sys.path.extend(glob.glob("
                        + "f'/nix/store/*-python{v}-*/lib/python{v}/site-packages')); "
                        + "import pytest; "
                        "sys.exit(pytest.main(['/suite', '-q', '-p', 'no:cacheprovider']))"
                    ),
                ],
                cwd=self.workspace,
                env={"PATH": "/nix/store", "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
                capture_output=True,
                text=True,
            )
        return result.returncode == 0

    def timeline(self, card_key: str) -> dict[str, Any]:
        return self.services.timeline(card_key) or {}

    def read_resource(self, service: str, kind: str, identity: str) -> dict[str, Any]:
        return self.services.read_resource(service, kind, identity) or {}


class Operations(Protocol):
    def create_repo(self, name: str) -> dict[str, Any]: ...
    def set_topics(self, full_name: str, topics: list[str]) -> object: ...
    def push_starter(self, project: str, full_name: str) -> object: ...
    def protect_main(self, full_name: str) -> object: ...
    def create_issue(self, full_name: str, title: str) -> dict[str, Any]: ...
    def create_card(self, full_name: str, card_key: str, issue_number: int) -> dict[str, Any]: ...
    def register_cf_repository(self, full_name: str, aif_project_id: str) -> dict[str, Any]: ...
    def enable_pr_endgame(self, aif_project_id: str) -> object: ...
    def onboard(self, service: str, full_name: str, surface: str) -> dict[str, Any]: ...
    def submit(self, project: str, full_name: str, surface: str) -> dict[str, Any]: ...
    def probe_c(self, full_name: str) -> dict[str, Any]: ...
    def probe_e(self, full_name: str) -> dict[str, Any]: ...
    def task(self, identity: str) -> dict[str, Any]: ...
    def pull_request(self, full_name: str, task_id: str) -> dict[str, Any]: ...
    def checks_green(self, full_name: str, sha: str) -> bool: ...
    def test(self, full_name: str, sha: str, surface: str) -> dict[str, Any]: ...
    def verdict(self, identity: str) -> dict[str, Any] | None: ...
    def hidden(self, project: str, full_name: str, sha: str) -> bool: ...
    def timeline(self, card_key: str) -> dict[str, Any]: ...
    def read_resource(self, service: str, kind: str, identity: str) -> dict[str, Any]: ...


GITHUB_POLL_S = 30


def build(  # noqa: PLR0915
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
        protection = guard.mutate(
            "github", "repo", repo["node_id"], lambda: operations.protect_main(repo["full_name"])
        )
        issue = guard.mutate(
            "github",
            "repo",
            repo["node_id"],
            lambda: operations.create_issue(repo["full_name"], repo_name),
        )
        if not isinstance(issue, dict) or not isinstance(issue.get("number"), int):
            raise RuntimeError("GitHub issue creation returned no issue number")
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
        # S4 needs the service to merge; AIFactory's autoPr/autoMerge default OFF (#3882).
        guard.mutate(
            "aifactory",
            "project",
            state["aifactory_project"],
            lambda: operations.enable_pr_endgame(state["aifactory_project"]),
        )
        guard.create_resource(
            "repository",
            "cfactory",
            repo["node_id"],
            lambda: operations.register_cf_repository(
                repo["full_name"], state["aifactory_project"]
            ),
        )
        card = guard.create_resource(
            "card",
            "cfactory",
            repo["node_id"],
            lambda: operations.create_card(repo["full_name"], repo_name, issue["number"]),
        )
        state["card_key"] = str(card["key"])
        return {
            "registered": True,
            "branch_protection": not (isinstance(protection, dict) and "unavailable" in protection),
            "branch_protection_note": protection.get("unavailable")
            if isinstance(protection, dict)
            else None,
            "projects": dict.fromkeys(("aifactory", "pfactory", "tfactory"), 1),
            "cards": 1,
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
        if result.get("session_id"):
            guard.registry.append(
                "session",
                str(result["session_id"]),
                state["repo_node_id"],
                service="pfactory",
                unverified=True,
            )
        task_id = result.get("task_id")
        if task_id:
            state["task_id"] = str(task_id)
            guard.registry.append(
                "task", str(task_id), state["repo_node_id"], service="aifactory", unverified=True
            )
            poll(str(task_id))
        for service, kind, field in (
            ("pfactory", "session", "session_id"),
            ("aifactory", "task", "task_id"),
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
        if result.get("correlation_key"):
            state["correlation_key"] = str(result["correlation_key"])
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

    def s4(deadline: float, poll: Callable[..., None]) -> dict[str, Any]:
        while True:
            poll(state.get("task_id"))
            pr = operations.pull_request(state["full_name"], state["task_id"])
            if (
                pr.get("merged")
                and pr.get("merge_commit_sha")
                and operations.checks_green(state["full_name"], str(pr["merge_commit_sha"]))
            ):
                return pr
            if time.monotonic() >= deadline:
                raise TimeoutError("PR merge deadline reached")
            # Each pass costs several GitHub calls; 1 s exhausted the hourly limit (#3882).
            time.sleep(GITHUB_POLL_S)

    def s5(deadline: float, poll: Callable[..., None]) -> dict[str, Any]:
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
        spec_id = str(result.get("spec_id") or "")
        if not spec_id:
            raise RuntimeError("test returned no TF spec ID")
        guard.create_resource(
            "spec",
            "tfactory",
            state["repo_node_id"],
            lambda: operations.read_resource("tfactory", "spec", spec_id),
        )
        while True:
            poll(state.get("task_id"))
            verdict = operations.verdict(spec_id)
            if verdict is not None:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("TF verdict deadline reached")
            time.sleep(1)
        if verdict["verdict_sha"] != sha:
            raise AssertionError("TF verdict is not for merge SHA")
        return {
            **result,
            **verdict,
            "merge_sha": sha,
            "hidden_suite_sha": sha,
            "hidden_green": operations.hidden(journey.project, state["full_name"], sha),
            "hidden_suite_status": "skipped"
            if getattr(operations, "hidden_skip_reason", None)
            else "ran",
            "hidden_suite_reason": getattr(operations, "hidden_skip_reason", None),
        }

    def x(_deadline: float, poll: Callable[..., None]) -> dict[str, Any]:
        poll(state.get("task_id"))
        return {**operations.timeline(state["correlation_key"]), "task_id": state.get("task_id")}

    return {"S1": s1, "S2": s2, "S3": s3, "S4": s4, "S5": s5, "X": x}
