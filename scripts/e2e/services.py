"""Pinned REST reads and confirmed service actions for the campaign."""

from http import HTTPStatus
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from scripts.e2e.config import HOSTS, KEY_FILES
from scripts.e2e.registry import Registry
from scripts.parr_regression import HttpClient  # type: ignore[attr-defined]


def _segment(value: str) -> str:
    if not value or value in {".", ".."} or "/" in value:
        raise ValueError("invalid resource identifier")
    return quote(value, safe="")


class Services:
    def __init__(
        self, key_files: dict[str, Path] | None = None, registry: Registry | None = None
    ) -> None:
        self.key_files = KEY_FILES if key_files is None else key_files
        self.registry = registry

    def _repo_node_id(self, repo: object) -> str | None:
        if not isinstance(repo, str) or self.registry is None:
            return None
        name = (
            repo.lower()
            .removeprefix("https://github.com/")
            .removeprefix("github.com/")
            .removesuffix(".git")
        )
        return next(
            (
                row["id"]
                for row in self.registry.active()
                if row["kind"] == "repo" and row["full_name"].lower() == name
            ),
            None,
        )

    def _request(
        self, service: str, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        if service not in HOSTS or not path.startswith("/") or path.startswith("//"):
            raise ValueError("invalid service request")

        # Auth is evaluated by HttpClient at request time; the key never enters a report.
        def auth() -> dict[str, str]:
            token = self.key_files[service].read_text(encoding="utf-8").strip()
            if not token:
                raise RuntimeError(f"{service} key is empty")
            return {"Authorization": f"Bearer {token}"}

        client = HttpClient(
            base_url=HOSTS[service], auth=auth, follow_redirects=False, max_attempts=1
        )
        response = client.request(method, path, body)
        if response.status == HTTPStatus.NOT_FOUND and method == "GET":
            return None
        if not HTTPStatus.OK <= response.status < HTTPStatus.MULTIPLE_CHOICES:
            raise RuntimeError(f"{service} HTTP {response.status}")
        return response.json

    def probe_request(
        self, service: str, method: str, path: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        if service not in HOSTS or not path.startswith("/") or path.startswith("//"):
            raise ValueError("invalid probe request")
        token = self.key_files[service].read_text(encoding="utf-8").strip()
        if not token:
            raise RuntimeError(f"{service} key is empty")
        client = HttpClient(
            base_url=HOSTS[service],
            auth=lambda: {"Authorization": f"Bearer {token}"},
            follow_redirects=False,
            max_attempts=1,
        )
        response = client.request(method, path, body)
        data = response.json if isinstance(response.json, dict) else {}
        detail = data.get("detail") or data.get("error") or ""
        return {"status": response.status, "reason": str(detail), "body": data}

    def read_resource(  # noqa: PLR0911
        self, service: str, kind: str, identity: str
    ) -> dict[str, Any] | None:
        value = _segment(identity)
        if service == "cfactory" and kind == "repository":
            # CF routes_git_config.py:591-603; git_connections.py:193-208.
            listing = self._request("cfactory", "GET", "/api/tenants/default/git-repositories")
            rows = listing.get("repositories", []) if listing else []
            row = next((item for item in rows if str(item.get("id")) == identity), None)
            return (
                {**row, "repo_node_id": self._repo_node_id(row.get("project")), "org": "default"}
                if row
                else None
            )
        # AIF mcp_stdio/router.py:281-287; PF mcp_stdio/router.py:655-665;
        # TF mcp_stdio/router.py:202-208; CF routes_cards.py:212-221.
        routes = {
            ("aifactory", "task"): f"/api/mcp-stdio/tasks/{value}",
            ("pfactory", "session"): f"/api/mcp-stdio/plan/sessions/{value}",
            ("cfactory", "card"): f"/api/cards/{value}",
            ("tfactory", "spec"): f"/api/mcp-stdio/tasks/{value}",
        }
        if kind == "project" and service in {"aifactory", "pfactory", "tfactory"}:
            result = self._request(service, "GET", "/api/mcp-stdio/projects")
            # HttpClient wraps JSON arrays as {"items": [...]}; test doubles may return lists.
            projects = result.get("items") if isinstance(result, dict) else result
            if not isinstance(projects, list):
                raise RuntimeError(f"{service} project list has an unknown shape")
            row = next(
                (
                    row
                    for row in projects
                    if isinstance(row, dict) and str(row.get("id")) == identity
                ),
                None,
            )
            if row is None:
                return None
            # AIF routes/projects.py:422-433 exposes repoIdentity; TF:343-348
            # exposes repoLabel. PF:373-382 exposes repo but clone onboarding
            # routes/projects.py:743-755 never fills it.
            # Project org_id: AIF routes/projects.py:871-883, PF:749-750,
            # TF routes/projects.py:743; absent values use the default org.
            repo = {
                "aifactory": row.get("repoIdentity"),
                "pfactory": row.get("repo"),
                "tfactory": row.get("repoLabel"),
            }[service]
            return {
                **row,
                "repo_node_id": self._repo_node_id(repo),
                "org": row.get("org_id") or "default",
            }
        if (service, kind) not in routes:
            raise NotImplementedError(f"no confirmed {service} {kind} read route")
        row = self._request(service, "GET", routes[service, kind])
        if row is None:
            return None
        # PF plan/service.py:111-131 stores session_id, repo, org_id;
        # AIF task_models.py:149-157 and TF routes/tasks.py:138-161 expose
        # repo; both task IDs include the parent project for org fallback.
        if service == "pfactory":
            return {
                **row,
                "id": row.get("session_id", identity),
                "repo_node_id": self._repo_node_id(row.get("repo")),
                "org": row.get("org_id") or "default",
            }
        if service in {"aifactory", "tfactory"}:
            project_id = identity.partition(":")[0]
            project = self.read_resource(service, "project", project_id)
            node = self._repo_node_id(row.get("repo"))
            return {
                **row,
                "id": identity,
                "repo_node_id": node
                if row.get("repo")
                else (project.get("repo_node_id") if project else None),
                "org": project.get("org") if project else "default",
            }
        # CF cards.py:343-362 exposes tenant_id and repository_id; the latter
        # resolves via routes_git_config.py:591-603 / git_connections.py:193-208.
        repositories = self._request(
            "cfactory",
            "GET",
            f"/api/tenants/{_segment(str(row['tenant_id']))}/git-repositories",
        )
        candidates = repositories.get("repositories", []) if repositories else []
        repo_id = row.get("repository_id") or (
            repositories.get("default_repository_id") if repositories else None
        )
        repo = next((item.get("project") for item in candidates if item.get("id") == repo_id), None)
        return {
            **row,
            "key": row.get("card_key", identity),
            "repo_node_id": self._repo_node_id(repo),
            "org": "default",
        }

    def exists(self, service: str, kind: str, identity: str) -> bool:
        resource = self.read_resource(service, kind, identity)
        if resource is None:
            return False
        if (service, kind) in {("aifactory", "task"), ("tfactory", "spec")}:
            # AIF routes/projects.py:1663-1667 and TF routes/projects.py:1436-1441
            # retain archived spec directories; metadata.archivedAt confirms cleanup.
            metadata = resource.get("metadata") or {}
            return not bool(metadata.get("archivedAt"))
        return True

    def delete(self, service: str, kind: str, identity: str) -> object:
        value = _segment(identity)
        # AIF routes/projects.py:965-990; PF routes/projects.py:848-863;
        # TF routes/projects.py:819-834; CF routes_cards.py:387-398.
        if kind == "project" and service in {"aifactory", "pfactory", "tfactory"}:
            return self._request(service, "DELETE", f"/api/projects/{value}")
        if service == "cfactory" and kind == "card":
            return self._request(service, "DELETE", f"/api/cards/{value}")
        if service == "cfactory" and kind == "repository":
            # CF routes_git_config.py:674-689.
            return self._request(
                service, "DELETE", f"/api/tenants/default/git-repositories/{value}"
            )
        if (service, kind) in {("tfactory", "spec"), ("aifactory", "task")}:
            return self.archive(service, kind, identity)
        raise NotImplementedError(f"no confirmed {service} {kind} delete route")

    def archive(self, service: str, kind: str, identity: str) -> object:
        if service in {"aifactory", "tfactory"} and kind in {"task", "spec"} and ":" in identity:
            project = _segment(identity.split(":", 1)[0])
            # AIF mcp_stdio/router.py:499-523; TF mcp_stdio/router.py:448-474;
            # factory_cli/actions.py uses the same scoped route.
            return self._request(
                service,
                "POST",
                f"/api/mcp-stdio/projects/{project}/tasks/archive",
                {"taskIds": [identity]},
            )
        raise NotImplementedError(f"no confirmed {service} {kind} archive route")

    def close_session(self, identity: str) -> object:
        # PF routes/plan_pipeline.py:857-879 provides discard; emitted sessions
        # are retained as the audit trail (delete route:881-898).
        session = self.read_resource("pfactory", "session", identity)
        if session is None:
            raise RuntimeError("PFactory session missing before cleanup")
        if session.get("status") == "emitted":
            return {"retained": True}
        return self._request(
            "pfactory",
            "POST",
            f"/api/plan/sessions/{_segment(identity)}/discard",
            {"actor": "factory-e2e", "reason": "campaign cleanup"},
        )

    def stop(self, task_id: str) -> object:
        # scripts/benchmarks/run_pipeline_task.py:351.
        return self._request("aifactory", "POST", f"/api/tasks/{_segment(task_id)}/stop")

    def task_status(self, task_id: str) -> dict[str, Any]:
        # AIF mcp_stdio/router.py:290-296 proxies execution status, distinct
        # from routes/task_models.py:18-38's frontend Kanban status.
        result = self._request(
            "aifactory", "GET", f"/api/mcp-stdio/tasks/{_segment(task_id)}/status"
        )
        return cast(dict[str, Any], result or {})

    def task_ids(self, project_id: str, service: str = "aifactory") -> set[str]:
        # AIF mcp_stdio/router.py:237-257 accepts project_id and returns
        # routes/task_models.py:164-168's tasks list.
        result = self._request(
            service, "GET", f"/api/mcp-stdio/tasks?project_id={_segment(project_id)}"
        )
        if result is None:
            return set()
        rows = result if isinstance(result, list) else result.get("tasks", result.get("items", []))
        return {str(row["id"]) for row in rows} if rows else set()

    def questions(self, task_id: str) -> list[dict[str, Any]]:
        response = self._request("aifactory", "GET", f"/api/tasks/{_segment(task_id)}/questions")
        rows = response if isinstance(response, list) else (response or {}).get("questions", [])
        if not isinstance(rows, list):
            raise RuntimeError("AIFactory questions have an unknown shape")
        return cast(list[dict[str, Any]], rows)

    def create_question_task(self, project_id: str, title: str, description: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "aifactory",
                "POST",
                f"/api/projects/{_segment(project_id)}/tasks",
                {
                    "title": title,
                    "description": description,
                    "metadata": {"mode": "quick", "requireReviewBeforeCoding": False},
                },
            ),
        )

    def start_task(self, task_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "aifactory",
                "POST",
                f"/api/tasks/{_segment(task_id)}/start",
                {"mode": "quick", "auto_handover_tfactory": False},
            ),
        )

    def merger_tick(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("aifactory", "POST", "/api/maintenance/merger/run?dry_run=false"),
        )

    def task_logs(self, task_id: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request("aifactory", "GET", f"/api/tasks/{_segment(task_id)}/logs") or {},
        )

    def stop_status(self, task_id: str) -> dict[str, Any]:
        # AIF routes/execution.py:329-365 reports is_running/queued after
        # routes/execution.py:1060-1090 accepts a stop.
        state = self.task_status(task_id)
        return {
            "status": "stopped"
            if state.get("is_running") is False and state.get("queued") is False
            else "running"
        }

    def usage(self, task_id: str) -> dict[str, Any]:
        # AIF routes/tasks_usage.py:29-43 returns token_attribution.py:633-641's
        # totalTokens/totalCostUsd wire fields.
        result = self._request("aifactory", "GET", f"/api/tasks/{_segment(task_id)}/token-usage")
        if result is None:
            raise RuntimeError("AIFactory usage returned HTTP 404")
        return {
            **result,
            "total_tokens": result.get("totalTokens", 0),
            "cost_usd": result.get("totalCostUsd", 0),
        }

    def timeline(self, card_key: str) -> dict[str, Any] | None:
        # CF routes_workitems.py:160-168.
        return cast(
            dict[str, Any] | None,
            self._request("cfactory", "GET", f"/api/workitems/{_segment(card_key)}/timeline"),
        )

    def workitem(self, key: str) -> dict[str, Any] | None:
        # CF routes_workitems.py:149-157 returns models.py:363-375's
        # per-service usage slices.
        return cast(
            dict[str, Any] | None,
            self._request("cfactory", "GET", f"/api/workitems/{_segment(key)}"),
        )

    def anomalies(self) -> list[dict[str, Any]]:
        # CF routes_workitems.py:143-146.
        response = self._request("cfactory", "GET", "/api/anomalies")
        if isinstance(response, list):
            return cast(list[dict[str, Any]], response)
        return cast(
            list[dict[str, Any]],
            response.get("anomalies", response.get("items", [])) if response else [],
        )

    def tokens(self) -> dict[str, Any]:
        # CF routes_workitems.py:83-85 and copilot/tools.py:128-176 expose
        # by_work_item, which can be filtered to the registered correlation key.
        return cast(dict[str, Any], self._request("cfactory", "GET", "/api/tokens"))

    def qa_report(self, task_id: str) -> dict[str, Any] | None:
        # AIF routes/tasks_views.py:31-92.
        return cast(
            dict[str, Any] | None,
            self._request(
                "aifactory", "GET", f"/api/mcp-stdio/tasks/{_segment(task_id)}/qa-report"
            ),
        )

    def verdict(self, identity: str) -> dict[str, Any] | None:
        project, sep, spec = identity.partition(":")
        if not sep:
            raise ValueError("TF spec requires project:spec")
        # TF main.py:628-633 mounts tfactory_tasks.py:399-405,458-463;
        # tfactory_tasks.py:385-395 exposes the tested source_sha.
        query = f"?project_id={_segment(project)}"
        detail = self._request("tfactory", "GET", f"/api/tfactory/tasks/{_segment(spec)}{query}")
        verdicts = self._request(
            "tfactory", "GET", f"/api/tfactory/tasks/{_segment(spec)}/verdicts.json{query}"
        )
        if detail is None or verdicts is None:
            return None
        return {"verdict_sha": detail.get("source_sha"), "verdicts": verdicts}

    def create_card(self, card_key: str, full_name: str, issue_number: int) -> dict[str, Any]:
        # CF routes_git_config.py:591-603 and git_connections.py:193-208
        # expose the tenant's repository IDs; routes_cards.py:110-127 and
        # cards.py:421-440 accept the repository_id on creation.
        listing = self._request("cfactory", "GET", "/api/tenants/default/git-repositories")
        rows = listing.get("repositories", []) if listing else []
        repo_id = next((row["id"] for row in rows if row.get("project") == full_name), None)
        if repo_id is None:
            raise RuntimeError("CFactory has no registered campaign repository")
        result = self._request(
            "cfactory",
            "POST",
            "/api/cards",
            {
                "card_key": card_key,
                "title": card_key,
                "repository_id": repo_id,
                "correlation_key": str(issue_number),
                "issue_ref": f"{full_name}#{issue_number}",
            },
        )
        if result is None:
            raise RuntimeError("CFactory card create returned no body")
        return self.read_resource("cfactory", "card", card_key) or {}

    def enable_pr_endgame(self, project_id: str) -> object:
        # AIF routes/projects.py update_project_settings: autoPr opens the PR,
        # autoMerge merges it on the review engine's approval.
        return self._request(
            "aifactory",
            "PATCH",
            f"/api/projects/{project_id}/settings",
            {"autoPr": True, "autoMerge": True},
        )

    def register_cf_repository(self, full_name: str, aif_project_id: str) -> dict[str, Any]:
        # CF routes_git_config.py:289-314,606-631 and
        # git_connections.py:213-245,274-285.
        listing = self._request("cfactory", "GET", "/api/tenants/default/git-connections")
        connections = listing.get("connections", []) if listing else []
        github = [
            row
            for row in connections
            if row.get("provider") == "github" and row.get("status") in {"configured", "verified"}
        ]
        if len(github) != 1:
            raise RuntimeError("CFactory needs one usable GitHub connection")
        result = self._request(
            "cfactory",
            "POST",
            f"/api/tenants/default/git-connections/{_segment(str(github[0]['id']))}/repositories",
            {"project": full_name, "aifactory_project_id": aif_project_id},
        )
        if not result or not result.get("id"):
            raise RuntimeError("CFactory repository registration returned no ID")
        return self.read_resource("cfactory", "repository", str(result["id"])) or {}
