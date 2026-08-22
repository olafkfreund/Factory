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

The download tests serve the tarball from a LOOPBACK HTTP SERVER built by a
fixture (Factory#928). They used to fetch the real GitHub release on every hub
PR, which made them flaky *and* false: a 504 from the release host produced the
same exit status (2) as a rejected digest, so the only thing separating "the
supply-chain check refused a bad artefact" from "the artefact never arrived"
was a substring of stderr. Served locally, a checksum mismatch is the only way
to reach the mismatch branch, and the script now gives the two failures
DISTINCT exit statuses (3 download, 4 digest) which these tests assert in both
directions.
"""

from __future__ import annotations

import functools
import hashlib
import http.server
import io
import os
import shutil
import subprocess
import tarfile
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "fides_gate_preflight.sh"

_SETTINGS = ("FIDES_SERVER_URL", "FIDES_API_TOKEN", "FIDES_FLOW_ID")

# The script's documented statuses. 3 and 4 exist so that "the tarball never
# arrived" and "the tarball arrived and was rejected" are distinguishable on the
# status channel rather than by reading prose out of stderr (Factory#928).
_EXIT_OK = 0
_EXIT_SETTING_MISSING = 1
_EXIT_INSTALL_FAILED = 2
_EXIT_DOWNLOAD_FAILED = 3
_EXIT_DIGEST_MISMATCH = 4

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
    # A proxy configured for the machine would swallow the loopback fetch and
    # turn every local-release test into a transport error -- i.e. back into the
    # failure mode this file exists to stop conflating with a digest rejection.
    for proxy_var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        env.pop(proxy_var, None)
    env["NO_PROXY"] = env["no_proxy"] = "*"
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
    assert proc.returncode == _EXIT_SETTING_MISSING
    # Both ways, for the same reason as the download statuses below: "I could
    # not reach my input" must not be readable as "I ran and the install
    # failed". A caller that retries install failures would retry forever on a
    # missing secret.
    assert proc.returncode not in (_EXIT_OK, _EXIT_INSTALL_FAILED)
    assert f"MISSING: {missing}" in proc.stderr


@pytest.mark.parametrize("empty", _SETTINGS)
def test_an_empty_setting_is_missing_not_present(empty: str, tmp_path: Path) -> None:
    """Set-but-empty is the interesting case.

    ``[ -z "${!var:-}" ]`` catches both; a ``[ -v ]`` style check would call an
    empty token "present" and let the gate run against a blank credential, then
    report whatever the server says to an unauthenticated request.
    """
    proc = _run(_all_present(**{empty: ""}), tmp_path)
    assert proc.returncode == _EXIT_SETTING_MISSING
    assert proc.returncode not in (_EXIT_OK, _EXIT_INSTALL_FAILED)
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


@dataclass(frozen=True)
class _LocalRelease:
    """A release tarball this test process built, served from loopback."""

    base_url: str
    version: str
    sha256: str
    root: Path


def _build_tarball(dest: Path, version: str, *, include_cli: bool = True) -> str:
    """Write a tarball shaped like the real release and return its sha256.

    The script unpacks into a versioned directory and takes the single
    user-executable file named ``fides``, so the fixture has to reproduce that
    shape or the success path would fail for the wrong reason.

    ``include_cli=False`` builds a tarball that downloads cleanly and matches
    its digest but carries no CLI -- the one way to reach the post-verification
    install failure.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest, "w:gz") as tar:
        if include_cli:
            payload = b"#!/bin/sh\necho fides " + version.encode() + b"\n"
            info = tarfile.TarInfo(f"fides_{version}_linux_amd64/fides")
            info.size = len(payload)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(payload))
        readme = tarfile.TarInfo(f"fides_{version}_linux_amd64/README.md")
        readme.size = 0
        readme.mode = 0o644
        tar.addfile(readme, io.BytesIO(b""))
    return hashlib.sha256(dest.read_bytes()).hexdigest()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence the per-request line; pytest output is not a web log."""


@pytest.fixture
def local_release(tmp_path: Path) -> Iterator[_LocalRelease]:
    """Serve a self-built release over loopback HTTP.

    Real HTTP, not ``file://``: the script relies on curl's ``-f`` turning an
    HTTP error into a non-zero status, and only a real server exercises that.
    """
    version = "v9.9.9-local"
    root = tmp_path / "release-root"
    tarball = root / version / f"fides_{version}_linux_amd64.tar.gz"
    digest = _build_tarball(tarball, version)

    handler = functools.partial(_QuietHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # server_address is typed loosely enough that mypy --strict will not let
        # it be interpolated; for an AF_INET server it is (host, port).
        host, port = cast("tuple[str, int]", server.server_address)
        yield _LocalRelease(
            base_url=f"http://{host}:{port}",
            version=version,
            sha256=digest,
            root=root,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _release_env(release: _LocalRelease, **overrides: str) -> dict[str, str | None]:
    env = _all_present()
    env.update(
        {
            "FIDES_CLI_BASE_URL": release.base_url,
            "FIDES_CLI_VERSION": release.version,
            "FIDES_CLI_SHA256": release.sha256,
        }
    )
    env.update(overrides)
    return env


@pytest.mark.skipif(shutil.which("curl") is None, reason="needs curl")
def test_a_locally_served_release_installs_and_is_runnable(
    local_release: _LocalRelease, tmp_path: Path
) -> None:
    """The other direction (rule 4.9), now without touching the network.

    Every failure test below would pass against a script that installs nothing;
    this is the one that says the happy path still works. It also proves the
    loopback fixture actually serves a fetchable, digest-matching tarball, so a
    non-zero status in the tests below is about the script, not the harness.
    """
    proc = _run(_release_env(local_release), tmp_path)
    assert proc.returncode == _EXIT_OK, proc.stderr
    installed = tmp_path / "bin" / "fides"
    assert installed.exists()
    assert os.access(installed, os.X_OK)


@pytest.mark.skipif(shutil.which("curl") is None, reason="needs curl")
def test_a_download_that_404s_is_an_error_not_a_silent_pass(
    local_release: _LocalRelease, tmp_path: Path
) -> None:
    """THE defect this script exists for.

    Piped into `sh`, a 404 left the step green with nothing installed. Fetched
    to a file, the HTTP error is the script's exit status -- and it is the
    DOWNLOAD status, distinct from the digest one, so a transport failure can
    never be mistaken for evidence that the digest check ran.
    """
    proc = _run(
        _release_env(local_release, FIDES_CLI_VERSION="v0.0.0-does-not-exist"),
        tmp_path,
    )
    assert proc.returncode == _EXIT_DOWNLOAD_FAILED
    assert proc.returncode != _EXIT_DIGEST_MISMATCH
    assert "could not download" in proc.stderr
    assert "checksum mismatch" not in proc.stderr
    assert not (tmp_path / "bin" / "fides").exists()


@pytest.mark.skipif(shutil.which("curl") is None, reason="needs curl")
def test_a_digest_mismatch_refuses_to_install(local_release: _LocalRelease, tmp_path: Path) -> None:
    """The digest is pinned in the script, NOT read from the .sha256 published
    beside the tarball. A checksum served from the same place as the artefact
    proves transfer integrity, not provenance -- it moves with the artefact.

    The tarball here is served from loopback and downloads successfully, so the
    ONLY way to reach exit 4 is for the digest comparison to have run and
    rejected it. That is what Factory#928 was about: this assertion used to be
    satisfiable by a 504 from the release host.
    """
    proc = _run(_release_env(local_release, FIDES_CLI_SHA256="00" * 32), tmp_path)
    assert proc.returncode == _EXIT_DIGEST_MISMATCH
    assert proc.returncode != _EXIT_DOWNLOAD_FAILED
    assert "checksum mismatch" in proc.stderr
    assert "could not download" not in proc.stderr
    assert not (tmp_path / "bin" / "fides").exists()


@pytest.mark.skipif(shutil.which("curl") is None, reason="needs curl")
def test_an_archive_without_the_cli_is_an_install_failure_not_a_success(
    local_release: _LocalRelease, tmp_path: Path
) -> None:
    """A verified download is not an install.

    This tarball downloads cleanly AND matches its pinned digest -- the two
    supply-chain checks both pass -- and still leaves nothing runnable. That is
    the shape the whole script exists for (Factory#642: the status channel
    reported on the process, not on the artefact), and it is the only state
    behind exit 2, so it must not be reported as either download status.
    """
    version = "v9.9.9-no-cli"
    tarball = local_release.root / version / f"fides_{version}_linux_amd64.tar.gz"
    digest = _build_tarball(tarball, version, include_cli=False)

    proc = _run(
        _release_env(local_release, FIDES_CLI_VERSION=version, FIDES_CLI_SHA256=digest),
        tmp_path,
    )
    assert proc.returncode == _EXIT_INSTALL_FAILED
    # Both ways: an install that failed AFTER the digest verified must not be
    # readable as the digest having been rejected, nor as the tarball never
    # arriving. Both of those would send someone to re-cut a release that is
    # fine.
    assert proc.returncode not in (_EXIT_OK, _EXIT_DOWNLOAD_FAILED, _EXIT_DIGEST_MISMATCH)
    assert "contained no 'fides' executable" in proc.stderr
    assert "checksum mismatch" not in proc.stderr
    assert "could not download" not in proc.stderr
    assert not (tmp_path / "bin" / "fides").exists()


def test_an_unknown_argument_is_rejected_rather_than_ignored() -> None:
    """The other exit-2 site. An unrecognised flag must not be silently dropped:
    a `--bindir` typo that installs to the default while the caller believes
    otherwise is how a green step leaves nothing where it is looked for."""
    proc = subprocess.run(  # noqa: S603
        ["bash", str(_SCRIPT), "--no-such-flag"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == _EXIT_INSTALL_FAILED
    assert proc.returncode not in (_EXIT_OK, _EXIT_SETTING_MISSING)
    assert "unknown arg: --no-such-flag" in proc.stderr


def test_the_two_download_failures_have_distinct_documented_statuses() -> None:
    """A gate whose failure modes share an exit status can only be told apart by
    prose, and prose is not a status channel (Factory#928, Factory#832)."""
    assert _EXIT_DOWNLOAD_FAILED != _EXIT_DIGEST_MISMATCH
    text = _SCRIPT.read_text()
    assert f"#        {_EXIT_DOWNLOAD_FAILED} the download did not complete" in text
    assert f"#        {_EXIT_DIGEST_MISMATCH} the download completed and its digest did NOT" in text


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
    """The REAL release, opt-in.

    The local-release test above carries the rule 4.9 duty on every PR; this one
    is the periodic check that the pinned digest still matches what GitHub
    serves. It is the only test in this file that touches the network, and it
    does not run unless asked."""
    proc = _run(_all_present(), tmp_path)
    assert proc.returncode == 0, proc.stderr
    installed = tmp_path / "bin" / "fides"
    assert installed.exists()
    assert os.access(installed, os.X_OK)
