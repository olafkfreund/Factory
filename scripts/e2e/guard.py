"""One live ownership check before every service mutation."""

import re
from collections.abc import Callable

from scripts.e2e.registry import Registry

REPO_NAME = re.compile(r"^e2e-\d{8}-P[1-5]-\d+$")
RESOURCE_KINDS = {"repo", "project", "session", "task", "spec", "card"}
KIND_SERVICES = {
    "project": {"aifactory", "pfactory", "tfactory"},
    "session": {"pfactory"},
    "task": {"aifactory"},
    "spec": {"tfactory"},
    "card": {"cfactory"},
}


class GuardRefusalError(Exception):
    """Mutation target is outside the registered campaign."""


class Guard:
    def __init__(
        self,
        registry: Registry,
        read_repo: Callable[[str], dict | None],
        read_resource: Callable[[str, str], dict | None],
    ) -> None:
        self.registry = registry
        self.read_repo = read_repo
        self.read_resource = read_resource

    def check(self, kind: str, identity: str) -> dict:
        if kind not in RESOURCE_KINDS:
            raise GuardRefusalError("unknown resource kind")
        entry = self.registry.find(kind, identity)
        if entry is None or entry not in self.registry.active():
            raise GuardRefusalError("unregistered target")
        repo_entry = self.registry.find("repo", entry["repo_node_id"])
        if repo_entry is None:
            raise GuardRefusalError("unregistered repo")
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
            resource = self.read_resource(kind, identity)
            if (
                resource is None
                or str(resource.get("key" if kind == "card" else "id", "")) != identity
                or resource.get("repo_node_id") != repo_entry["id"]
            ):
                raise GuardRefusalError("resource ownership changed or unavailable")
        return entry

    def mutate(self, kind: str, identity: str, operation: Callable[[], object]) -> object:
        self.check(kind, identity)
        return operation()

    def create_repo(self, name: str, create: Callable[[], dict]) -> dict:
        if not REPO_NAME.fullmatch(name):
            raise GuardRefusalError("unsafe repo name")
        repo = create()
        if (
            repo.get("name") != name
            or repo.get("owner", {}).get("login") != "Freundcloud"
            or "factory-e2e" not in repo.get("topics", [])
            or not repo.get("node_id")
            or not repo.get("id")
        ):
            raise GuardRefusalError("created repo failed safety predicates")
        self.registry.append(
            "repo",
            repo["node_id"],
            repo["node_id"],
            repo_id=repo["id"],
            full_name=repo["full_name"],
        )
        return repo

    def create_resource(
        self, kind: str, service: str, repo_node_id: str, create: Callable[[], dict]
    ) -> dict:
        if service not in KIND_SERVICES.get(kind, set()):
            raise GuardRefusalError("invalid resource service")
        self.check("repo", repo_node_id)
        resource = create()
        identity = str(resource.get("key" if kind == "card" else "id", ""))
        if not identity or resource.get("repo_node_id") != repo_node_id:
            raise GuardRefusalError("created resource ownership mismatch")
        self.registry.append(kind, identity, repo_node_id, service=service)
        return resource
