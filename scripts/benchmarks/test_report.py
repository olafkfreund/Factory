#!/usr/bin/env python3
"""Asserts for report.py. Run directly (`python3 test_report.py`) or under pytest."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import report

# The exact record run_pipeline_task.py::build_meta_record writes.
SIDECAR: dict[str, Any] = {
    "instance_id": "django__django-11299",
    "task_id": "t-1",
    "spec_id": "s-1",
    "status": "completed",
    "halt_reason": None,
    "total_tokens": 2931714,
    "cost_usd": 1.26,
    "duration_sec": 1800.0,
}


def _annotated(**overrides: Any) -> dict[str, Any]:
    record = dict(SIDECAR)
    record.update(overrides)
    return record


def test_reads_the_existing_sidecar_shape() -> None:
    run = report.to_run(SIDECAR)
    assert run.job == "django__django-11299"
    assert run.status == "completed"
    assert run.passed
    assert run.total_tokens == 2931714
    assert run.duration_sec == 1800.0
    # not annotated by the base harness -> unknown, never a crash
    assert run.service == report.UNKNOWN
    assert run.mode == "serial"


def test_halt_reason_blocks_a_pass() -> None:
    run = report.to_run(_annotated(halt_reason="no_evidence", status="failed"))
    assert not run.passed
    assert run.halt_reason == "no_evidence"
    # a hollow completed (evidence gate downgrade) must not read as a pass
    assert not report.to_run(_annotated(halt_reason="no_evidence")).passed


def test_missing_fields_render_as_dash() -> None:
    run = report.to_run({"instance_id": "x"})
    assert run.duration_sec is None
    log = report.run_log_table([run], {})
    assert "| x |" in log
    assert report.UNKNOWN in log


def test_backend_table_groups_and_scores() -> None:
    runs = [
        report.to_run(_annotated(instance_id="a", backend="anthropic", duration_sec=600.0)),
        report.to_run(_annotated(instance_id="b", backend="anthropic", duration_sec=1200.0)),
        report.to_run(_annotated(instance_id="c", backend="ollama", status="failed")),
    ]
    table = report.backend_table(runs, {"a": "resolved", "b": "unresolved"})
    rows = {line.split("|")[1].strip(): line for line in table.splitlines() if "|" in line}
    assert "2/2 (100%)" in rows["anthropic"]  # pipeline pass
    assert "1/2 (50%)" in rows["anthropic"]  # resolved out of the scored ones
    assert "15.0" in rows["anthropic"]  # median of 10 and 20 minutes
    assert "0/1 (0%)" in rows["ollama"]
    assert report.UNKNOWN in rows["ollama"]  # unscored -> blank quality


def test_wallclock_speedup() -> None:
    serial = [
        report.to_run(_annotated(instance_id=f"s{i}", mode="serial", duration_sec=600.0))
        for i in range(3)
    ]
    parallel = [
        report.to_run(
            _annotated(
                instance_id=f"p{i}", mode="parallel", duration_sec=600.0, wall_clock_sec=660.0
            )
        )
        for i in range(3)
    ]
    table = report.wallclock_table([*serial, *parallel])
    rows = {line.split("|")[1].strip(): line for line in table.splitlines() if "|" in line}
    # serial: no measured wall-clock -> longest task (10 min), 30 min of work
    assert "| 10.0 | 30.0 | 3.00x" in rows["serial"]
    # parallel: measured 11 min wave vs 30 min of work
    assert "| 11.0 | 30.0 | 2.73x" in rows["parallel"]


def test_gold_precedence_and_bad_report() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.run.json"
        path.write_text(
            json.dumps(
                {
                    "resolved_ids": ["a"],
                    "unresolved_ids": ["b", "a"],
                    "empty_patch_ids": ["c"],
                    "error_ids": ["d"],
                }
            )
        )
        gold = report.load_gold(str(path))
        assert gold == {
            "a": "resolved",
            "b": "unresolved",
            "c": "empty-patch",
            "d": "harness-error",
        }
        broken = Path(tmp) / "broken.json"
        broken.write_text("{not json")
        assert report.load_gold(str(broken)) == {}
        assert report.load_gold(None) == {}
        assert report.load_gold(str(Path(tmp) / "missing.json")) == {}


def test_load_runs_from_a_directory_is_fail_safe() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        (out / "a.meta.json").write_text(json.dumps(_annotated(instance_id="a")))
        (out / "b.meta.json").write_text(json.dumps(_annotated(instance_id="b")))
        (out / "broken.meta.json").write_text("{oops")
        # prediction records share the output dir and must not become runs
        prediction = {"instance_id": "a", "model_name_or_path": "m", "model_patch": "diff"}
        (out / "predictions.jsonl").write_text(json.dumps(prediction) + "\n")
        runs = report.load_runs([str(out)])
        assert sorted(run.job for run in runs) == ["a", "b"]
        assert report.load_runs([str(out / "nope.json")]) == []


def test_build_report_has_all_three_tables_and_survives_empty_input() -> None:
    doc = report.build_report([report.to_run(SIDECAR)], {}, "Matrix")
    assert doc.startswith("# Matrix")
    for heading in ("Per-backend latency", "Parallel vs serial", "Run log"):
        assert heading in doc
    empty = report.build_report([], {}, "Empty")
    assert empty.count("_(no records)_") == 3


def test_cli_writes_a_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        (out / "a.meta.json").write_text(json.dumps(SIDECAR))
        target = out / "nested" / "report.md"
        assert report.main([str(out), "--title", "CLI", "-o", str(target)]) == 0
        assert target.read_text().startswith("# CLI")


if __name__ == "__main__":
    for name, fn in sorted(vars().copy().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            sys.stdout.write(f"ok {name}\n")
    sys.stdout.write("all tests passed\n")
