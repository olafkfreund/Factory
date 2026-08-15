#!/usr/bin/env python3
"""Fail CI when a repo's CodeQL setup does not resolve to security-and-quality.

Factory security-cleanup review (2026-08-13, Factory#711/#712). Four repos
silently ran CodeQL's DEFAULT query suite while one ran security-and-quality.
Fleet alert count went 1526 -> 3876 on levelling up, with ZERO code change —
a repo reporting "0 open alerts" was asking narrower questions, not writing
safer code.

THE MECHANIC THIS EXISTS TO CATCH: a CodeQL "advanced setup" config file
(``.github/codeql/codeql-config.yml``) REPLACES the workflow's ``queries:``
INPUT — it does not add to it. A workflow with
``queries: security-and-quality`` is silently downgraded to CodeQL's narrow
default suite the moment a ``config-file:`` is introduced, UNLESS that config
file itself lists ``- uses: security-and-quality`` under its own ``queries:``
key. This is exactly how a "reduce false positives" or "add a barrier query"
change (the kind Gate 2 is about) can quietly regress Gate 1, and it is why
this check reads BOTH files together rather than either alone.

This script is a static check: it parses the workflow's ``codeql-action/init``
step and (if present) the referenced config file, and computes the EFFECTIVE
query suite the same way ``github/codeql-action`` resolves it. It cannot see
what actually ran on GitHub's servers — see ``--sarif`` below for the other
half (Gate 1's "assert the analysis actually ran" requirement), which reads a
downloaded SARIF/analysis result and asserts a floor on rule/result count so
a workflow that is green but scanned nothing is caught too.

Usage:
    python scripts/check_codeql_query_suite.py --repo /path/to/PFactory
    python scripts/check_codeql_query_suite.py --repo . --sarif codeql-results.sarif
    python scripts/check_codeql_query_suite.py --self-test

Exit codes:
    0 - effective suite includes security-and-quality (and, if --sarif given,
        the run produced at least --min-rules distinct rule ids)
    1 - suite resolves to something narrower, or the SARIF floor is not met
    2 - bad invocation / could not find a codeql-action/init step
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from gate_evidence import expect, gate_argparser, gate_fixture, parse_or_self_test, report_self_test

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

_REQUIRED_SUITE = "security-and-quality"


def _find_init_step_queries(workflow_text: str) -> tuple[str | None, str | None]:
    """Return (queries_input, config_file_input) from the FIRST codeql-action/init step.

    Regex, not a full YAML-in-YAML parse: workflow step bodies are themselves
    a `run:`-adjacent block and GitHub Actions expression syntax (`${{ }}`)
    routinely breaks strict YAML loaders. This mirrors how the value is
    actually consumed (a `with:` block under one `uses: .../init` step).
    """
    m = re.search(
        r"uses:\s*github/codeql-action/init@.*?(?=\n\s*-\s*(?:uses|name|run):|\Z)",
        workflow_text,
        re.S,
    )
    if not m:
        return None, None
    block = m.group(0)
    queries_m = re.search(r"^\s*queries:\s*(\S.*)$", block, re.M)
    config_m = re.search(r"^\s*config-file:\s*(\S.*)$", block, re.M)
    return (
        queries_m.group(1).strip() if queries_m else None,
        config_m.group(1).strip() if config_m else None,
    )


def _config_file_queries(config_path: Path) -> list[str]:
    if yaml is None:
        raise RuntimeError("pyyaml is required to read a codeql-config.yml")
    if not config_path.is_file():
        raise FileNotFoundError(f"config-file referenced but not found: {config_path}")
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    queries = data.get("queries") or []
    return [q.get("uses", "") for q in queries if isinstance(q, dict)]


def analysis_workflows(repo: Path) -> list[Path]:
    """Every workflow that actually runs a CodeQL analysis, not merely named for one.

    Factory#737. This used to be ``candidates[0]`` -- the alphabetically first
    file matching ``*codeql*.y*ml`` -- which had two failure modes, and the
    dangerous one is not the noisy one:

    - a repo with more than one analysis workflow had all but the first
      unchecked
    - **a file sorting before ``codeql.yml`` silently became the thing this
      gate measured.** ``codeql-fork-validation.yml`` (Factory#737) is such a
      file, and it does not run an analysis at all. Had it carried an init
      step with ``queries: security-and-quality``, this gate would have
      reported PASS while the real ``codeql.yml`` sat downgraded -- a green
      verdict on a file nobody meant it to read.

    Selection is now by CONTENT: a workflow qualifies if it contains a
    ``codeql-action/init`` step, because that step is what creates the alert
    surface this gate exists to keep broad. A workflow that drives the CodeQL
    CLI directly to run specific queries for a differential measurement is not
    a repo's analysis configuration and has no suite to widen.
    """
    workflow_dir = repo / ".github" / "workflows"
    if not workflow_dir.is_dir():
        return []
    return [
        path
        for path in sorted(workflow_dir.glob("*codeql*.y*ml"))
        if "codeql-action/init" in path.read_text(encoding="utf-8")
    ]


def effective_suite(repo: Path) -> tuple[bool, str]:
    """Return (resolves_to_security_and_quality, explanation).

    EVERY analysis workflow must resolve broadly, not just one of them: a
    second workflow analysing the same code with the default suite produces
    exactly the "0 open alerts because we asked a narrower question" result
    this gate was written for.
    """
    candidates = analysis_workflows(repo)
    if not candidates:
        return False, "no *codeql*.yml workflow with a codeql-action/init step found"
    reasons: list[str] = []
    for candidate in candidates:
        ok, why = _suite_of(repo, candidate)
        if not ok:
            return False, why
        reasons.append(why)
    # Each workflow's own reason is carried through, not summarised into a
    # count: "2 workflows resolve broadly" is unfalsifiable by a reader, while
    # "codeql.yml: queries: input is 'security-and-quality'" can be checked.
    return True, "; ".join(reasons)


def _suite_of(repo: Path, workflow: Path) -> tuple[bool, str]:
    """Resolve one analysis workflow's effective query suite."""
    workflow_text = workflow.read_text(encoding="utf-8")
    queries_input, config_file_input = _find_init_step_queries(workflow_text)
    if queries_input is None and config_file_input is None:
        return (
            False,
            f"{workflow.name}: codeql-action/init has neither `queries:` nor "
            "`config-file:` — defaults to CodeQL's narrow default suite",
        )

    if config_file_input:
        # THE MECHANIC: config-file REPLACES queries:, regardless of what
        # queries: says. Only the config file's own `queries:` list counts.
        config_path = repo / config_file_input.strip("'\"")
        resolved = _config_file_queries(config_path)
        if _REQUIRED_SUITE in resolved:
            return True, (
                f"{workflow.name}: config-file {config_file_input} lists "
                f"`- uses: {_REQUIRED_SUITE}`"
            )
        return False, (
            f"{workflow.name}: config-file {config_file_input} REPLACES the workflow's "
            f"`queries:` input "
            f"({queries_input!r}) and does not itself list `- uses: {_REQUIRED_SUITE}` "
            f"(found: {resolved or 'nothing'}) — effective suite is CodeQL's narrow default"
        )

    if queries_input and _REQUIRED_SUITE in queries_input:
        return True, f"{workflow.name}: queries: input is {queries_input!r}"
    return False, (
        f"{workflow.name}: queries: input is {queries_input!r}, missing {_REQUIRED_SUITE}"
    )


def check_sarif_floor(sarif_path: Path, min_rules: int) -> tuple[bool, str]:
    """Assert a SARIF result carries evidence of a real broad-suite run.

    Gate 1's second half: "assert the analysis actually ran with the expected
    rule count rather than trusting the YAML — a workflow can be green and
    scan nothing." A config error, a query-pack resolution failure, or an
    empty analysis all produce a SARIF with few or zero distinct rule ids
    while the `codeql-action/analyze` step still exits 0.
    """
    if not sarif_path.is_file():
        return False, f"SARIF file not found: {sarif_path}"
    data = json.loads(sarif_path.read_text(encoding="utf-8"))
    rule_ids: set[str] = set()
    for run in data.get("runs", []):
        for rule in run.get("tool", {}).get("driver", {}).get("rules") or []:
            if rule.get("id"):
                rule_ids.add(rule["id"])
    if len(rule_ids) < min_rules:
        return (
            False,
            f"SARIF carries only {len(rule_ids)} distinct rule id(s), expected >= {min_rules}",
        )
    return True, f"SARIF carries {len(rule_ids)} distinct rule id(s)"


def run_check(repo: Path, sarif: Path | None, min_rules: int) -> int:
    ok, explanation = effective_suite(repo)
    print(f"codeql-query-suite: {repo}")  # noqa: T201
    print(f"  {explanation}")  # noqa: T201
    if not ok:
        print(f"FAIL: effective query suite does not include {_REQUIRED_SUITE}")  # noqa: T201
        return 1
    if sarif is not None:
        sarif_ok, sarif_explanation = check_sarif_floor(sarif, min_rules)
        print(f"  {sarif_explanation}")  # noqa: T201
        if not sarif_ok:
            print("FAIL: SARIF evidence does not support a real broad-suite run")  # noqa: T201
            return 1
    print(f"OK: effective query suite includes {_REQUIRED_SUITE}.")  # noqa: T201
    return 0


def _self_test() -> int:
    with gate_fixture() as (repo, failures):
        (repo / ".github" / "workflows").mkdir(parents=True)
        (repo / ".github" / "codeql").mkdir(parents=True)

        # Case 1: queries: input only, no config file -> resolves correctly.
        (repo / ".github" / "workflows" / "codeql.yml").write_text(
            "jobs:\n  analyze:\n    steps:\n      - uses: github/codeql-action/init@v3\n"
            "        with:\n          queries: security-and-quality\n"
        )
        ok, _ = effective_suite(repo)
        expect(failures, ok, "queries: security-and-quality with no config-file must resolve true")

        # Case 2 (the mutation, exact shape of today's failure): a config file
        # is introduced for a barrier query, WITHOUT re-listing
        # security-and-quality. The workflow's queries: input is now dead.
        (repo / ".github" / "workflows" / "codeql.yml").write_text(
            "jobs:\n  analyze:\n    steps:\n      - uses: github/codeql-action/init@v3\n"
            "        with:\n          queries: security-and-quality\n"
            "          config-file: ./.github/codeql/codeql-config.yml\n"
        )
        (repo / ".github" / "codeql" / "codeql-config.yml").write_text(
            "name: test\nqueries:\n  - uses: ./.github/codeql/custom-queries\n"
            "query-filters:\n  - exclude:\n      id: py/path-injection\n"
        )
        ok, explanation = effective_suite(repo)
        expect(
            failures,
            not ok,
            "a config-file that drops security-and-quality must be caught even "
            "though queries: still says it",
        )
        expect(failures, "REPLACES" in explanation, "explanation must name the replace mechanic")
        expect(
            failures, run_check(repo, None, 0) == 1, "run_check must fail on the silent downgrade"
        )

        # Case 3: config file correctly re-lists security-and-quality -> fixed.
        (repo / ".github" / "codeql" / "codeql-config.yml").write_text(
            "name: test\nqueries:\n  - uses: security-and-quality\n"
            "  - uses: ./.github/codeql/custom-queries\n"
            "query-filters:\n  - exclude:\n      id: py/path-injection\n"
        )
        expect(
            failures,
            run_check(repo, None, 0) == 0,
            "run_check must pass once the config re-lists the suite",
        )

        # Case 4: neither queries: nor config-file present -> narrow default, caught.
        (repo / ".github" / "workflows" / "codeql.yml").write_text(
            "jobs:\n  analyze:\n    steps:\n      - uses: github/codeql-action/init@v3\n"
        )
        ok, _ = effective_suite(repo)
        expect(
            failures,
            not ok,
            "no queries: and no config-file must resolve to the narrow default and fail",
        )

        # Case 5: SARIF floor — a green-but-empty analysis is caught.
        sarif_empty = repo / "empty.sarif"
        sarif_empty.write_text(json.dumps({"runs": [{"tool": {"driver": {"rules": []}}}]}))
        ok, explanation = check_sarif_floor(sarif_empty, min_rules=50)
        expect(failures, not ok, "an empty SARIF must fail the rule-count floor")

        sarif_real = repo / "real.sarif"
        sarif_real.write_text(
            json.dumps(
                {
                    "runs": [
                        {"tool": {"driver": {"rules": [{"id": f"py/rule-{i}"} for i in range(60)]}}}
                    ]
                }
            )
        )
        ok, explanation = check_sarif_floor(sarif_real, min_rules=50)
        expect(failures, ok, "a SARIF with 60 distinct rules must pass a floor of 50")

        # Case 6 (Factory#737): a NON-analysis workflow sorting before
        # codeql.yml must not become the file this gate reads. This is the
        # dangerous direction, so it is asserted as a false GREEN, not just as
        # noise: the decoy is given a passing queries: input while the real
        # analysis workflow is left downgraded. Under the old candidates[0]
        # selection this returned True.
        (repo / ".github" / "workflows" / "codeql.yml").write_text(
            "jobs:\n  analyze:\n    steps:\n      - uses: github/codeql-action/init@v3\n"
        )
        (repo / ".github" / "workflows" / "codeql-aaa-decoy.yml").write_text(
            "jobs:\n  measure:\n    steps:\n      - uses: github/codeql-action/init@v3\n"
            "        with:\n          queries: security-and-quality\n"
        )
        ok, why = effective_suite(repo)
        expect(
            failures,
            not ok and "codeql.yml" in why,
            f"a passing decoy must not mask a downgraded codeql.yml, got {ok} / {why!r}",
        )

        # Case 7: a workflow that drives the CodeQL CLI directly (no init step)
        # is not an analysis config and has no suite to widen -- it must be
        # ignored rather than failed. codeql-fork-validation.yml is exactly this.
        (repo / ".github" / "workflows" / "codeql-aaa-decoy.yml").unlink()
        (repo / ".github" / "workflows" / "codeql.yml").write_text(
            "jobs:\n  analyze:\n    steps:\n      - uses: github/codeql-action/init@v3\n"
            "        with:\n          queries: security-and-quality\n"
        )
        (repo / ".github" / "workflows" / "codeql-fork-validation.yml").write_text(
            "jobs:\n  validate:\n    steps:\n      - run: codeql database analyze /tmp/db\n"
        )
        ok, why = effective_suite(repo)
        expect(
            failures,
            ok,
            f"a CLI-driven measurement workflow must not be read as an analysis config: {why!r}",
        )
        expect(
            failures,
            "codeql-fork-validation.yml" not in why,
            f"the non-analysis workflow must not appear in the verdict, got {why!r}",
        )
        (repo / ".github" / "workflows" / "codeql-fork-validation.yml").unlink()

    return report_self_test(failures)


def main(argv: list[str] | None = None) -> int:
    parser = gate_argparser(__doc__)
    parser.add_argument("--repo", help="repo root containing .github/")
    parser.add_argument("--sarif", help="path to a downloaded SARIF file to floor-check")
    parser.add_argument("--min-rules", type=int, default=50)
    early, args = parse_or_self_test(parser, argv, _self_test)
    if early is not None:
        return early
    assert args is not None  # noqa: S101 - parse_or_self_test guarantees this when early is None
    if not args.repo:
        parser.error("--repo is required (or pass --self-test)")
    sarif = Path(args.sarif) if args.sarif else None
    return run_check(Path(args.repo), sarif, args.min_rules)


if __name__ == "__main__":
    sys.exit(main())
