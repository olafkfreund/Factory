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

Four distinct verdicts, because collapsing them loses the diagnosis:

``absent``      the workflow file is not in the repo's workflow list at all
``disabled``    present but not ``active`` -- the 60-day auto-disable case
``never_ok``    it has runs, but none reached a verdict at all: every one was
                cancelled or died in startup before the first step
``stale``       its newest COMPLETED run is older than the registered budget

**Liveness is not health, and this gate deliberately does not measure health.**
Recency is scored on completed runs, green OR red. A drift gate is designed to
conclude failure when it finds drift, so scoring liveness on success alone
reports every gate that is currently doing its job as dead. The first version
of this script did exactly that and called ``orphaned-pr-commits.yml`` dead
while it was correctly reporting the four branches in Factory#690.

The cost of that choice is stated rather than hidden: this check cannot
distinguish a gate failing because it found something from a gate failing
because a credential is missing (Factory#693). Both are red runs. Telling them
apart needs the step-summary tee Factory#720 added, read by a human or by a
per-gate assertion -- not by a generic liveness sweep. What this catches is the
strictly worse case the summary tee cannot: a gate producing no runs at all.

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
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from gate_evidence import expect, gate_argparser, gate_fixture, parse_or_self_test, report_self_test

_API = "https://api.github.com"
_NOT_FOUND = 404
# The registry is allowed to grow, never to quietly shrink: a gate removed
# from it stops being watched, which looks exactly like a gate that is fine.
_MIN_REGISTERED_GATES = 11


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
)

Fetcher = Callable[[str], object]


def _fetch(url: str, *, timeout: int = 20) -> object:
    """GET and parse JSON. Uses GITHUB_TOKEN when present (private repos and
    a far higher rate limit); works unauthenticated against public ones."""
    # Enforced rather than suppressed. Every URL here is built from the _API
    # constant, so this can only fire if someone later threads a caller-
    # supplied URL through -- at which point `file:///etc/shadow` would be a
    # readable local file, not a failed HTTP request.
    if not url.startswith(f"{_API}/"):
        raise ValueError(f"refusing to fetch a URL outside {_API}: {url!r}")
    request = urllib.request.Request(  # noqa: S310 - scheme enforced immediately above
        url, headers={"Accept": "application/vnd.github+json"}
    )
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def _age_hours(timestamp: str, now: dt.datetime) -> float:
    when = dt.datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return (now - when).total_seconds() / 3600.0


def verdict(gate: Gate, repo: str, fetch: Fetcher, now: dt.datetime) -> str | None:
    """None if the gate is alive, else a one-line problem description."""
    base = f"{_API}/repos/{repo}/actions/workflows/{gate.workflow}"
    try:
        meta = _fetch_json(fetch, base)
    except urllib.error.HTTPError as exc:
        if exc.code == _NOT_FOUND:
            return (
                f"{gate.workflow}: ABSENT -- no such workflow in {repo}. "
                "Renamed or deleted, which orphans its schedule silently."
            )
        raise

    state = str(meta.get("state", "unknown"))
    if state != "active":
        return (
            f"{gate.workflow}: DISABLED (state={state}). A scheduled workflow "
            "in this state never fires; GitHub sets disabled_inactivity after "
            "60 days without repository activity."
        )

    runs = _fetch_json(fetch, f"{base}/runs?per_page=100")
    raw = runs.get("workflow_runs", [])
    items: list[dict[str, object]] = (
        [r for r in raw if isinstance(r, dict)] if isinstance(raw, list) else []
    )
    if not items:
        return f"{gate.workflow}: NEVER RAN -- zero runs recorded, though the schedule is active."

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
            "verdict (cancelled, or a startup failure before the first step)."
        )

    newest = max(completed, key=lambda r: str(r.get("created_at", "")))
    age = _age_hours(str(newest["created_at"]), now)
    if age > gate.max_age_hours:
        return (
            f"{gate.workflow}: STALE -- newest completed run is {age:.0f}h old, "
            f"budget {gate.max_age_hours}h (cron {gate.cron})."
        )
    return None


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


def check(repo: str, fetch: Fetcher | None = None, now: dt.datetime | None = None) -> list[str]:
    fetch = fetch or _fetch
    now = now or dt.datetime.now(dt.UTC)
    return [problem for gate in GATES if (problem := verdict(gate, repo, fetch, now)) is not None]


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

    def responder(meta: object, runs: object) -> Fetcher:
        def fetch(url: str) -> object:
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

        expect(
            failures,
            len(GATES) >= _MIN_REGISTERED_GATES,
            "the registry must not silently shrink",
        )

    return report_self_test(failures)


def main(argv: list[str] | None = None) -> int:
    parser = gate_argparser("Assert every scheduled gate ran successfully and recently.")
    parser.add_argument("--repo", default="olafkfreund/Factory", help="owner/name to inspect")
    code, args = parse_or_self_test(parser, argv, _self_test)
    if code is not None or args is None:
        return code if code is not None else 2
    try:
        return run_check(args.repo)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"ERROR: could not reach the GitHub API: {exc}")  # noqa: T201
        # 2, not 0. An unreachable API is an unknown verdict, and an unknown
        # verdict must never be reported as a healthy fleet.
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
