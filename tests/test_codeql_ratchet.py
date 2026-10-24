"""Hooks the CodeQL ratchet self-test into hub PR CI (Factory#813)."""

import codeql_ratchet as ratchet


def test_builtin_self_test_passes() -> None:
    assert ratchet._self_test() == 0


def test_increase_fails_and_prints_delta() -> None:
    ok, lines = ratchet.compare({"critical": 0, "high": 3, "error": 0, "medium": 0}, {"high": 2})
    assert not ok
    assert "high: 3 / baseline 2 (+1)" in lines
