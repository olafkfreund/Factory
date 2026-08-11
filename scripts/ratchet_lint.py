#!/usr/bin/env python3
"""Diff-scoped lint ratchet for the Factory hub Python (scripts/, tests/).

Implements the Factory coding-standards ratchet (coding-standards.md sections 0
and 4.6): the strict bar (`ruff` with the shared select set + `mypy --strict`)
is enforced on the files a PR changes, and a changed file MAY NOT REGRESS - i.e.
it may not gain ruff or mypy violations relative to the PR base. Untouched
legacy hotspots are allowed until touched, and the existing legacy backlog
inside a touched file does not block (a whole-repo strict gate would be
instantly red: the hub's scripts/ carry pre-existing S/BLE/PL/T20 and untyped
debt at adoption). New code and any net-new violation a PR introduces are
blocked.

Mechanism: for each changed Python file, count violations (ruff: per rule code;
mypy: per file) at the PR base and at HEAD; fail if HEAD has more. `ruff format`
reflowing legacy lines never increases the count, so a pure-cleanup PR stays
green while genuine new violations are caught.

Two tools are supported (mirrors AIFactory scripts/cq_ratchet.py and CFactory):

* ``--tool ruff`` - per-rule-code ruff violation counts on each changed file.
* ``--tool mypy`` - mypy --strict error count per changed file. The legacy
  scripts are only partially annotated, so a whole-tree strict run would be
  instantly red; counting per file base-vs-head lets a touched legacy file keep
  its existing mypy debt while forbidding NET-NEW type errors.

This module is intentionally vendored from CFactory's reference implementation
(cross-service reuse of the proven Factory ratchet); only the default package
scope differs (the hub's first-class Python is the flat `scripts/` dir).

``--package`` takes a COMMA-SEPARATED list of directories (Factory#493). The hub
gates `scripts,tests`: with `scripts` alone the ratchet's own test-file carve-out
(Factory#403) was reachable for exactly one file — `scripts/test_model_probe.py`,
the seventeenth test file, which lives outside `tests/` — while the other
seventeen suites under `tests/` were linted by nothing at all. A comma list
rather than a repeated flag because MYPYPATH must carry every scoped dir at once:
a changed `tests/` file imports the module it gates out of `scripts/`.

Usage:
    python scripts/ratchet_lint.py --base <git-ref> [--tool ruff|mypy] [--package <dir>[,<dir>...]]

Exit code 0 if no changed file regressed; 1 otherwise.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections import Counter
from functools import cache
from pathlib import Path

# Canonical shared ratchet rules, vendored byte-exact from the hub and
# drift-gated (Factory#403). scripts/ is sys.path[0] when this runs as a
# script, so the sibling import resolves without packaging.
from ratchet_helpers import (
    MYPY_TEST_RELAX,
    is_test_file,
    require_tool_ran,
    ruff_findings,
    ruff_stdin_argv,
    write_temp,
)

PACKAGE_DEFAULT = "scripts"

# mypy text output lines look like:  path/to/file.py:12: error: <msg>  [code]
# The path is CAPTURED because it has to be compared: see mypy_count.
_MYPY_ERROR_RE = re.compile(r"^(?P<path>.+?):\d+: error:")


def _emit(message: str) -> None:
    # This is a CLI lint tool; its stdout report IS its purpose, so the T20
    # (no-print) rule is intentionally suppressed at the single output sink.
    print(message)  # noqa: T201


def _run(
    cmd: list[str], env: dict[str, str] | None = None, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    # cmd is built from constant git/ruff/mypy argv plus repo-internal paths, not
    # untrusted input; this lint tool legitimately shells out to git and linters.
    return subprocess.run(  # noqa: S603
        cmd, capture_output=True, text=True, check=False, env=env, input=stdin
    )


def packages(package: str) -> list[str]:
    """Split the ``--package`` value into its directories.

    Empty segments are dropped so a trailing comma or an accidental `a,,b`
    cannot silently widen the scope to the repo root.
    """
    return [part for part in (p.strip() for p in package.split(",")) if part]


def changed_python_files(base: str, package: str) -> list[str]:
    """Python files under any of *package*'s dirs, changed vs *base*.

    ``ACMR``, not ``AM``. ``diff.renames`` has defaulted to true since git 2.9,
    so a moved file has status **R** — and ``AM`` excluded it, meaning a rename
    was not gated AT ALL, in either the pre-commit lane or CI (TFactory#1005,
    found on a 1561-line ``git mv``). A move that carried new violations in
    would have passed exactly the same way.

    Seeing renames is only half of it: see :func:`rename_sources` for why the
    baseline has to follow the file to its old path.
    """
    res = _run(["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"])
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        sys.exit(2)
    pkgs = [Path(p) for p in packages(package)]
    out: list[str] = []
    for line in res.stdout.splitlines():
        path = Path(line)
        # `pkg in path.parents` matches both nested packages and a flat dir like
        # scripts/ (for scripts/foo.py, parents == [scripts, .]).
        if path.suffix == ".py" and any(p in path.parents for p in pkgs) and path.exists():
            out.append(str(path))
    return out


def ruff_counts(source: str, filename: str) -> Counter[str]:
    """Per-rule ruff violation counts for *source* checked as *filename*.

    Fed on stdin under the file's REAL path so ruff's per-file-ignores see the
    same path ``ruff check`` would (Factory#510). A temp copy could not: outside
    the project root only basename globs match, so ``**/tests/**`` was dead here
    and a test helper under ``tests/`` not named ``test_*.py`` was held to the
    production assert bar the real tree exempts it from.
    """
    res = _run(ruff_stdin_argv("ruff.toml", filename), stdin=source)
    # The shared "is this run a measurement" rule, both halves (Factory#590 for
    # the exit code, Factory#648 for the output). This used to be four lines of
    # exit-code check plus a `return Counter()` for empty stdout plus a bare
    # `except json.JSONDecodeError`, restated here and in the mypy counter below
    # and in both halves of the four sibling ratchets. The empty-stdout branch
    # was the one with teeth: the pinned ruff prints `[]` for a clean run, so
    # empty stdout was always ruff writing no report, counted as zero
    # violations. Both verdicts now live in the drift-gated canonical, so the
    # next correction reaches every consumer.
    return ruff_findings(res)


def mypy_command(target: str, original: str | None = None) -> list[str]:
    """The mypy invocation used for both the base and HEAD version of a file.

    ``--follow-imports=silent`` keeps mypy from reporting errors in imported
    legacy modules the changed file merely references, and
    ``--ignore-missing-imports`` stops third-party stub gaps (and the base
    version's temp-file location) from inflating the count - the strict bar
    still applies to the file's own annotations.

    For TEST files the untyped-def bar is relaxed (Factory#403). The shared
    ``standards/mypy.ini`` cannot express this: mypy per-module sections need
    dotted package paths, and a bare ``[mypy-test_*]`` (or even ``[mypy-*]``)
    silently does not match a top-level test module - measured, it left the
    error count unchanged. The ratchet knows which file it is checking, so the
    decision belongs here.

    ``--no-incremental`` is what makes the path in an error line trustworthy, and
    :func:`mypy_count` compares it (Factory#601). On a cache HIT mypy replays the
    stored diagnostics under the path the module was FIRST seen at, and every
    call here hands it a fresh temp dir — so the second check of identical
    content is blamed on a directory that no longer exists. Measured: run 1
    blames ``/tmp/tmpo8g7itfz/thing.py``, run 2 hands over
    ``/tmp/tmp9pdmz5z2/thing.py`` and is told about ``/tmp/tmpo8g7itfz`` again. A
    counter keyed on that path would read zero for both sides of the comparison
    and pass the gate having measured nothing. Costs ~1.1s per call on a warm
    cache; a gate that is only correct when its cache is cold is not correct.

    AIFactory hit the same cache independently (its #1057: base counts of 9 and
    then 0 for the same command on the same tree) and keyed a cache dir per tree
    instead, because ``--no-incremental`` measured ~5x slower there. That trade
    does not exist here: every call already writes to a FRESH ``mkdtemp``, so a
    cache keyed to it would be cold every time anyway. CFactory needs neither —
    its copy carries a random name, so two runs never share an entry (#319).
    Three forks, three answers, each measured against its own copy strategy.

    Production code is untouched: these flags are per-invocation and the ratchet
    checks one file at a time.
    """
    relax: list[str] = []
    if is_test_file(original if original is not None else target):
        relax = list(MYPY_TEST_RELAX)
    return [
        "mypy",
        "--config-file",
        "mypy.ini",
        "--ignore-missing-imports",
        "--follow-imports=silent",
        "--no-incremental",
        "--no-error-summary",
        "--no-color-output",
        "--hide-error-context",
        *relax,
        target,
    ]


def _mypy_env(package: str) -> dict[str, str]:
    # Put EVERY scoped dir on MYPYPATH so a changed file's imports of its
    # siblings resolve (the file under test is a temp copy outside the tree).
    # A changed test under tests/ imports the module it gates out of scripts/,
    # so scoping MYPYPATH to the file's own dir would not resolve it.
    return {**os.environ, "MYPYPATH": os.pathsep.join(packages(package))}


def mypy_count(source: str, filename: str, package: str) -> int:
    """mypy --strict error count for *source* checked as *filename*.

    Only lines mypy attributed to the file it was HANDED are counted, and that
    is the temp copy's path, not the repo-relative one. ``--follow-imports=silent``
    silences imported modules for ordinary errors but NOT for a blocking one: an
    import that fails to parse prints its own error line and stops the run before
    the target is checked at all. Counting that line attributed a foreign file's
    error to this one — measured, a clean file whose import would not parse came
    back as 1 (Factory#601, and CFactory#319 for the identical fork). The other
    three ratchets already compare the path; the hub was an outlier.

    A zero count out of such a run is not "clean" either, and is not treated as
    one: ``require_tool_ran`` sees exit 2 with nothing attributed to the target
    and aborts with "could not measure", which is the truthful verdict when mypy
    never reached the file.

    Base and HEAD are both checked from a temp file so the comparison is
    symmetric.
    """
    tmpdir, tmp = write_temp(source, filename)
    try:
        res = _run(mypy_command(tmp, filename), env=_mypy_env(package))
        target = Path(tmp)
        count = sum(
            1
            for line in res.stdout.splitlines()
            if (m := _MYPY_ERROR_RE.match(line)) is not None and Path(m.group("path")) == target
        )
        # Same shared rule as the ruff counter, with `measured` passed: mypy's
        # exit 2 also covers a BLOCKING error, which still emits an error line
        # and so belongs in the count rather than aborting the run.
        require_tool_ran("mypy", res, measured=count)
        return count
    finally:
        Path(tmp).unlink(missing_ok=True)
        Path(tmpdir).rmdir()


@cache
def rename_sources(base: str) -> tuple[tuple[str, str], ...]:
    """``(head_path, base_path)`` pairs for files this diff MOVED.

    The other half of the ``ACMR`` change above. Once renames are visible,
    looking the file up on base by its HEAD path finds nothing and reads the
    baseline as **0** — so every pre-existing violation in a moved file reports
    as net-new. AIFactory's fork had exactly that and made a pure ``git mv`` of
    a legacy file report ``0 -> 167``: a gate punishing the cleanup it exists to
    encourage (AIFactory#1218).

    Renames are what ``-M`` reports; ask git rather than guessing from content
    similarity here. Cached per base — this is one subprocess, not one per file.

    Returns a tuple of pairs (not a dict) so the result stays hashable and
    immutable behind ``lru_cache``.
    """
    res = _run(["git", "diff", "--name-status", "-M", "--diff-filter=R", f"{base}...HEAD"])
    if res.returncode != 0:
        # No rename information available: fall back to identity mapping rather
        # than failing. Worst case is the pre-#1005 behaviour for moved files.
        return ()
    pairs: list[tuple[str, str]] = []
    for line in res.stdout.splitlines():
        # `R<similarity>\told\tnew`
        status, _, paths = line.partition("\t")
        old, _, new = paths.partition("\t")
        if status.startswith("R") and old and new:
            pairs.append((new, old))
    return tuple(pairs)


def file_at_base(base: str, path: str) -> str | None:
    """The file's content on *base*, following a rename to its old path.

    Identity (the ``path`` the counter judges by) deliberately stays the HEAD
    path in :func:`regressions` — only the CONTENT comes from the old location.
    Judging the two sides under different per-file-ignores is Factory#510.
    """
    src = dict(rename_sources(base)).get(path, path)
    res = _run(["git", "show", f"{base}:{src}"])
    return res.stdout if res.returncode == 0 else None


def regressions(base: str, path: str, tool: str, package: str) -> list[str]:
    head_src = Path(path).read_text()
    base_src = file_at_base(base, path)
    if tool == "mypy":
        head_n = mypy_count(head_src, path, package)
        base_n = mypy_count(base_src, path, package) if base_src is not None else 0
        if head_n > base_n:
            return [f"{path}: mypy errors +{head_n - base_n} (base {base_n} -> head {head_n})"]
        return []
    head_counts = ruff_counts(head_src, path)
    base_counts = ruff_counts(base_src, path) if base_src is not None else Counter()
    out: list[str] = []
    for code, head_n in head_counts.items():
        base_n = base_counts.get(code, 0)
        if head_n > base_n:
            out.append(f"{path}: {code} +{head_n - base_n} (base {base_n} -> head {head_n})")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="git ref to diff against")
    parser.add_argument("--tool", choices=["ruff", "mypy"], default="ruff")
    parser.add_argument(
        "--package",
        default=PACKAGE_DEFAULT,
        help="comma-separated directories to gate (e.g. 'scripts,tests')",
    )
    args = parser.parse_args()

    files = changed_python_files(args.base, args.package)
    if not files:
        _emit(f"ratchet ({args.tool}): no changed Python under {args.package}; nothing to gate.")
        return 0

    _emit(f"ratchet ({args.tool}): gating changed files:\n  " + "\n  ".join(files))

    all_regressions: list[str] = []
    regressed_paths: list[str] = []
    for path in files:
        found = regressions(args.base, path, args.tool, args.package)
        all_regressions.extend(found)
        if found:
            regressed_paths.append(path)

    if all_regressions:
        _emit(f"\nratchet FAILED: changed files gained {args.tool} violations (shared strict bar):")
        for line in all_regressions:
            _emit(f"  {line}")
        if args.tool == "mypy":
            # Show the actual findings to make the failure actionable.
            for path in regressed_paths:
                res = _run(mypy_command(path), env=_mypy_env(args.package))
                sys.stdout.write(res.stdout)
        _emit(
            "\nFix the new violations (or clean the file further). The ratchet only "
            "blocks NET-NEW violations - pre-existing legacy in a touched file is "
            "allowed (coding-standards.md section 4.6)."
        )
        return 1

    _emit(f"ratchet PASSED ({args.tool}): no changed file regressed; new violations: none.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
