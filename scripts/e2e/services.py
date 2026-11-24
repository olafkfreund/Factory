"""Pinned REST reads and confirmed service actions for the campaign."""

from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import quote

from scripts.e2e.config import HOSTS, KEY_FILES
from scripts.parr_regression import HttpClient  # type: ignore[attr-defined]


def _segment(value: str) -> str:
    if not value or value in {".", ".."} or "/" in value:
        raise ValueError("invalid resource identifier")
    return quote(value, safe="")


class Services:
    def __init__(self, key_files: dict[str, Path] | None = None) -> None:
        self.key_files = KEY_FILES if key_files is None else key_files

    def _request(
        self, service: str, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
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

    def read_resource(self, service: str, kind: str, identity: str) -> dict[str, Any] | None:
        value = _segment(identity)
        # status.py:153,183,245,340; testrun.py:314; actions.py:113.
        routes = {
            ("aifactory", "task"): f"/api/mcp-stdio/tasks/{value}",
            ("pfactory", "session"): f"/api/mcp-stdio/plan/sessions/{value}",
            ("cfactory", "card"): f"/api/workitems/{value}",
            ("tfactory", "spec"): f"/api/specs/{value}",
        }
        if kind == "project" and service in {"aifactory", "pfactory", "tfactory"}:
            result = self._request(service, "GET", "/api/mcp-stdio/projects")
            projects = result.get("items", result.get("projects", [])) if result else []
            if not isinstance(projects, list):
                raise RuntimeError(f"{service} project list has an unknown shape")
            return next(
                (
                    row
                    for row in projects
                    if isinstance(row, dict) and str(row.get("id")) == identity
                ),
                None,
            )
        if (service, kind) not in routes:
            raise NotImplementedError(f"no confirmed {service} {kind} read route")
        return self._request(service, "GET", routes[service, kind])

    def exists(self, service: str, kind: str, identity: str) -> bool:
        return self.read_resource(service, kind, identity) is not None

    def delete(self, service: str, kind: str, identity: str) -> object:
        raise NotImplementedError(f"no confirmed {service} {kind} delete route")

    def archive(self, service: str, kind: str, identity: str) -> object:
        if service == "aifactory" and kind == "task" and ":" in identity:
            project = _segment(identity.split(":", 1)[0])
            # actions.py:170: scoped archive is the only confirmed cleanup action.
            return self._request(
                service,
                "POST",
                f"/api/mcp-stdio/projects/{project}/tasks/archive",
                {"taskIds": [identity]},
            )
        raise NotImplementedError(f"no confirmed {service} {kind} archive route")

    def close_session(self, identity: str) -> object:
        raise NotImplementedError("no confirmed PFactory session close route")

    def stop(self, task_id: str) -> object:
        # scripts/benchmarks/run_pipeline_task.py:351.
        return self._request("aifactory", "POST", f"/api/tasks/{_segment(task_id)}/stop")

    def usage(self, task_id: str) -> dict[str, Any]:
        # plan/2026-11-24-3882-e2e-campaign.md, Cost/Sources.
        result = self._request("aifactory", "GET", f"/api/tasks/{_segment(task_id)}/token-usage")
        if result is None:
            raise RuntimeError("AIFactory usage returned HTTP 404")
        return result

    def timeline(self, card_key: str) -> dict[str, Any] | None:
        # apis/cfactory.openapi.yaml:96.
        return self._request("cfactory", "GET", f"/api/workitems/{_segment(card_key)}/timeline")
