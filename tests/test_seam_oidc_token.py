"""Service-account JWT minting for seams behind an OIDC proxy (Factory#420).

The behaviour that matters is the DEGRADATION. A service behind oauth2-proxy
answers an opaque API token with a 302 to the identity provider, so the probe
needs a real JWT -- but if it cannot mint one it must fall back to reporting
honestly, never crash the whole run and never silently look authenticated.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from typing import Any

import parr_regression as pr  # scripts/ is on sys.path via tests/conftest.py
import pytest


def _clear() -> None:
    # The minting helper is cached per service, so every case needs a fresh one.
    pr._oidc_bearer.cache_clear()


def _stub_transport(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Record every token request and fail it, without touching the network.

    Two jobs. It makes these cases hermetic — they used to resolve
    ``*.invalid`` for real, so the suite's verdict depended on what the runner's
    resolver did with a reserved TLD. And it makes the returned list the
    evidence for the assertion below: "" is the right answer for BOTH "no
    credential configured" and "the issuer could not be reached", so a test that
    only checks the return value cannot tell which one it observed.
    """
    attempts: list[Any] = []

    def _fail(req: Any, timeout: int | None = None) -> Any:  # noqa: ARG001
        attempts.append(req)
        raise urllib.error.URLError("stubbed: this test must not reach the network")

    monkeypatch.setattr(urllib.request, "urlopen", _fail)
    return attempts


def test_unconfigured_returns_empty_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear()
    attempts = _stub_transport(monkeypatch)
    for var in ("CFACTORY_OIDC_CLIENT_ID", "CFACTORY_OIDC_CLIENT_SECRET", "PARR_OIDC_TOKEN_URL"):
        monkeypatch.delenv(var, raising=False)
    assert pr._oidc_bearer("cfactory") == ""
    assert attempts == [], "an unconfigured seam must not send a token request"


def test_partial_config_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """An id with no secret is a misconfiguration, not a credential.

    Returning a half-formed request here would produce a confusing 400 from the
    identity provider instead of a clear "no credential".

    The assertion that carries this is ``attempts == []``, not the return value.
    Asserting only ``== ""`` was theatre: with the secret absent the helper
    happily built a request with ``client_secret=None`` and got "" back from the
    FAILED CALL, so deleting the config guard entirely left this test green
    (measured). The rule is that no request is made at all.
    """
    _clear()
    attempts = _stub_transport(monkeypatch)
    monkeypatch.setenv("CFACTORY_OIDC_CLIENT_ID", "parr-seam-probe")
    monkeypatch.delenv("CFACTORY_OIDC_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("PARR_OIDC_TOKEN_URL", "https://example.invalid/token")
    assert pr._oidc_bearer("cfactory") == ""
    assert attempts == [], "a half-configured client must never be sent to the issuer"


def test_unreachable_issuer_degrades_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead or wrong issuer must not take the whole probe down with it.

    The seam then reports what it can see, which is the point: an unmintable
    token is a missing credential, not a crash. Unlike the case above this one
    SHOULD reach the transport — fully configured — and the attempt count is
    what distinguishes the two.
    """
    _clear()
    attempts = _stub_transport(monkeypatch)
    monkeypatch.setenv("CFACTORY_OIDC_CLIENT_ID", "parr-seam-probe")
    monkeypatch.setenv("CFACTORY_OIDC_CLIENT_SECRET", "irrelevant")
    monkeypatch.setenv("PARR_OIDC_TOKEN_URL", "https://issuer.invalid./token")
    assert pr._oidc_bearer("cfactory") == ""
    assert len(attempts) == 1, "a fully configured seam must actually try to mint"


def test_token_prefers_oidc_then_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """OIDC wins when available; the opaque token still serves the others.

    PFactory/AIFactory/TFactory are exposed directly and authenticate with the
    shared bearer, so the fallback is not legacy -- it is the live path for
    three of the four services.
    """
    _clear()
    monkeypatch.setattr(pr, "_oidc_bearer", lambda _svc: "jwt-from-oidc")
    monkeypatch.setenv("FACTORY_TOKEN", "opaque-token")
    assert pr._token("cfactory") == "jwt-from-oidc"

    monkeypatch.setattr(pr, "_oidc_bearer", lambda _svc: "")
    assert pr._token("pfactory") == "opaque-token"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
