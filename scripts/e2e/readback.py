"""Independent REST/remote-MCP and GitHub observations."""

from collections.abc import Callable
from typing import Any, cast
from urllib.error import HTTPError

from scripts.e2e.config import HOSTS
from scripts.parr_regression import HttpClient, bearer_auth  # type: ignore[attr-defined]

HTTP_OK = 200
HTTP_REDIRECT = 300
HTTP_NOT_FOUND = 404


class SurfaceMismatchError(Exception):
    """Surface output disagrees with the independent source."""


def pinned_rest(
    tokens: dict[str, str], client_factory: Callable[..., Any] = HttpClient
) -> Callable[[str, str], dict[str, Any]]:
    """Build independent REST readers on pinned hosts; tokens never enter reports."""
    clients = {
        service: client_factory(
            base_url=host,
            auth=bearer_auth(tokens[service]),
            follow_redirects=False,
        )
        for service, host in HOSTS.items()
    }

    def read(service: str, path: str) -> dict[str, Any]:
        response = clients[service].get(path)
        if not HTTP_OK <= response.status < HTTP_REDIRECT:
            raise SurfaceMismatchError(f"{service} read-back returned HTTP {response.status}")
        return cast(dict[str, Any], response.json)

    return read


class Readback:
    def __init__(
        self,
        rest: Callable[[str, str], dict[str, Any]],
        github: Callable[[str], dict[str, Any]],
    ) -> None:
        self.rest = rest
        self.github = github

    def compare(
        self, service: str, path: str, surface: dict[str, Any], keys: tuple[str, ...]
    ) -> dict[str, Any]:
        observed = self.rest(service, path)
        if not keys or any(
            key not in surface or key not in observed or surface[key] != observed[key]
            for key in keys
        ):
            raise SurfaceMismatchError(f"{service} surface disagrees with REST on {keys}")
        return observed

    def repo(self, full_name: str, node_id: str) -> dict[str, Any]:
        observed = self.github(full_name)
        if observed.get("node_id") != node_id:
            raise SurfaceMismatchError("GitHub repo identity differs")
        return observed


def absent(  # noqa: PLR0913
    read: Callable[[str, str], object],
    delete: Callable[[], object],
    service: str,
    path: str,
    key: str,
    expected: object,
) -> None:
    """A positive read of this key must precede a 404 absence check."""
    present = read(service, path)
    if not isinstance(present, dict) or present.get(key) != expected:
        raise SurfaceMismatchError("positive read failed before absence check")
    delete()
    try:
        read(service, path)
    except HTTPError as exc:
        if service == "github" and exc.code == HTTP_NOT_FOUND:
            return
        raise
    except SurfaceMismatchError as exc:
        if str(exc) == f"{service} read-back returned HTTP 404":
            return
        raise
    raise SurfaceMismatchError("resource still present")
