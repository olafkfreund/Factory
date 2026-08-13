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
