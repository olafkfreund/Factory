"""Independent REST/remote-MCP and GitHub observations."""

from collections.abc import Callable

from scripts.e2e.config import HOSTS
from scripts.parr_regression import HttpClient, bearer_auth

HTTP_OK = 200
HTTP_REDIRECT = 300


class SurfaceMismatchError(Exception):
    """Surface output disagrees with the independent source."""


def pinned_rest(tokens: dict[str, str], client_factory: Callable = HttpClient) -> Callable:
    """Build independent REST readers on pinned hosts; tokens never enter reports."""
    clients = {
        service: client_factory(
            base_url=host,
            auth=bearer_auth(tokens[service]),
            follow_redirects=False,
        )
        for service, host in HOSTS.items()
    }

    def read(service: str, path: str) -> dict:
        response = clients[service].get(path)
        if not HTTP_OK <= response.status < HTTP_REDIRECT:
            raise SurfaceMismatchError(f"{service} read-back returned HTTP {response.status}")
        return response.json

    return read


class Readback:
    def __init__(self, rest: Callable[[str, str], dict], github: Callable[[str], dict]) -> None:
        self.rest = rest
        self.github = github

    def compare(self, service: str, path: str, surface: dict, keys: tuple[str, ...]) -> dict:
        observed = self.rest(service, path)
        if any(surface.get(key) != observed.get(key) for key in keys):
            raise SurfaceMismatchError(f"{service} surface disagrees with REST on {keys}")
        return observed

    def repo(self, full_name: str, node_id: str) -> dict:
        observed = self.github(full_name)
        if observed.get("node_id") != node_id:
            raise SurfaceMismatchError("GitHub repo identity differs")
        return observed
