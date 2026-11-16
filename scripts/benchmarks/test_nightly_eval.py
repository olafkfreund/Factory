"""Tests for nightly_eval.py pure logic (Factory#3713). No network, no harness."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import nightly_eval as ne

CFG = {
    "tasks": ["a", "b", "c"],
    "max_tasks": 3,
    "tier": "medium",
    "timeout_min": 1,
    "per_task_token_cap": 100,
    "total_token_budget": 250,
    "regression_drop_tasks": 2,
    "min_paired": 3,
    "baseline": {"a": "resolved", "b": "unresolved", "zzz": "resolved"},
}
PROV = {"models_configured": {"coding": "opus"}, "prompt_hash": "h1", "commits": {"Factory": "f"}}


def _result(run_id: str, outcomes: dict[str, str], prompt: str = "h1") -> dict[str, Any]:
    rows = [
        {"instance_id": i, "pipeline_status": "completed", "tokens": 10, "outcome": o}
        for i, o in outcomes.items()
    ]
    return ne.build_result(run_id, {**PROV, "prompt_hash": prompt}, CFG, rows)


def test_select_tasks_order_cap_and_missing() -> None:
    catalog = [{"instance_id": i} for i in "cba"]
    assert [t["instance_id"] for t in ne.select_tasks({**CFG, "max_tasks": 2}, catalog)] == [
        "a",
        "b",
    ]
    with pytest.raises(SystemExit):
        ne.select_tasks({**CFG, "tasks": ["nope"]}, catalog)


def test_find_models_nested() -> None:
    assert ne.find_models({"w": [{"model": "x"}, {"u": {"model": "y"}}], "model": "x"}) == [
        "x",
        "y",
    ]


def test_task_row_driver_crash_and_over_cap() -> None:
    assert ne.task_row("a", None, 100)["pipeline_status"] == "driver_error"
    assert (
        ne.task_row("a", {"status": "human_review", "total_tokens": 101}, 100)["over_cap"] is True
    )


def test_budget_charges_cap_for_missing_tokens() -> None:
    assert ne.budget_used([{"tokens": 30}, {"tokens": None}], 100) == 130


def test_exit2_task_with_patch_is_still_scored() -> None:
    rows = [ne.task_row("a", {"status": "human_review", "halt_reason": "pipeline_error"}, 100)]
    ne.apply_outcomes(rows, {"a": "resolved"})
    assert rows[0]["outcome"] == "resolved"


def test_apply_outcomes_keeps_skip_and_crash_and_unscored() -> None:
    rows = [
        {"instance_id": "a", "pipeline_status": "skipped_budget"},
        {"instance_id": "b", "pipeline_status": "driver_error"},
        {"instance_id": "c", "pipeline_status": "completed"},
    ]
    ne.apply_outcomes(rows, {})
    assert [r["outcome"] for r in rows] == ["skipped_budget", "driver_error", "unscored"]


def test_compare_flags_drop_of_two() -> None:
    prev = _result("1", {"a": "resolved", "b": "resolved", "c": "resolved"})
    cur = _result("2", {"a": "unresolved", "b": "empty-patch", "c": "resolved"})
    cmp = ne.compare_results(prev, cur, CFG)
    assert cmp["regression"] and cmp["drop"] == 2 and cmp["lost"] == ["a", "b"]


def test_gain_offsets_loss_and_one_drop_is_not_regression() -> None:
    prev = _result("1", {"a": "resolved", "b": "unresolved", "c": "resolved"})
    cur = _result("2", {"a": "unresolved", "b": "resolved", "c": "resolved"})
    assert not ne.compare_results(prev, cur, CFG)["regression"]


def test_harness_errors_and_skips_do_not_fake_a_regression() -> None:
    prev = _result("1", {"a": "resolved", "b": "resolved", "c": "resolved"})
    cur = _result("2", {"a": "harness-error", "b": "skipped_budget", "c": "resolved"})
    cmp = ne.compare_results(prev, cur, CFG)
    assert cmp["paired"] == 1 and not cmp["enough_coverage"] and not cmp["regression"]


def test_prompt_change_is_reported() -> None:
    prev = _result("1", {"a": "resolved", "b": "resolved", "c": "resolved"})
    cur = _result("2", {"a": "resolved", "b": "resolved", "c": "resolved"}, prompt="h2")
    cmp = ne.compare_results(prev, cur, CFG)
    assert cmp["prompt_changed"] and "Prompt hash changed" in ne.render_comparison(cmp)


def test_report_has_baseline_for_the_subset_only() -> None:
    text = ne.render_report(
        [_result("1", {"a": "resolved", "b": "unresolved", "c": "resolved"})], CFG
    )
    assert "| 2026-07 baseline | - | 1 / 2 | 2 |" in text and "2 / 3" in text


def test_compare_cli_exit_codes_and_same_day_runs_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NIGHTLY_RESULTS_DIR", str(tmp_path))
    monkeypatch.setattr(ne, "CONFIG_PATH", tmp_path / "cfg.json")
    ne.CONFIG_PATH.write_text(json.dumps(CFG))
    assert ne.main(["compare"]) == 0  # no results at all
    first = _result("20261116T030000Z", {"a": "resolved", "b": "resolved", "c": "resolved"})
    (tmp_path / "20261116T030000Z.json").write_text(json.dumps(first))
    assert ne.main(["compare"]) == 0  # no previous
    second = _result("20261116T150000Z", {"a": "unresolved", "b": "unresolved", "c": "resolved"})
    (tmp_path / "20261116T150000Z.json").write_text(json.dumps(second))
    assert ne.main(["compare"]) == ne.EXIT_REGRESSION
