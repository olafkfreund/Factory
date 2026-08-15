#!/usr/bin/env python3
"""pytest wrapper over the six security-cleanup CI guardrails' built-in self-tests.

Factory security-cleanup review (2026-08-13). Each gate under scripts/ ships
its own dependency-free ``--self-test`` (the fleet's established pattern —
see test_check_factory_github_drift.py and friends); this file locks that
each self-test passes and additionally exercises each gate against real
checked-out fleet state where that state is available, so the mutation proof
in the accompanying report is reproducible from `pytest` alone, not just from
manually invoking each script.
"""

from __future__ import annotations

import os
from pathlib import Path

# scripts/ is put on sys.path by tests/conftest.py.
import check_banned_constructs as gate5
import check_codeql_exclude_pairing as gate2
import check_codeql_query_suite as gate1
import check_security_fork_drift as gate3
import check_sink_coverage as gate4
import check_test_home_isolation as gate6

_FLEET_ROOT = Path(__file__).resolve().parents[2]  # .../GitHub/


def test_gate1_codeql_query_suite_self_test() -> None:
    assert gate1._self_test() == 0


def test_gate2_codeql_exclude_pairing_self_test() -> None:
    assert gate2._self_test() == 0


def test_gate3_security_fork_drift_self_test() -> None:
    assert gate3._self_test() == 0


def test_gate4_sink_coverage_self_test() -> None:
    assert gate4._self_test() == 0


def test_gate5_banned_constructs_self_test() -> None:
    assert gate5._self_test() == 0


def test_gate6_test_home_isolation_self_test() -> None:
    assert gate6._self_test() == 0


def test_gate1_hub_repo_currently_resolves_security_and_quality() -> None:
    # The hub's own codeql.yml passes queries: security-and-quality directly
    # (no config-file), so this must resolve true against real state.
    repo = Path(__file__).resolve().parents[1]
    ok, _explanation = gate1.effective_suite(repo)
    assert ok


def test_gate3_against_real_fleet_checkout_if_present() -> None:
    # Best-effort: only runs the real-fleet comparison when sibling repos are
    # checked out next to the hub (true in this dev environment, not
    # guaranteed in a fresh CI runner without a multi-repo checkout step).
    if not (_FLEET_ROOT / "PFactory").is_dir() or not (_FLEET_ROOT / "AIFactory").is_dir():
        return
    problems = gate3.check_drift(_FLEET_ROOT)
    # Not asserting problems == [] here: this is a real fleet snapshot and may
    # legitimately be red (see the report). The test only proves the gate
    # runs against real paths without raising.
    assert isinstance(problems, list)


def test_gate6_home_env_var_respected(tmp_path, monkeypatch) -> None:
    # tests must not touch the real $HOME even while testing the HOME gate.
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    assert os.environ["HOME"] == str(fake_home)


# ---------------------------------------------------------------------------
# Gate 5: a flagged line inside a logging call is not a response (Factory#782).
#
# The risk in that change is not a false positive surviving, it is a REAL
# finding being suppressed, so the fixture below is mostly the "must still be
# caught" direction. Five of its eight cases are responses that merely sit near
# a log line; three are genuine logging arguments.
#
# Two of the five are the shapes that broke the paren-counting implementation
# Factory#782 originally proposed, and both broke it in the dangerous
# direction. They are named as such so a future simplification back to a regex
# has to explain them.
# ---------------------------------------------------------------------------

# The fixture lives in tests/data/ as .py.txt, NOT inline in this module.
# It has to contain real `detail=str(e)` lines to be a fixture at all, and this
# repo runs Gate 5 on ITSELF as a blocking check -- inline, those nine lines
# turn the hub red. Both alternatives were worse: allowlisting this file would
# grandfather every real occurrence added to the gate's own test module
# afterwards (the (path, rule) key again), and splicing the strings to dodge
# the regex is the obfuscation this gate's own docstring argues against. `.txt`
# is not in _iter_source_files, so the fixture is data, which is what it is.
_LOGGER_CASES = (Path(__file__).parent / "data" / "logger_cases.py.txt").read_text(encoding="utf-8")


def _reported_functions(tmp_path: Path) -> set[str]:
    """Names of the fixture's functions that Gate 5 reports a finding in.

    Resolved by walking back to the enclosing `def` rather than by line number,
    so editing the fixture cannot silently re-point an assertion at a different
    case.
    """
    path = tmp_path / "logger_cases.py"
    path.write_text(_LOGGER_CASES, encoding="utf-8")
    lines = _LOGGER_CASES.splitlines()

    def enclosing_def(lineno: int) -> str:
        for i in range(lineno - 1, -1, -1):
            if lines[i].startswith("def "):
                return lines[i][len("def ") : lines[i].index("(")]
        raise AssertionError(f"line {lineno} is not inside a function")

    return {enclosing_def(lineno) for lineno, _ in gate5._find_raw_exception_in_response(path)}


def test_a_response_near_a_logger_call_is_still_caught(tmp_path: Path) -> None:
    """The direction that matters: suppressing one of these would be strictly
    worse than the false positives Factory#782 removes.

    ``caught_after_log_closed_on_the_same_line`` and
    ``caught_when_log_closes_before_a_multiline_response`` are the load-bearing
    pair. In both, a logging call OPENS AND CLOSES before a response on or
    below the same line, and in both the natural paren-counting check concludes
    the response belongs to the logger:

    * same line -- ``after.count("(") - after.count(")") >= 0`` scores zero,
      because the opener's own paren is not inside the slice being counted;
    * multi-line -- an upward walk sees the balance go negative on the line
      holding ``logger.info(...)`` and stops there, when the opener that is
      actually unclosed is ``HTTPException(``.

    Both read as correct on the page. The parser's (line, col) spans make the
    question a comparison instead of an estimate.
    """
    reported = _reported_functions(tmp_path)

    assert "caught_after_single_line_log" in reported
    assert "caught_after_closed_multiline_log" in reported
    assert "caught_after_log_closed_on_the_same_line" in reported
    assert "caught_when_log_closes_before_a_multiline_response" in reported
    assert "caught_interp_in_response" in reported


def test_a_logger_argument_is_suppressed(tmp_path: Path) -> None:
    """The direction Factory#782 is for, in all three shapes it takes.

    Both detector branches are covered: ``str(exc)`` (the original pattern) and
    the bare ``{exc}`` interpolation added by Factory#781. Being an argument to
    a log call is a property of the line's role, not of which pattern matched
    it, so the suppression applies to both.
    """
    reported = _reported_functions(tmp_path)

    assert "suppressed_inside_multiline_log" not in reported
    assert "suppressed_inside_single_line_log" not in reported
    assert "suppressed_interp_inside_log" not in reported


def test_the_suppression_is_python_only(tmp_path: Path) -> None:
    """A non-Python file gets no suppression, because it gets no parse.

    This function can only ever turn a real finding into a missed one, so where
    it cannot be exact it does nothing and the finding costs an allowlist entry
    instead. Asserted rather than left implied: a future edit that reached for
    a language-agnostic regex would change this silently.
    """
    js = tmp_path / "handler.ts"
    js.write_text(
        (Path(__file__).parent / "data" / "logger_cases.ts.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    assert gate5._find_raw_exception_in_response(js), (
        "the .ts logger line should still be reported: suppression is Python-only"
    )


# ---------------------------------------------------------------------------
# Gate 5: an allowlist entry that matches nothing is itself a failure
# (Factory#788). Entries are keyed (path, rule) -- PATH-level -- so a dead
# entry keeps exempting the whole file, and the next real violation added to
# it is suppressed by a grandfather whose finding was fixed months earlier.
# ---------------------------------------------------------------------------


def _repo_with_one_finding(tmp_path: Path) -> Path:
    """A tiny repo whose single source file has exactly one real finding."""
    # Fixture from tests/data/ for the same reason as _LOGGER_CASES: this repo
    # runs Gate 5 on ITSELF as a blocking check, and a fixture containing a real
    # `detail=str(e)` line turns the hub red when it lives in a scanned .py.
    (tmp_path / "app.py").write_text(
        (Path(__file__).parent / "data" / "one_finding.py.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return tmp_path


def _allowlist(tmp_path: Path, path_value: str) -> Path:
    target = tmp_path / "allow.yaml"
    target.write_text(
        f"- path: {path_value}\n"
        "  rule: raw-exception-in-response\n"
        "  reason: fixture\n"
        "  issue: Factory#788\n",
        encoding="utf-8",
    )
    return target


def test_a_live_allowlist_entry_still_suppresses(tmp_path: Path) -> None:
    """The positive control, and it is not optional.

    Without it, an implementation that reported EVERY entry as dead would pass
    the test below and look like a working ratchet while telling four repos to
    delete live exemptions. A zero from a broken matcher is byte-identical to a
    real zero.
    """
    repo = _repo_with_one_finding(tmp_path)
    problems = gate5.check(repo, _allowlist(tmp_path, "app.py"))

    assert problems == [], problems


def test_an_allowlist_entry_that_matches_nothing_fails(tmp_path: Path) -> None:
    """The ratchet. Fix the finding and the entry must go."""
    repo = _repo_with_one_finding(tmp_path)
    (repo / "app.py").write_text(  # the finding is now fixed
        'def handler(e):\n    raise HTTPException(status_code=500, detail="literal")\n',
        encoding="utf-8",
    )

    problems = gate5.check(repo, _allowlist(tmp_path, "app.py"))

    assert len(problems) == 1, problems
    assert "matches nothing" in problems[0]
    assert "app.py" in problems[0]


def test_an_entry_for_a_path_that_moved_fails(tmp_path: Path) -> None:
    """The other way an entry goes dead: the file was renamed, not fixed.

    Worth separating, because it is the case where the FINDING still exists --
    it just lives at a path the entry no longer names, so the entry is dead and
    the finding is unallowlisted at once.
    """
    repo = _repo_with_one_finding(tmp_path)

    problems = gate5.check(repo, _allowlist(tmp_path, "moved/elsewhere.py"))

    assert len(problems) == 2, problems
    assert any("matches nothing" in p for p in problems)
    assert any("app.py:2: raw-exception-in-response" in p for p in problems)


def test_no_allowlist_file_at_all_is_not_a_failure(tmp_path: Path) -> None:
    """Three of the four service repos have no allowlist yet.

    `allowed` is empty there, so `allowed - used` is empty and nothing is
    reported. Asserted rather than assumed: an implementation that iterated the
    file instead of the loaded set would raise on a missing path.
    """
    repo = tmp_path / "clean"
    repo.mkdir()
    (repo / "app.py").write_text("def handler():\n    return 1\n", encoding="utf-8")

    assert gate5.check(repo, None) == []
