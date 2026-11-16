"""The nightly bench issue step must create its label first (Factory#3727)."""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/bench-nightly.yml"


def test_label_created_before_use() -> None:
    text = WORKFLOW.read_text()
    create = text.index("gh label create bench-regression --force")
    assert create < text.index("gh issue create --title")
    assert create < text.index("gh issue list --label bench-regression")
