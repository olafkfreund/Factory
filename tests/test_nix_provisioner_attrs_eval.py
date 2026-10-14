"""Every attr the provisioner's tables can emit exists at the pinned nixpkgs (#1020).

The tables' comments say each entry was "measured against the pin", but that
measurement lived in prose: unit tests assert on the flake's TEXT, and a missing
attr fails the WHOLE devShell eval. This forces each attr's ``drvPath`` -- the
name alone passes on a lazy package list -- in one ``nix eval`` against
``DEFAULT_NIXPKGS``.

Hub CI has no Nix, so the test skips there, and the skip says so: an absent Nix
means these attrs were NOT verified, not that they are fine.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import nix_provisioner as np  # noqa: E402

# Attrs generate_flake adds itself, outside the tables.
_FIXED_ATTRS = {"nodejs_22", "playwright-test", "dejavu_fonts", "uv", "go", "python313"}


def _reachable_attrs() -> set[str]:
    attrs = set(_FIXED_ATTRS)
    for value in np._LANG_ATTRS.values():
        attrs.update(value)
    for alias in np._SYSTEM_PKG_ALIASES.values():
        attrs.update([alias] if isinstance(alias, str) else alias)
    attrs.update(np._PY_ATTR.values())
    attrs.update(np._GO_ATTR.values())
    return attrs


def test_reachable_attrs_cover_every_table() -> None:
    attrs = _reachable_attrs()
    assert {"rustc", "cargo", "python313", "go_1_25", "dotnet-sdk"} <= attrs


@pytest.mark.skipif(
    shutil.which("nix") is None,
    reason="nix not on PATH: provisioner attrs NOT verified against the pin",
)
def test_every_reachable_attr_evaluates_at_the_pin() -> None:
    names = sorted(_reachable_attrs())
    expr = (
        f'let pkgs = (builtins.getFlake "{np.DEFAULT_NIXPKGS}").legacyPackages.x86_64-linux; '
        "in builtins.filter (a: !(builtins.hasAttr a pkgs "
        "&& (builtins.tryEval pkgs.${a}.drvPath).success)) "
        f"(builtins.fromJSON {json.dumps(json.dumps(names))})"
    )
    out = subprocess.run(  # noqa: S603 - fixed argv, expr built from repo tables
        [  # noqa: S607
            "nix",
            "--extra-experimental-features",
            "nix-command flakes",
            "eval",
            "--json",
            "--expr",
            expr,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    missing = json.loads(out.stdout)
    assert missing == [], f"attrs absent or failing at {np.DEFAULT_NIXPKGS}: {missing}"
