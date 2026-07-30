#!/usr/bin/env python3
"""Self-test for the deploy-drift watchdog comparator (Factory#461).

The comparator ships its own dependency-free ``--self-test``, which the
scheduled watchdog runs before it believes its own verdict. That only runs on a
schedule, though, so a hub PR could break the comparator and nothing on the PR
would say so - which is the same "the gate did not run" shape Factory#471 is
about. This file hooks the self-test into hub PR CI.
"""

from __future__ import annotations

# scripts/ is put on sys.path by tests/conftest.py.
import check_deploy_drift as gate


def test_builtin_self_test_passes() -> None:
    assert gate._self_test() == 0


def test_unreadable_deployed_tag_fails_immediately() -> None:
    # The direction the grace window would otherwise hide: no answer from
    # factory-gitops must be red now, not "pending" for 45 minutes.
    now = 1_000_000_000
    code, message = gate.check("abc1234def", now - 60, "", now)
    assert code == 1
    assert "CANNOT VERIFY" in message
