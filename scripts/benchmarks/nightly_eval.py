#!/usr/bin/env python3
"""Nightly standing evaluation of the pipeline (Factory#3713).

Runs the fixed subset in benchmarks/nightly-config.json through
run_pipeline_task.py, scores it with the official harness (evaluate.py), stores
one result file per run with its provenance (models, prompt hash, service
commits), and compares against the previous run.

  nightly_eval.py run [--dry-run]   run + score + store
  nightly_eval.py compare           newest vs previous; exit 3 on regression
  nightly_eval.py report            markdown time series

Env: NIGHTLY_RESULTS_DIR (default ~/.factory-bench/nightly), APP_API_TOKEN,
AIFACTORY_URL, AIFACTORY_DIR and friends (see provenance.py). Design:
spec/2026-11-16-3713-standing-eval.md. Never prints the token.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import provenance  # noqa: E402
import report as report_mod  # noqa: E402

CONFIG_PATH = HERE.parents[1] / "benchmarks" / "nightly-config.json"
TASKS_PATH = HERE.parents[1] / "benchmarks" / "swebench-verified-50.json"
HF_FILTER = (
    "https://datasets-server.huggingface.co/filter?dataset=princeton-nlp%2FSWE-bench_Verified"
    "&config=default&split=test&where="
)
SCORED = frozenset({"resolved", "unresolved", "empty-patch"})
EXIT_REGRESSION = 3
EXIT_UNGRADED = 4
MIN_RUNS_TO_COMPARE = 2


def results_dir() -> Path:
    return Path(os.environ.get("NIGHTLY_RESULTS_DIR") or Path.home() / ".factory-bench" / "nightly")


# ── pure logic ───────────────────────────────────────────────────────────────


def select_tasks(config: dict[str, Any], catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The configured ids, in config order, capped at max_tasks. An id missing
    from the catalog is a config error, not something to skip silently."""
    by_id = {t["instance_id"]: t for t in catalog}
    missing = [i for i in config["tasks"] if i not in by_id]
    if missing:
        raise SystemExit(f"tasks not in the catalog: {missing}")
    return [by_id[i] for i in config["tasks"][: config["max_tasks"]]]


def find_models(obj: Any) -> list[str]:
    """Every string under a `model` key, anywhere in a JSON document."""
    found: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "model" and isinstance(value, str):
                found.add(value)
            found.update(find_models(value))
    elif isinstance(obj, list):
        for item in obj:
            found.update(find_models(item))
    return sorted(found)


def task_row(instance_id: str, meta: dict[str, Any] | None, cap: int) -> dict[str, Any]:
    """One result row from a driver sidecar; no sidecar means the driver died."""
    if meta is None:
        return {"instance_id": instance_id, "pipeline_status": "driver_error", "tokens": None}
    tokens = meta.get("total_tokens")
    return {
        "instance_id": instance_id,
        "pipeline_status": meta.get("status"),
        "halt_reason": meta.get("halt_reason"),
        "tokens": tokens,
        "cost_usd": meta.get("cost_usd"),
        "duration_sec": meta.get("duration_sec"),
        "over_cap": isinstance(tokens, int | float) and tokens > cap,
        "models_observed": meta.get("models_observed", []),
    }


def budget_used(rows: list[dict[str, Any]], cap: int) -> float:
    """A task with no token evidence is charged the cap, so a silent failure
    cannot make the budget look unspent."""
    return sum(r["tokens"] if isinstance(r.get("tokens"), int | float) else cap for r in rows)


def apply_outcomes(rows: list[dict[str, Any]], gold: dict[str, str]) -> None:
    for row in rows:
        if row["pipeline_status"] in ("skipped_budget", "driver_error"):
            row["outcome"] = row["pipeline_status"]
        else:
            row["outcome"] = gold.get(row["instance_id"], "unscored")


def build_result(
    run_id: str,
    prov: dict[str, Any],
    config: dict[str, Any],
    rows: list[dict[str, Any]],
    wall_sec: float,
) -> dict[str, Any]:
    scored = [r for r in rows if r["outcome"] in SCORED]
    return {
        "run_id": run_id,
        "label": provenance.label(prov),
        "provenance": prov,
        "config": {
            k: config[k]
            for k in ("tasks", "tier", "timeout_min", "per_task_token_cap", "total_token_budget")
        },
        "tasks": rows,
        "totals": {
            "resolved": sum(r["outcome"] == "resolved" for r in rows),
            "scored": len(scored),
            "tasks": len(rows),
            "tokens": sum(r["tokens"] for r in rows if isinstance(r.get("tokens"), int | float)),
            "cost_usd": round(sum(r.get("cost_usd") or 0 for r in rows), 2),
            "duration_sec": round(wall_sec, 1),
        },
    }


def compare_results(
    prev: dict[str, Any], cur: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    """Paired comparison: only tasks scored in BOTH runs count, so harness
    infrastructure errors, budget skips and driver crashes cannot fake a drop."""
    p = {r["instance_id"]: r["outcome"] for r in prev["tasks"]}
    c = {r["instance_id"]: r["outcome"] for r in cur["tasks"]}
    paired = sorted(i for i in c if c[i] in SCORED and p.get(i) in SCORED)
    lost = [i for i in paired if p[i] == "resolved" and c[i] != "resolved"]
    gained = [i for i in paired if p[i] != "resolved" and c[i] == "resolved"]
    drop = len(lost) - len(gained)
    enough = len(paired) >= config["min_paired"]
    return {
        "prev": prev["run_id"],
        "cur": cur["run_id"],
        "paired": len(paired),
        "enough_coverage": enough,
        "lost": lost,
        "gained": gained,
        "drop": drop,
        "regression": enough and drop >= config["regression_drop_tasks"],
        "prompt_changed": prev["provenance"]["prompt_hash"] != cur["provenance"]["prompt_hash"],
        "tasks_changed": prev["config"]["tasks"] != cur["config"]["tasks"],
        "cost_delta": round(cur["totals"]["cost_usd"] - prev["totals"]["cost_usd"], 2),
        "duration_delta_sec": round(
            cur["totals"]["duration_sec"] - prev["totals"]["duration_sec"], 1
        ),
    }


def render_comparison(cmp: dict[str, Any]) -> str:
    lines = [f"## Change vs previous run ({cmp['prev']} -> {cmp['cur']})", ""]
    lines.append(
        f"- Paired scored tasks: {cmp['paired']}; net change in resolved: {-cmp['drop']:+d}"
    )
    lines.append(f"- Resolved before, not now: {', '.join(cmp['lost']) or 'none'}")
    lines.append(f"- Resolved now, not before: {', '.join(cmp['gained']) or 'none'}")
    lines.append(
        f"- Cost {cmp['cost_delta']:+.2f} USD, duration {cmp['duration_delta_sec']:+.0f} s"
    )
    if cmp["prompt_changed"]:
        lines.append("- Prompt hash changed between these runs.")
    if cmp["tasks_changed"]:
        lines.append("- WARNING: the task list differs; only common tasks were compared.")
    if not cmp["enough_coverage"]:
        lines.append("- Insufficient paired coverage: no regression verdict.")
    if cmp["regression"]:
        lines.append(f"- **REGRESSION: {cmp['drop']} fewer resolved**")
    elif cmp["enough_coverage"]:
        lines.append("- No regression.")
    return "\n".join(lines) + "\n"


def render_report(results: list[dict[str, Any]], config: dict[str, Any]) -> str:
    ids = set(config["tasks"])
    base = {i: o for i, o in config.get("baseline", {}).items() if i in ids}
    rows = [
        "| run | label | resolved / scored | tasks | tokens | cost USD | wall min |",
        "|---|---|---|---|---|---|---|",
        f"| 2026-07 baseline | - | {sum(o == 'resolved' for o in base.values())} / "
        f"{sum(o in SCORED for o in base.values())} | {len(base)} | - | - | - |",
    ]
    for r in results:
        t = r["totals"]
        rows.append(
            f"| {r['run_id']} | {r['label']} | {t['resolved']} / {t['scored']} | {t['tasks']} "
            f"| {t['tokens']:,.0f} | {t['cost_usd']:.2f} | {t['duration_sec'] / 60:.0f} |"
        )
    return "# Nightly evaluation history\n\n" + "\n".join(rows) + "\n"


def load_results(directory: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text()) for p in sorted(directory.glob("2*T*Z.json"))]


# ── edges (subprocess, network) ──────────────────────────────────────────────


def fetch_problem(instance_id: str, cache: Path) -> str:
    path = cache / f"{instance_id}.txt"
    if path.exists():
        return path.read_text()
    where = urllib.parse.quote(f"\"instance_id\"='{instance_id}'")
    # fixed https datasets-server URL; the id comes from our own config
    with urllib.request.urlopen(HF_FILTER + where, timeout=60) as resp:  # noqa: S310
        text: str = json.load(resp)["rows"][0]["row"]["problem_statement"]
    cache.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return text


def run_driver(
    task: dict[str, Any], run_id: str, model: str, work: Path, config: dict[str, Any]
) -> dict[str, Any] | None:
    """Run the driver for one task; exit 2 (non-completed) still yields a record."""
    iid = task["instance_id"]
    statement = work / f"{iid}.problem.txt"
    statement.write_text(fetch_problem(iid, work.parent.parent / "problems"))
    cmd = [
        sys.executable, str(HERE / "run_pipeline_task.py"),
        "--instance-id", iid,
        "--repo-url", f"https://github.com/{task['repo']}.git",
        "--base-commit", task["base_commit"],
        "--problem-statement-file", str(statement),
        "--scratch-root", str(work / "scratch"),
        "--tier", config["tier"],
        "--timeout-min", str(config["timeout_min"]),
        "--model-name", model,
        "--run-id", run_id,
        "--out", str(work / "predictions.jsonl"),
    ]  # fmt: skip
    # fixed argv, sys.executable + our own script, no shell
    subprocess.run(cmd, check=False)  # noqa: S603
    sidecar = work / f"{iid}.meta.json"
    if not sidecar.exists():
        return None
    meta: dict[str, Any] = json.loads(sidecar.read_text())
    if meta.get("spec_id"):
        spec_dir = work / "scratch" / iid / ".aifactory" / "specs" / str(meta["spec_id"])
        models: list[str] = []
        for name in ("token_usage.json", "COMPLETED.json"):
            if (spec_dir / name).exists():
                models += find_models(json.loads((spec_dir / name).read_text()))
        meta["models_observed"] = sorted(set(models))
    return meta


def score(work: Path, run_id: str, model: str, ids: list[str]) -> dict[str, str]:
    ids_file = work / "ids.json"
    ids_file.write_text(json.dumps(ids))
    cmd = [
        sys.executable, str(HERE / "evaluate.py"),
        "-p", str(work / "predictions.jsonl"), "-id", run_id,
        "--instance-ids-file", str(ids_file),
    ]  # fmt: skip
    # fixed argv, our own script, no shell; the harness writes its report to cwd
    subprocess.run(cmd, cwd=work, check=False)  # noqa: S603
    harness_report = work / f"{model.replace('/', '__')}.{run_id}.json"
    return report_mod.load_gold(str(harness_report)) if harness_report.exists() else {}


def cmd_run(args: argparse.Namespace) -> int:
    config = json.loads(CONFIG_PATH.read_text())
    tasks = select_tasks(config, json.loads(TASKS_PATH.read_text()))
    prov = provenance.collect(config)
    model = provenance.label(prov)
    print(f"label {model}\nmodels {prov['models_configured']}")  # noqa: T201
    print(f"prompt_hash {prov['prompt_hash']}\ncommits {prov['commits']}")  # noqa: T201
    print(f"{len(tasks)} tasks, budget {config['total_token_budget']} tokens")  # noqa: T201
    if args.dry_run:
        return 0
    started = time.monotonic()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    directory = results_dir()
    work = directory / "work" / run_id
    work.mkdir(parents=True)
    cap = config["per_task_token_cap"]
    rows: list[dict[str, Any]] = []
    for task in tasks:
        if budget_used(rows, cap) >= config["total_token_budget"]:
            rows.append(
                {
                    "instance_id": task["instance_id"],
                    "pipeline_status": "skipped_budget",
                    "tokens": None,
                }
            )
            continue
        try:
            meta = run_driver(task, run_id, model, work, config)
        except (OSError, ValueError, KeyError, IndexError) as exc:  # fetch or setup failure
            print(f"[{task['instance_id']}] setup failed: {exc}")  # noqa: T201
            meta = None
        rows.append(task_row(task["instance_id"], meta, cap))
    ran = [
        r["instance_id"]
        for r in rows
        if r["pipeline_status"] not in ("skipped_budget", "driver_error")
    ]
    gold = score(work, run_id, model, ran) if ran else {}
    apply_outcomes(rows, gold)
    result = build_result(run_id, prov, config, rows, time.monotonic() - started)
    (directory / f"{run_id}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"stored {directory / f'{run_id}.json'}: {result['totals']}")  # noqa: T201
    # The record is kept as evidence, but a night the harness could not grade is
    # not a successful evaluation.
    return 0 if result["totals"]["scored"] else EXIT_UNGRADED


def cmd_compare(_args: argparse.Namespace) -> int:
    results = load_results(results_dir())
    if len(results) < MIN_RUNS_TO_COMPARE:
        print("No previous run to compare against.")  # noqa: T201
        return 0
    cmp = compare_results(results[-2], results[-1], json.loads(CONFIG_PATH.read_text()))
    print(render_comparison(cmp))  # noqa: T201
    if cmp["regression"]:
        return EXIT_REGRESSION
    return 0 if cmp["enough_coverage"] else EXIT_UNGRADED


def cmd_report(_args: argparse.Namespace) -> int:
    print(render_report(load_results(results_dir()), json.loads(CONFIG_PATH.read_text())))  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--dry-run", action="store_true")
    run.set_defaults(fn=cmd_run)
    sub.add_parser("compare").set_defaults(fn=cmd_compare)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    sys.exit(main())
