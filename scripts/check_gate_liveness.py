#!/usr/bin/env python3
"""Assert every scheduled gate actually ran recently, from outside the gate.

Factory#738 / #737. A scheduled workflow can go silently absent, and none of
the defences a workflow carries INSIDE itself can detect it:

- the cron is wrong, or was edited to a schedule that never fires
- a credential the first step needs was revoked, so the job dies before
  reaching the check it exists to run (Factory#693: two gates sat at zero
  successful runs ever, one across 16 attempts)
- GitHub auto-disables scheduled workflows in a repository with no activity
  for 60 days
- the file was renamed, orphaning the schedule
- the workflow was deleted

``if: always()`` cannot see any of these, because it only runs when the
workflow runs. A workflow cannot report its own non-existence. The detection
has to come from outside, which is what this is.

**Not a pin-freshness check.** ``check_pin_freshness.py``'s ``GATES`` registry
asks "is a vendored module stale". This asks "did the scheduled workflow
execute recently". The surface similarity is misleading and the registries are
deliberately separate (Factory#738 says so explicitly).

Five distinct verdicts, because collapsing them loses the diagnosis:

``absent``      the workflow is not in the repo's workflow list, OR its file is
                gone from the default branch while GitHub still keeps the
                workflow record (see the false positives below)
``disabled``    present but not ``active`` -- the 60-day auto-disable case
``never_ok``    it has runs, but none reached a verdict at all: every one was
                cancelled or died in startup before the first step
``stale``       its newest COMPLETED run is older than the registered budget
``never_green`` it reaches verdicts, on time, and every verdict it has EVER
                reached is red -- zero successes in its whole history

**Liveness is not health, and this gate deliberately does not measure health.**
Recency is scored on completed runs, green OR red. A drift gate is designed to
conclude failure when it finds drift, so scoring liveness on success alone
reports every gate that is currently doing its job as dead. The first version
of this script did exactly that and called ``orphaned-pr-commits.yml`` dead
while it was correctly reporting the four branches in Factory#690.

``never_green`` (Factory#816) does not re-introduce that bug, and the line it
draws is deliberately not "is it red today":

    *currently failing* is none of this gate's business. A gate that passed in
    March and is red this week is doing its job, or has found something; either
    way there is evidence the check CAN pass, so a red run is information
    about the subject.

    *never once green in its entire history* is a statement about the gate
    itself, not about its subject. Nothing in the record shows the check has
    ever been able to conclude PASS, so a red run from it carries no
    information at all -- it is indistinguishable from a gate that cannot run.
    Factory's ``branch-protection-drift.yml`` sat at 21-for-21 failures for
    months on a credential that was never minted, and every one of those runs
    read, from the checks list, exactly like a gate reporting real drift.

So ``orphaned-pr-commits.yml`` (3 successes, 5 failures, newest run red) stays
clean under this verdict, which is the property the first version got wrong.

The cost of the original choice is still stated rather than hidden: this check
cannot distinguish a gate failing TODAY because it found something from a gate
failing today because a credential is missing (Factory#693). Both are red runs.
Telling them apart needs the step-summary tee Factory#720 added, read by a
human or by a per-gate assertion. ``never_green`` narrows that blind spot to
the runs after the first green one, and leaves the rest of it open.

**Exemptions carry a written reason and an issue, and must match something.**
A gate legitimately parked in the never-green state (blocked on a credential
only the repo owner can mint, say) goes in ``NEVER_GREEN_ALLOWED``. Two rules,
both learned the hard way:

- an entry that matches nothing FAILS the gate (Factory#788). A stale exemption
  is not tidy-up debt: it goes on widening coverage over a workflow whose
  problem was fixed, and the next real never-green state is silently exempt.
  ``branch-protection-drift.yml`` is the live case -- it was the headline
  never-green gate in Factory#816 and produced its first success on
  2026-08-19, so an exemption written from that issue's table would already
  be dead.
- a placeholder reason is REJECTED at construction, not accepted (``TODO``,
  ``TBD``, ``N/A``, ``none``, ``grandfathered``, or anything under six words).
  Same shape as PFactory's ``factory_invariants`` registry (Factory#818): a
  generated default that passes the gate ships an unreviewable entry that
  looks reviewed.

**Two false positives, excluded here with the reason, so the next sweep does
not re-report them** (Factory#816 found four occurrences between them):

1. ``workflow_call``-only reusable workflows -- ``deploy-drift.yml`` and
   ``parr-regression.yml`` in this repo -- correctly have zero standalone
   runs. They are not registrable here at all: every ``Gate`` carries a cron,
   and these have no schedule of their own. Verified 2026-08-19: both at
   0 runs, both ``on: workflow_call``.
2. GitHub keeps the workflow RECORD, still reporting ``state: active``, after
   the file is deleted from the default branch. ``Factory/zz-rule47-proof.yml``
   and ``AIFactory/zz-drift-proof.yml`` are both in that state (4 runs, 0
   successes, last run 2026-07-30, file gone). The discriminator is whether
   the file exists on the default branch, which is why ``check`` lists
   ``.github/workflows`` once per run and reports a registered gate whose file
   has gone as ``absent`` rather than believing ``state: active``.

**Counting, not paging.** Run totals come from ``total_count`` on a filtered
one-item query (``runs?status=success&per_page=1``), never from tallying a
page. ``per_page=100`` silently caps: Factory#816's "100 runs" for
``TFactory/copilot-pr-test.yml`` is really 852, so every count taken that way
is a floor rather than a total, and "zero successes in 100" is not the same
claim as "zero successes ever".

The budgets are generously above each cron's period. GitHub delays scheduled
runs under load, sometimes by hours, and a liveness check that cries wolf gets
switched off -- which would reproduce the exact failure it exists to catch.

This gate runs on a schedule AND on every push to main. That is the answer to
"who watches the watchman": it cannot go dark from an auto-disable or a broken
cron without also failing to run on pushes, and a repository with no pushes
and no scheduled runs is not a repository anyone is relying on.

Usage:
    python scripts/check_gate_liveness.py --repo olafkfreund/Factory
    python scripts/check_gate_liveness.py --self-test

Exit codes:
    0 - every registered gate is alive
    1 - at least one gate is absent, disabled, never-completing, or stale
    2 - bad invocation, or the API could not be reached
"""

from __future__ import annotations

import datetime as dt
import re
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass

from gate_evidence import (
    GITHUB_API,
    add_repo_arg,
    expect,
    fetch_github_json,
    gate_fixture,
    report_self_test,
    run_gate_main,
)

_API = GITHUB_API
_NOT_FOUND = 404
# The registry is allowed to grow, never to quietly shrink: a gate removed
# from it stops being watched, which looks exactly like a gate that is fine.
_MIN_REGISTERED_GATES = 12


@dataclass(frozen=True)
class Gate:
    """A scheduled workflow, and how long it may go without producing a verdict."""

    workflow: str
    max_age_hours: int
    cron: str
    why: str


# Budgets are ~3x the cron period for daily and faster gates, and ~1.4x for
# weekly ones (a week is already long enough that 3x would mean a month of
# silence reading as healthy).
GATES: tuple[Gate, ...] = (
    Gate(
        "security-fork-drift.yml",
        72,
        "53 5 * * *",
        "Factory#738 filed this gate as the motivating case: a brand-new "
        "scheduled cross-repo job with no external liveness check.",
    ),
    Gate(
        "branch-protection-drift.yml",
        72,
        "17 6 * * *",
        "Sat at 0 successes across 16 runs (Factory#693) because a secret "
        "was never set. Exactly what never_ok is for.",
    ),
    Gate(
        "cli-freshness.yml",
        240,
        "41 6 * * 1",
        "Also 0/1 in Factory#693, missing GITOPS_PAT.",
    ),
    Gate(
        "orphaned-pr-commits.yml",
        72,
        "53 5 * * *",
        "Working today; it is the source of Factory#690's worklist.",
    ),
    Gate("pin-freshness.yml", 72, "11 5 * * *", "Vendored-module staleness."),
    Gate(
        "chart-vs-gitops.yml", 72, "41 5 * * *", "Named in Factory#738 as having no liveness check."
    ),
    Gate("branch-divergence.yml", 24, "47 */6 * * *", "Six-hourly, so a day of silence is real."),
    Gate(
        "job-watchdog-heartbeat.yml",
        6,
        "23 * * * *",
        "Hourly heartbeat; six hours quiet is a fault.",
    ),
    Gate("parr-nightly.yml", 72, "0 3 * * *", "The end-to-end pipeline run."),
    Gate("model-probe.yml", 240, "0 7 * * 1", "Weekly model availability probe."),
    Gate(
        "codeql-fork-validation.yml",
        72,
        "29 4 * * *",
        "Factory#737. Measures PFactory's four barrier forks against their stock "
        "rules. Registered only after its first confirmed run (2026-08-15, run "
        "31883490034) produced a real cleared/NEW pair -- registering a workflow "
        "with zero runs makes this gate report NEVER RAN on the next push to main.",
    ),
    Gate(
        "codeql-analysis-honesty.yml",
        72,
        "37 4 * * *",
        "Factory#774. Reads the code-scanning API directly for whether the "
        "LATEST CodeQL analysis per category on main is a real scan, not a "
        "cancelled run's zero-rule ghost. Registered only after its first "
        "confirmed run (2026-08-15, run 31888580025) reported all categories "
        "honest -- same reasoning as codeql-fork-validation.yml above.",
    ),
)

# How many red verdicts it takes before "never green" is a finding rather than
# noise. One red run is a flake, a first run mid-rollout, or a gate registered
# the day it landed. Two or more completed verdicts with no success anywhere in
# the history is a pattern, and it is the smallest number that still catches
# cli-freshness.yml, which has exactly two runs and has never passed either.
_NEVER_GREEN_MIN_VERDICTS = 2

# Rejected reasons, and the floor on a real one. Same shape as PFactory's
# factory_invariants registry (Factory#818) rather than a second invention.
_PLACEHOLDER_REASON = re.compile(r"^\s*(todo|tbd|n/?a|none|placeholder|grandfathered)\b", re.I)
_MIN_REASON_WORDS = 6


@dataclass(frozen=True)
class NeverGreenExemption:
    """A gate allowed to sit at zero successes, with who said so and why.

    Validated on construction, so a placeholder cannot reach the registry at
    all: an entry that reads ``reason="TODO"`` passes any check that only asks
    whether the field is set, which is how an unreviewed exemption ends up
    looking reviewed.
    """

    workflow: str
    issue: str
    reason: str

    def __post_init__(self) -> None:
        if not self.issue.strip():
            raise ValueError(
                f"{self.workflow}: a never-green exemption needs an issue reference -- "
                "an exemption nobody filed is one nobody will ever revisit"
            )
        if _PLACEHOLDER_REASON.match(self.reason) or len(self.reason.split()) < _MIN_REASON_WORDS:
            raise ValueError(
                f"{self.workflow}: the exemption reason must say what keeps this gate "
                f"red and why that is not a defect; got {self.reason!r}"
            )


# Gates that have never once passed and are KNOWN not to be defects.
#
# Deliberately short. branch-protection-drift.yml, the headline case in
# Factory#816 at 21-for-21 failures, is NOT here: it produced its first
# success on 2026-08-19, so an exemption for it would already match nothing
# and fail this gate -- which is the rule working, not an inconvenience.
# Empty on purpose. cli-freshness.yml was the last entry: GITOPS_PAT was set on
# the Factory repo on 2026-08-21 and the workflow produced its first success the
# same day, opening the three bump PRs it had never been able to open. Its own
# exemption said "remove this entry when the secret is set", and leaving it would
# now fail this gate for matching nothing -- the same rule that kept
# branch-protection-drift.yml out of here after it went green on 2026-08-19.
NEVER_GREEN_ALLOWED: tuple[NeverGreenExemption, ...] = ()

# A written reason of the shape the rules are meant to ACCEPT, used only by the
# self-test. It is a literal rather than ``_SELF_TEST_GOOD_REASON``
# because the allowlist is legitimately empty whenever every gate is green --
# sampling from it made emptying the list an IndexError, so the rules could only
# be tested while an exemption happened to exist. This is the text of the last
# real entry (cli-freshness.yml, Factory#693), kept so the "a real reason is
# accepted" check still runs against something that genuinely was one.
_SELF_TEST_GOOD_REASON = (
    "Both of its runs died fetching factory-gitops, which needs GITOPS_PAT "
    "-- a cross-repo credential only the repository owner can mint. The gate "
    "logic has never executed, so there is nothing here for a code change to "
    "fix; remove this entry when the secret is set."
)

_EXEMPT_WORKFLOWS = frozenset(e.workflow for e in NEVER_GREEN_ALLOWED)

Fetcher = Callable[[str], object]
# Factory#774: extracted to gate_evidence.fetch_github_json, shared with
# check_codeql_analysis_honesty.py -- this was a byte-identical second copy.
_fetch = fetch_github_json


def _age_hours(timestamp: str, now: dt.datetime) -> float:
    when = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return (now - when).total_seconds() / 3600.0


def _total(fetch: Fetcher, base: str, status: str) -> int:
    """How many runs of *base* ended in *status*, EVER.

    ``total_count`` on a one-item query, not the length of a page: see the
    module docstring's note on ``per_page=100`` silently capping.
    """
    counted = _fetch_json(fetch, f"{base}/runs?status={status}&per_page=1").get("total_count", 0)
    return counted if isinstance(counted, int) else 0


def workflow_files(repo: str, fetch: Fetcher) -> frozenset[str] | None:
    """Workflow filenames present on *repo*'s default branch, or None if unreadable.

    None is propagated as an explicit problem by :func:`check`, never swallowed.
    A listing that failed to load looks exactly like a repo with no deleted
    workflows, and that confusion is the defect Factory#816 is about.
    """
    listing = fetch(f"{_API}/repos/{repo}/contents/.github/workflows")
    if not isinstance(listing, list):
        return None
    return frozenset(str(e["name"]) for e in listing if isinstance(e, dict) and "name" in e)


def _registration_problem(
    gate: Gate, repo: str, fetch: Fetcher, present: frozenset[str] | None
) -> str | None:
    """Whether the workflow exists and can fire at all, before any run is read."""
    try:
        meta = _fetch_json(fetch, f"{_API}/repos/{repo}/actions/workflows/{gate.workflow}")
    except urllib.error.HTTPError as exc:
        if exc.code == _NOT_FOUND:
            return (
                f"{gate.workflow}: ABSENT -- no such workflow in {repo}. "
                "Renamed or deleted, which orphans its schedule silently."
            )
        raise

    # Before believing `state`. GitHub keeps the workflow record, still
    # `active`, after the file is deleted from the default branch -- so a
    # deleted gate reports as healthy until its budget expires, and then as
    # STALE, which sends the reader looking for a broken cron on a file that
    # is not there (Factory#816: zz-rule47-proof.yml, zz-drift-proof.yml).
    if present is not None and gate.workflow not in present:
        return (
            f"{gate.workflow}: ABSENT -- GitHub still lists this workflow as "
            f"{meta.get('state', 'unknown')}, but the file is not on {repo}'s default "
            "branch. The record outlives the file; the schedule does not."
        )

    state = str(meta.get("state", "unknown"))
    if state != "active":
        return (
            f"{gate.workflow}: DISABLED (state={state}). A scheduled workflow "
            "in this state never fires; GitHub sets disabled_inactivity after "
            "60 days without repository activity."
        )
    return None


def assess(
    gate: Gate,
    repo: str,
    fetch: Fetcher,
    now: dt.datetime,
    present: frozenset[str] | None = None,
) -> tuple[str | None, bool]:
    """``(problem or None, has_never_been_green)``.

    The second element is returned even when the gate is exempt from
    ``never_green``, because that is what lets :func:`check` tell an exemption
    that is still doing work from one that matches nothing.
    """
    base = f"{_API}/repos/{repo}/actions/workflows/{gate.workflow}"
    registration = _registration_problem(gate, repo, fetch, present)
    if registration is not None:
        return registration, False

    runs = _fetch_json(fetch, f"{base}/runs?per_page=100")
    raw = runs.get("workflow_runs", [])
    items: list[dict[str, object]] = (
        [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []
    )
    if not items:
        return (
            f"{gate.workflow}: NEVER RAN -- zero runs recorded, though the schedule is active.",
            False,
        )

    # Recency is measured on COMPLETED runs, green or red -- not on green ones
    # only. A drift gate is DESIGNED to conclude failure when it finds drift,
    # so scoring liveness on success would report every gate that is currently
    # doing its job as dead. Liveness is not health: whether the findings are
    # real is the gate's own business, and this check has no way to tell a
    # correct red from a broken one.
    completed = [r for r in items if r.get("conclusion") in ("success", "failure")]
    if not completed:
        return (
            f"{gate.workflow}: NEVER COMPLETED -- {len(items)} run(s), none reached a "
            "verdict (cancelled, or a startup failure before the first step).",
            False,
        )

    # Whole-history totals, on the same "reached a verdict" definition the
    # recency check above uses -- `status=completed` would fold in cancelled
    # and skipped runs, which is a different question with a different answer.
    greens = _total(fetch, base, "success")
    reds = _total(fetch, base, "failure")
    never_green = greens == 0 and reds >= _NEVER_GREEN_MIN_VERDICTS

    newest = max(completed, key=lambda r: str(r.get("created_at", "")))
    age = _age_hours(str(newest["created_at"]), now)
    if age > gate.max_age_hours:
        return (
            f"{gate.workflow}: STALE -- newest completed run is {age:.0f}h old, "
            f"budget {gate.max_age_hours}h (cron {gate.cron}).",
            never_green,
        )
    if never_green and gate.workflow not in _EXEMPT_WORKFLOWS:
        return (
            f"{gate.workflow}: NEVER GREEN -- {reds} verdict(s), 0 successes in its "
            "entire history. Being red today is fine and this gate does not judge it; "
            "never having been green means nothing shows the check CAN pass, so its "
            "red runs carry no information. Fix it, or add a "
            "NeverGreenExemption with a written reason and an issue.",
            True,
        )
    return None, never_green


def verdict(
    gate: Gate,
    repo: str,
    fetch: Fetcher,
    now: dt.datetime,
    present: frozenset[str] | None = None,
) -> str | None:
    """None if the gate is alive, else a one-line problem description."""
    return assess(gate, repo, fetch, now, present)[0]


def evidence(gate: Gate, repo: str, fetch: Fetcher, now: dt.datetime) -> str:
    """The line printed for a gate that PASSED.

    The pass path has to cite what it compared, not just how many things it
    compared (``docs/dev/gate-honesty.md``: a count is not a check). "10 gates
    are alive" is unfalsifiable by a reader; "security-fork-drift.yml, newest
    verdict 4h ago, budget 72h" can be checked against the Actions tab.
    """
    base = f"{_API}/repos/{repo}/actions/workflows/{gate.workflow}"
    runs = _fetch_json(fetch, f"{base}/runs?per_page=100")
    raw = runs.get("workflow_runs", [])
    items = [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []
    completed = [r for r in items if r.get("conclusion") in ("success", "failure")]
    if not completed:
        return f"{gate.workflow}: no completed run"
    newest = max(completed, key=lambda r: str(r.get("created_at", "")))
    age = _age_hours(str(newest["created_at"]), now)
    return (
        f"{gate.workflow}: newest verdict {age:.0f}h ago "
        f"({newest.get('conclusion')}), budget {gate.max_age_hours}h, cron {gate.cron}"
    )


def _fetch_json(fetch: Fetcher, url: str) -> dict[str, object]:
    result = fetch(url)
    return result if isinstance(result, dict) else {}


def _stale_exemptions(
    never_green: frozenset[str],
    exemptions: tuple[NeverGreenExemption, ...] = NEVER_GREEN_ALLOWED,
) -> list[str]:
    """Exemptions that suppressed nothing this run (Factory#788).

    ``exemptions`` is injectable so the rule can be tested when the live
    allowlist is empty -- which is its healthy state, and was exactly when the
    test for it stopped exercising anything (it asserted against
    NEVER_GREEN_ALLOWED directly and returned [] once the last entry went).
    """
    return [
        f"{e.workflow}: never-green exemption ({e.issue}) matches nothing -- the gate "
        "has passed since, or the workflow was renamed. Delete the entry; while it "
        "stands, the next real never-green state on that workflow is silently exempt."
        for e in exemptions
        if e.workflow not in never_green
    ]


def check(repo: str, fetch: Fetcher | None = None, now: dt.datetime | None = None) -> list[str]:
    fetch = fetch or _fetch
    now = now or dt.datetime.now(dt.UTC)
    present = workflow_files(repo, fetch)
    problems: list[str] = []
    if present is None:
        # Explicit, not silent. Skipping the deleted-file discriminator would
        # make an unreadable listing indistinguishable from a repo with no
        # deleted workflows -- "printed nothing" reading as "found nothing" is
        # the exact defect Factory#816 hit inside its own investigation.
        problems.append(
            f"could not list {repo}'s .github/workflows on the default branch, so a "
            "workflow whose file was deleted cannot be told from a live one. Unknown, "
            "not clean."
        )
    never_green: set[str] = set()
    for gate in GATES:
        problem, was_never_green = assess(gate, repo, fetch, now, present)
        if problem is not None:
            problems.append(problem)
        if was_never_green:
            never_green.add(gate.workflow)
    problems.extend(_stale_exemptions(frozenset(never_green)))
    return problems


def run_check(repo: str) -> int:
    now = dt.datetime.now(dt.UTC)
    problems = check(repo, None, now)
    # Enumerated on BOTH paths. Printing the subject only when something is
    # wrong covers the direction that costs an investigation and leaves the
    # direction that costs a missing control: a registry someone shortened
    # reports fewer gates, all green, and says nothing about the one it
    # stopped watching.
    print(f"Gates registered: {len(GATES)}")  # noqa: T201
    for gate in GATES:
        print(f"  * {evidence(gate, repo, _fetch, now)}")  # noqa: T201
    # Enumerated on the pass path for the same reason the gates are: an
    # exemption is a hole in this gate's coverage, and a hole nobody prints is
    # a hole nobody revisits.
    print(f"Never-green exemptions: {len(NEVER_GREEN_ALLOWED)}")  # noqa: T201
    for exemption in NEVER_GREEN_ALLOWED:
        print(f"  * {exemption.workflow} ({exemption.issue}): {exemption.reason}")  # noqa: T201
    if problems:
        print("GATE LIVENESS -- one or more scheduled gates are not running:")  # noqa: T201
        for problem in problems:
            print(f"  - {problem}")  # noqa: T201
        print(  # noqa: T201
            "\nA gate that does not run reports nothing, which reads as "
            "'found no problems'. Fix the schedule, the credential, or the "
            "registration in scripts/check_gate_liveness.py."
        )
        return 1
    print(f"OK: all {len(GATES)} registered gates produced a verdict within budget.")  # noqa: T201
    return 0


def _self_test() -> int:
    now = dt.datetime(2026, 8, 15, 12, 0, tzinfo=dt.UTC)
    gate = Gate("x.yml", 72, "0 5 * * *", "fixture")

    def responder(meta: object, runs: object, greens: int = 1, reds: int = 0) -> Fetcher:
        def fetch(url: str) -> object:
            if url.endswith("/contents/.github/workflows"):
                return [{"name": gate.workflow}]
            if "status=success" in url:
                return {"total_count": greens}
            if "status=failure" in url:
                return {"total_count": reds}
            if url.endswith("/runs?per_page=100"):
                if isinstance(runs, Exception):
                    raise runs
                return runs
            if isinstance(meta, Exception):
                raise meta
            return meta

        return fetch

    def fresh(hours: int) -> str:
        return (now - dt.timedelta(hours=hours)).isoformat().replace("+00:00", "Z")

    with gate_fixture() as (_root, failures):
        alive = responder(
            {"state": "active"},
            {"workflow_runs": [{"conclusion": "success", "created_at": fresh(5)}]},
        )
        expect(failures, verdict(gate, "o/r", alive, now) is None, "a fresh green run is alive")

        missing = responder(
            urllib.error.HTTPError("u", 404, "Not Found", {}, None),  # type: ignore[arg-type]
            {},
        )
        problem = verdict(gate, "o/r", missing, now)
        expect(
            failures, problem is not None and "ABSENT" in problem, "a deleted workflow is caught"
        )

        disabled = responder({"state": "disabled_inactivity"}, {"workflow_runs": []})
        problem = verdict(gate, "o/r", disabled, now)
        expect(
            failures,
            problem is not None and "DISABLED" in problem,
            "the 60-day auto-disable is caught",
        )

        never = responder({"state": "active"}, {"workflow_runs": []})
        problem = verdict(gate, "o/r", never, now)
        expect(failures, problem is not None and "NEVER RAN" in problem, "zero runs is caught")

        # A gate that runs and correctly reports findings concludes FAILURE.
        # It is alive. Getting this backwards is the bug the first version of
        # this script shipped with: it called orphaned-pr-commits.yml dead
        # while that gate was correctly reporting Factory#690's four branches.
        red = responder(
            {"state": "active"},
            {
                "workflow_runs": [
                    {"conclusion": "failure", "created_at": fresh(2)} for _ in range(16)
                ]
            },
            greens=1,
            reds=16,
        )
        expect(
            failures,
            verdict(gate, "o/r", red, now) is None,
            "a gate concluding red is alive -- liveness is not health",
        )

        # But runs that never reach a verdict are not liveness either.
        stillborn = responder(
            {"state": "active"},
            {
                "workflow_runs": [
                    {"conclusion": "cancelled", "created_at": fresh(2)} for _ in range(9)
                ]
            },
        )
        problem = verdict(gate, "o/r", stillborn, now)
        expect(
            failures,
            problem is not None and "NEVER COMPLETED" in problem,
            "runs that only ever cancel must not read as alive",
        )

        stale = responder(
            {"state": "active"},
            {"workflow_runs": [{"conclusion": "success", "created_at": fresh(100)}]},
        )
        problem = verdict(gate, "o/r", stale, now)
        expect(
            failures, problem is not None and "STALE" in problem, "an over-budget gate is caught"
        )

        # A green run inside budget must win even when newer red runs exist --
        # otherwise a gate that fails intermittently reads as dead.
        mixed = responder(
            {"state": "active"},
            {
                "workflow_runs": [
                    {"conclusion": "failure", "created_at": fresh(1)},
                    {"conclusion": "success", "created_at": fresh(10)},
                ]
            },
        )
        expect(
            failures,
            verdict(gate, "o/r", mixed, now) is None,
            "a recent completed run counts regardless of its conclusion",
        )

        # Factory#816. Zero successes across the whole history, with the
        # newest run perfectly fresh -- every other verdict here reads clean.
        barren = responder(
            {"state": "active"},
            {"workflow_runs": [{"conclusion": "failure", "created_at": fresh(2)}]},
            greens=0,
            reds=21,
        )
        problem = verdict(gate, "o/r", barren, now)
        expect(
            failures,
            problem is not None and "NEVER GREEN" in problem,
            "a gate that has never once passed is caught",
        )

        # ...but a SINGLE red verdict is not that claim. A gate registered the
        # day it landed would otherwise be condemned by its first bad run.
        firstred = responder(
            {"state": "active"},
            {"workflow_runs": [{"conclusion": "failure", "created_at": fresh(2)}]},
            greens=0,
            reds=1,
        )
        expect(
            failures,
            verdict(gate, "o/r", firstred, now) is None,
            "one red verdict is not a history of never passing",
        )

        # The record outlives the file: still `active`, still with runs, but
        # deleted from the default branch (Factory#816's zz-*-proof pair).
        problem = verdict(gate, "o/r", alive, now, frozenset({"other.yml"}))
        expect(
            failures,
            problem is not None and "ABSENT" in problem,
            "a workflow whose file was deleted must not read as active",
        )
        expect(
            failures,
            verdict(gate, "o/r", alive, now, frozenset({gate.workflow})) is None,
            "a workflow whose file IS on the default branch stays clean",
        )

        # An unreadable listing is unknown, not clean.
        blind = _self_test_check(responder({"state": "active"}, {"workflow_runs": []}))
        expect(
            failures,
            any("Unknown, not clean" in p for p in blind),
            "an unreadable workflow listing must be reported, not skipped",
        )

        _self_test_exemptions(failures)

        expect(
            failures,
            len(GATES) >= _MIN_REGISTERED_GATES,
            "the registry must not silently shrink",
        )

    return report_self_test(failures)


def _self_test_exemptions(failures: list[str]) -> None:
    """Exemption hygiene: placeholders cannot be written, dead entries cannot hide.

    Split out of :func:`_self_test` on the seam that matters rather than to fit
    a statement limit: nothing here touches the run-history fixture, and the
    two rules it enforces are what stop the allowlist from becoming the hole
    (Factory#788, Factory#818).
    """
    expect(
        failures,
        _rejects_exemption(issue="", reason=_SELF_TEST_GOOD_REASON),
        "an exemption with no issue reference is rejected",
    )
    expect(failures, _rejects_reason("TODO fix later"), "a TODO reason is rejected")
    expect(failures, _rejects_reason("N/A"), "an N/A reason is rejected")
    expect(failures, _rejects_reason("grandfathered"), "a grandfathered reason is rejected")
    expect(failures, _rejects_reason("blocked on a secret"), "a too-short reason is rejected")
    expect(
        failures,
        not _rejects_reason(_SELF_TEST_GOOD_REASON),
        "a real written reason is accepted -- or this proves only that everything fails",
    )
    expect(
        failures,
        len(_stale_exemptions(frozenset())) == len(NEVER_GREEN_ALLOWED),
        "an exemption that suppressed nothing must be reported",
    )
    expect(
        failures,
        _stale_exemptions(_EXEMPT_WORKFLOWS) == [],
        "an exemption that is still doing work must not be reported",
    )


def _rejects_exemption(issue: str, reason: str) -> bool:
    """True if an exemption with this *issue* and *reason* is refused."""
    try:
        NeverGreenExemption(workflow="x.yml", issue=issue, reason=reason)
    except ValueError:
        return True
    return False


def _rejects_reason(reason: str) -> bool:
    """True if *reason* is refused as an exemption justification."""
    return _rejects_exemption(issue="Factory#1", reason=reason)


def _self_test_check(fetch: Fetcher) -> list[str]:
    """``check`` against a fetcher whose ``.github/workflows`` listing is unusable."""

    def blind(url: str) -> object:
        return {} if url.endswith("/contents/.github/workflows") else fetch(url)

    return check("o/r", blind, dt.datetime(2026, 8, 15, 12, 0, tzinfo=dt.UTC))


def main(argv: list[str] | None = None) -> int:
    return run_gate_main(
        "Assert every scheduled gate ran successfully and recently.",
        _self_test,
        lambda args: run_check(args.repo),
        argv,
        configure=add_repo_arg,
    )


if __name__ == "__main__":
    raise SystemExit(main())
