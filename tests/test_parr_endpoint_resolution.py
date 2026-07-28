"""Seam-probe endpoint resolution must survive an EMPTY env var (Factory#416).

The bug this locks: a GitHub Actions step written as

    env:
      PFACTORY_API: ${{ vars.PFACTORY_API }}

sets the variable to the EMPTY STRING when the repo variable is unset -- it does
not leave it absent. ``os.environ.get(key, default)`` only falls back when the
key is MISSING, so the endpoint resolved to "", urllib was handed a bare
"/api/health", and every deploy died on ``ValueError: unknown url type``. The
caller's ``|| true`` swallowed it and the job reported green, so the seam gate
had never run a single probe.

The empty case is the one that matters and is the one nobody writes a test for,
because "unset" is naturally tested as *absent*.
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ is put on sys.path by tests/conftest.py.
import parr_regression as pr
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_empty_env_var_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Exactly what GitHub Actions passes for an unset repo variable.
    monkeypatch.setenv("PFACTORY_API", "")
    assert pr._endpoint("pfactory") == pr.DEFAULTS["pfactory"]


def test_absent_env_var_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PFACTORY_API", raising=False)
    assert pr._endpoint("pfactory") == pr.DEFAULTS["pfactory"]


def test_set_env_var_wins_and_trailing_slash_is_stripped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TFACTORY_API", "https://custom.example/")
    assert pr._endpoint("tfactory") == "https://custom.example"


def test_scheme_less_endpoint_fails_with_a_useful_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A host with no scheme fails the same way, from a different direction.

    urllib's own error ("unknown url type") names neither the variable nor the
    service, three frames from the cause.
    """
    monkeypatch.setenv("AIFACTORY_API", "localhost:8000")
    with pytest.raises(ValueError, match="AIFACTORY_API"):
        pr._endpoint("aifactory")


def test_every_default_is_an_absolute_url() -> None:
    # A default that is not absolute would reintroduce the crash for whichever
    # service it belonged to, and only on the deploy that touched it.
    for svc, url in pr.DEFAULTS.items():
        assert url.startswith("https://"), f"{svc} default is not absolute: {url}"


def test_no_caller_swallows_the_exit_code() -> None:
    """`|| true` in a service workflow makes this probe unable to fail.

    The Python fix alone is not enough: the harness can exit 1 correctly and
    still be reported as success if the caller discards it. Guarding the hub
    copy here; the service workflows are fixed in their own repos.
    """
    offenders = []
    for wf in sorted((_REPO_ROOT / ".github" / "workflows").glob("*.yml")):
        text = wf.read_text()
        for line in text.splitlines():
            if "parr_regression.py" in line and "|| true" in line:
                offenders.append(wf.name)
    assert not offenders, f"parr_regression.py exit code discarded in: {offenders}"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
