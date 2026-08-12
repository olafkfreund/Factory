#!/usr/bin/env python3
"""Find commits pushed to a branch AFTER its pull request merged (factory-gitops#187).

An agent opens a PR, the PR is merged quickly -- factory-gitops#180 merged 96
seconds after opening -- and the agent, still mid-task, writes one more commit
and pushes it to the same branch. That branch no longer has an open PR, so the
commit sits there permanently. EVERY signal says success: the PR merged, CI was
green, ``git push`` succeeded, and the branch genuinely contains the commit.
Only the default branch does not, and nothing the author looks at says so.

Two commits were lost this way on 2026-08-07, both +2 minutes after their merge.
Both were prose, so nothing broke -- that is luck, not mitigation. The same
window over a Kyverno policy lands a mirror-list entry without its glob, which
is factory-gitops#181 through a different door and passes CI, because the gates
validate each policy in isolation rather than whether the pair is coherent.

WHY NOT ``git merge-base --is-ancestor <tip> origin/main``. Because it is wrong
for every squash-merging repo, which is all of them here. A squash folds a PR's
commits into ONE new commit with a NEW sha, so the branch tip is never an
ancestor of the default branch even on a perfect merge. factory-gitops#187
measured this on three PRs (#178 ``b2e07da`` -> ``cb25b1b``, #179 ``e6e5f6f`` ->
``ac09ced``, #180 ``50b70a3`` -> ``d4eddcf``). That check returns non-zero for
EVERY correctly merged PR in the repo -- a control that fires on the happy path,
which is the fastest way to get a control ignored.

WHY NOT ``git cherry`` / patch-id, which is what check_branch_divergence.py uses
and is right THERE. Patch-id pairs commits with identical diffs regardless of
sha. A squash of a multi-commit PR has the COMBINED diff, so it matches none of
the originals individually, and every multi-commit squashed PR would look
unmerged. The primitive that kills false positives for dev-vs-main creates them
here.

WHAT IS COMPARED INSTEAD. The branch tip against the ``headRefOid`` of the most
recent pull request opened from that branch. GitHub freezes ``headRefOid`` on a
merged, closed PR and it never advances again -- factory-gitops#187 v2 read that
as the bug ("PR 180 head STILL stale after 10min") when it is exactly the
property that makes this work. Equal means everything on the branch went into
the merge. Ahead means the extra commits were in no pull request at all.

This is the one test that distinguishes the two real cases, and it does not care
how the merge was performed.

WHY THE MOST RECENT PR, not any merged one. If the author noticed and opened a
second PR from the same branch, that PR is the most recent and its head is the
new tip -- so a correctly-recovered branch compares equal and stays silent. An
OPEN most-recent PR is skipped outright: work in flight is not orphaned.

WHY A GRACE WINDOW. Pushing to a branch seconds after a merge and opening the
follow-up PR a minute later is a normal, correct sequence. Alarming inside that
window would fire on the recovery as well as the accident. The default grace is
generous for the same reason the pin-freshness budget is: one non-event is all
it takes to train everyone to ignore the signal.

REPORTS, NEVER FIXES. The remedy is a human opening a PR (or deciding the commit
was superseded). Nothing here pushes, merges or deletes.

NO ISSUE IS FILED, matching pin-freshness.yml and branch-divergence.yml. A
failing scheduled workflow on a repo you own already emails you and shows red in
the Actions tab; an auto-filed issue needs auto-closing logic, which is a second
small state machine that rots.

Usage:
    python3 scripts/check_orphaned_pr_commits.py                 # whole fleet
    python3 scripts/check_orphaned_pr_commits.py --repo factory-gitops
    python3 scripts/check_orphaned_pr_commits.py --grace-hours 0 # no grace
    python3 scripts/check_orphaned_pr_commits.py --self-test     # offline

Exit codes: 0 = nothing orphaned, 1 = orphaned commits found, 2 = could not
determine (missing gh, API failure). A check that cannot read what it compares
against FAILS -- it never reports green (standards rule 4.7).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta

# Sibling import: this runs out of a full hub checkout, exactly as
# check_branch_divergence.py imports the same helper. No sys.path juggling --
# `python3 scripts/x.py` already puts scripts/ first on the path.
from gate_evidence import report_self_test

OWNER = "olafkfreund"
REPOS = ("Factory", "PFactory", "TFactory", "AIFactory", "CFactory", "factory-gitops")

# GitHub's list endpoints cap at 100 per page, so a short page is the last page.
_PAGE_SIZE = 100

# How long a commit must sit on a merged branch before it is reported. Pushing
# right after a merge and opening the follow-up PR a minute later is the CORRECT
# recovery, and alarming on it would fire on the fix as loudly as on the fault.
DEFAULT_GRACE_HOURS = 12.0


def eprint(*a: object) -> None:
    print(*a, file=sys.stderr)  # noqa: T201


def say(msg: str) -> None:
    print(msg)  # noqa: T201


def die(msg: str) -> None:
    eprint(f"FATAL: {msg}")
    sys.exit(2)


def gh_json(path: str) -> object:
    """One authenticated API read. Any failure is fatal, never an empty result."""
    try:
        res = subprocess.run(  # noqa: S603
            ["gh", "api", path],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        die("`gh` is not on PATH -- this check cannot read anything without it")
    if res.returncode != 0:
        die(f"gh api {path} failed: {res.stderr.strip()}")
    return json.loads(res.stdout)


def parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def classify(
    branch: str, tip: str, prs: list[dict], now: datetime, grace_hours: float
) -> dict | None:
    """Pure. Return a finding for an orphaned branch, else None.

    ``prs`` is every PR opened from this branch, in any state. Only the most
    recent one decides -- see the module docstring.
    """
    # A branch that never had a PR is ordinary work in progress, not an orphan.
    # This check is about the gap AFTER a merge, nothing else.
    if not prs:
        return None

    newest = max(prs, key=lambda p: p.get("number", 0))
    merged = parse_ts(newest.get("merged_at"))
    quiet = (
        # In flight: whatever is pushed now still has a way in.
        (newest.get("state") or "").upper() == "OPEN"
        # Closed without merging. Abandoned, not orphaned -- those commits were
        # never expected to land, and saying otherwise is noise.
        or not newest.get("merged_at")
        # Everything on the branch is exactly what merged. The common case, so a
        # false positive here would bury every true one.
        or newest.get("head_sha") == tip
        # An unparseable timestamp means we cannot age it: never alarm on doubt.
        or merged is None
    )
    if quiet:
        return None

    # Still inside the window where pushing and then opening a follow-up PR is
    # the correct recovery rather than the fault.
    age_hours = (now - merged).total_seconds() / 3600.0
    if age_hours < grace_hours:
        return None

    return {
        "branch": branch,
        "tip": tip,
        "pr": newest.get("number"),
        "pr_head": newest.get("head_sha"),
        "merged_at": newest.get("merged_at"),
        "hours_since_merge": age_hours,
    }


def branches_of(repo: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    page = 1
    while True:
        rows = gh_json(f"repos/{OWNER}/{repo}/branches?per_page={_PAGE_SIZE}&page={page}")
        if not isinstance(rows, list) or not rows:
            break
        out.extend((b["name"], b["commit"]["sha"]) for b in rows)
        if len(rows) < _PAGE_SIZE:
            break
        page += 1
    return out


def prs_for(repo: str, branch: str) -> list[dict]:
    rows = gh_json(
        f"repos/{OWNER}/{repo}/pulls?state=all&head={OWNER}:{branch}&per_page={_PAGE_SIZE}"
    )
    if not isinstance(rows, list):
        return []
    return [
        {
            "number": p.get("number"),
            "state": p.get("state"),
            "merged_at": p.get("merged_at"),
            "head_sha": (p.get("head") or {}).get("sha"),
        }
        for p in rows
    ]


def scan(repo: str, now: datetime, grace_hours: float) -> list[dict]:
    meta = gh_json(f"repos/{OWNER}/{repo}")
    if not isinstance(meta, dict):
        die(f"repos/{OWNER}/{repo} did not return an object")
    # `main` and `dev` are skipped alongside the declared default because the
    # fleet promotes dev -> main: both are long-lived and neither is ever the
    # head of a PR whose merge could strand a commit. branch-divergence.yml is
    # what watches the gap between those two.
    long_lived = {meta.get("default_branch"), "main", "dev"}
    findings: list[dict] = []
    branches = branches_of(repo)
    for name, tip in branches:
        if name in long_lived:
            continue
        f = classify(name, tip, prs_for(repo, name), now, grace_hours)
        if f is not None:
            f["repo"] = repo
            findings.append(f)
    eprint(f"  {repo}: {len(branches)} branch(es) examined, {len(findings)} orphaned")
    return findings


def _expect(failures: list[str], condition: bool, label: str) -> None:
    if not condition:
        failures.append(label)


def self_test() -> int:
    """The rules that decide whether a human is told. Offline.

    Failures are collected rather than asserted, so one run reports every broken
    case and ``python -O`` cannot silence the gate (the house pattern, see
    gate_evidence.report_self_test).
    """
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    old = (now - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
    recent = (now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    grace = DEFAULT_GRACE_HOURS
    failures: list[str] = []

    def pr(n, state="closed", merged=old, head="aaa"):
        return {"number": n, "state": state, "merged_at": merged, "head_sha": head}

    # THE REAL CASE: factory-gitops#180. Merged, then pushed to 2m32s later.
    f = classify("fix/563-odin-now-public", "3fd8ca1a", [pr(180, head="50b70a32")], now, grace)
    _expect(failures, f is not None, "the real factory-gitops#180 orphan must fire")
    if f is not None:
        _expect(
            failures,
            f["tip"] == "3fd8ca1a" and f["pr_head"] == "50b70a32",
            "the finding must carry both shas, so the reader can diff them",
        )

    # A correctly merged branch: tip IS the merged head. The commonest case by
    # far, so a false positive here would bury every true one.
    _expect(
        failures,
        classify("b", "50b70a32", [pr(180, head="50b70a32")], now, grace) is None,
        "a correctly merged branch must stay silent",
    )

    # Work in flight must never be called orphaned.
    _expect(
        failures,
        classify("b", "zzz", [pr(1, state="open", merged=None)], now, grace) is None,
        "an open PR is work in flight, not an orphan",
    )

    # RECOVERY: the author noticed and opened a second PR from the same branch.
    # The newest PR's head is the new tip, so this goes quiet -- a check that
    # keeps shouting after the fix is one people learn to close unread.
    _expect(
        failures,
        classify("b", "ccc", [pr(1, head="aaa"), pr(2, head="ccc")], now, grace) is None,
        "a follow-up PR that lands the commits must silence the finding",
    )
    # ...and it is the NEWEST PR that decides, not merely "some PR matches".
    _expect(
        failures,
        classify("b", "ddd", [pr(1, head="ddd"), pr(2, head="ccc")], now, grace) is not None,
        "an OLD PR matching the tip must not excuse a newer merge that did not",
    )

    # Closed unmerged is abandoned, not orphaned.
    _expect(
        failures,
        classify("b", "zzz", [pr(1, merged=None)], now, grace) is None,
        "a PR closed without merging leaves an abandoned branch, not an orphan",
    )

    # A branch that never had a PR is ordinary work in progress.
    _expect(
        failures,
        classify("b", "zzz", [], now, grace) is None,
        "a branch with no PR at all is ordinary WIP",
    )

    # GRACE: inside the window, pushing and then opening a follow-up PR is the
    # correct recovery and must stay silent; outside it, the same shape reports.
    _expect(
        failures,
        classify("b", "zzz", [pr(1, merged=recent)], now, grace) is None,
        "a just-merged branch is inside the grace window",
    )
    _expect(
        failures,
        classify("b", "zzz", [pr(1, merged=recent)], now, 0.0) is not None,
        "with no grace, the same branch must fire -- proving grace is what muted it",
    )

    # An unparseable merge timestamp must not be reported: never alarm on doubt.
    _expect(
        failures,
        classify("b", "zzz", [pr(1, merged="not-a-date")], now, grace) is None,
        "an unreadable merged_at must not produce a finding",
    )

    return report_self_test(failures)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append", help="limit to this repo (repeatable)")
    ap.add_argument("--grace-hours", type=float, default=DEFAULT_GRACE_HOURS)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    repos = tuple(args.repo) if args.repo else REPOS
    now = datetime.now(UTC)
    eprint(f"scanning {len(repos)} repo(s), grace={args.grace_hours:g}h")
    findings: list[dict] = []
    for r in repos:
        findings.extend(scan(r, now, args.grace_hours))

    if not findings:
        say(
            f"ok  no branch carries commits pushed after its PR merged "
            f"({len(repos)} repo(s) scanned)"
        )
        return 0

    for f in sorted(findings, key=lambda x: (x["repo"], x["branch"])):
        say(
            f"::error::{f['repo']} `{f['branch']}` is at {f['tip'][:8]} but PR "
            f"#{f['pr']} merged at {f['pr_head'][:8]} ({f['hours_since_merge']:.0f}h "
            f"ago). Those commits are in no pull request and are not on the "
            f"default branch. Open a PR for them, or delete the branch if they "
            f"were superseded."
        )
    say(f"{len(findings)} orphaned branch(es)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
