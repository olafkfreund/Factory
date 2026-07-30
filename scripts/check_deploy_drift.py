#!/usr/bin/env python3
"""Fail loudly when main is built-but-undeployed (CFactory#219, Factory#461).

CANONICAL COPY. This started life in CFactory and now lives in the hub, driven
for every service repo by ``.github/workflows/deploy-drift.yml`` here
(``on: workflow_call``). Factory#461 asked for the watchdog in the three repos
that can actually drift; four hand-written copies of one contract is how
Factory#483 happened, so there is one script and one workflow and the service
repos hold a twelve-line caller each. Nothing repo-specific lives in here - the
gitops path is an input and the repo name is only used to word the recovery
hint.

``deploy.yml`` sets ``cancel-in-progress: true``, which is correct -- an older
commit must not race a newer one to the cluster. The hazard is that a
cancellation is only safe if the run that superseded it actually deploys
something newer, and on 2026-07-26 neither did. Main sat undeployed while every
PR check was green and the run showed ``cancelled``, an outcome nothing alerts
on.

WHY THIS RUNS OUT OF BAND. The obvious fix -- a post-deploy step asserting the
live tag matches the commit -- cannot work for this failure. ``seam-check``
already ``needs: build-push-bump``, so when the run is cancelled the
verification is cancelled with it. Anything that verifies a run from inside
that run dies with it. Only a separate, scheduled observer can see the gap,
which is the same instinct as the CronJob health watchdog in Factory#381: no
news must not read as success.

Being out of band also makes it general. It catches a cancelled run, a skipped
job, an unset GITOPS_PAT, a failed gitops push and a manual revert
identically, because it compares the world against the intent rather than
watching one mechanism.

Usage:
    check_deploy_drift.py --expected-sha <full-sha> --commit-epoch <int> \
        --deployed-tag sha-abc1234 [--grace-minutes 45] [--now-epoch <int>]
    check_deploy_drift.py --self-test

Exit codes:
    0 - deployed, or a deploy is still plausibly in flight
    1 - drift, or the deployed tag could not be read at all
    2 - bad invocation
"""

from __future__ import annotations

import argparse
import os
import sys

# A commit needs time to build and roll out before its absence means anything.
# 45 minutes is comfortably longer than an observed deploy (build + push of two
# images, then the gitops commit) without letting a real stall sit unnoticed
# for hours. Too short and this cries wolf on every merge, which is how a
# watchdog gets muted and stops being a watchdog.
DEFAULT_GRACE_MINUTES = 45


def tag_matches(expected_sha: str, deployed_tag: str) -> bool:
    """Does ``deployed_tag`` name ``expected_sha``?

    The tag is ``sha-<short>`` where the short length is whatever
    ``git rev-parse --short`` chose at build time, and that length grows as the
    repo does. Comparing prefixes rather than fixed-length strings means this
    does not start reporting false drift the day git widens the abbreviation.
    """
    if not deployed_tag.startswith("sha-"):
        return False
    short = deployed_tag[len("sha-") :]
    if not short:
        return False
    return expected_sha.startswith(short)


def check(
    expected_sha: str,
    commit_epoch: int,
    deployed_tag: str,
    now_epoch: int,
    grace_minutes: int = DEFAULT_GRACE_MINUTES,
) -> tuple[int, str]:
    """Return ``(exit_code, message)``."""
    # An empty tag is not "the wrong tag", it is "no answer". It happens when the
    # kustomization moves or is renamed and the awk finds no `newTag:` line, and
    # the grace window below would then report a clean pending: for the first 45
    # minutes after every commit - a watchdog reporting green while reading
    # nothing. Rule 4.7: unverifiable is not verified, so this is red at once and
    # never waits out a grace period it has no business inside.
    if not deployed_tag.strip():
        return 1, (
            "CANNOT VERIFY: factory-gitops returned no deployed tag.\n"
            "The kustomization path is probably wrong or the file no longer has a "
            "`newTag:` line. This is a blind watchdog, not a healthy deploy."
        )

    if tag_matches(expected_sha, deployed_tag):
        return 0, f"OK: deployed tag {deployed_tag} matches main {expected_sha[:8]}"

    age_minutes = (now_epoch - commit_epoch) / 60
    if age_minutes < grace_minutes:
        return 0, (
            f"pending: main {expected_sha[:8]} is {age_minutes:.0f}m old, "
            f"deployed tag is {deployed_tag} (grace {grace_minutes}m)"
        )

    # One script now serves four repos, so the recovery hint must not name one of
    # them. GITHUB_REPOSITORY is set by Actions; the fallback only shows up when
    # someone runs this by hand, where they already know which repo they are in.
    repo = os.environ.get("GITHUB_REPOSITORY", "<owner>/<repo>")
    return 1, (
        f"DEPLOY DRIFT: main is at {expected_sha[:8]} ({age_minutes:.0f}m old) "
        f"but factory-gitops still points at {deployed_tag}.\n"
        "\n"
        "Main is built-but-undeployed. The most likely cause is a deploy run "
        "cancelled by cancel-in-progress where the superseding run did not "
        "publish either (#219); a cancelled run reports neither success nor "
        "failure, so nothing else notices.\n"
        "\n"
        "Recover by re-running the Deploy workflow on main "
        f"(gh workflow run deploy.yml --repo {repo})."
    )


def _self_test() -> int:
    """Exercise the comparison logic without touching any repo or network.

    Uses a failure collector rather than bare asserts: it matches the other
    check_*_drift.py gates in this fleet, it survives `python -O`, and it
    reports every broken case in one run instead of stopping at the first.
    """
    failures: list[str] = []

    def expect(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    full = "e3613aa1122334455"
    expect(tag_matches(full, "sha-e3613aa"), "7-char abbreviation should match")
    expect(tag_matches(full, "sha-e3613aa11"), "longer abbreviation should match")
    expect(not tag_matches(full, "sha-deadbee"), "different sha must not match")
    expect(not tag_matches(full, "latest"), "a non sha- tag must not match")
    expect(not tag_matches(full, "sha-"), "an empty abbreviation must not match")
    # A short-but-wrong tag must fail on content, not pass by being short.
    expect(not tag_matches(full, "sha-e36ffff"), "near-miss sha must not match")

    now = 1_000_000_000
    code, _ = check("abc1234def", now - 99999, "sha-abc1234", now)
    expect(code == 0, "a deployed commit is clean at any age")

    code, msg = check("abc1234def", now - 60, "sha-old0000", now)
    expect(code == 0 and "pending" in msg, "inside grace is not yet a failure")

    code, msg = check("abc1234def", now - 60 * 60, "sha-old0000", now)
    expect(code == 1 and "DEPLOY DRIFT" in msg, "past grace must fail loudly")

    # Exactly at the edge fails, so a stall cannot sit forever one second under
    # the line.
    code, _ = check("abc1234def", now - 45 * 60, "sha-old0000", now, grace_minutes=45)
    expect(code == 1, "the grace boundary itself must fail")

    # No answer from gitops must be red immediately, INSIDE the grace window -
    # the direction a grace period would otherwise paper over (Factory#471).
    code, msg = check("abc1234def", now - 60, "", now)
    expect(code == 1 and "CANNOT VERIFY" in msg, "an empty tag must fail at once")
    code, msg = check("abc1234def", now - 60, "   \n", now)
    expect(code == 1 and "CANNOT VERIFY" in msg, "a whitespace tag must fail at once")

    # The recovery hint names the repo this is running in, so four repos sharing
    # one script do not all tell you to go and redeploy CFactory.
    os.environ["GITHUB_REPOSITORY"] = "olafkfreund/PFactory"
    _, msg = check("abc1234def", now - 60 * 60, "sha-old0000", now)
    expect(
        "--repo olafkfreund/PFactory" in msg,
        "the recovery hint must name the repo it runs in",
    )

    for label in failures:
        print(f"self-test FAILED: {label}")  # noqa: T201
    if failures:
        return 1
    print("self-test OK")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--expected-sha")
    ap.add_argument("--commit-epoch", type=int)
    ap.add_argument("--deployed-tag")
    ap.add_argument("--now-epoch", type=int)
    ap.add_argument("--grace-minutes", type=int, default=DEFAULT_GRACE_MINUTES)
    args = ap.parse_args(argv)

    if args.self_test:
        return _self_test()

    missing = [
        name
        for name, value in (
            ("--expected-sha", args.expected_sha),
            ("--commit-epoch", args.commit_epoch),
            ("--deployed-tag", args.deployed_tag),
        )
        if value is None
    ]
    if missing:
        ap.error(f"missing required argument(s): {', '.join(missing)}")

    now = args.now_epoch
    if now is None:
        import time  # noqa: PLC0415

        now = int(time.time())

    code, message = check(
        args.expected_sha,
        args.commit_epoch,
        args.deployed_tag,
        now,
        args.grace_minutes,
    )
    print(message)  # noqa: T201
    return code


if __name__ == "__main__":
    sys.exit(main())
