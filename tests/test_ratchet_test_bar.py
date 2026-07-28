#!/usr/bin/env python3
"""The ratchet applies the test bar to tests, and only to tests (Factory#403).

Two rules are locked here:

1. Test files are not held to the production untyped-def bar. A brand-new test
   file has a base count of 0, so *any* violation blocks it — which trained
   people to sprinkle `type: ignore` on rules the config says do not apply to
   tests, the exact "suppress the guard" failure mode this repo warns about.

2. Production code is NOT relaxed. That is the assertion with teeth: the naive
   fix (relax unconditionally) makes every test here pass except this one, and
   would quietly collapse the type bar fleet-wide.

The carve-out lives in the ratchet rather than standards/mypy.ini because mypy
per-module sections need dotted package paths — a bare `[mypy-test_*]`, and even
`[mypy-*]`, silently fails to match a top-level test module. Measured: the error
count was unchanged, and mypy reports nothing unless `warn_unused_configs`
happens to flag the section.
"""

from __future__ import annotations

import pytest
import ratchet_helpers as rh

# scripts/ is put on sys.path by tests/conftest.py.
import ratchet_lint as rl

_UNTYPED = "def helper(a):\n    return a\n"


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_thing.py",
        "apps/web-server/tests/test_thing.py",
        "tests/helpers.py",
        "thing_test.py",
    ],
)
def test_test_paths_are_recognised(path: str) -> None:
    assert rl.is_test_file(path) is True


@pytest.mark.parametrize(
    "path",
    ["apps/backend/thing.py", "scripts/ratchet_lint.py", "server/auth.py"],
)
def test_production_paths_are_not_test_files(path: str) -> None:
    assert rl.is_test_file(path) is False


def test_test_files_get_the_relaxing_flags() -> None:
    cmd = rl.mypy_command("workdir/test_thing.py", "tests/test_thing.py")
    assert "--allow-untyped-defs" in cmd
    assert "--allow-incomplete-defs" in cmd


def test_production_files_do_not() -> None:
    # THE ASSERTION WITH TEETH. Relaxing unconditionally would pass every other
    # test in this file and collapse the type bar for the whole fleet.
    cmd = rl.mypy_command("workdir/thing.py", "apps/backend/thing.py")
    assert "--allow-untyped-defs" not in cmd
    assert "--allow-incomplete-defs" not in cmd


def test_same_source_is_judged_by_path_not_content() -> None:
    """Identical source, two paths, two verdicts — proves the scoping is real."""
    as_test = rl.mypy_count(_UNTYPED, "tests/test_thing.py", "scripts")
    as_prod = rl.mypy_count(_UNTYPED, "apps/backend/thing.py", "scripts")
    assert as_test == 0, "a test file must not trip the untyped-def bar"
    assert as_prod > 0, "production code must still be held to it"


def test_the_rules_live_in_the_canonical_module() -> None:
    """The ratchet must CONSUME the shared rules, not carry its own copy.

    Factory#403: five forks each reimplemented these. Within an hour of writing
    the same helper into all five, the hub copy and the fork copies already
    differed (a docstring), which is exactly how drift starts. ratchet_lint must
    therefore re-export the canonical objects, not define look-alikes.
    """
    assert rl.is_test_file is rh.is_test_file
    assert rl.write_temp is rh.write_temp
    assert rl.MYPY_TEST_RELAX is rh.MYPY_TEST_RELAX
