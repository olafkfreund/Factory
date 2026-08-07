#!/usr/bin/env python3
"""Mutation table for the Fides change-gate preflight (Factory#541, #331).

The gate this guards was red for a fortnight on missing settings, which was the
correct behaviour. The defect underneath it was the next step: the original
``curl -sSfL "$FIDES_SERVER_URL/cli/install.sh" | sh`` runs under Actions'
``bash -e {0}``, which has no ``pipefail``. Against the Fides server actually
deployed in this cluster that path 404s -- curl exits 22, ``sh`` exits 0, and the
step reports success having installed nothing.

So the property under test is not only "a missing setting is red". It is also
"an install that installed nothing is red", because that is the one that would
have gone green the moment the three settings were supplied.

Each case holds everything else constant and removes exactly one thing.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "scripts" / "fides_gate_preflight.sh"

_SETTINGS = ("FIDES_SERVER_URL", "FIDES_API_TOKEN", "FLOW_ID")


def _fixture(tmp_path: Path) -> dict[str, str]:
    """A server root curl can fetch (file://) whose installer produces a CLI."""
    bindir = tmp_path / "bin"
    bindir.mkdir()

    cli = tmp_path / "cli"
    cli.mkdir()
    (cli / "install.sh").write_text(
        f"#!/bin/sh\nprintf '#!/bin/sh\\nexit 0\\n' > {bindir}/fides\n"
        f"chmod +x {bindir}/fides\n",
        encoding="utf-8",
    )

    return {
        "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
        "FIDES_SERVER_URL": tmp_path.as_uri(),
        "FIDES_API_TOKEN": "not-a-real-key",
        "FLOW_ID": "00000000-0000-0000-0000-000000000000",
    }


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [str(_SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        cwd=_REPO_ROOT,
    )


def test_preflight_passes_when_all_three_settings_are_present(tmp_path: Path) -> None:
    out = _run(_fixture(tmp_path))
    assert out.returncode == 0, out.stderr
    # The pass path cites what it compared, not just that it passed.
    assert "3/3 settings present" in out.stderr
    for setting in _SETTINGS:
        assert f"{setting:<18} set" in out.stderr


@pytest.mark.parametrize("dropped", _SETTINGS)
def test_preflight_fails_closed_when_one_setting_is_missing(
    tmp_path: Path, dropped: str
) -> None:
    env = _fixture(tmp_path)
    del env[dropped]
    out = _run(env)
    assert out.returncode == 1, out.stdout + out.stderr
    assert f"{dropped:<18} MISSING" in out.stderr
    assert dropped in out.stderr.splitlines()[-1]


@pytest.mark.parametrize("dropped", _SETTINGS)
def test_preflight_treats_empty_as_missing(tmp_path: Path, dropped: str) -> None:
    env = _fixture(tmp_path)
    env[dropped] = ""
    out = _run(env)
    assert out.returncode == 1, out.stdout + out.stderr
    assert f"{dropped:<18} MISSING" in out.stderr


def test_preflight_fails_when_the_server_does_not_serve_the_installer(
    tmp_path: Path,
) -> None:
    """The live defect: this is the case that used to exit 0 through a pipe."""
    env = _fixture(tmp_path)
    (tmp_path / "cli" / "install.sh").unlink()
    out = _run(env)
    assert out.returncode == 1, out.stdout + out.stderr
    assert "cannot fetch" in out.stderr


def test_preflight_fails_when_the_installer_produces_no_cli(tmp_path: Path) -> None:
    """An installer that exits 0 without installing anything is not a pass."""
    env = _fixture(tmp_path)
    (tmp_path / "cli" / "install.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    out = _run(env)
    assert out.returncode == 1, out.stdout + out.stderr
    assert "not on PATH" in out.stderr


def test_preflight_never_echoes_a_setting_value(tmp_path: Path) -> None:
    env = _fixture(tmp_path)
    env["FIDES_API_TOKEN"] = "fides_ci_SUPERSECRETVALUE"
    out = _run(env)
    assert "SUPERSECRETVALUE" not in out.stdout + out.stderr
