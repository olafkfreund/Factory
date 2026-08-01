#!/usr/bin/env python3
"""The ratchet applies the test bar to tests, and only to tests (Factory#403).

Three rules are locked here:

1. Test files are not held to the production untyped-def bar. A brand-new test
   file has a base count of 0, so *any* violation blocks it — which trained
   people to sprinkle `type: ignore` on rules the config says do not apply to
   tests, the exact "suppress the guard" failure mode this repo warns about.

2. Production code is NOT relaxed. That is the assertion with teeth: the naive
   fix (relax unconditionally) makes every test here pass except this one, and
   would quietly collapse the type bar fleet-wide.

3. RUFF agrees with mypy about which files those are, for all three carve-out
   shapes — including ``**/tests/**``, which the ratchet could not match at all
   while it linted a temp copy (Factory#510).

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
_ASSERTION = "assert 1 == 2\n"


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


def test_ruff_exempts_every_shape_of_test_path() -> None:
    """All THREE carve-outs must be live under the ratchet, not just two.

    Factory#510: the ratchet checked a temp COPY, and ruff relativises a path
    against the project root before matching per-file-ignores — so a path
    outside it matched BASENAME globs only. ``**/test_*.py`` and ``**/*_test.py``
    worked; ``**/tests/**`` was dead. A helper under tests/ named neither way was
    therefore held to the production assert bar by the ratchet while
    ``ruff check`` on the real tree exempted it: two tools disagreeing about what
    a test is, the mismatch is_test_file was extracted to prevent.

    Note the shape of the assertion. Mirroring the directories inside the temp
    dir (``<tmpdir>/tests/helpers.py``) does NOT make this pass — measured — so
    this is not a test of "did we nest the temp file", it is a test of the
    verdict.
    """
    named = rl.ruff_counts(_ASSERTION, "tests/test_x.py")
    helper = rl.ruff_counts(_ASSERTION, "tests/helpers.py")
    assert "S101" not in helper, "a helper under tests/ must get the test assert carve-out"
    assert helper == named, "two files under tests/ must not get two different verdicts"


def test_ruff_still_holds_production_to_the_assert_bar() -> None:
    # THE ASSERTION WITH TEETH, ruff side. Exempting unconditionally (or losing
    # the path in a way that made everything look like a test) passes the test
    # above and silently drops S101 for the whole fleet.
    assert "S101" in rl.ruff_counts(_ASSERTION, "scripts/prod.py")


def test_the_rules_live_in_the_canonical_module() -> None:
    """The ratchet must CONSUME the shared rules, not carry its own copy.

    Factory#403: five forks each reimplemented these. Within an hour of writing
    the same helper into all five, the hub copy and the fork copies already
    differed (a docstring), which is exactly how drift starts. ratchet_lint must
    therefore re-export the canonical objects, not define look-alikes.

    Looked up by NAME rather than as four attribute asserts because mypy strict
    reports every `rl.<name>` here as an implicit re-export (`attr-defined`) -
    four grandfathered errors that would have become five with ruff_stdin_argv.
    A missing name still fails: getattr raises.
    """
    for name in ("is_test_file", "write_temp", "ruff_stdin_argv", "MYPY_TEST_RELAX"):
        assert getattr(rl, name) is getattr(rh, name), f"{name} is not the canonical object"
