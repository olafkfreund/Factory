#!/usr/bin/env python3
"""Fail CI when a test suite reads or writes under the real $HOME.

Factory security-cleanup review (2026-08-13). SkillsService tests read and
wrote the developer's real ``~/.aifactory/`` cache. A mutation to the parser
APPEARED to pass because the warm cache short-circuited the parser; it only
failed once the real home file was deleted, and a mutated run then POISONED
the real cache so a later run of CORRECT code failed too. Contamination
persisted across runs and across branches. A suite that can go green because
of a file outside the repo is not testing the repo, and it makes every other
gate's verdict unreliable — this is why it is a correctness gate on the test
suite itself, not hygiene.

Mechanism: snapshot every regular file under a set of home-relative paths
(mtime + size + content hash) BEFORE the test command runs, run the command
with the real $HOME, snapshot again AFTER, and fail if anything changed,
appeared, or disappeared. This does not require test code changes or a
fixture convention the suite must already follow — it catches the actual
observable effect (files touched under HOME) regardless of how the test got
there, which matches the failure Factory#(pf-pickle) found: the contamination
was in ``~/.aifactory/`` and ``~/.pfactory/`` caches specifically.

Usage:
    python scripts/check_test_home_isolation.py --home /home/dev -- pytest -q
    python scripts/check_test_home_isolation.py --self-test

Exit codes:
    0 - $HOME was untouched by the command (or self-test passed)
    1 - the command touched something under $HOME, OR the wrapped command itself failed
    2 - bad invocation
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from hashlib import sha256
from pathlib import Path

from gate_evidence import expect, gate_argparser, parse_or_self_test, report_self_test


def _snapshot(home: Path) -> dict[str, tuple[int, float, str]]:
    """Map of relative path -> (size, mtime_ns, content sha256) for every file under home."""
    out: dict[str, tuple[int, float, str]] = {}
    if not home.is_dir():
        return out
    for path in home.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
            digest = sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue  # unreadable (permissions, race) — not this gate's concern
        out[str(path.relative_to(home))] = (stat.st_size, stat.st_mtime, digest)
    return out


def diff_snapshots(
    before: dict[str, tuple[int, float, str]], after: dict[str, tuple[int, float, str]]
) -> list[str]:
    problems: list[str] = []
    for rel in sorted(set(before) | set(after)):
        if rel not in before:
            problems.append(f"CREATED under $HOME: {rel}")
        elif rel not in after:
            problems.append(f"DELETED under $HOME: {rel}")
        elif before[rel] != after[rel]:
            problems.append(f"MODIFIED under $HOME: {rel}")
    return problems


def run_isolated(home: Path, command: list[str]) -> int:
    before = _snapshot(home)
    result = subprocess.run(command, check=False)  # noqa: S603
    after = _snapshot(home)
    problems = diff_snapshots(before, after)
    print(f"test-home-isolation: watched {home} ({len(before)} file(s) before the run)")  # noqa: T201
    if problems:
        print("HOME CONTAMINATION — the test run touched files outside the repo:")  # noqa: T201
        for problem in problems:
            print(f"  - {problem}")  # noqa: T201
        print(  # noqa: T201
            "\nA test suite that reads or writes real $HOME state can pass or fail "
            "depending on what a developer happens to have cached there, and a "
            "mutated run can poison that state for every run after it. Route the "
            "code under test through a HOME override / tmp_path fixture instead."
        )
        return 1
    if result.returncode != 0:
        print(f"command failed with exit {result.returncode} (unrelated to HOME isolation)")  # noqa: T201
        return 1
    print("OK: $HOME was untouched by the run.")  # noqa: T201
    return 0


def _self_test() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        home.mkdir()
        (home / "existing.txt").write_text("unchanged\n")

        # Case 1: command that touches nothing under home -> clean.
        rc = run_isolated(home, [sys.executable, "-c", "pass"])
        expect(failures, rc == 0, "a no-op command must not report contamination")

        # Case 2 (the mutation): command writes a new file under home, exactly
        # the shape of a test suite warming ~/.aifactory/skills-cache.pkl.
        write_cmd = [
            sys.executable,
            "-c",
            f"open(r'{home / 'skills-cache.pkl'}', 'wb').write(b'poisoned')",
        ]
        rc = run_isolated(home, write_cmd)
        expect(failures, rc == 1, "a command that creates a file under $HOME must fail the gate")
        (home / "skills-cache.pkl").unlink()

        # Case 3: command that modifies an existing home file.
        modify_cmd = [
            sys.executable,
            "-c",
            f"open(r'{home / 'existing.txt'}', 'w').write('mutated\\n')",
        ]
        rc = run_isolated(home, modify_cmd)
        expect(failures, rc == 1, "a command that modifies a $HOME file must fail the gate")
        (home / "existing.txt").write_text("unchanged\n")

        # Case 4: healed again -> back to green.
        rc = run_isolated(home, [sys.executable, "-c", "pass"])
        expect(failures, rc == 0, "gate must pass again once the run stops touching $HOME")

    return report_self_test(failures)


def main(argv: list[str] | None = None) -> int:
    parser = gate_argparser(__doc__)
    parser.add_argument("--home", help="the $HOME directory to watch")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- the test command to run")
    early, args = parse_or_self_test(parser, argv, _self_test)
    if early is not None:
        return early
    assert args is not None  # noqa: S101 - parse_or_self_test guarantees this when early is None
    if not args.home or not args.command:
        parser.error("--home and a -- command are required (or pass --self-test)")
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    return run_isolated(Path(args.home), command)


if __name__ == "__main__":
    sys.exit(main())
