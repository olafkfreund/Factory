#!/usr/bin/env python3
"""Fail CI when jscpd reports MORE clones than the agreed duplication budget.

The jscpd gate (``.github/workflows/jscpd.yml``, ``.jscpd.json``) detects
copy-paste clones across the Factory hub (epic Factory#154, issue Factory#161).
It started life *advisory* (report-only) so the known, deliberate-for-now
duplication did not instantly redden CI. This script is the ratchet that moves it
from advisory toward *enforcing*: it reads the jscpd JSON report and fails when
the clone count exceeds a fixed BUDGET.

WHY A CLONE-COUNT BUDGET (not jscpd's percentage ``threshold``)
------------------------------------------------------------------
jscpd's built-in ``threshold`` is a single duplicated-*token* percentage for the
whole run. That is coarse: deleting an unrelated large file raises the percentage
without any new copy-paste, and a small net-new paste can hide under the noise.
A clone *count* is the unit the dedup program actually works in ("this paste is
one new clone"), so the budget is the current clone count as a hard ceiling. The
gate fails on NET-NEW duplication (one more clone than today) while grandfathering
the existing debt - a no-regression ratchet.

RATCHET-DOWN PLAN
-----------------
The budget only ever moves DOWN. Each extraction that removes clones (the
``factory_common`` / ``factory-github`` service consumptions, catalog templating)
lowers :data:`CLONE_BUDGET` to the new, smaller count in the same PR. The ceiling
therefore tracks reality and can never silently drift up: a PR that adds a clone
fails until either the paste is removed or the duplication is extracted to the hub
and the budget consciously re-based (which a reviewer sees in the diff).

Usage:
    # Run jscpd first (writes reports/jscpd/jscpd-report.json), then:
    python scripts/check_jscpd_budget.py
    python scripts/check_jscpd_budget.py --report reports/jscpd/jscpd-report.json
    python scripts/check_jscpd_budget.py --self-test

Exit codes:
    0 - clone count is within (<=) the budget, or self-test passed
    1 - clone count EXCEEDS the budget (net-new duplication), or self-test failed
    2 - bad invocation / report missing or unparseable
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

# Current clone count (>=8 lines, >=50 tokens; see .jscpd.json) at the moment the
# gate flipped to enforcing. This is the ceiling: the gate fails on clone 74+.
# RATCHET RULE: this number only ever DECREASES. Lower it (never raise it) in the
# same PR that removes clones via a hub extraction.
CLONE_BUDGET = 73

_DEFAULT_REPORT = Path(__file__).resolve().parent.parent / "reports/jscpd/jscpd-report.json"

# Exit code for a bad invocation (missing / unparseable report).
_EXIT_BAD_INVOCATION = 2


def _emit(message: str) -> None:
    # A CLI gate: its stdout report IS its purpose (T201 intentionally suppressed).
    print(message)  # noqa: T201


def clone_count(report: dict[str, object]) -> int:
    """Return the number of clones jscpd recorded in *report*.

    Prefers the authoritative ``statistics.total.clones`` counter and falls back
    to ``len(duplicates)`` (older report shapes), so the gate keeps working across
    jscpd report-format revisions.
    """
    statistics = report.get("statistics")
    if isinstance(statistics, dict):
        total = statistics.get("total")
        if isinstance(total, dict) and isinstance(total.get("clones"), int):
            return total["clones"]
    duplicates = report.get("duplicates")
    if isinstance(duplicates, list):
        return len(duplicates)
    msg = "report has neither statistics.total.clones nor a duplicates list"
    raise ValueError(msg)


def run_check(report_path: Path, budget: int = CLONE_BUDGET) -> int:
    """Compare the report's clone count against *budget*; emit a report + exit code."""
    if not report_path.is_file():
        _emit(f"ERROR: jscpd report not found: {report_path}")
        _emit("Run jscpd first: npx jscpd@4 --config .jscpd.json .")
        return _EXIT_BAD_INVOCATION
    try:
        report = json.loads(report_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        _emit(f"ERROR: could not read jscpd report {report_path}: {exc}")
        return _EXIT_BAD_INVOCATION
    try:
        count = clone_count(report)
    except ValueError as exc:
        _emit(f"ERROR: unexpected jscpd report shape: {exc}")
        return _EXIT_BAD_INVOCATION

    if count > budget:
        _emit(
            f"jscpd budget EXCEEDED: {count} clones found, budget is {budget} "
            f"(+{count - budget} net-new)."
        )
        _emit(
            "\nThis PR introduces new copy-paste duplication. Either remove the "
            "paste, or extract the shared logic into the hub (shared/factory-common, "
            "shared/factory-github) and consume it. The budget in "
            "scripts/check_jscpd_budget.py only ever ratchets DOWN."
        )
        return 1
    _emit(f"OK: {count} clones <= budget {budget} (no net-new duplication).")
    if count < budget:
        _emit(
            f"NOTE: clone count is {budget - count} below budget - consider "
            f"lowering CLONE_BUDGET to {count} in this PR to tighten the ratchet."
        )
    return 0


def _self_test() -> int:
    """Exercise the budget logic on synthetic reports (no real jscpd run needed)."""
    failures: list[str] = []

    def expect(condition: bool, label: str) -> None:
        if not condition:
            failures.append(label)

    # clone_count: statistics.total.clones is authoritative.
    expected_total = 5
    expect(
        clone_count({"statistics": {"total": {"clones": expected_total}}}) == expected_total,
        "clone_count must read statistics.total.clones",
    )
    # clone_count: falls back to len(duplicates).
    expected_len = 3
    expect(
        clone_count({"duplicates": [{}] * expected_len}) == expected_len,
        "clone_count must fall back to len(duplicates)",
    )
    # clone_count: malformed report raises.
    raised = False
    try:
        clone_count({"nonsense": True})
    except ValueError:
        raised = True
    expect(raised, "clone_count must raise on a shapeless report")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        at_budget = root / "at.json"
        at_budget.write_text(json.dumps({"statistics": {"total": {"clones": 10}}}))
        expect(run_check(at_budget, budget=10) == 0, "count == budget must pass")

        under = root / "under.json"
        under.write_text(json.dumps({"statistics": {"total": {"clones": 7}}}))
        expect(run_check(under, budget=10) == 0, "count < budget must pass")

        over = root / "over.json"
        over.write_text(json.dumps({"statistics": {"total": {"clones": 11}}}))
        expect(run_check(over, budget=10) == 1, "count > budget must FAIL")

        missing = root / "missing.json"
        expect(
            run_check(missing, budget=10) == _EXIT_BAD_INVOCATION,
            "missing report must return 2",
        )

        garbage = root / "garbage.json"
        garbage.write_text("{ not json")
        expect(
            run_check(garbage, budget=10) == _EXIT_BAD_INVOCATION,
            "unparseable report must return 2",
        )

    if failures:
        _emit("SELF-TEST FAILED:")
        for failure in failures:
            _emit(f"  - {failure}")
        return 1
    _emit("SELF-TEST OK: jscpd budget gate behaves as specified.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        default=str(_DEFAULT_REPORT),
        help="path to jscpd JSON report (default: reports/jscpd/jscpd-report.json)",
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=CLONE_BUDGET,
        help=f"max allowed clone count (default: {CLONE_BUDGET})",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the built-in budget-gate self-test, then exit",
    )
    args = parser.parse_args(argv)
    return _self_test() if args.self_test else run_check(Path(args.report), budget=args.budget)


if __name__ == "__main__":
    sys.exit(main())
