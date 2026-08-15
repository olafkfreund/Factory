#!/usr/bin/env python3
"""Compare a barrier-aware CodeQL fork against its stock rule, in both directions.

Factory#737. Gate 2 (``check_codeql_exclude_pairing.py``) asks a STRUCTURAL
question -- does every excluded stock rule have a ``-sanitized`` query with a
doc comment -- and answers it in milliseconds on every commit. That trade is
deliberate and stays. What it explicitly disclaims is whether the fork is still
measurably *correct*, and this is that check: run the fork and its stock
counterpart against the same database and read the two numbers that come out.

Both directions matter, and they fail in opposite ways:

``cleared`` falling toward zero
    The fork rotted. A barrier that no longer matches suppresses nothing while
    still looking installed -- and because the stock rule is EXCLUDED in its
    favour, that sink is then covered by neither. This is the row Gate 2 exists
    for and the one this check strengthens most.

``NEW`` rising above zero
    The fork reports a source stock did not. That is usually a broadened query,
    but not always: blocking one flow can reveal a separate finding stock never
    selected, because CodeQL's per-sink path selection stops once one flow to a
    sink is reported. Factory#737 measured that case rather than inferring it.

**Why NEW is a failure here even though it is sometimes legitimate.** A gate
cannot tell the two apart -- the procedure that can is in AIFactory's
``.github/codeql/VALIDATION.md``: sever the cleared flow at its sink, rebuild,
re-run STOCK, and see whether stock reports the NEW alert on its own. That needs
a source edit and a human reading a diff. So this reports NEW as a failure that
demands that triage, not as a verdict that the query is wrong. The distinction
is in the output text, because "NEW must be 0" encoded as a silent hard rule is
exactly the flattening AIFactory#1293 warns against.

**What this check cannot see, stated because the numbers look more complete than
they are.** It compares two runs against ONE database. A barrier that clears
alerts for the wrong reason -- registered on the wrong argument, or matching a
name by accident -- clears them just as effectively as a correct one and looks
identical here. Distinguishing those needs the unfixed-tree run and the
sanitizer-deletion mutation in standards rule 4.13, neither of which is a
single-database comparison. This measures that the fork still *does something*
and still *only removes*; it does not measure that what it removes deserved to
go.

Counts are per distinct SOURCE, not per flow. One unguarded source fans out to
many sinks, so flow counts overstate the work: on PFactory 988 stock flows are
76 distinct sources. Flow counts are reported alongside, never compared.

Baseline measured 2026-08-15, PFactory ``dev`` @ 306d0f7, CodeQL 2.25.6,
database over the whole repo (1192 Python files):

===========================  ======  ======  =======  ===
rule                         stock   fork    cleared  NEW
===========================  ======  ======  =======  ===
py/path-injection            76      6       70       0
py/command-line-injection    2       0       2        0
py/full-ssrf                 1       0       1        0
py/partial-ssrf              10      0       10       0
===========================  ======  ======  =======  ===

All four forks are alive. ``py/partial-ssrf``'s stock column reproduces the
"11 alerts" recorded in PFactory's own ``codeql-config.yml`` comment, which is
the cross-check that this method measures the same thing that comment did.

**The rule-4.13 discriminating check was run, and the forks pass it.** Numbers
alone cannot tell a real barrier from a silencer, so the path-injection
sanitizer was deleted from the SOURCE -- 88 guard calls across 20 files rewritten
to pass their first argument through -- and the database rebuilt:

===============================  =============  ============
tree                             stock sources  fork sources
===============================  =============  ============
as shipped                       76             6
guards stripped                  63             63
===============================  =============  ============

Read the second row. With the barriers gone from the code the fork reports
**exactly what stock reports, source for source** -- so it suppresses nothing on
its own, and its silence on the first row is the barrier and not blindness.
And stock does not collapse toward 6: it goes 76 -> 63, because the deleted
guard call sites were themselves path expressions stock reported. A barrier that
was a branch deletion in disguise would have shown stock falling to the fork's
own number. This one does not.

That check is NOT what this script does. It needs a source mutation and a second
database, so it belongs in a human's hands when a barrier changes; this script
is the cheap daily signal that the fork still moves the numbers at all.

Usage:
    python scripts/check_codeql_fork_validation.py --rule py/path-injection \
        --stock stock.csv --fork fork.csv
    python scripts/check_codeql_fork_validation.py --manifest results.json
    python scripts/check_codeql_fork_validation.py --self-test

Exit codes:
    0 - every fork cleared something and introduced nothing
    1 - a fork rotted (cleared 0 against a non-empty stock) or reported NEW sources
    2 - bad invocation
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from gate_evidence import expect, gate_argparser, gate_fixture, parse_or_self_test, report_self_test

# CodeQL CSV embeds source locations as `relative:///path:line:col:line:col`
# inside the message column. This is the extraction AIFactory's VALIDATION.md
# documents, kept identical so numbers stay comparable with the baselines
# recorded there.
_SOURCE = re.compile(r"relative:///[^\]|]*")


@dataclass(frozen=True)
class Comparison:
    """One fork measured against its stock counterpart on one database."""

    rule: str
    stock_flows: int
    fork_flows: int
    stock_sources: int
    fork_sources: int
    cleared: int
    new: int

    @property
    def rotted(self) -> bool:
        """The fork suppresses nothing while the stock rule still finds things.

        Guarded on ``stock_sources`` deliberately. A fork clearing nothing
        because the CODE was fixed and stock now reports nothing either is a
        healthy repo, not a rotted query, and failing on it would train people
        to ignore this gate.
        """
        return self.stock_sources > 0 and self.cleared == 0

    @property
    def broadened(self) -> bool:
        return self.new > 0

    @property
    def ok(self) -> bool:
        return not self.rotted and not self.broadened


def extract_sources(csv_text: str) -> set[str]:
    """Distinct source locations named in a CodeQL CSV result set."""
    return {match.rstrip('"') for match in _SOURCE.findall(csv_text)}


def say(message: str) -> None:
    """Report a line. This gate's output IS its verdict, so print is correct."""
    print(message)  # noqa: T201 - a gate report, not stray debugging


def _flows(csv_text: str) -> int:
    return len([line for line in csv_text.splitlines() if line.strip()])


def compare(rule: str, stock_csv: str, fork_csv: str) -> Comparison:
    stock = extract_sources(stock_csv)
    fork = extract_sources(fork_csv)
    return Comparison(
        rule=rule,
        stock_flows=_flows(stock_csv),
        fork_flows=_flows(fork_csv),
        stock_sources=len(stock),
        fork_sources=len(fork),
        cleared=len(stock - fork),
        new=len(fork - stock),
    )


def report(comparisons: list[Comparison], source_files: int | None = None) -> int:
    """Print every comparison and return the exit code.

    Prints on the PASS path too. A gate that speaks only when it fails is
    indistinguishable from one that never ran (Factory#738), and this one runs
    on a schedule where that is the likely failure.
    """
    if source_files is not None:
        # Factory#737: alert counts are comparable only at the same scan
        # breadth. A count that fell because the database covered less code is
        # not an improvement, and without this line nobody can tell.
        say(f"database covered {source_files} source file(s)")
    if not comparisons:
        say("FAIL: no fork was measured at all -- a run that measured nothing is not a pass")
        return 1

    failures = 0
    for item in comparisons:
        verdict = "OK  "
        if item.rotted:
            verdict = "ROT "
            failures += 1
        elif item.broadened:
            verdict = "NEW "
            failures += 1
        say(
            f"{verdict}{item.rule}: cleared {item.cleared}, NEW {item.new} "
            f"(sources: stock {item.stock_sources} -> fork {item.fork_sources}; "
            f"flows: {item.stock_flows} -> {item.fork_flows})"
        )

    for item in comparisons:
        if item.rotted:
            say(
                f"\nROT {item.rule}: stock finds {item.stock_sources} source(s) and the fork "
                "clears none of them. The stock rule is EXCLUDED in this fork's favour, so "
                "that sink is now covered by neither."
            )
        if item.broadened:
            say(
                f"\nNEW {item.rule}: the fork reports {item.new} source(s) stock did not. "
                "This is not automatically a broken query -- blocking one flow can reveal a "
                "finding stock never selected. Decide which by severing the cleared flow at "
                "its sink, rebuilding, and re-running STOCK: if stock then reports it alone, "
                "it was masked and belongs in triage on its merits. If not, the query is "
                "wrong. See AIFactory .github/codeql/VALIDATION.md."
            )

    measured = len(comparisons)
    say(f"\n{measured} fork(s) measured, {measured - failures} OK, {failures} needing attention")
    return 1 if failures else 0


def _load_manifest(path: Path) -> tuple[list[Comparison], int | None]:
    """Read a manifest the workflow writes: rule -> stock/fork CSV paths.

    A missing manifest returns no comparisons rather than raising. The workflow
    calls this from an ``if: always()`` step, so the case it hits is "an earlier
    step died before writing one" -- and the honest report for that is the
    gate's own "measured nothing is not a pass" line, not a traceback that
    obscures which step actually failed.
    """
    if not path.is_file():
        say(f"no manifest at {path}: the measurement step did not produce one")
        return [], None
    data = json.loads(path.read_text(encoding="utf-8"))
    root = path.parent
    comparisons = [
        compare(
            entry["rule"],
            (root / entry["stock"]).read_text(encoding="utf-8"),
            (root / entry["fork"]).read_text(encoding="utf-8"),
        )
        for entry in data["forks"]
    ]
    return comparisons, data.get("source_files")


def _self_test() -> int:
    with gate_fixture() as (root, failures):
        stock = (
            '"Path","desc","error","a [[""x""|""relative:///a.py:1:1:1:2""]] flows","/s.py","3"\n'
            '"Path","desc","error","a [[""x""|""relative:///b.py:9:1:9:2""]] flows","/s.py","4"\n'
            '"Path","desc","error","a [[""x""|""relative:///b.py:9:1:9:2""]] flows","/t.py","5"\n'
        )
        # Same source set minus a.py: one source cleared, nothing introduced.
        healthy = (
            '"Path","desc","error","a [[""x""|""relative:///b.py:9:1:9:2""]] flows","/s.py","4"\n'
        )

        expect(
            failures,
            extract_sources(stock) == {"relative:///a.py:1:1:1:2", "relative:///b.py:9:1:9:2"},
            f"three flows over two distinct sources must extract two, got {extract_sources(stock)}",
        )

        stock_flow_count, fork_flow_count, breadth = 3, 1, 1192
        good = compare("py/path-injection", stock, healthy)
        expect(failures, good.cleared == 1 and good.new == 0, f"expected cleared 1 NEW 0, {good}")
        expect(
            failures,
            good.stock_flows == stock_flow_count and good.fork_flows == fork_flow_count,
            f"flow counts: {good}",
        )
        expect(failures, good.ok, "a fork that clears one and introduces none must pass")
        expect(failures, report([good]) == 0, "a healthy comparison must exit 0")

        # Rot: the fork reproduces stock exactly, so the exclusion covers nothing.
        rotted = compare("py/full-ssrf", stock, stock)
        expect(
            failures, rotted.cleared == 0 and rotted.rotted, f"identical output is rot: {rotted}"
        )
        expect(failures, report([rotted]) == 1, "a rotted fork must exit 1")

        # Broadened: a source the stock rule never reported.
        broader = compare("py/full-ssrf", healthy, stock)
        expect(failures, broader.new == 1 and broader.broadened, f"expected NEW 1: {broader}")
        expect(failures, report([broader]) == 1, "a fork reporting a new source must exit 1")

        # Empty stock is NOT rot: the code was fixed, nothing left to clear.
        clean = compare("py/command-line-injection", "", "")
        expect(failures, not clean.rotted, "an empty stock result must not read as a rotted fork")
        expect(failures, report([clean]) == 0, "nothing to clear and nothing new must pass")

        # A run that measured nothing must fail. This is the Factory#738 shape:
        # a green exit that produced no measurement is the failure being caught.
        expect(failures, report([]) == 1, "measuring no forks at all must not be a pass")

        # The manifest path the workflow uses, end to end.
        (root / "stock.csv").write_text(stock, encoding="utf-8")
        (root / "fork.csv").write_text(healthy, encoding="utf-8")
        (root / "m.json").write_text(
            json.dumps(
                {
                    "source_files": breadth,
                    "forks": [
                        {"rule": "py/path-injection", "stock": "stock.csv", "fork": "fork.csv"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        loaded, files = _load_manifest(root / "m.json")
        expect(failures, len(loaded) == 1 and loaded[0].cleared == 1, f"manifest load: {loaded}")
        expect(failures, files == breadth, f"scan breadth must survive the manifest, got {files}")

        # A manifest that was never written -- an earlier workflow step died.
        # It must reach the "measured nothing" verdict, not raise: the workflow
        # calls this from an `if: always()` step precisely to catch that case.
        absent, _ = _load_manifest(root / "does-not-exist.json")
        expect(failures, absent == [], "a missing manifest must yield no comparisons, not raise")
        expect(failures, report(absent) == 1, "a missing manifest must fail, not pass quietly")

    return report_self_test(failures)


def main(argv: list[str] | None = None) -> int:
    parser = gate_argparser(__doc__)
    parser.add_argument("--manifest", help="JSON manifest of rule -> stock/fork CSV paths")
    parser.add_argument("--rule", help="rule id, for a single pair")
    parser.add_argument("--stock", help="CSV from the stock query")
    parser.add_argument("--fork", help="CSV from the barrier-aware fork")
    early, args = parse_or_self_test(parser, argv, _self_test)
    if early is not None:
        return early
    assert args is not None  # noqa: S101 - guaranteed when early is None
    if args.manifest:
        comparisons, source_files = _load_manifest(Path(args.manifest))
        return report(comparisons, source_files)
    if not (args.rule and args.stock and args.fork):
        parser.error("pass --manifest, or all of --rule/--stock/--fork (or --self-test)")
    single = compare(
        args.rule,
        Path(args.stock).read_text(encoding="utf-8"),
        Path(args.fork).read_text(encoding="utf-8"),
    )
    return report([single])


if __name__ == "__main__":
    sys.exit(main())
