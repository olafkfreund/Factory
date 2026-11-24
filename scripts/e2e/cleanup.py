"""Seven-day registry-only sweeper. Dry-run is the default."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from scripts.e2e.config import SWEEP_AGE_DAYS
from scripts.e2e.guard import REPO_NAME, Guard, GuardRefusalError
from scripts.e2e.registry import Registry


class DeleteClient(Protocol):
    def delete(self, service: str, kind: str, identity: str) -> object: ...
    def close_session(self, identity: str) -> object: ...
    def exists(self, service: str, kind: str, identity: str) -> bool: ...


def sweep(  # noqa: PLR0912
    registry: Registry,
    guard: Guard,
    delete: DeleteClient,
    *,
    dry_run: bool = True,
    now: datetime | None = None,
) -> list[dict]:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=SWEEP_AGE_DAYS)
    groups: dict[str, list[dict]] = {}
    for entry in registry.active():
        groups.setdefault(entry["repo_node_id"], []).append(entry)
    actions = []
    for entries in groups.values():
        repo = next((entry for entry in entries if entry["kind"] == "repo"), None)
        if repo is None:
            continue
        repo_due = datetime.fromisoformat(repo["at"]) < cutoff
        ordered = sorted(entries, key=lambda entry: entry["kind"] == "repo")
        for entry in ordered:
            if not repo_due and datetime.fromisoformat(entry["at"]) >= cutoff:
                continue
            service, kind, identity = entry["service"], entry["kind"], entry["id"]
            guard.check(service, kind, identity)
            action = "retain" if kind == "session" else "delete"
            actions.append({"service": service, "kind": kind, "id": identity, "action": action})
            if dry_run:
                continue
            if kind == "session":
                guard.mutate(
                    service,
                    kind,
                    identity,
                    lambda identity=identity: delete.close_session(identity),
                )
                registry.append(
                    "retained", identity, entry["repo_node_id"], service=service, target_kind=kind
                )
            else:
                guard.mutate(
                    service,
                    kind,
                    identity,
                    lambda service=service, kind=kind, identity=identity: delete.delete(
                        service, kind, identity
                    ),
                )
                if delete.exists(service, kind, identity):
                    raise RuntimeError(f"{kind} deletion unconfirmed")
                registry.append(
                    "deleted", identity, entry["repo_node_id"], service=service, target_kind=kind
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
            or intent["full_name"] in finalized
            or datetime.fromisoformat(intent["at"]) >= cutoff
        ):
            continue
        name = intent["name"]
        if not REPO_NAME.fullmatch(name) or intent["full_name"] != f"Freundcloud/{name}":
            raise GuardRefusalError("unsafe repo intent")
        live = guard.read_repo(intent["full_name"])
        if live is None:
            continue
        if (
            live.get("full_name") != intent["full_name"]
            or live.get("owner", {}).get("login") != "Freundcloud"
            or live.get("name") != name
        ):
            raise GuardRefusalError("orphan repo safety predicates failed")
        actions.append(
            {"service": "github", "kind": "repo", "id": intent["full_name"], "action": "delete"}
        )
        if not dry_run:
            delete.delete("github", "repo", intent["full_name"])
            if delete.exists("github", "repo", intent["full_name"]):
                raise RuntimeError("orphan repo deletion unconfirmed")
            registry.append("deleted", name, name, service="github", target_kind="repo")
    return actions


def unregistered_repos(registry: Registry, list_repos: Callable[[], list[dict]]) -> list[str]:
    registered = {
        entry["full_name"] for entry in registry.entries() if entry["kind"] in {"repo", "intent"}
    }
    return [
        repo["full_name"]
        for repo in list_repos()
        if repo.get("name", "").startswith("e2e-") and repo["full_name"] not in registered
    ]
