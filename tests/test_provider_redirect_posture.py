"""Guard: every credential-bearing provider HTTP client declines redirects.

Factory#825. Every ``httpx.AsyncClient`` construction under
``shared/factory-github/providers/`` all attach a real credential to an address
built from the provider's ``_base_url`` -- a value the services take from
API-writable settings. None of them stated a redirect posture; they inherited
httpx's default of not following redirects.

A library default is not a control. The consequence if it ever changes is
specific: httpx strips ``Authorization`` when a redirect crosses origins, but it
does **not** strip GitLab's ``PRIVATE-TOKEN``. A host that passed a caller-side
URL check could 302 the PAT onward in full, to all four consumers at once
(TFactory, PFactory, AIFactory, CFactory vendor this layer byte-for-byte).

Three guards, weakest to strongest:

* :func:`test_every_async_client_states_follow_redirects_false` is the fleet-wide
  one: an :mod:`ast` pass over every provider module, requiring the kwarg to be
  present *and* ``False``. A client added tomorrow that omits it fails here --
  which is the whole point, since omitting it is exactly what #825 was about.
* :func:`test_live_provider_clients_decline_redirects` constructs the real
  providers and reads the attribute off the built client, so the property is
  proven on the object, not on the source text.
* :func:`test_redirect_does_not_carry_the_credential_onward` proves the end-to-end
  behaviour against two real local HTTP servers: hop 1 answers 302, hop 2 records
  every credential header it receives, and hop 2 must never be reached.

Mutation check: set ``follow_redirects=True`` at any one of the client sites and
the first two tests go red; do it at ``GitLabProvider._client`` and all three do.
"""

from __future__ import annotations

import ast
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

pytest.importorskip("httpx", reason="provider modules import httpx at module scope")

# conftest.py already puts shared/factory-github on sys.path (Factory#721), so
# these import directly rather than re-pasting the bootstrap a third time.
from providers.azure_devops_provider import (
    AzureDevOpsProvider,
)
from providers.gitlab_provider import (
    GitLabProvider,
)
from providers.http_github_provider import (
    HttpGitHubProvider,
)

_PROVIDERS_DIR = Path(__file__).resolve().parents[1] / "shared" / "factory-github" / "providers"

# #825 enumerated eight sites; four of them were the Azure DevOps write paths,
# which this change collapsed onto AzureDevOpsProvider._patch_client(). What is
# left is GitLab _client() + the Duo workflow POST, Azure _client() +
# _patch_client(), and the HTTP GitHub provider's _client(). Asserting the count
# stops the AST pass from passing vacuously if the tree moves or a glob stops
# matching -- an empty offender list over zero calls is not a green property.
_KNOWN_CLIENT_SITES = 5


def _async_client_calls() -> list[tuple[str, int, ast.Call]]:
    """Every ``httpx.AsyncClient(...)`` construction in the canonical providers."""
    found: list[tuple[str, int, ast.Call]] = []
    for module in sorted(_PROVIDERS_DIR.glob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "AsyncClient":
                found.append((module.name, node.lineno, node))
    return found


def test_every_async_client_states_follow_redirects_false() -> None:
    """Each client must SET the flag -- inheriting httpx's default is the defect."""
    calls = _async_client_calls()
    assert len(calls) >= _KNOWN_CLIENT_SITES, (
        f"expected at least the {_KNOWN_CLIENT_SITES} known client sites under "
        f"{_PROVIDERS_DIR}, found {len(calls)} -- has the tree moved?"
    )

    offenders: list[str] = []
    for name, lineno, node in calls:
        kwarg = next((kw for kw in node.keywords if kw.arg == "follow_redirects"), None)
        if kwarg is None:
            offenders.append(
                f"{name}:{lineno} httpx.AsyncClient(...) carries a credential but "
                "states no redirect posture -- add `follow_redirects=False`"
            )
        elif not (isinstance(kwarg.value, ast.Constant) and kwarg.value.value is False):
            offenders.append(
                f"{name}:{lineno} httpx.AsyncClient(follow_redirects=...) is not False -- "
                "a 302 would carry the credential to the redirect target"
            )

    assert not offenders, "credential-bearing clients with a bad redirect posture:\n  " + (
        "\n  ".join(offenders)
    )


def test_live_provider_clients_decline_redirects() -> None:
    """Read the property off the constructed clients, not off the source text."""
    gitlab = GitLabProvider(_repo="owner/repo", _token="glpat-fake")  # noqa: S106 - fake probe value
    azure = AzureDevOpsProvider(_repo="owner/repo", _pat="azdo-fake")
    github = HttpGitHubProvider(_repo="owner/repo", _token="ghp-fake")  # noqa: S106 - fake probe value

    # _patch_client() is included deliberately: it is the ADO write path (the one
    # that mutates work items), and it builds its own client rather than reusing
    # _client()'s.
    for label, client in (
        ("GitLab", gitlab._client()),
        ("AzureDevOps", azure._client()),
        ("AzureDevOps._patch_client", azure._patch_client()),
        ("HttpGitHub", github._client()),
    ):
        assert client.follow_redirects is False, label
        # The credential is still attached -- otherwise the "fix" would read green
        # by having broken authentication.
        assert any(h in client.headers for h in ("private-token", "authorization")), label


class _RecorderHandler(BaseHTTPRequestHandler):
    """Hop 2: records any credential header that reaches it."""

    received: ClassVar[list[dict[str, str]]] = []

    def do_GET(self) -> None:
        _RecorderHandler.received.append(
            {
                k: v
                for k, v in self.headers.items()
                if k.lower() in {"private-token", "authorization"}
            }
        )
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


class _RedirectHandler(BaseHTTPRequestHandler):
    """Hop 1: the host that passed the caller's URL check, and answers 302."""

    target = ""

    def do_GET(self) -> None:
        self.send_response(302)
        self.send_header("Location", _RedirectHandler.target)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        pass


def _serve(handler_cls: type[BaseHTTPRequestHandler]) -> HTTPServer:
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_redirect_does_not_carry_the_credential_onward() -> None:
    """A 302 from a passing host must not deliver the PAT to the redirect target.

    The GitLab client is the sharp case: httpx would strip ``Authorization``
    across origins, but ``PRIVATE-TOKEN`` is not a header it knows about, so with
    ``follow_redirects=True`` hop 2 receives ``glpat-secret`` verbatim. This is
    what a URL check at the caller cannot cover -- hop 1 passed it.
    """
    _RecorderHandler.received = []
    recorder = _serve(_RecorderHandler)
    try:
        _RedirectHandler.target = f"http://127.0.0.1:{recorder.server_port}/stolen"
        redirector = _serve(_RedirectHandler)
        try:
            provider = GitLabProvider(
                _repo="owner/repo",
                _token="glpat-secret",  # noqa: S106 - fake probe value
                _base_url=f"http://127.0.0.1:{redirector.server_port}",
            )

            async def _fetch() -> int:
                async with provider._client() as client:
                    resp = await client.get("/api/v4/projects")
                    # int(): httpx has no stubs under the ratchet's
                    # --ignore-missing-imports, so status_code is Any.
                    return int(resp.status_code)

            status = asyncio.run(_fetch())

            # The credential assertion comes first: it is the one that says what
            # an attacker actually walks away with.
            assert _RecorderHandler.received == [], (
                "the credential-bearing request followed the redirect and carried: "
                f"{_RecorderHandler.received}"
            )
            assert status == 302
        finally:
            redirector.shutdown()
    finally:
        recorder.shutdown()
