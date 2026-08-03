#!/usr/bin/env python3
"""One self-test reporter for the hub's gate scripts (Factory#504).

Every gate here carries a ``--self-test`` that must be observed FAILING before
the gate is trusted (docs/dev/gate-honesty.md), and each one had grown the same
nine-line harness: a counter, a ``req(ok, label)`` that prints PASS/FAIL, and a
summary line. Two copies of it tripped the jscpd clone budget while
``check_chart_vs_gitops`` was being added, which is the budget doing exactly its
job — nobody wrote that duplication deliberately, a copy-paste did.

HUB-ONLY, and deliberately NOT in scripts/ratchet_helpers.py. That module is
vendored byte-exact into four services and gated on it; putting a test-reporting
helper there would ship it fleet-wide to satisfy a hub-local convenience, which
is how a shared surface accretes things nobody outside the hub needs.

Pure stdlib, no side effects on import, so a gate script can depend on it without
inheriting anything.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field


@dataclass
class SelfTest:
    """Collects PASS/FAIL lines and reports a process exit code.

    The label is printed for every case, passing or failing. A self-test that
    prints only its failures gives a reader no way to tell "all six checks ran
    and passed" from "one check ran, and the other five silently stopped
    existing" — the silent-scope-loss shape one level down.
    """

    name: str
    failures: int = 0
    labels: list[str] = field(default_factory=list)

    def req(self, ok: bool, label: str) -> None:
        """Record one case. *ok* false counts a failure; both are printed."""
        self.labels.append(label)
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")  # noqa: T201
        self.failures += not ok

    def finish(self) -> int:
        """Print the summary and return the exit code (0 pass, 1 fail)."""
        verdict = "PASSED" if not self.failures else f"FAILED ({self.failures})"
        print(f"{self.name} self-test: {verdict}")  # noqa: T201
        return 1 if self.failures else 0


def gate_argparser(description: str | None) -> argparse.ArgumentParser:
    """A gate script's parser, pre-wired with ``--self-test``.

    Every watchdog here takes the same first two lines — a RawDescriptionHelp
    parser over the module docstring, and a ``--self-test`` flag — and two copies
    of that preamble tripped the jscpd clone budget while
    ``check_cli_freshness`` was being added. Same finding as :class:`SelfTest`
    above, one function along: nobody wrote that duplication, a copy-paste did.

    Only the shared part lives here. Each gate adds its own flags to the returned
    parser, because a helper that tried to own those would need a flag registry
    and would be a worse trade than the four lines it saved.
    """
    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--self-test", action="store_true", help="run the built-in self-test and exit"
    )
    return parser


def _selftest() -> int:
    """This module's own self-test, because the reporter can lie too.

    Explicit raises rather than `assert`: this file is new, so the lint ratchet
    measures it against a base of zero and every S101 would be net-new. Bare
    asserts also vanish under `python -O`, which for a self-test means the checks
    silently stop running — the exact shape everything here exists to catch.
    """

    def must(ok: bool, why: str) -> None:
        if not ok:
            raise AssertionError(f"selftest_report is broken: {why}")

    probe = SelfTest("selftest-report")
    probe.req(True, "a passing case counts no failure")
    must(probe.failures == 0, "a passing req() counted a failure")
    probe.req(False, "a failing case is counted")
    must(probe.failures == 1, "a failing req() did not count")
    must(
        probe.labels == ["a passing case counts no failure", "a failing case is counted"],
        "every case must be recorded, not just the failures",
    )

    must(SelfTest("clean").finish() == 0, "a clean run must exit 0")
    must(SelfTest("dirty", failures=2).finish() == 1, "a run with failures must not exit 0")

    parser = gate_argparser("doc")
    must(parser.parse_args(["--self-test"]).self_test is True, "--self-test parses")
    must(parser.parse_args([]).self_test is False, "and defaults to off")
    print("selftest_report self-test: PASSED")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
