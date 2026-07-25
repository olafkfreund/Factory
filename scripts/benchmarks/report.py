#!/usr/bin/env python3
"""Aggregate benchmark run records into the markdown evidence tables (Factory#295 F1-F3).

Input is what the harness ALREADY emits -- no new schema:

  * `<instance_id>.meta.json` sidecars written by `run_pipeline_task.py`
    (`build_meta_record`: instance_id, task_id, spec_id, status, halt_reason,
    total_tokens, cost_usd, duration_sec). Pass the file, or the directory
    holding them.
  * the same records concatenated as `.jsonl`.
  * optionally the OFFICIAL harness report `{model}.{run_id}.json` produced by
    `evaluate.py` (`--eval-report`), which supplies the gold outcome per
    instance (resolved / unresolved / empty-patch / harness-error). We never
    self-score; quality columns are blank without it.

Validation runs (epic #295 C/D) annotate a record with the extra fields the
matrix needs -- `service`, `backend`, `model`, `val_level`, `mode`
(serial|parallel), `wall_clock_sec` -- and they flow straight through. Records
missing them still report; unknown values render as "-".

Output (markdown, stdout or --out):

  * per-backend latency / cost / quality table  (F2)
  * parallel-vs-serial wall-clock table         (F3)
  * combined run log                            (F1)

Pure stdlib, no third-party deps. Unreadable or malformed inputs are skipped
with a warning on stderr rather than aborting the report.

Usage:
  python3 report.py bench-out/ --eval-report factory-pipeline.run-1.json \\
      --title "Backend matrix 2026-07" -o docs/benchmarks/matrix.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

UNKNOWN = "-"

# Terminal statuses the pipeline reports as a clean finish. Deliberately narrow:
# the 2026-07 baseline showed pipeline status is a weak proxy for correctness,
# so this is labelled "pipeline pass", never "resolved".
PASS_STATUSES = frozenset({"completed", "success", "passed", "resolved"})

# Official-harness report id lists -> the gold outcome label, in precedence order
# (an instance can appear in more than one list; the first match wins).
GOLD_ID_KEYS: tuple[tuple[str, str], ...] = (
    ("resolved_ids", "resolved"),
    ("unresolved_ids", "unresolved"),
    ("empty_patch_ids", "empty-patch"),
    ("error_ids", "harness-error"),
    ("incomplete_ids", "incomplete"),
)


def _warn(message: str) -> None:
    sys.stderr.write(f"report.py: {message}\n")


# -- record model ------------------------------------------------------------


@dataclass(frozen=True)
class Run:
    """One task run. Field names mirror the meta sidecar; the rest are optional
    annotations a validation run adds (service/backend/model/VAL/mode)."""

    job: str
    service: str
    backend: str
    model: str
    status: str
    halt_reason: str | None
    val: str
    mode: str
    duration_sec: float | None
    total_tokens: float | None
    cost_usd: float | None
    wall_clock_sec: float | None

    @property
    def passed(self) -> bool:
        return self.status in PASS_STATUSES and not self.halt_reason


def _pick_str(raw: Mapping[str, Any], keys: Sequence[str], default: str = UNKNOWN) -> str:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def _pick_num(raw: Mapping[str, Any], keys: Sequence[str]) -> float | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            return float(value)
    return None


def to_run(raw: Mapping[str, Any]) -> Run:
    """Normalise one raw record. Every field is best-effort: a sidecar written by
    a failed run is still a data point."""
    halt = raw.get("halt_reason")
    return Run(
        job=_pick_str(raw, ("instance_id", "job", "job_name", "task_id", "name")),
        service=_pick_str(raw, ("service", "factory")),
        backend=_pick_str(raw, ("backend", "provider", "model", "model_resolved")),
        model=_pick_str(raw, ("model_resolved", "model", "model_name_or_path")),
        status=_pick_str(raw, ("status", "verdict"), default="unknown"),
        halt_reason=halt if isinstance(halt, str) and halt else None,
        val=_pick_str(raw, ("val_level", "val", "verification_level")),
        mode=_pick_str(raw, ("mode", "execution_mode"), default="serial"),
        duration_sec=_pick_num(raw, ("duration_sec", "duration", "elapsed_sec")),
        total_tokens=_pick_num(raw, ("total_tokens", "tokens")),
        cost_usd=_pick_num(raw, ("cost_usd", "cost", "total_cost_usd")),
        wall_clock_sec=_pick_num(raw, ("wall_clock_sec", "run_wall_clock_sec")),
    )


def _is_result_record(raw: Mapping[str, Any]) -> bool:
    """Prediction records (`model_patch`) live in the same output dir as the meta
    sidecars; they carry no outcome, so they are not run records."""
    if "model_patch" in raw:
        return False
    return any(k in raw for k in ("status", "verdict", "duration_sec", "instance_id"))


# -- input loading -----------------------------------------------------------


def _as_dicts(data: object) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _loads(label: str, text: str) -> Any:
    """Parsed JSON, or None on a malformed input (callers narrow with _as_dicts)."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        _warn(f"skipping {label}: {exc}")
        return None


def load_file(path: Path) -> list[dict[str, Any]]:
    """Records from one .json / .jsonl file. Never raises."""
    try:
        text = path.read_text()
    except OSError as exc:
        _warn(f"skipping {path}: {exc}")
        return []
    if path.suffix == ".jsonl":
        records: list[dict[str, Any]] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.strip():
                records.extend(_as_dicts(_loads(f"{path}:{lineno}", line)))
        return records
    return _as_dicts(_loads(str(path), text))


def load_runs(paths: Iterable[str]) -> list[Run]:
    """Load every record under `paths` (files, or directories of *.meta.json)."""
    raw: list[dict[str, Any]] = []
    for entry in paths:
        path = Path(entry)
        if path.is_dir():
            files = sorted(path.glob("*.meta.json")) + sorted(path.glob("*.jsonl"))
            if not files:
                _warn(f"no *.meta.json or *.jsonl under {path}")
        elif path.exists():
            files = [path]
        else:
            _warn(f"skipping {path}: not found")
            continue
        for file in files:
            raw.extend(load_file(file))
    return [to_run(r) for r in raw if _is_result_record(r)]


def load_gold(path: str | None) -> dict[str, str]:
    """instance_id -> gold outcome, from the official harness report JSON."""
    if not path:
        return {}
    data = _loads(path, Path(path).read_text()) if Path(path).exists() else None
    if data is None:
        _warn(f"eval report {path} unreadable; quality columns will be blank")
        return {}
    if not isinstance(data, dict):
        _warn(f"eval report {path} is not an object; ignoring")
        return {}
    gold: dict[str, str] = {}
    for key, label in GOLD_ID_KEYS:
        ids = data.get(key)
        if isinstance(ids, list):
            for instance in ids:
                if isinstance(instance, str):
                    gold.setdefault(instance, label)
    return gold


# -- markdown ----------------------------------------------------------------


def md_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    if not rows:
        return "_(no records)_"
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _fmt_min(seconds: float | None) -> str:
    return UNKNOWN if seconds is None else f"{seconds / 60:.1f}"


def _fmt_count(value: float | None) -> str:
    return UNKNOWN if value is None else f"{value:,.0f}"


def _fmt_usd(value: float | None) -> str:
    return UNKNOWN if value is None else f"${value:,.2f}"


def _rate(numerator: int, denominator: int) -> str:
    if not denominator:
        return UNKNOWN
    return f"{numerator}/{denominator} ({100 * numerator / denominator:.0f}%)"


def _nums(runs: Sequence[Run], field: str) -> list[float]:
    return [v for v in (getattr(run, field) for run in runs) if isinstance(v, float)]


def _median(values: Sequence[float]) -> float | None:
    return statistics.median(values) if values else None


def _sum(values: Sequence[float]) -> float | None:
    return sum(values) if values else None


def _group(runs: Iterable[Run], field: str) -> dict[str, list[Run]]:
    groups: dict[str, list[Run]] = defaultdict(list)
    for run in runs:
        groups[str(getattr(run, field))].append(run)
    return groups


def backend_table(runs: Sequence[Run], gold: Mapping[str, str]) -> str:
    """F2: latency / cost / quality per model backend."""
    rows: list[list[str]] = []
    groups = _group(runs, "backend")
    for backend in sorted(groups):
        group = groups[backend]
        durations = _nums(group, "duration_sec")
        tokens = _nums(group, "total_tokens")
        resolved = sum(1 for run in group if gold.get(run.job) == "resolved")
        scored = sum(1 for run in group if run.job in gold)
        rows.append(
            [
                backend,
                str(len(group)),
                _rate(sum(1 for run in group if run.passed), len(group)),
                _rate(resolved, scored) if scored else UNKNOWN,
                _fmt_min(_median(durations)),
                _fmt_min(max(durations) if durations else None),
                _fmt_count(_median(tokens)),
                _fmt_usd(_sum(_nums(group, "cost_usd"))),
            ]
        )
    return md_table(
        (
            "backend",
            "runs",
            "pipeline pass",
            "resolved (gold)",
            "median min",
            "max min",
            "median tokens",
            "cost",
        ),
        rows,
    )


def wallclock_table(runs: Sequence[Run]) -> str:
    """F3: parallel vs serial wall-clock, grouped by the record's `mode`."""
    rows: list[list[str]] = []
    groups = _group(runs, "mode")
    for mode in sorted(groups):
        group = groups[mode]
        durations = _nums(group, "duration_sec")
        measured = _nums(group, "wall_clock_sec")
        serial_total = _sum(durations)
        # measured group wall-clock when a run recorded one, else the longest
        # single task (the floor for a perfectly parallel wave).
        wall = max(measured) if measured else (max(durations) if durations else None)
        speedup = f"{serial_total / wall:.2f}x" if serial_total and wall and wall > 0 else UNKNOWN
        rows.append(
            [
                mode,
                str(len(group)),
                _fmt_min(wall),
                _fmt_min(serial_total),
                speedup,
                _fmt_count(_sum(_nums(group, "total_tokens"))),
                _fmt_usd(_sum(_nums(group, "cost_usd"))),
            ]
        )
    return md_table(
        ("mode", "tasks", "wall-clock min", "serial total min", "speedup", "tokens", "cost"),
        rows,
    )


def run_log_table(runs: Sequence[Run], gold: Mapping[str, str]) -> str:
    """F1: one row per run -- the combined evidence log."""
    rows = [
        [
            run.job,
            run.service,
            run.backend,
            run.model,
            run.status if not run.halt_reason else f"{run.status} ({run.halt_reason})",
            run.val,
            gold.get(run.job, UNKNOWN),
            _fmt_min(run.duration_sec),
            _fmt_count(run.total_tokens),
            _fmt_usd(run.cost_usd),
        ]
        for run in sorted(runs, key=lambda r: (r.backend, r.job))
    ]
    return md_table(
        (
            "job",
            "service",
            "backend",
            "model",
            "status",
            "VAL",
            "gold",
            "min",
            "tokens",
            "cost",
        ),
        rows,
    )


def build_report(runs: Sequence[Run], gold: Mapping[str, str], title: str) -> str:
    scored = sum(1 for run in runs if run.job in gold)
    provenance = f"{len(runs)} run record(s)"
    provenance += f"; {scored} scored by the official harness." if scored else "; no gold scoring."
    return "\n".join(
        [
            f"# {title}",
            "",
            provenance,
            "",
            "## Per-backend latency, cost and quality",
            "",
            backend_table(runs, gold),
            "",
            "`pipeline pass` is the pipeline's own terminal status and is a weak proxy for",
            "correctness; `resolved (gold)` is the official harness verdict over the runs it",
            "scored. Times are per-task wall-clock minutes.",
            "",
            "## Parallel vs serial wall-clock",
            "",
            wallclock_table(runs),
            "",
            "`wall-clock` is the group's recorded `wall_clock_sec` when the harness captured",
            "one, else the longest single task (the floor for a perfectly parallel wave);",
            "`serial total` is the sum of task durations.",
            "",
            "## Run log",
            "",
            run_log_table(runs, gold),
            "",
        ]
    )


# -- CLI ---------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate harness run records into the #295 markdown evidence tables.",
        epilog="Inputs are the meta sidecars run_pipeline_task.py already writes.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="*.meta.json / *.jsonl files, or directories containing them",
    )
    parser.add_argument(
        "--eval-report",
        help="official SWE-bench report JSON ({model}.{run_id}.json) for gold outcomes",
    )
    parser.add_argument("--title", default="Benchmark results", help="markdown H1")
    parser.add_argument("-o", "--out", help="write markdown here instead of stdout")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    runs = load_runs(args.paths)
    if not runs:
        _warn("no run records found; emitting an empty report")
    report = build_report(runs, load_gold(args.eval_report), args.title)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report)
        sys.stderr.write(f"report.py: wrote {out} ({len(runs)} runs)\n")
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
