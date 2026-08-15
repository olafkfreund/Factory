#!/usr/bin/env python3
"""PR-time cover for the safe agent-worktree cleanup tool (Factory#616).

The tool ships a ``--self-test`` that builds real git worktrees and grades every
verdict, but nothing runs it on a schedule -- it is a hand-run cleanup tool, not
a gate. That is the "the check exists and never runs" shape, so this file hooks
it into hub PR CI and pins the two properties that must not regress silently:
the tool must never force, and "committed clean" must never on its own mean
"nobody is using this".
"""

from __future__ import annotations

from pathlib import Path

# scripts/ is put on sys.path by tests/conftest.py.
import prune_agent_worktrees as tool

_SOURCE = Path(tool.__file__).read_text()


def test_builtin_self_test_passes() -> None:
    assert tool._self_test() == 0


def test_the_tool_never_forces() -> None:
    """No ``--force``/``-f`` anywhere in the git commands it runs.

    This is the single edit that would recreate Factory#616, and it is the edit
    a future maintainer is most likely to make -- the git error text for a
    stale lock literally recommends ``remove -f -f``. Asserted against the
    source because it must hold on every path, including ones the self-test's
    fixtures do not reach.
    """
    for banned in ('"-f"', "'-f'", '"--force"', "'--force'"):
        assert banned not in _SOURCE, f"{banned} in the cleanup tool recreates Factory#616"


def test_an_unparseable_lock_is_kept_not_removed() -> None:
    """Unknown owner is a keep. Never infer a dead agent from a lock you cannot read."""
    opaque = tool.Worktree(path=Path("/nonexistent"), locked=True, lock_reason="manual hold")
    assert tool.lock_holder_alive(opaque) is None
    verdict = tool.classify([opaque], min_idle_hours=0.0)[0]
    assert verdict[1] == "keep"


def test_a_live_pid_in_the_lock_is_kept() -> None:
    live = tool.Worktree(
        path=Path("/nonexistent"), locked=True, lock_reason="claude agent x (pid 4242)"
    )
    assert tool.lock_holder_alive(live, alive=lambda _pid: True) is True
    verdict = tool.classify([live], min_idle_hours=0.0, alive=lambda _pid: True)[0]
    assert verdict[1] == "keep"


def test_recency_alone_keeps_a_clean_unlocked_worktree(tmp_path: Path) -> None:
    """The regression case for the measurement that changed the design.

    All 19 real agent worktrees on the fleet were unlocked and committed clean,
    so lock-and-dirty checks alone declared every one removable -- including
    three whose branches had unmerged commits. A freshly touched tree with no
    lock and nothing dirty must still be kept.
    """
    tree = tmp_path / "wt"
    tree.mkdir()
    # A real, committed-clean repo: the recency check sits behind the
    # dirty check, so a fake directory would be kept for the wrong reason.
    tool.git(tree, "init", "-q", ".", check=True)
    tool.git(tree, "config", "user.email", "t@e.com", check=True)
    tool.git(tree, "config", "user.name", "t", check=True)
    (tree / "f.txt").write_text("x\n")
    tool.git(tree, "add", "f.txt", check=True)
    tool.git(tree, "commit", "-qm", "seed", check=True)
    fresh = tool.Worktree(path=tree, locked=False, lock_reason="")

    assert not tool.tree_has_work(tree), (
        "fixture must be committed clean for this case to mean anything"
    )

    kept = tool.classify([fresh], min_idle_hours=24.0)[0]
    assert kept[1] == "keep"
    assert "touched" in kept[2]

    # With the window off, the same tree is removable -- proving the keep above
    # came from recency and not from some other check passing by accident.
    assert tool.classify([fresh], min_idle_hours=0.0)[0][1] == "remove"


def test_the_main_checkout_is_never_a_candidate() -> None:
    """``parse_worktrees`` drops record zero. Removing it would delete the repo."""
    porcelain = (
        "worktree /repo\nHEAD abc\nbranch refs/heads/main\n\n"
        "worktree /repo/.claude/worktrees/a\nHEAD def\n"
    )
    parsed = tool.parse_worktrees(porcelain)
    assert [str(w.path) for w in parsed] == ["/repo/.claude/worktrees/a"]
