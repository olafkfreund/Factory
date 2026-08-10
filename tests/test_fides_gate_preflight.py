#!/usr/bin/env python3
"""Tests for the Fides change-gate preflight (Factory#541).

The step this replaces was::

    curl -sSfL "$FIDES_SERVER_URL/cli/install.sh" | sh

GitHub Actions runs ``run:`` under ``bash -e {0}`` with no ``pipefail``, so
curl's failure is discarded and only ``sh``'s status survives -- and ``sh``
reading empty stdin exits 0. The server does not serve that path (404, measured
against the live host), so the step reported success having installed nothing.

Every test here is the mutation of one guard: remove the guard and the test
fails. Tests that would pass against a preflight which checks nothing are worse
than no tests, because they certify the certifier.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "fides_gate_preflight.sh"

_SETTINGS = ("FIDES_SERVER_URL", "FIDES_API_TOKEN", "FIDES_FLOW_ID")

# The real v0.4.0 linux_amd64 digest, pinned in the script. Duplicated here on
# purpose: if someone changes the pin, this test fails and they must say so.
_PINNED_SHA = "db2bca7fb10553cd9b526089db65d1bd3f19bf08680d6fdcd99d9c2b12a89d6a"


def _run(
    env_overrides: dict[str, str | None],
    tmp_path: Path,
    *,
    bindir: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in _SETTINGS}
    # Strip any real CLI from PATH: if `fides` is already installed on the
    # machine running the tests, the script short-circuits and every install
    # assertion below would pass without exercising the install at all.
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if not (Path(p) / "fides").exists()
    )
    for key, value in env_overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return subprocess.run(  # noqa: S603
        ["bash", str(_SCRIPT), "--bindir", bindir or str(tmp_path / "bin")],  # noqa: S607
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _all_present(**overrides: str) -> dict[str, str | None]:
    base: dict[str, str | None] = {
        "FIDES_SERVER_URL": "https://fides.example.invalid",
        "FIDES_API_TOKEN": "dummy-token-value",
        "FIDES_FLOW_ID": "00000000-0000-0000-0000-000000000000",
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize("missing", _SETTINGS)
def test_each_missing_setting_fails_closed(missing: str, tmp_path: Path) -> None:
    proc = _run(_all_present(**{missing: None}), tmp_path)  # type: ignore[arg-type]
    assert proc.returncode == 1
    assert f"MISSING: {missing}" in proc.stderr


@pytest.mark.parametrize("empty", _SETTINGS)
def test_an_empty_setting_is_missing_not_present(empty: str, tmp_path: Path) -> None:
    """Set-but-empty is the interesting case.

    ``[ -z "${!var:-}" ]`` catches both; a ``[ -v ]`` style check would call an
    empty token "present" and let the gate run against a blank credential, then
    report whatever the server says to an unauthenticated request.
    """
    proc = _run(_all_present(**{empty: ""}), tmp_path)
    assert proc.returncode == 1
    assert f"MISSING: {empty}" in proc.stderr


def test_the_pass_path_enumerates_every_setting(tmp_path: Path) -> None:
    """A check that lists what it verified only when it fails cannot be audited
    when it passes."""
    proc = _run(_all_present(), tmp_path)
    for var in _SETTINGS:
        assert f"present: {var}" in proc.stdout


def test_no_setting_value_ever_reaches_the_output(tmp_path: Path) -> None:
    # Named "canary" rather than "secret": ruff S105 flags the latter as a
    # hardcoded password, and silencing a real lint with a noqa to keep a nicer
    # variable name is a bad trade.
    canary = "c4n4ry-must-not-appear"
    proc = _run(_all_present(FIDES_API_TOKEN=canary), tmp_path)
    assert canary not in proc.stdout
    assert canary not in proc.stderr


@pytest.mark.skipif(shutil.which("curl") is None, reason="needs curl")
def test_a_download_that_404s_is_an_error_not_a_silent_pass(tmp_path: Path) -> None:
    """THE defect this script exists for.

    Piped into `sh`, a 404 left the step green with nothing installed. Fetched
    to a file, the HTTP error is the script's exit status.
    """
    proc = _run(_all_present() | {"FIDES_CLI_VERSION": "v0.0.0-does-not-exist"}, tmp_path)
    assert proc.returncode == 2
    assert "could not download" in proc.stderr
    assert not (tmp_path / "bin" / "fides").exists()


@pytest.mark.skipif(shutil.which("curl") is None, reason="needs curl")
def test_a_digest_mismatch_refuses_to_install(tmp_path: Path) -> None:
    """The digest is pinned in the script, NOT read from the .sha256 published
    beside the tarball. A checksum served from the same place as the artefact
    proves transfer integrity, not provenance -- it moves with the artefact."""
    proc = _run(_all_present() | {"FIDES_CLI_SHA256": "00" * 32}, tmp_path)
    assert proc.returncode == 2
    assert "checksum mismatch" in proc.stderr
    assert not (tmp_path / "bin" / "fides").exists()


def test_the_pinned_digest_is_the_one_the_script_uses() -> None:
    """Guards the pin itself. Bumping the version without re-verifying the
    digest is how a supply-chain check becomes decorative."""
    text = _SCRIPT.read_text()
    assert _PINNED_SHA in text
    assert "FIDES_CLI_VERSION:-v0.4.0" in text


def test_the_installer_is_never_piped_into_a_shell() -> None:
    """The regression guard for the original shape.

    `curl ... | sh` under `bash -e` without pipefail discards curl's status.
    Nothing in this script may reintroduce it.
    """
    # Comments only, stripped: the header QUOTES the bad pattern in order to
    # explain it, so a whole-file match would flag the documentation rather than
    # the code. Match executable lines.
    code = "\n".join(
        line for line in _SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#")
    )
    assert "| sh" not in code.replace("| sha256sum", "")
    assert "curl" in code
    assert "-o " in code


@pytest.mark.skipif(shutil.which("curl") is None, reason="needs curl")
@pytest.mark.skipif(
    os.environ.get("FIDES_PREFLIGHT_NETWORK_TEST") != "1",
    reason="hits github.com; set FIDES_PREFLIGHT_NETWORK_TEST=1 to run",
)
def test_the_real_release_installs_and_is_runnable(tmp_path: Path) -> None:
    """The other direction (rule 4.9): the failure tests above would all pass
    against a script that never installs anything."""
    proc = _run(_all_present(), tmp_path)
    assert proc.returncode == 0, proc.stderr
    installed = tmp_path / "bin" / "fides"
    assert installed.exists()
    assert os.access(installed, os.X_OK)
