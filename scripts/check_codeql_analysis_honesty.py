#!/usr/bin/env python3
"""Fail when the LATEST CodeQL analysis for a ref, in any category, loaded zero rules.

Factory#774. ``github/codeql-action/analyze`` defaults to ``upload: always``,
which uploads a SARIF file even when the run dies mid-flight -- and a job
killed by ``cancel-in-progress: true`` can reach that upload with a SARIF that
never finished loading its query suite. Confirmed twice in this repo's own
history, not hypothesised:

- Factory#771 (a PR merge-ref): a fast follow-up push cancelled an in-flight
  ``actions``-language scan; the cancelled run still published
  ``rules_count=0, results_count=0`` to the code-scanning API.
- commit ``4e2420e9`` on ``main`` itself (2026-08-15T10:18:30Z): the same
  shape, and it stood as the ONLY recorded analysis for that commit's
  ``/language:actions`` category. It stopped mattering only because a new
  push landed 100 seconds later and produced a real analysis for the next
  commit -- if nothing had pushed again, that zero-rule analysis would have
  remained the CURRENT result for ``main`` indefinitely. Nothing re-scans an
  unchanged commit on its own.

Both entries are, in the code-scanning API and the Security tab, byte-for-byte
indistinguishable from a scan that ran properly and found nothing. That is the
run-level version of the same defect class Factory#711 closed at the query-
suite level: a green that comes from asking less, not from looking and
finding nothing.

``codeql.yml`` (Factory#775 follow-up) now uploads through an explicit
``upload-sarif`` step gated on a local rules-count check, which should make
new zero-rule uploads structurally impossible: a cancelled job dies before
reaching a step after the one that was cancelled, so nothing reaches the
upload at all. This script is the OUTSIDE check for that promise, the same
relationship ``check_gate_liveness.py`` has to "did the scheduled workflow
run": nothing a workflow does to itself can prove it is not being bypassed by
a future edit to ``codeql.yml``, a differently-configured CodeQL workflow, or
a code path this fix did not anticipate.

**What counts as "latest".** The code-scanning API returns every analysis
ever uploaded for a ref, not just the current one. For each ``category``
(one per language), this takes the analysis with the newest ``created_at``
as the one that is CURRENT -- the one an unfiltered look at Code Scanning
would show. That is deliberately not "did a zero-rule analysis ever get
uploaded" (Factory#775's PR-merge-ref case answers yes, harmlessly, because
every PR push gets a fresh merge-ref commit and the next one supersedes it):
the question this asks is whether the zero-rule analysis is the one that
WINS.

**No analyses at all is not silence read as success.** A ref with zero
recorded analyses could mean CodeQL never ran there, which is a difference
question (``check_gate_liveness.py``'s job), but this script must not read
"nothing to check" as "everything is fine" -- it fails loudly instead, the
same reasoning ``check_gate_liveness.py`` applies to a workflow with zero
runs.

Usage:
    python scripts/check_codeql_analysis_honesty.py --repo olafkfreund/Factory
    python scripts/check_codeql_analysis_honesty.py --self-test

Exit codes:
    0 - the latest analysis for every category on the checked ref loaded rules
    1 - at least one category's latest analysis loaded zero rules, or none
        were found at all
    2 - bad invocation, or the API could not be reached
"""

from __future__ import annotations

import argparse
from collections.abc import Callable

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
_DEFAULT_REF = "refs/heads/main"

Fetcher = Callable[[str], object]
_fetch = fetch_github_json


def latest_by_category(analyses: list[dict[str, object]], ref: str) -> dict[str, dict[str, object]]:
    """The most recently created analysis per category, for *ref* only.

    ``created_at`` sorts correctly as a string because the API returns
    ISO-8601 UTC timestamps of uniform width.
    """
    latest: dict[str, dict[str, object]] = {}
    for analysis in analyses:
        if analysis.get("ref") != ref:
            continue
        category = analysis.get("category")
        if not isinstance(category, str):
            continue
        current = latest.get(category)
        if current is None or str(analysis.get("created_at", "")) > str(
            current.get("created_at", "")
        ):
            latest[category] = analysis
    return latest


def _cite(category: str, analysis: dict[str, object]) -> str:
    """The fragment every verdict on this category carries -- pass or fail.

    Printed on both paths (gate-honesty rule #2): a reader must be able to
    check "rules_count=27 as of <time>" against the Security tab without
    re-deriving it.
    """
    commit = str(analysis.get("commit_sha", ""))[:10]
    return (
        f"{category}: rules_count={analysis.get('rules_count')} "
        f"results_count={analysis.get('results_count')} commit={commit} "
        f"created_at={analysis.get('created_at')}"
    )


def verdict_for_category(category: str, analysis: dict[str, object]) -> str | None:
    """None if this category's latest analysis is honest, else the problem."""
    if analysis.get("rules_count") == 0:
        return (
            f"{_cite(category, analysis)} -- LATEST analysis for this category "
            "loaded zero rules. Indistinguishable from a real clean scan in "
            "the UI and the API (Factory#774)."
        )
    return None


def check(repo: str, ref: str, fetch: Fetcher) -> list[str]:
    """Problems for *ref*: one entry per category whose latest analysis lied clean."""
    url = f"{_API}/repos/{repo}/code-scanning/analyses?ref={ref}&per_page=100"
    raw = fetch(url)
    items = [a for a in raw if isinstance(a, dict)] if isinstance(raw, list) else []
    latest = latest_by_category(items, ref)
    if not latest:
        return [
            f"no CodeQL analyses found for {ref} -- cannot assess honesty here, "
            "treated as unknown, not as clean (see check_gate_liveness.py for "
            "whether CodeQL is running here at all)"
        ]
    return [
        problem
        for category, analysis in latest.items()
        if (problem := verdict_for_category(category, analysis)) is not None
    ]


def evidence(repo: str, ref: str, fetch: Fetcher) -> list[str]:
    """One enumerated, cited line per category -- the pass-path fragment."""
    url = f"{_API}/repos/{repo}/code-scanning/analyses?ref={ref}&per_page=100"
    raw = fetch(url)
    items = [a for a in raw if isinstance(a, dict)] if isinstance(raw, list) else []
    latest = latest_by_category(items, ref)
    return [_cite(category, analysis) for category, analysis in sorted(latest.items())]


def run_check(repo: str, ref: str) -> int:
    lines = evidence(repo, ref, _fetch)
    print(f"Categories checked for {ref}: {len(lines)}")  # noqa: T201
    for line in lines:
        print(f"  * {line}")  # noqa: T201
    problems = check(repo, ref, _fetch)
    if problems:
        print(  # noqa: T201
            "CODEQL ANALYSIS HONESTY -- at least one category's latest analysis is not a real scan:"
        )
        for problem in problems:
            print(f"  - {problem}")  # noqa: T201
        print(  # noqa: T201
            "\nA zero-rule analysis reads as 'found no problems' with nothing "
            "behind it. If this fired for a category codeql.yml no longer "
            "scans, remove it there first (Gate 1, check_codeql_query_suite.py "
            "owns coverage-shrink); otherwise the fix is a real re-run, not a "
            "waiver here."
        )
        return 1
    print(f"OK: all {len(lines)} categories' latest analyses for {ref} loaded real rules.")  # noqa: T201
    return 0


def _self_test() -> int:
    def responder(analyses: list[dict[str, object]] | Exception) -> Fetcher:
        def fetch(_url: str) -> object:
            if isinstance(analyses, Exception):
                raise analyses
            return analyses

        return fetch

    def analysis(
        rules: int,
        results: int,
        commit: str,
        created_at: str,
        *,
        category: str = "/language:actions",
    ) -> dict[str, object]:
        return {
            "ref": "refs/heads/main",
            "category": category,
            "rules_count": rules,
            "results_count": results,
            "commit_sha": commit * 40,
            "created_at": created_at,
        }

    with gate_fixture() as (_root, failures):
        honest = responder(
            [
                analysis(172, 8, "a", "2026-08-15T12:00:00Z", category="/language:python"),
                analysis(27, 0, "a", "2026-08-15T12:00:00Z"),
            ]
        )
        expect(
            failures,
            check("o/r", "refs/heads/main", honest) == [],
            "two real analyses on the target ref is clean",
        )
        lines = evidence("o/r", "refs/heads/main", honest)
        expect(failures, len(lines) == 2, "evidence enumerates every category checked")  # noqa: PLR2004
        expect(
            failures,
            all("rules_count=" in line for line in lines),
            "every evidence line carries the fragment it was derived from",
        )

        # The exact shape from Factory#771/#774: an OLDER real analysis
        # superseded by a NEWER zero-rule one on the same ref+category. This
        # is the "can it win" question -- it must be caught, not shadowed by
        # the earlier honest entry.
        cancelled_wins = responder(
            [
                analysis(27, 0, "a", "2026-08-15T10:00:00Z"),
                analysis(0, 0, "b", "2026-08-15T10:18:30Z"),
            ]
        )
        problems = check("o/r", "refs/heads/main", cancelled_wins)
        expect(
            failures,
            len(problems) == 1 and "rules_count=0" in problems[0],
            "a later zero-rule upload superseding an earlier real one is caught",
        )

        # The inverse must NOT fire: an OLDER zero-rule analysis that a later
        # real one has already superseded is exactly Factory#775's benign PR
        # case, and must read as clean.
        cancelled_loses = responder(
            [
                analysis(0, 0, "a", "2026-08-15T10:00:00Z"),
                analysis(27, 0, "b", "2026-08-15T10:18:30Z"),
            ]
        )
        expect(
            failures,
            check("o/r", "refs/heads/main", cancelled_loses) == [],
            "a superseded zero-rule analysis from an earlier commit is not a problem",
        )

        # A ref other than the one asked about must not leak in.
        other_ref_entry = analysis(0, 0, "a", "2026-08-15T10:00:00Z", category="/language:python")
        other_ref_entry["ref"] = "refs/heads/other"
        wrong_ref = responder([other_ref_entry])
        problem = check("o/r", "refs/heads/main", wrong_ref)
        expect(
            failures,
            len(problem) == 1 and "no CodeQL analyses found" in problem[0],
            "a ref with no matching analyses fails loudly, not silently clean",
        )

        # No data at all -- must not read as "nothing to check, therefore fine".
        empty = responder([])
        problem = check("o/r", "refs/heads/main", empty)
        expect(
            failures,
            len(problem) == 1 and "no CodeQL analyses found" in problem[0],
            "zero analyses is caught, not silently passed",
        )

    return report_self_test(failures)


def _configure(parser: argparse.ArgumentParser) -> None:
    add_repo_arg(parser)
    parser.add_argument("--ref", default=_DEFAULT_REF, help="ref to check, e.g. refs/heads/main")


def main(argv: list[str] | None = None) -> int:
    return run_gate_main(
        "Fail when the latest CodeQL analysis for a category loaded zero rules.",
        _self_test,
        lambda args: run_check(args.repo, args.ref),
        argv,
        configure=_configure,
    )


if __name__ == "__main__":
    raise SystemExit(main())
