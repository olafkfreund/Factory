"""One live ownership check before every service mutation."""

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from scripts.e2e.config import ORG
from scripts.e2e.registry import KIND_SERVICES, Registry

REPO_NAME = re.compile(r"^e2e-\d{8}-P[1-5]-\d+$")
RESOURCE_KINDS = set(KIND_SERVICES)
# PF's project response has no clone repo (routes/projects.py:373-382,743-755).
# Its guard uses registry identity plus a live existence check. CF cards resolve
# their repository_id through routes_git_config.py:591-603.
NO_REPO_LINK = {("pfactory", "project")}


class GuardRefusalError(Exception):
    """Mutation target is outside the registered campaign."""


class Guard:
    def __init__(
        self,
        registry: Registry,
        read_repo: Callable[[str], dict[str, Any] | None],
        read_resource: Callable[[str, str, str], dict[str, Any] | None],
    ) -> None:
        self.registry = registry
        self.read_repo = read_repo
        self.read_resource = read_resource

    def check(self, service: str, kind: str, identity: str) -> dict[str, Any]:
        if service not in KIND_SERVICES.get(kind, set()):
            raise GuardRefusalError("unknown resource service or kind")
        entry = self.registry.find(service, kind, identity)
        if entry is None and service == "github" and kind == "repo":
            entry = next(
                (
                    row
                    for row in self.registry.entries()
                    if row["kind"] == "intent" and row["full_name"] == identity
                ),
                None,
            )
            if entry is None or any(
                row["kind"] in {"create_failed", "deleted"} and row["id"] == entry["id"]
                for row in self.registry.entries()
            ):
                raise GuardRefusalError("closed or missing repo intent")
            repo = self.read_repo(identity)
            if repo is None:
                raise GuardRefusalError("repo creation time unavailable")
            try:
                created = datetime.fromisoformat(repo["created_at"].replace("Z", "+00:00"))
                intended = datetime.fromisoformat(entry["at"])
            except (KeyError, TypeError, ValueError, AttributeError):
                raise GuardRefusalError("repo creation time unavailable") from None
            if (
                created.tzinfo is None
                or created < intended
                or repo.get("full_name") != identity
                or repo.get("owner", {}).get("login") != "Freundcloud"
                or not REPO_NAME.fullmatch(repo.get("name", ""))
                or "factory-e2e" not in repo.get("topics", [])
            ):
                raise GuardRefusalError("orphan repo safety predicates failed")
            return entry
        if entry is None or entry not in self.registry.active():
            raise GuardRefusalError("unregistered target")
        repo_entry = self.registry.find("github", "repo", entry["repo_node_id"])
        if repo_entry is None or repo_entry not in self.registry.active():
            raise GuardRefusalError("unregistered or inactive repo")
        repo = self.read_repo(repo_entry["full_name"])
        if (
            repo is None
            or repo.get("node_id") != repo_entry["id"]
            or repo.get("id") != repo_entry["repo_id"]
            or repo.get("full_name") != repo_entry["full_name"]
        ):
            raise GuardRefusalError("repo identity changed or unavailable")
        if (
            repo.get("owner", {}).get("login") != "Freundcloud"
            or not REPO_NAME.fullmatch(repo.get("name", ""))
            or "factory-e2e" not in repo.get("topics", [])
        ):
            raise GuardRefusalError("repo safety predicates failed")
        if kind != "repo":
            resource = self.read_resource(service, kind, identity)
            if (
                resource is None
                or str(resource.get("key" if kind == "card" else "id", "")) != identity
                or (
                    (service, kind) not in NO_REPO_LINK
                    and resource.get("repo_node_id") != repo_entry["id"]
                )
                or not entry.get("org")
                or resource.get("org") != entry["org"]
            ):
                raise GuardRefusalError("resource ownership changed or unavailable")
        return entry

    def mutate(
        self, service: str, kind: str, identity: str, operation: Callable[[], object]
    ) -> object:
        self.check(service, kind, identity)
        return operation()

    def create_repo(
        self,
        name: str,
        create: Callable[[], dict[str, Any]],
        set_topics: Callable[[str, list[str]], object],
    ) -> dict[str, Any]:
        if not REPO_NAME.fullmatch(name):
            raise GuardRefusalError("unsafe repo name")
        full_name = f"Freundcloud/{name}"
        self.registry.append(
            "intent",
            name,
            name,
            service="github",
            target_kind="repo",
            name=name,
            full_name=full_name,
        )
        try:
            repo = create()
        except Exception:
            self.registry.append("create_failed", name, name, service="github", target_kind="repo")
            raise
        if (
            repo.get("name") != name
            or repo.get("owner", {}).get("login") != "Freundcloud"
            or repo.get("full_name") != full_name
            or not repo.get("node_id")
            or not repo.get("id")
        ):
            raise GuardRefusalError("created repo failed safety predicates")
        set_topics(full_name, ["factory-e2e"])
        self.registry.append(
            "repo",
            repo["node_id"],
            repo["node_id"],
            service="github",
            repo_id=repo["id"],
            full_name=full_name,
        )
        return repo

    def create_resource(
        self,
        kind: str,
        service: str,
        repo_node_id: str,
        create: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        if service not in KIND_SERVICES.get(kind, set()):
            raise GuardRefusalError("invalid resource service")
        self.check("github", "repo", repo_node_id)
        resource = create()
        identity = str(resource.get("key" if kind == "card" else "id", ""))
        if (
            not identity
            or (
                (service, kind) not in NO_REPO_LINK and resource.get("repo_node_id") != repo_node_id
            )
            or not resource.get("org")
            or (service in {"aifactory", "pfactory", "tfactory"} and ORG and resource["org"] != ORG)
        ):
            raise GuardRefusalError("created resource ownership mismatch")
        self.registry.append(
            kind, identity, repo_node_id, service=service, org=str(resource.get("org") or "")
        )
        return resource
