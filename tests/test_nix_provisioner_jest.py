"""The flake must ship jest when a jest lane is implied (TFactory#1165).

The jest lane was the only unit-capable lane with no in-cluster path: its runner
built a DockerRunner, and TFactory pods have no container runtime -- which is why
every other lane runs as a k8s Job. So every JavaScript/TypeScript unit test
errored before it started. Spec 160 had all 10 unit verdicts at
stability=error while the tests themselves were correct and matched the
contracted API; lane_progress read "unit: error". It looked like flakiness; it
was total.

Giving the lane a Job is only half the fix -- the shell has to be able to RUN
jest. It does not get jest from nixpkgs: the `nodePackages` set was removed on
2026-03-03 and the attribute now throws, so emitting it failed the whole flake
eval rather than just omitting a package. These tests previously asserted
`nodePackages.jest` was present, which pinned exactly that broken output and
stayed green while every jest flake failed to evaluate.

What the flake owes the lane is node. The runner is installed from npm at lane
setup (nix_env.py), which is why there is no jest attribute to assert here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from nix_provisioner import generate_flake


def _flake(**env: object) -> str:
    env.setdefault("provisioning", {"method": "nix", "generated": True})
    flake: str = generate_flake(env)
    return flake


def test_jest_is_added_when_implied() -> None:
    """One token buys the toolchain, exactly as `chromium` does for the browser
    lane: the manifest never names the attribute path."""
    f = _flake(system_packages=["jest"])

    assert "nodejs_22" in f
    # The removed set must never come back. It does not fail loudly -- the
    # attribute throws at eval time, so the symptom is a dead shell, not a
    # missing binary.
    assert "nodePackages" not in f


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
    assert "nodePackages" not in f
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


# ── harness-provided tokens (Factory#1007 follow-up) ────────────────────────
#
# `pytest`, `pip` and `python` are trigger tokens exactly as `jest` is: the
# Python harness supplies all three through `withPackages`, and none is a
# top-level nixpkgs attr. `pkgs.pytest` does not exist -- nixpkgs answers
# "Did you mean btest, cpptest, evtest" -- so emitting it failed the WHOLE
# flake eval rather than omitting one package.
#
# A manifest naming `pytest` in system_packages is the most obvious thing a
# planner writes for a Python lane, which is what made this expensive.


def test_harness_provided_tokens_are_not_emitted_as_attrs() -> None:
    # Matched on a WORD BOUNDARY, not as a substring: the flake legitimately
    # contains `pkgs.python313.withPackages`, and a plain `"pkgs.python" in f`
    # matches that too -- reporting a failure the code does not have.
    for token in ("pytest", "pip", "python"):
        f = _flake(system_packages=[token])
        assert not re.search(rf"pkgs\.{token}\b(?!\d)", f), (
            f"pkgs.{token} is not a nixpkgs attr; emitting it fails the flake eval"
        )


def test_pytest_still_reaches_the_shell_through_withpackages() -> None:
    """Dropping the attr must not drop the tool: the harness still provides it."""
    f = _flake(system_packages=["pytest"], language="python")

    assert 'p."pytest"' in f


# ── aliased toolchain tokens (Factory#1009) ─────────────────────────────────
#
# Six more tokens a planner plausibly writes generated flakes that could not
# evaluate: `node`, `npm`, `vitest`, `selenium`, `rust`, `dotnet`. None is a
# top-level nixpkgs attr, and a missing attr fails the WHOLE devShell, so the
# lane reported a runner failure rather than a test result.
#
# Unlike the harness-provided tokens above, most of these name a REAL toolchain
# under a different attr, so a bare drop would silently take the toolchain away.
# They are aliased instead. Verified by forcing the derivation on each generated
# flake (`nix eval ... .drvPath`) against nixpkgs 567a49d1 -- all six failed
# before, all six evaluate after. `nix eval` of the shell's NAME is not enough:
# the package list is lazy, so it passes on a flake that cannot build.


def test_aliased_tokens_never_reach_the_flake_as_bare_attrs() -> None:
    # Word boundary again, for the same reason as the harness tokens: a plain
    # substring check for "pkgs.node" matches the legitimate `pkgs.nodejs_22`.
    for token in ("node", "npm", "vitest", "selenium", "rust", "dotnet"):
        f = _flake(system_packages=[token])
        assert not re.search(rf"pkgs\.{token}\b(?![\w-])", f), (
            f"pkgs.{token} is not a nixpkgs attr; emitting it fails the flake eval"
        )


def test_node_tokens_still_buy_the_node_toolchain() -> None:
    """Aliasing must not lose the tool. node/npm/vitest all mean nodejs_22 --
    npm ships inside the nodejs derivation, and vitest comes from npm at lane
    setup exactly as jest does."""
    for token in ("node", "npm", "vitest"):
        assert "pkgs.nodejs_22" in _flake(system_packages=[token]), token


def test_rust_and_dotnet_map_to_the_attrs_that_exist() -> None:
    assert "pkgs.rustc" in _flake(system_packages=["rust"])
    assert "pkgs.dotnet-sdk" in _flake(system_packages=["dotnet"])
    # cargo is already a valid top-level attr and must pass through untouched.
    assert "pkgs.cargo" in _flake(system_packages=["cargo"])


def test_selenium_is_dropped_rather_than_guessed() -> None:
    """Selenium bindings exist for Python AND node; the manifest's `language`
    already decides which harness runs, so inferring a toolchain here would be
    wrong half the time. Drop it and let the lane's package manager install it."""
    f = _flake(system_packages=["selenium"], language="python")

    assert "selenium" not in f
    assert "nodejs" not in f


def test_colliding_aliases_are_emitted_once() -> None:
    """`node` + `npm` is the likeliest pair a planner writes, and both alias to
    nodejs_22. A doubled line still evaluates, but the flake is a committed
    deliverable and reads as a bug."""
    assert _flake(system_packages=["node", "npm"]).count("pkgs.nodejs_22") == 1
    # ...and against the blocks that add node themselves.
    assert _flake(system_packages=["vitest", "playwright"]).count("pkgs.nodejs_22") == 1
    assert _flake(system_packages=["node", "jest"]).count("pkgs.nodejs_22") == 1


def test_alias_matching_is_case_insensitive() -> None:
    """Same convention as the drop set, which has always lower-cased. A planner
    writing `Node` or `DotNet` is not writing a different package, and a
    case-sensitive lookup would pass the token straight through as a bare attr
    -- the exact failure this table exists to stop."""
    assert "pkgs.nodejs_22" in _flake(system_packages=["Node"])
    assert not re.search(r"pkgs\.Node\b", _flake(system_packages=["Node"]))
    assert "pkgs.dotnet-sdk" in _flake(system_packages=["DotNet"])
