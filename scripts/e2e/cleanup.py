"""Seven-day registry-only sweeper. Dry-run is the default."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from scripts.e2e.config import SWEEP_AGE_DAYS
from scripts.e2e.guard import Guard
from scripts.e2e.registry import Registry


class DeleteClient(Protocol):
    def delete(self, kind: str, identity: str) -> object: ...
    def close_session(self, identity: str) -> object: ...
    def exists(self, kind: str, identity: str) -> bool: ...


def sweep(
    registry: Registry,
    guard: Guard,
    delete: DeleteClient,
    *,
    dry_run: bool = True,
    now: datetime | None = None,
) -> list[dict]:
    """Client must expose delete(kind, id), close_session(id), and exists(kind, id)."""
    cutoff = (now or datetime.now(UTC)) - timedelta(days=SWEEP_AGE_DAYS)
    actions = []
    for entry in reversed(registry.active()):
        if datetime.fromisoformat(entry["at"]) >= cutoff:
            continue
        kind, identity = entry["kind"], entry["id"]
        guard.check(kind, identity)
        action = "retain" if kind == "session" else "delete"
        actions.append({"kind": kind, "id": identity, "action": action})
        if dry_run:
            continue
        if kind == "session":
            guard.mutate(kind, identity, lambda identity=identity: delete.close_session(identity))
            registry.append("retained", identity, entry["repo_node_id"], target_kind=kind)
        else:
            guard.mutate(
                kind, identity, lambda kind=kind, identity=identity: delete.delete(kind, identity)
            )
            if delete.exists(kind, identity):
                raise RuntimeError(f"{kind} deletion unconfirmed")
            registry.append("deleted", identity, entry["repo_node_id"], target_kind=kind)
    return actions


def unregistered_repos(registry: Registry, list_repos: Callable[[], list[dict]]) -> list[str]:
    registered = {entry["full_name"] for entry in registry.entries() if entry["kind"] == "repo"}
    return [
        repo["full_name"]
        for repo in list_repos()
        if repo.get("name", "").startswith("e2e-") and repo["full_name"] not in registered
    ]
