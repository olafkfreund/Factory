#!/usr/bin/env python3
"""Fail loudly when dev and main hold different code (Factory#498).

CFactory#266 and PFactory#406 were the same accident twice: a fix was merged to
``dev``, the service deploys from ``main``, and for hours the deployed branch
kept the broken behaviour while every dashboard was green. Both were found by
someone tripping over them while doing something else. From the outside a fix
that is merged but not on the deployed branch is indistinguishable from a fix
nobody wrote.

WHY NOT COUNT COMMITS. The obvious detector is
``GET /repos/{o}/{r}/compare/dev...main -> .ahead_by/.behind_by``, and it is
useless. Measured on the real fleet on 2026-08-01: PFactory ahead 11, TFactory
10, CFactory 8, AIFactory 4 -- and every single one of those commits was a
``Merge pull request #N from olafkfreund/dev`` promotion merge carrying no
content ``dev`` did not already have. A counter fires on all four repos on a
completely healthy fleet, and a detector that cries wolf in week one is muted in
week two. Factory#498 records a second flavour of the same trap: PFactory once
read ``ahead=5 behind=5`` where four of the ten commits were the *same two*
Dependabot bumps applied to each branch separately -- identical content, distinct
shas.

WHAT IS COMPARED INSTEAD. ``git cherry <upstream> <head>`` -- content, via
patch-id. It answers exactly the question worth asking: which commits on this
branch have no equivalent on the other one? It drops merge commits (a merge has
no patch-id, so promotion merges vanish) and it pairs commits with identical
diffs regardless of sha, subject or PR number (so the Dependabot double-apply
vanishes). Both classes of false positive are killed by the primitive rather
than by a heuristic anyone has to maintain.

TWO DIRECTIONS, TWO SEVERITIES.

*Unpromoted* (on ``dev``, no equivalent on ``main``) is the normal state of a
dev-first flow for a while, and the "merged but not deployed" window when it
stops being a while. So it is graded by AGE: the oldest unpromoted commit older
than ``--max-unpromoted-hours`` is the alert. Stateless on purpose -- the age is
in the commit, so nothing has to remember anything between runs.

*Backflow* (on ``main``, no equivalent on ``dev``) is never normal. It means work
exists on the deployed branch that ``dev`` will never see, which is how the two
trees drift apart permanently and how the next promotion silently reverts
something. Any amount of it is an alert immediately.

SCOPE IS DERIVED, NOT RE-DECLARED. Which repos even have a ``dev`` branch is
already stated once, in the ``BRANCHES=`` column of
``scripts/apply_branch_protection.sh``. This reads that table rather than
carrying a second list that can shrink without anyone noticing -- the
Factory#523 shape. It also checks the claim in the other direction: a repo the
table declares ``main``-only that turns out to HAVE a ``dev`` branch is a scope
hole and fails, because that is precisely the repo nobody is watching.

Usage:
    check_branch_divergence.py --workdir /tmp/fleet [--max-unpromoted-hours 24]
    check_branch_divergence.py --self-test

Exit codes:
    0 - every repo checked, no divergence
    1 - divergence found (backflow, or unpromoted work past the budget)
    2 - COULD NOT DETERMINE (clone failed, branch missing, intent unparseable).
        Never 0. A gate that cannot run has verified nothing
        (standards/coding-standards.md rule 4.7, Factory#433).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# Sibling import: this runs out of a full hub checkout, exactly as the three
# byte-comparison gates import `digest` from the same module.
from gate_evidence import expect, report_self_test

DEFAULT_MAX_UNPROMOTED_HOURS = 24.0
DEFAULT_CLONE_BASE = "https://github.com/olafkfreund"
INTENT_PATH = Path(__file__).resolve().parent / "apply_branch_protection.sh"

_ALL_REPOS_RE = re.compile(r"^ALL_REPOS=\(([^)]*)\)", re.MULTILINE)
_BRANCHES_RE = re.compile(r'^\s{4}(\S+)\)\s.*BRANCHES="([^"]*)"', re.MULTILINE)


class CannotDetermineError(RuntimeError):
    """The check could not be performed. Distinct from "the check found nothing"."""


@dataclass(frozen=True)
class Commit:
    """One commit with no content-equivalent on the other branch."""

    sha: str
    subject: str
    epoch: int


def _run(args: list[str], env: dict[str, str] | None = None) -> str:
    """Run a git command, raising CannotDetermineError rather than returning silence."""
    merged = {**os.environ, **env} if env else None
    try:
        proc = subprocess.run(  # noqa: S603
            args, env=merged, capture_output=True, text=True, check=False
        )
    except OSError as exc:  # git missing entirely
        raise CannotDetermineError(f"could not execute {args[0]}: {exc}") from exc
    if proc.returncode != 0:
        raise CannotDetermineError(
            f"`{' '.join(args)}` exited {proc.returncode}: {proc.stderr.strip()}"
        )
    return proc.stdout


def parse_intent(text: str) -> dict[str, list[str]]:
    """Read the per-repo BRANCHES table out of apply_branch_protection.sh.

    Raises CannotDetermineError if the table cannot be read or a repo in ALL_REPOS has
    no BRANCHES entry -- a half-parsed table would quietly narrow this gate's
    scope, which is the failure mode it exists to prevent.
    """
    all_repos_match = _ALL_REPOS_RE.search(text)
    if not all_repos_match:
        raise CannotDetermineError("no ALL_REPOS=(...) line in the branch-protection intent table")
    declared = all_repos_match.group(1).split()
    if not declared:
        raise CannotDetermineError("ALL_REPOS is empty")

    branches = {repo: value.split() for repo, value in _BRANCHES_RE.findall(text)}
    missing = [repo for repo in declared if repo not in branches]
    if missing:
        raise CannotDetermineError(f"ALL_REPOS names repos with no BRANCHES= entry: {missing}")
    return {repo: branches[repo] for repo in declared}


def _resolve(repo: Path, branch: str) -> str:
    """Full sha of *branch*, preferring the remote-tracking ref of a clone."""
    for ref in (f"refs/remotes/origin/{branch}", f"refs/heads/{branch}"):
        proc = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", ref],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    raise CannotDetermineError(f"{repo.name}: branch '{branch}' does not exist")


def _describe(repo: Path, sha: str) -> Commit:
    raw = _run(["git", "-C", str(repo), "show", "-s", "--format=%ct%x00%s", sha]).strip()
    epoch, _, subject = raw.partition("\0")
    return Commit(sha=sha, subject=subject, epoch=int(epoch))


def unmatched(repo: Path, upstream: str, head: str) -> list[Commit]:
    """Commits on *head* with no patch-equivalent on *upstream*.

    ``git cherry`` marks these ``+``; commits whose diff already exists upstream
    under a different sha are marked ``-`` and are not divergence. Merge commits
    have no patch-id and are omitted entirely, which is what makes a fleet full
    of dev->main promotion merges read as clean.
    """
    out = _run(["git", "-C", str(repo), "cherry", upstream, head])
    shas = [line[1:].strip() for line in out.splitlines() if line.startswith("+")]
    return [_describe(repo, sha) for sha in shas]


def _hours(now: int, epoch: int) -> float:
    return (now - epoch) / 3600.0


def _render(label: str, commits: list[Commit], now: int) -> list[str]:
    if not commits:
        return [f"  {label}: none"]
    lines = [f"  {label}:"]
    lines += [f"    {c.sha[:8]}  {_hours(now, c.epoch):6.1f}h  {c.subject}" for c in commits]
    return lines


def verdict(
    unpromoted: list[Commit], backflow: list[Commit], now: int, budget_hours: float
) -> tuple[int, str]:
    """Grade one repo. Returns (exit_code, one-line verdict)."""
    if backflow:
        return 1, (
            f"DIVERGED: {len(backflow)} commit(s) on main have no equivalent on dev. "
            "dev will never see this work and the next promotion may revert it."
        )
    if unpromoted:
        oldest = min(c.epoch for c in unpromoted)
        age = _hours(now, oldest)
        if age > budget_hours:
            return 1, (
                f"DIVERGED: oldest unpromoted commit is {age:.1f}h old "
                f"(budget {budget_hours:.0f}h). It is merged but not on the deployed "
                "branch, which is CFactory#266 and PFactory#406 exactly."
            )
        return 0, (
            f"OK: {len(unpromoted)} unpromoted commit(s), oldest {age:.1f}h "
            f"(budget {budget_hours:.0f}h), no backflow."
        )
    return 0, "OK: dev and main hold the same content."


def check_repo(path: Path, pair: tuple[str, str], now: int, budget_hours: float) -> tuple[int, str]:
    """Compare one clone's two branches. Returns (exit_code, report block)."""
    dev, main = pair
    # Resolve to shas first and compare THOSE. In a clone the branches are
    # `origin/dev` / `origin/main` and the bare names do not resolve at all; that
    # cost a run that reported CANNOT DETERMINE on all four repos. Shas work for a
    # clone and for a local repo identically.
    dev_sha = _resolve(path, dev)
    main_sha = _resolve(path, main)
    unpromoted = unmatched(path, main_sha, dev_sha)
    backflow = unmatched(path, dev_sha, main_sha)
    code, line = verdict(unpromoted, backflow, now, budget_hours)

    # Cite the bytes on the PASS path too, not only when something is wrong: a
    # verdict whose inputs are invisible cannot be falsified by a reader.
    body = [f"  compared {dev}={dev_sha[:8]} against {main}={main_sha[:8]}"]
    body += _render(f"unpromoted (on {dev}, no equivalent on {main})", unpromoted, now)
    body += _render(f"backflow (on {main}, no equivalent on {dev})", backflow, now)
    body.append(f"  VERDICT: {line}")
    return code, "\n".join(body)


def ensure_clone(workdir: Path, clone_base: str, name: str) -> Path:
    """Local clone for *name*, cloned on first use. Full history: patch-id needs blobs."""
    path = workdir / name
    if (path / ".git").is_dir() or (path / "HEAD").is_file():
        return path
    workdir.mkdir(parents=True, exist_ok=True)
    _run(["git", "clone", "--quiet", "--no-checkout", f"{clone_base}/{name}", str(path)])
    return path


def assert_no_dev(clone_base: str, name: str) -> None:
    """A repo the intent table calls main-only must really have no dev branch.

    Without this the scope silently narrows: edit one BRANCHES= column and a repo
    leaves this gate's coverage with no trace, which is Factory#523's shape.
    """
    out = _run(["git", "ls-remote", "--heads", f"{clone_base}/{name}", "refs/heads/dev"])
    if out.strip():
        raise CannotDetermineError(
            f"{name}: the branch-protection intent table declares it main-only, but it "
            "HAS a dev branch. Either add dev to its BRANCHES= column or delete the "
            "branch -- an unwatched dev branch is how Factory#498 happened."
        )


def run_check(workdir: Path, clone_base: str, intent: str, budget_hours: float, now: int) -> int:
    """Check every repo the intent table knows about. Returns the worst exit code."""
    table = parse_intent(intent)
    worst = 0
    for name, branches in table.items():
        try:
            if "dev" not in branches:
                assert_no_dev(clone_base, name)
                skipped = f"{name}: SKIPPED -- intent declares {branches}, no dev upstream"
                print(skipped)  # noqa: T201
                continue
            path = ensure_clone(workdir, clone_base, name)
            code, block = check_repo(path, ("dev", "main"), now, budget_hours)
        except CannotDetermineError as exc:
            print(f"{name}: CANNOT DETERMINE -- {exc}")  # noqa: T201
            worst = 2
            continue
        print(f"{name}:")  # noqa: T201
        print(block)  # noqa: T201
        worst = max(worst, code)
    print(f"\nchecked {len(table)} repo(s): {', '.join(table)}")  # noqa: T201
    return worst


# ---------------------------------------------------------------------------
# self-test: builds real git repositories, because the whole gate rests on what
# `git cherry` does with merge commits and duplicate patches. Asserting that
# from memory rather than from git is how a detector nobody ever saw fire ships.
# ---------------------------------------------------------------------------

_DAY = 86400


def _authored(repo: Path, *args: str) -> list[str]:
    """A git command carrying an identity, so the self-test needs no global config."""
    identity = ["-c", "user.email=self@test", "-c", "user.name=self test"]
    return ["git", "-C", str(repo), *identity, *args]


def _commit(repo: Path, name: str, body: str, subject: str, epoch: int) -> None:
    (repo / name).write_text(body)
    stamp = f"{epoch} +0000"
    _run(["git", "-C", str(repo), "add", "-A"])
    _run(
        _authored(repo, "commit", "--quiet", "-m", subject),
        # Committer date, not just author date: the gate ages commits by %ct
        # because that is what "how long has this been sitting unpromoted"
        # actually means, and it is what the GitHub compare API reports.
        env={"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
    )


def _new_repo(root: Path, name: str, now: int) -> Path:
    repo = root / name
    repo.mkdir(parents=True)
    _run(["git", "-C", str(repo), "init", "--quiet", "--initial-branch=main"])
    _commit(repo, "base.txt", "base\n", "base", now - 90 * _DAY)
    _run(["git", "-C", str(repo), "branch", "dev"])
    return repo


def _promote(repo: Path, pr: int) -> None:
    """A dev->main promotion exactly as the fleet does it: a real merge commit."""
    _run(["git", "-C", str(repo), "checkout", "--quiet", "main"])
    subject = f"Merge pull request #{pr} from olafkfreund/dev"
    _run(_authored(repo, "merge", "--no-ff", "--quiet", "dev", "-m", subject))
    _run(["git", "-C", str(repo), "checkout", "--quiet", "dev"])


def _build_benign(root: Path, now: int, name: str = "Benign") -> Path:
    """The real fleet on 2026-08-01: promotion merges on main, fresh work on dev."""
    repo = _new_repo(root, name, now)
    _run(["git", "-C", str(repo), "checkout", "--quiet", "dev"])
    for pr in (1, 2, 3):
        _commit(repo, f"f{pr}.txt", f"work {pr}\n", f"feat: thing {pr} (#{pr})", now - 30 * _DAY)
        _promote(repo, pr)
    _commit(repo, "fresh.txt", "fresh\n", "fix: fresh work (#9)", now - 3600)
    return repo


def _build_dependabot(root: Path, now: int) -> Path:
    """One bump applied to each branch separately: same patch, two shas, two PR numbers."""
    repo = _new_repo(root, "Dependabot", now)
    patch = "requests==2.32.4\n"
    _run(["git", "-C", str(repo), "checkout", "--quiet", "dev"])
    _commit(repo, "reqs.txt", patch, "chore(deps): bump requests (#40)", now - 30 * _DAY)
    _run(["git", "-C", str(repo), "checkout", "--quiet", "main"])
    _commit(repo, "reqs.txt", patch, "chore(deps): bump requests (#41)", now - 30 * _DAY)
    _run(["git", "-C", str(repo), "checkout", "--quiet", "dev"])
    return repo


def _build_stranded(root: Path, now: int, name: str = "Stranded") -> Path:
    """CFactory#266: a fix merged to dev, never promoted, while main is deployed."""
    repo = _build_benign(root, now, name)
    _commit(
        repo,
        "honesty.txt",
        "ok=false\n",
        "fix(approve): stop reporting Done (#266)",
        now - 3 * _DAY,
    )
    return repo


def _build_backflow(root: Path, now: int) -> Path:
    """Real content on main that dev will never see."""
    repo = _build_benign(root, now, "Backflow")
    _run(["git", "-C", str(repo), "checkout", "--quiet", "main"])
    _commit(repo, "hotfix.txt", "patched\n", "fix: hotfix straight to main (#77)", now - 3600)
    _run(["git", "-C", str(repo), "checkout", "--quiet", "dev"])
    return repo


def _self_test_cases(root: Path, now: int, failures: list[str]) -> None:
    budget = 24.0

    code, block = check_repo(_build_benign(root, now), ("dev", "main"), now, budget)
    expect(
        failures,
        code == 0,
        "the real fleet shape (promotion merges + fresh dev work) must be quiet",
    )
    expect(
        failures,
        "backflow" in block and "none" in block,
        "the benign report must show zero backflow",
    )

    code, _ = check_repo(_build_dependabot(root, now), ("dev", "main"), now, budget)
    expect(failures, code == 0, "the same patch applied to both branches is not divergence")

    code, block = check_repo(_build_stranded(root, now), ("dev", "main"), now, budget)
    expect(failures, code == 1, "a 3-day-old unpromoted fix must fire")
    expect(failures, "#266" in block, "the report must name the stranded commit, not just count it")

    # Same repo, same commit, generous budget: the detector must be quiet again,
    # or "it fires" would only mean "it always fires".
    code, _ = check_repo(_build_stranded(root / "wide", now), ("dev", "main"), now, 24.0 * 30)
    expect(failures, code == 0, "an unpromoted commit inside the budget must stay quiet")

    code, block = check_repo(_build_backflow(root, now), ("dev", "main"), now, budget)
    expect(failures, code == 1, "a real commit on main with no equivalent on dev must fire at once")
    expect(failures, "#77" in block, "the backflow report must name the commit")

    missing = _new_repo(root, "NoDev", now)
    _run(["git", "-C", str(missing), "branch", "-D", "dev"])
    try:
        check_repo(missing, ("dev", "main"), now, budget)
        expect(failures, False, "a missing dev branch must raise, never return clean")
    except CannotDetermineError:
        pass  # expected: this is the raise under test, not a swallowed error


def _self_test() -> int:
    """Exercise the detector against real repositories built on the fly."""
    failures: list[str] = []
    now = int(time.time())
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "wide").mkdir()
        try:
            _self_test_cases(root, now, failures)
        except CannotDetermineError as exc:
            failures.append(f"self-test could not run: {exc}")

        try:
            parse_intent("nothing here")
            failures.append("an unparseable intent table must raise, never return an empty scope")
        except CannotDetermineError:
            pass  # expected: this is the raise under test, not a swallowed error

    return report_self_test(failures)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--workdir", help="where clones are kept (created on first use)")
    ap.add_argument("--clone-base", default=DEFAULT_CLONE_BASE)
    ap.add_argument("--intent", default=str(INTENT_PATH))
    ap.add_argument("--max-unpromoted-hours", type=float, default=DEFAULT_MAX_UNPROMOTED_HOURS)
    ap.add_argument("--now-epoch", type=int)
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.workdir:
        ap.error("--workdir is required (or use --self-test)")

    now = args.now_epoch if args.now_epoch is not None else int(time.time())
    try:
        intent = Path(args.intent).read_text()
    except OSError as exc:
        print(f"CANNOT DETERMINE -- unreadable intent table {args.intent}: {exc}")  # noqa: T201
        return 2
    try:
        return run_check(
            Path(args.workdir), args.clone_base, intent, args.max_unpromoted_hours, now
        )
    except CannotDetermineError as exc:
        print(f"CANNOT DETERMINE -- {exc}")  # noqa: T201
        return 2


if __name__ == "__main__":
    sys.exit(main())
