#!/usr/bin/env python3
"""Remove finished agent isolation worktrees without stranding a live agent.

Factory#616. On 2026-08-07 two agents lost their isolation worktree while still
running and spent the rest of their task with no shell. The investigation on
that issue ruled out ``git worktree prune`` (it only drops registry entries whose
directory is already gone) and ruled out branch deletion (git refuses a branch a
worktree has checked out). What it could not rule out is the harness's own
"auto-cleaned if unchanged" pass, which lives upstream and cannot be gated from
here.

The one removal path that IS ours is bulk cleanup, and that path has a specific
trap. ``git worktree remove`` refuses a locked worktree -- but it refuses a
STALE lock exactly as loudly as a live one, and the checkout accumulates stale
locks from every agent that has ever finished. Someone tidying up 30 worktrees
hits a wall of refusals whose text does not distinguish "an agent is working in
this" from "an agent died three weeks ago", and the documented way past a wall
of refusals is ``-f -f`` or ``rm -rf`` -- which strands every live agent at once.

So this tool exists to make the *safe* cleanup the *easy* one, and it never
passes ``--force``.

**Why "clean tree" is not enough, measured rather than assumed.** A first cut
kept a worktree only if it was locked-and-live or dirty. Run against the fleet's
19 real agent worktrees on 2026-08-15, that version proposed removing **all 19**
-- because not one of them carried a lock, and every one was committed clean.
Three of those branches had commits pushed after their PR merged (Factory#690).
This is the harness's own defect reproduced exactly: *an agent that has
committed and pushed looks identical to an agent that did nothing.* Content
cannot tell them apart. Recency can, so recency is a check.

Four independent reasons to keep. ``remove`` requires all four to be silent:

1. the lock names a **live pid** (harness-created trees carry one)
2. a **live process** has its cwd inside the tree
3. the tree has **uncommitted or untracked** files
4. it was **touched recently** (default: within 24h; ``--min-idle-hours``)

A lock whose reason names no pid is also a keep. "Unknown" is never a remove --
that is exactly the case where guessing costs an agent its shell.

Usage:
    python scripts/prune_agent_worktrees.py                    # report only
    python scripts/prune_agent_worktrees.py --remove           # act
    python scripts/prune_agent_worktrees.py --repo ../PFactory --under .claude/worktrees
    python scripts/prune_agent_worktrees.py --min-idle-hours 72
    python scripts/prune_agent_worktrees.py --self-test

Exit codes:
    0 - reported (or removed) successfully
    1 - a removal that was supposed to succeed failed, or the self-test failed
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from gate_evidence import expect, gate_argparser, gate_fixture, parse_or_self_test, report_self_test

DEFAULT_MIN_IDLE_HOURS = 24.0

# `locked claude agent agent-a0fe0977b570fc340 (pid 311603 start 12662981)`
_PID_IN_LOCK = re.compile(r"\bpid\s+(\d+)\b")


@dataclass(frozen=True)
class Worktree:
    """One entry from ``git worktree list --porcelain``."""

    path: Path
    locked: bool
    lock_reason: str


def parse_worktrees(porcelain: str) -> list[Worktree]:
    """Parse ``git worktree list --porcelain`` output, skipping the main checkout.

    The main checkout is the first record and must never be a removal
    candidate, so it is dropped here rather than filtered by any caller.
    """
    out: list[Worktree] = []
    for block in porcelain.strip().split("\n\n"):
        path: Path | None = None
        locked = False
        reason = ""
        for line in block.splitlines():
            if line.startswith("worktree "):
                path = Path(line[len("worktree ") :])
            elif line == "locked" or line.startswith("locked "):
                locked = True
                reason = line[len("locked ") :] if len(line) > len("locked") else ""
        if path is not None:
            out.append(Worktree(path=path, locked=locked, lock_reason=reason))
    return out[1:]  # [0] is the main checkout


def pid_is_alive(pid: int) -> bool:
    """True if a process with *pid* exists (signal 0 probes without delivering)."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    return True


def lock_holder_alive(
    worktree: Worktree, alive: Callable[[int], bool] = pid_is_alive
) -> bool | None:
    """True/False if the lock names a pid we could check, None if it names none.

    None is deliberately distinct from False. A lock whose reason we cannot
    parse is not evidence of a dead owner -- it is evidence we do not know, and
    the caller must treat it as occupied.
    """
    if not worktree.locked:
        return False
    match = _PID_IN_LOCK.search(worktree.lock_reason)
    if match is None:
        return None
    return bool(alive(int(match.group(1))))


def process_in_tree(path: Path, proc: Path = Path("/proc")) -> bool:
    """True if any live process has its working directory inside *path*.

    Catches an agent with a command in flight. It is a narrow signal on its own
    -- an agent's shell exits between tool calls, so the usual state is "live
    agent, no process" -- which is why it is one of three checks and not the
    check. Non-Linux hosts have no /proc and get False here; the idle-time and
    lock checks still apply.
    """
    prefix = f"{path}/"
    if not proc.is_dir():
        return False
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            cwd = (entry / "cwd").readlink()
        except OSError:
            continue  # process exited, or not ours to read
        if str(cwd) == str(path) or str(cwd).startswith(prefix):
            return True
    return False


def hours_idle(path: Path, now: float | None = None) -> float:
    """Hours since anything in the worktree's git state was last touched.

    The signal that actually discriminates in practice. Measured 2026-08-15
    across the fleet's 19 agent worktrees: every one was 20-50h idle, and none
    carried a lock -- so lock-and-dirty checks alone would have declared all 19
    removable, including three whose branches had commits pushed after their
    PR merged. An agent that has committed everything is indistinguishable from
    an idle one by content; it is distinguishable by when it last wrote.

    Reads HEAD, the index and the reflog rather than the checkout, because a
    read-only agent still moves those and never touches a tracked file.
    """
    now = now if now is not None else time.time()
    newest = 0.0
    candidates = [path, path / ".git"]
    git_dir = path / ".git"
    if git_dir.is_file():
        # A linked worktree's .git is a `gitdir: <path>` pointer.
        try:
            pointed = git_dir.read_text().partition("gitdir:")[2].strip()
            candidates += [Path(pointed) / name for name in ("index", "HEAD", "logs/HEAD")]
        except OSError:
            pass
    for candidate in candidates:
        try:
            newest = max(newest, candidate.stat().st_mtime)
        except OSError:
            continue
    if newest == 0.0:
        return 0.0  # nothing readable -> treat as just-touched, i.e. keep
    return (now - newest) / 3600.0


def git(repo: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Every git call this tool makes, in one place.

    One helper rather than a call site per command: the security lint needs a
    ``noqa`` on each ``subprocess.run`` with a partial executable path, and a
    dozen scattered suppressions is a dozen places for one to be added without
    anyone reading why. It also puts every git invocation somewhere a reviewer
    can see the whole set at once -- which for this tool is the point, because
    the argument that must never appear is ``--force``.
    """
    return subprocess.run(  # noqa: S603 - fixed argv, no shell, no user-supplied executable
        ["git", "-C", str(repo), *args],  # noqa: S607 - `git` from PATH, as every hub gate does
        capture_output=True,
        text=True,
        check=check,
    )


def say(message: str) -> None:
    """Report a line. This tool's whole output is its report, so print is correct."""
    print(message)  # noqa: T201 - a CLI report, not stray debugging


def tree_has_work(path: Path) -> bool:
    """True if the worktree has uncommitted or untracked files.

    Untracked counts. An agent that has written a new file and not yet added it
    has done the work that removal would destroy -- committed history survives a
    worktree removal, an untracked file does not.
    """
    if not path.is_dir():
        return False
    result = git(path, "status", "--porcelain")
    if result.returncode != 0:
        return True  # cannot tell -> assume occupied
    return bool(result.stdout.strip())


def classify(
    worktrees: list[Worktree],
    min_idle_hours: float = DEFAULT_MIN_IDLE_HOURS,
    alive: Callable[[int], bool] = pid_is_alive,
) -> list[tuple[Worktree, str, str]]:
    """Return ``(worktree, verdict, reason)`` for each, verdict in {remove, keep}.

    Four independent reasons to keep, checked in that order. Any one of them is
    enough; ``remove`` requires all four to be silent.
    """
    verdicts: list[tuple[Worktree, str, str]] = []
    for tree in worktrees:
        holder = lock_holder_alive(tree, alive=alive)
        idle = hours_idle(tree.path)
        if holder is True:
            verdicts.append((tree, "keep", "lock names a live pid"))
        elif holder is None:
            verdicts.append((tree, "keep", "locked, lock reason names no pid to check"))
        elif process_in_tree(tree.path):
            verdicts.append((tree, "keep", "a live process is working in it"))
        elif tree_has_work(tree.path):
            verdicts.append((tree, "keep", "uncommitted or untracked files"))
        elif idle < min_idle_hours:
            verdicts.append((tree, "keep", f"touched {idle:.1f}h ago (< {min_idle_hours:g}h)"))
        else:
            verdicts.append((tree, "remove", f"no live owner, clean, idle {idle:.1f}h"))
    return verdicts


def prune(
    repo: Path,
    under: str,
    remove: bool,
    min_idle_hours: float = DEFAULT_MIN_IDLE_HOURS,
    alive: Callable[[int], bool] = pid_is_alive,
) -> int:
    listing = git(repo, "worktree", "list", "--porcelain", check=True).stdout
    scoped = [w for w in parse_worktrees(listing) if under in str(w.path)]
    if not scoped:
        say(f"No worktrees under {under!r} in {repo}.")
        return 0

    failures = 0
    for tree, verdict, reason in classify(scoped, min_idle_hours=min_idle_hours, alive=alive):
        if verdict == "keep":
            say(f"KEEP    {tree.path} -- {reason}")
            continue
        if not remove:
            say(f"REMOVE  {tree.path} -- {reason} (dry run; pass --remove to act)")
            continue
        # A stale lock still makes git refuse, and the refusal text recommends
        # `-f -f` -- the command that strands live agents. Unlock explicitly
        # instead: we reach this line only after reading the lock's pid and
        # finding no such process, so this drops a marker for a dead owner and
        # nothing more. It is narrower than force, which overrides every check
        # at once including the dirty-tree one below it.
        if tree.locked:
            git(repo, "worktree", "unlock", str(tree.path))
        # Plain `remove`, never `-f -f`: a tree git declines is a tree we want
        # declined. Factory#616 is what forcing past that refusal looks like.
        result = git(repo, "worktree", "remove", str(tree.path))
        if result.returncode == 0:
            say(f"REMOVED {tree.path} -- {reason}")
        else:
            failures += 1
            say(f"FAILED  {tree.path} -- git refused: {result.stderr.strip()}")
    return 1 if failures else 0


def _self_test() -> int:
    with gate_fixture() as (root, failures):
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.email", "gate@example.com")
        git(repo, "config", "user.name", "gate")
        (repo / "seed.txt").write_text("seed\n")
        git(repo, "add", "seed.txt")
        git(repo, "commit", "-qm", "seed")

        trees = root / "wt"
        trees.mkdir()
        names = ("clean", "dirty", "untracked", "live-lock", "stale-lock", "opaque-lock")
        for name in names:
            git(repo, "worktree", "add", "-q", "-b", name, str(trees / name), "main")
        (trees / "dirty" / "seed.txt").write_text("modified\n")
        (trees / "untracked" / "scratch.md").write_text("notes\n")
        git(
            repo,
            "worktree",
            "lock",
            "--reason",
            f"claude agent x (pid {os.getpid()})",
            str(trees / "live-lock"),
        )
        git(
            repo,
            "worktree",
            "lock",
            "--reason",
            "claude agent y (pid 2147480000)",
            str(trees / "stale-lock"),
        )
        git(repo, "worktree", "lock", "--reason", "manual hold", str(trees / "opaque-lock"))

        listing = git(repo, "worktree", "list", "--porcelain", check=True).stdout
        parsed = parse_worktrees(listing)
        expect(
            failures,
            len(parsed) == len(names),
            f"main checkout must be excluded (got {len(parsed)}, want {len(names)})",
        )

        # The recency check is disabled here so the other three are what is
        # being graded; it gets its own case below. Fixtures are seconds old, so
        # leaving it on would make every verdict "keep" for one reason and prove
        # nothing about the rest.
        # pid 2147480000 is above any real /proc/sys/kernel/pid_max, so it is
        # genuinely absent rather than mocked absent.
        verdicts = {w.path.name: (v, r) for w, v, r in classify(parsed, min_idle_hours=0.0)}
        expect(failures, verdicts["clean"][0] == "remove", "a clean unlocked worktree is removable")
        expect(
            failures, verdicts["stale-lock"][0] == "remove", "a lock naming a dead pid is removable"
        )
        expect(failures, verdicts["dirty"][0] == "keep", "uncommitted changes must be kept")
        expect(failures, verdicts["untracked"][0] == "keep", "untracked files must be kept")
        expect(
            failures, verdicts["live-lock"][0] == "keep", "a lock naming a live pid must be kept"
        )
        expect(failures, verdicts["opaque-lock"][0] == "keep", "an unparseable lock must be kept")

        # The regression case for the 19-worktree measurement in the module
        # docstring: a committed-clean, unlocked worktree that an agent touched
        # minutes ago is the shape that stranded two agents on 2026-08-07. With
        # the default window it must be KEPT, and kept for the recency reason
        # specifically -- if this ever reads "remove", the tool has become the
        # bug it was written to prevent.
        recent = {w.path.name: (v, r) for w, v, r in classify(parsed, min_idle_hours=24.0)}
        expect(
            failures,
            recent["clean"][0] == "keep" and "touched" in recent["clean"][1],
            f"a clean tree touched just now must be kept for recency (got {recent['clean']})",
        )

        rc = prune(repo, str(trees), remove=True, min_idle_hours=0.0)
        expect(failures, rc == 0, "removing the removable ones must succeed")
        # The load-bearing assertion: what survives on disk. A future edit that
        # reaches for --force to clear the refusals would pass every verdict
        # check above and fail here, which is the Factory#616 failure exactly.
        for name in ("dirty", "untracked", "live-lock", "opaque-lock"):
            expect(
                failures, (trees / name).is_dir(), f"{name} must still exist after a --remove run"
            )
        for name in ("clean", "stale-lock"):
            expect(failures, not (trees / name).exists(), f"{name} should have been removed")

    return report_self_test(failures)


def main(argv: list[str] | None = None) -> int:
    parser = gate_argparser(__doc__)
    parser.add_argument("--repo", default=".", help="repository to prune (default: cwd)")
    parser.add_argument(
        "--under",
        default=".claude/worktrees",
        help="only consider worktrees whose path contains this (default: .claude/worktrees)",
    )
    parser.add_argument(
        "--remove", action="store_true", help="actually remove; without it this only reports"
    )
    parser.add_argument(
        "--min-idle-hours",
        type=float,
        default=DEFAULT_MIN_IDLE_HOURS,
        help=(
            "keep any worktree touched more recently than this "
            f"(default: {DEFAULT_MIN_IDLE_HOURS:g})"
        ),
    )
    early, args = parse_or_self_test(parser, argv, _self_test)
    if early is not None:
        return early
    assert args is not None  # noqa: S101 - guaranteed when early is None
    return prune(
        Path(args.repo), args.under, remove=args.remove, min_idle_hours=args.min_idle_hours
    )


if __name__ == "__main__":
    sys.exit(main())
