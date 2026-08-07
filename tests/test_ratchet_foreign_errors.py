#!/usr/bin/env python3
"""The ratchet counts errors mypy blamed on THIS file, not on some other one.

Factory#601 (and CFactory#319, the identical fork). ``mypy_count`` matched every
``path:line: error:`` line in mypy's output and counted it, while the regex did
not even capture the path -- so nothing could have compared it. PFactory,
TFactory and AIFactory all compare; the hub did not.

WHY THAT IS REACHABLE, given ``--follow-imports=silent``. Silent covers ordinary
errors in imported modules. It does not cover a BLOCKING one: an import that
fails to parse prints its own error line and mypy stops there, before the target
is type-checked at all. The hub then attributed that foreign line to the file
under test -- a clean file came back as 1 -- and, worse, base and HEAD can blame
a different set of foreign files, so the comparison could report a regression
that is not one or hide one that is.

These run REAL mypy against a real broken import, because the defect only exists
in the shape of mypy's actual output. The two assertions with teeth point the
other way: a file's own errors, blocking or not, must still be counted, which is
what a path comparison that is merely too strict would silently destroy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# scripts/ is put on sys.path by tests/conftest.py.
import ratchet_lint as rl

_CLEAN_BUT_IMPORTS_BROKEN = "from broken_dep import oops\n\n\ndef go() -> None:\n    oops()\n"


def test_a_foreign_files_blocking_error_is_not_counted_as_this_files(
    tmp_path: Path,
) -> None:
    """The case from the issue: the target is clean, its import will not parse."""
    (tmp_path / "broken_dep.py").write_text("def oops(:\n    pass\n")

    # Pre-fix this returned 1, silently, for a file with nothing wrong with it.
    # mypy never reached the target, so the honest verdict is "could not
    # measure" (exit 2) -- not 1, and not a fabricated 0 either.
    with pytest.raises(SystemExit) as exc:
        rl.mypy_count(_CLEAN_BUT_IMPORTS_BROKEN, "scripts/thing.py", str(tmp_path))
    assert exc.value.code == 2


def test_the_files_own_errors_are_still_counted(tmp_path: Path) -> None:
    """Teeth the other way: a path comparison that never matches counts nothing."""
    source = 'def go() -> int:\n    return "not an int"\n'
    assert rl.mypy_count(source, "scripts/thing.py", str(tmp_path)) == 1


def test_a_blocking_error_in_the_file_under_test_is_still_counted(
    tmp_path: Path,
) -> None:
    """mypy exits 2 here too, but the error IS this file's, so it is a regression."""
    assert rl.mypy_count("def go(:\n    pass\n", "scripts/thing.py", str(tmp_path)) == 1


def test_the_same_content_counts_the_same_twice(tmp_path: Path) -> None:
    """The count may not depend on whether mypy's cache happens to be warm.

    This is what makes the path comparison above safe to rely on. On a cache HIT
    mypy replays the stored diagnostics under the path the module was FIRST seen
    at, and every call gets a fresh temp dir -- so the second run of identical
    content is blamed on a directory that no longer exists, both sides of the
    base-vs-head comparison read zero, and the gate passes having measured
    nothing. ``--no-incremental`` in ``mypy_command`` is the fix; delete it and
    the second assertion here reads 0.
    """
    source = 'def go() -> int:\n    return "not an int"\n'
    first = rl.mypy_count(source, "scripts/twice.py", str(tmp_path))
    second = rl.mypy_count(source, "scripts/twice.py", str(tmp_path))
    assert (first, second) == (1, 1)
