"""The flake must ship jest when a jest lane is implied (TFactory#1165).

The jest lane was the only unit-capable lane with no in-cluster path: its runner
built a DockerRunner, and TFactory pods have no container runtime -- which is why
every other lane runs as a k8s Job. So every JavaScript/TypeScript unit test
errored before it started. Spec 160 had all 10 unit verdicts at
stability=error while the tests themselves were correct and matched the
contracted API; lane_progress read "unit: error". It looked like flakiness; it
was total.

Giving the lane a Job is only half the fix -- the dev shell has to contain jest.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from nix_provisioner import generate_flake  # noqa: E402


def _flake(**env) -> str:
    env.setdefault("provisioning", {"method": "nix", "generated": True})
    return generate_flake(env)


def test_jest_is_added_when_implied() -> None:
    """One token buys the toolchain, exactly as `chromium` does for the browser
    lane: the manifest never names the attribute path."""
    f = _flake(system_packages=["jest"])

    assert "nodePackages.jest" in f
    assert "nodejs_22" in f


def test_a_jest_only_flake_does_not_drag_in_playwright() -> None:
    """The two node lanes are independent. A unit-test-only task should not pay
    for a browser stack it never uses."""
    f = _flake(system_packages=["jest"])

    assert "playwright-test" not in f


def test_node_is_declared_once_when_both_lanes_are_implied() -> None:
    """A duplicate package is a Nix EVAL ERROR, not a harmless repeat -- the
    whole flake fails and the lane reports a runner failure rather than a test
    result."""
    f = _flake(system_packages=["jest", "chromium"])

    assert f.count("nodejs_22") == 1
    assert "nodePackages.jest" in f
    assert "playwright-test" in f


def test_the_bare_jest_token_is_not_emitted_as_an_attr() -> None:
    """There is no top-level `pkgs.jest`; emitting one fails the flake eval."""
    f = _flake(system_packages=["jest"])

    assert "pkgs.jest\n" not in f
    assert "pkgs.jest " not in f


def test_a_flake_with_no_jest_is_unchanged() -> None:
    """The common case. Every other task must generate exactly as before."""
    f = _flake(language="python")

    assert "jest" not in f
    assert "nodejs" not in f
