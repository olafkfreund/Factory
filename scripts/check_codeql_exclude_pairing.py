#!/usr/bin/env python3
"""Every excluded stock CodeQL rule must have a custom query that replaces it.

Ported from PFactory's tests/test_codeql_config_pairs_excludes_with_queries.py
(PFactory#517) into one reusable, repo-agnostic implementation so the fleet
stops carrying N copies of the same check (the whole point of Gate 3/4 in
this batch is to STOP that pattern, so this gate should not itself become an
instance of it).

Barrier-aware custom queries are legitimate — stock CodeQL cannot follow a
validator imported from a service module, or one that establishes safety by
raising rather than returning a sanitized value. But an `exclude:` with no
replacement is just silencing the rule: the failure mode is losing one half
(delete the custom query, rename its `@id`, or let the pack fail to resolve)
while the exclude stays, so the rule is checked by nothing and CodeQL still
reports success.

Usage:
    python scripts/check_codeql_exclude_pairing.py --repo /path/to/PFactory
    python scripts/check_codeql_exclude_pairing.py --self-test

Exit codes:
    0 - every excluded rule id has a `<id>-sanitized` query with a doc'd Sanitizer class
        (or the repo has no codeql-config.yml at all — nothing to pair)
    1 - an exclude has no replacement, or a replacement has no doc comment
    2 - bad invocation
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

from gate_evidence import expect, gate_argparser, gate_fixture, parse_or_self_test, report_self_test


def _excluded_rule_ids(config_path: Path) -> list[str]:
    text = config_path.read_text(encoding="utf-8")
    return re.findall(r"^\s*id:\s*(\S+)\s*$", text, flags=re.MULTILINE)


def _query_ids(query_dir: Path) -> dict[str, Path]:
    out: dict[str, Path] = {}
    if not query_dir.is_dir():
        return out
    for ql in sorted(query_dir.glob("*.ql")):
        m = re.search(r"^\s*\*\s*@id\s+(\S+)\s*$", ql.read_text(encoding="utf-8"), re.MULTILINE)
        if m:
            out[m.group(1)] = ql
    return out


def _local_library_sources(query: Path, query_dir: Path) -> list[str]:
    """The query's body plus every sibling ``.qll`` it imports, transitively.

    A query that shares its barrier with another query factors the guard into a
    ``.qll`` and imports it -- which is the right structure, and used to make
    the pair look undocumented here, because this gate read only the ``.ql``
    body (Factory#807). AIFactory's ``FullSsrfSanitized.ql`` and
    ``PartialSsrfSanitized.ql`` both register the same guard and both document
    it once, in ``SsrfBarriers.qll``.

    The alternative was to require the reasoning be duplicated into each
    ``.ql``. That satisfies the regex and trains people to paste a paragraph to
    satisfy a regex, which is the failure mode this gate family exists to
    prevent, so it was rejected.

    Only bare single-identifier imports are followed, and only to a file that
    exists in the same directory. ``import python`` and
    ``import semmle.python.dataflow.new.DataFlow`` name library packs, not
    files here, and resolve to nothing.
    """
    seen: set[Path] = set()
    bodies: list[str] = []
    pending = [query]
    while pending:
        current = pending.pop()
        if current in seen or not current.is_file():
            continue
        seen.add(current)
        body = current.read_text(encoding="utf-8")
        bodies.append(body)
        for name in re.findall(r"^\s*import\s+([A-Za-z_]\w*)\s*$", body, re.MULTILINE):
            sibling = query_dir / f"{name}.qll"
            if sibling.is_file():
                pending.append(sibling)
    return bodies


def check(repo: Path) -> list[str]:
    config_path = repo / ".github" / "codeql" / "codeql-config.yml"
    query_dir = repo / ".github" / "codeql" / "custom-queries"
    if not config_path.is_file():
        return []  # no config file -> nothing to pair, not a violation of this gate

    problems: list[str] = []
    excluded = _excluded_rule_ids(config_path)
    queries = _query_ids(query_dir)

    for rule_id in excluded:
        replacement = queries.get(f"{rule_id}-sanitized")
        if replacement is None:
            problems.append(
                f"{rule_id}: excluded in {config_path.name} with no `{rule_id}-sanitized` "
                f"query in {query_dir} — nothing checks this rule"
            )
            continue
        bodies = _local_library_sources(replacement, query_dir)
        has_reasoning = any("sanitiz" in b.lower() or "barrier" in b.lower() for b in bodies)
        has_doc_comment = any(
            re.search(r"/\*\*.*?\*/\s*class \w+ extends", b, re.S) for b in bodies
        )
        if not has_reasoning or not has_doc_comment:
            problems.append(
                f"{rule_id}-sanitized: {replacement.name} exists but does not document "
                "its sanitizer claim (needs a doc comment + 'sanitiz'/'barrier' wording, "
                "in the .ql or in a sibling .qll it imports)"
            )
    return problems


def run_check(repo: Path) -> int:
    problems = check(repo)
    config_path = repo / ".github" / "codeql" / "codeql-config.yml"
    print(f"codeql-exclude-pairing: {repo}")  # noqa: T201
    if not config_path.is_file():
        print("  no codeql-config.yml — nothing to pair, skipping")  # noqa: T201
        return 0
    if problems:
        print("UNPAIRED EXCLUDE — a stock CodeQL rule is silenced with no replacement:")  # noqa: T201
        for problem in problems:
            print(f"  - {problem}")  # noqa: T201
        return 1
    print("OK: every excluded rule has a documented -sanitized replacement.")  # noqa: T201
    return 0


def _self_test() -> int:
    with gate_fixture() as (repo, failures):
        (repo / ".github" / "codeql" / "custom-queries").mkdir(parents=True)
        config = repo / ".github" / "codeql" / "codeql-config.yml"
        query_dir = repo / ".github" / "codeql" / "custom-queries"

        # Case 1: exclude with a proper paired, documented replacement -> clean.
        config.write_text("query-filters:\n  - exclude:\n      id: py/path-injection\n")
        (query_dir / "PathInjectionSanitized.ql").write_text(
            "/**\n"
            " * @id py/path-injection-sanitized\n"
            " * Barrier-aware path-injection. Recognises safe_spec_component as a sanitizer.\n"
            " */\n"
            "class Sanitizer extends DataFlow::Node { }\n"
        )
        expect(
            failures, check(repo) == [], "a properly paired, documented exclude must not be flagged"
        )

        # Case 2 (the mutation): the custom query file is deleted (or its @id
        # renamed) while the exclude stays — the exact failure PFactory#517
        # exists to catch.
        (query_dir / "PathInjectionSanitized.ql").unlink()
        problems = check(repo)
        expect(
            failures,
            len(problems) == 1,
            f"a deleted replacement query must be caught, got {problems}",
        )
        expect(
            failures,
            bool(problems) and "py/path-injection" in problems[0],
            "the flagged rule id must be the orphaned exclude",
        )
        expect(
            failures,
            run_check(repo) == 1,
            "run_check must fail when an exclude loses its replacement",
        )

        # Case 3: replacement restored but with no doc comment -> still flagged.
        (query_dir / "PathInjectionSanitized.ql").write_text(
            " * @id py/path-injection-sanitized\nclass Sanitizer extends DataFlow::Node { }\n"
        )
        problems = check(repo)
        expect(
            failures,
            len(problems) == 1 and "does not document" in problems[0],
            f"a replacement with no @id doc comment must be flagged as unpaired, got {problems}",
        )

        # Case 4: healed -> back to green.
        (query_dir / "PathInjectionSanitized.ql").write_text(
            "/**\n"
            " * @id py/path-injection-sanitized\n"
            " * Barrier-aware path-injection sanitizer.\n"
            " */\n"
            "class Sanitizer extends DataFlow::Node { }\n"
        )
        expect(
            failures,
            run_check(repo) == 0,
            "run_check must pass once the replacement is restored and documented",
        )

        # Case 6: the reasoning lives in a sibling .qll the query imports, which
        # is how two queries sharing one barrier are correctly factored
        # (Factory#807). Documented there, it counts.
        (query_dir / "PathInjectionSanitized.ql").write_text(
            "/**\n * @id py/path-injection-sanitized\n */\n"
            "import python\n"
            "import semmle.python.dataflow.new.DataFlow\n"
            "import SharedBarriers\n"
            "class Q extends int { }\n"
        )
        (query_dir / "SharedBarriers.qll").write_text(
            "/**\n"
            " * The shared barrier. Recognises safe_spec_component as a sanitizer.\n"
            " */\n"
            "class Sanitizer extends DataFlow::Node { }\n"
        )
        expect(
            failures,
            run_check(repo) == 0,
            "documentation in an imported sibling .qll must satisfy the gate",
        )

        # Case 7 (the mutation that keeps case 6 honest): strip the doc comment
        # out of the .qll and it must fail again. Without this, case 6 would
        # pass for a gate that had simply stopped checking.
        (query_dir / "SharedBarriers.qll").write_text(
            "class Sanitizer extends DataFlow::Node { }\n"
        )
        expect(
            failures,
            run_check(repo) == 1,
            "an undocumented sibling .qll must NOT satisfy the gate",
        )

        # Case 8: documentation that exists but is not imported does not count.
        # Following the import is the point; scanning the directory would let an
        # unrelated well-documented file vouch for an undocumented query.
        (query_dir / "SharedBarriers.qll").write_text(
            "/**\n * The shared barrier, a documented sanitizer.\n */\n"
            "class Sanitizer extends DataFlow::Node { }\n"
        )
        (query_dir / "PathInjectionSanitized.ql").write_text(
            "/**\n * @id py/path-injection-sanitized\n */\nimport python\nclass Q extends int { }\n"
        )
        expect(
            failures,
            run_check(repo) == 1,
            "an un-imported .qll must not vouch for an undocumented query",
        )
        (query_dir / "SharedBarriers.qll").unlink()

        # Case 5: no config file at all -> not a violation (nothing to pair).
        no_config_repo = Path(tempfile.mkdtemp())
        expect(
            failures,
            run_check(no_config_repo) == 0,
            "a repo with no codeql-config.yml must pass trivially",
        )

    return report_self_test(failures)


def main(argv: list[str] | None = None) -> int:
    parser = gate_argparser(__doc__)
    parser.add_argument("--repo", help="repo root containing .github/codeql/")
    early, args = parse_or_self_test(parser, argv, _self_test)
    if early is not None:
        return early
    assert args is not None  # noqa: S101 - parse_or_self_test guarantees this when early is None
    if not args.repo:
        parser.error("--repo is required (or pass --self-test)")
    return run_check(Path(args.repo))


if __name__ == "__main__":
    sys.exit(main())
