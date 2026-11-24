"""Seven-day registry-only sweeper. Dry-run is the default."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any, Protocol
from urllib.error import HTTPError

from scripts.e2e.config import SWEEP_AGE_DAYS
from scripts.e2e.github import GitHub
from scripts.e2e.guard import Guard
from scripts.e2e.registry import Registry
from scripts.e2e.services import Services

HTTP_NOT_FOUND = 404


class DeleteClient(Protocol):
    def delete(self, service: str, kind: str, identity: str) -> object: ...
    def close_session(self, identity: str) -> object: ...
    def exists(self, service: str, kind: str, identity: str) -> bool: ...


class LiveDelete:
    def __init__(self, services: Services, github: GitHub, registry: Registry) -> None:
        self.services = services
        self.github = github
        self.registry = registry

    def _repo_name(self, node_id: str) -> str:
        if node_id.startswith("olafkfreund/") and any(
            row["kind"] == "intent" and row["full_name"] == node_id
            for row in self.registry.entries()
        ):
            return node_id
        row = self.registry.find("github", "repo", node_id)
        if row is None or row not in self.registry.active():
            raise ValueError("unregistered repo node ID")
        return str(row["full_name"])

    def delete(self, service: str, kind: str, identity: str) -> object:
        if (service, kind) == ("github", "repo"):
            return self.github.delete_repo(self._repo_name(identity))
        return self.services.delete(service, kind, identity)

    def close_session(self, identity: str) -> object:
        return self.services.close_session(identity)

    def exists(self, service: str, kind: str, identity: str) -> bool:
        if (service, kind) == ("github", "repo"):
            return self.github.read_repo(self._repo_name(identity)) is not None
        return self.services.exists(service, kind, identity)


def _exists(delete: DeleteClient, service: str, kind: str, identity: str) -> bool:
    try:
        return delete.exists(service, kind, identity)
    except HTTPError as exc:
        if exc.code == HTTP_NOT_FOUND:
            return False
        raise


def sweep(  # noqa: PLR0912
    registry: Registry,
    guard: Guard,
    delete: DeleteClient,
    *,
    dry_run: bool = True,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=SWEEP_AGE_DAYS)
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in registry.active():
        groups.setdefault(entry["repo_node_id"], []).append(entry)
    actions = []
    for entries in groups.values():
        repo = next((entry for entry in entries if entry["kind"] == "repo"), None)
        if repo is None:
            continue
        repo_due = datetime.fromisoformat(repo["at"]) < cutoff
        order = {
            "card": 0,
            "session": 1,
            "spec": 2,
            "task": 2,
            "repository": 3,
            "project": 4,
            "repo": 5,
        }
        ordered = sorted(entries, key=lambda entry: order[entry["kind"]])
        for entry in ordered:
            if not repo_due and datetime.fromisoformat(entry["at"]) >= cutoff:
                continue
            service, kind, identity = entry["service"], entry["kind"], entry["id"]
            action = (
                "retain"
                if kind == "session"
                else "archive"
                if kind in {"task", "spec"}
                else "delete"
            )
            try:
                guard.check(service, kind, identity)
                actions.append({"service": service, "kind": kind, "id": identity, "action": action})
                if dry_run:
                    continue
                if kind == "session":
                    guard.mutate(
                        service,
                        kind,
                        identity,
                        partial(delete.close_session, identity),
                    )
                    registry.append(
                        "retained",
                        identity,
                        entry["repo_node_id"],
                        service=service,
                        target_kind=kind,
                    )
                else:
                    guard.mutate(
                        service,
                        kind,
                        identity,
                        partial(delete.delete, service, kind, identity),
                    )
                    if _exists(delete, service, kind, identity):
                        raise RuntimeError(f"{kind} deletion unconfirmed")
                    registry.append(
                        "deleted",
                        identity,
                        entry["repo_node_id"],
                        service=service,
                        target_kind=kind,
                    )
            except Exception:  # noqa: BLE001
                actions.append(
                    {"service": service, "kind": kind, "id": identity, "action": "failed"}
                )
                if not dry_run:
                    registry.append(
                        "failed", identity, entry["repo_node_id"], service=service, target_kind=kind
                    )
    # A failed create can leave a repo without a node ID. Its intent is the only authority.
    finalized = {entry["full_name"] for entry in registry.entries() if entry["kind"] == "repo"}
    ended_intents = {
        entry["id"]
        for entry in registry.entries()
        if entry["kind"] == "deleted" and entry.get("target_kind") == "repo"
    }
    for intent in registry.entries():
        if (
            intent["kind"] != "intent"
            or intent["id"] in ended_intents
            or registry.find("github", "create_failed", intent["id"]) is not None
            or intent["full_name"] in finalized
            or datetime.fromisoformat(intent["at"]) >= cutoff
        ):
            continue
        name = intent["name"]
        try:
            guard.check("github", "repo", intent["full_name"])
            actions.append(
                {"service": "github", "kind": "repo", "id": intent["full_name"], "action": "delete"}
            )
            if not dry_run:
                guard.mutate(
                    "github",
                    "repo",
                    intent["full_name"],
                    partial(delete.delete, "github", "repo", intent["full_name"]),
                )
                if _exists(delete, "github", "repo", intent["full_name"]):
                    raise RuntimeError("orphan repo deletion unconfirmed")
                registry.append("deleted", name, name, service="github", target_kind="repo")
        except Exception:  # noqa: BLE001
            actions.append(
                {"service": "github", "kind": "repo", "id": intent["full_name"], "action": "failed"}
            )
            if not dry_run:
                registry.append("failed", name, name, service="github", target_kind="repo")
    return actions


def unregistered_repos(
    registry: Registry, list_repos: Callable[[], list[dict[str, Any]]]
) -> list[str]:
    registered = {
        entry["full_name"] for entry in registry.entries() if entry["kind"] in {"repo", "intent"}
    }
    return [
        repo["full_name"]
        for repo in list_repos()
        if repo.get("name", "").startswith("e2e-") and repo["full_name"] not in registered
    ]
