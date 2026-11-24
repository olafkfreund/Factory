"""Offline-first entry point for the minimum viable campaign slice."""

import argparse
import json
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.e2e.config import HOSTS
from scripts.e2e.cost import Budget
from scripts.e2e.evidence import safe_fields
from scripts.e2e.github import GitHub
from scripts.e2e.guard import Guard
from scripts.e2e.journey import STAGES, Journey
from scripts.e2e.probes import matches
from scripts.e2e.registry import Registry
from scripts.e2e.report import summarize
from scripts.e2e.services import Services
from scripts.e2e.stages import LiveOperations, build

SKIPPED_PROBES = {
    "c": {"status": "skipped", "reason": "S2 was not reached"},
    "d": {
        "status": "skipped",
        "reason": "an accepted invalid contract could dispatch an unregistered AIF task",
    },
    "e": {"status": "skipped", "reason": "replay could dispatch an unregistered AIF task"},
    "f": {"status": "skipped", "reason": "no isolated empty-diff AIF task is registered"},
    "g": {
        "status": "skipped",
        "reason": "zero usage cannot be forced without changing live telemetry",
    },
    "i": {"status": "skipped", "reason": "no isolated zero-test TF spec is registered"},
    "j": {"status": "skipped", "reason": "stale verdict request could merge an unregistered head"},
    "l": {
        "status": "skipped",
        "reason": "duplicate event delivery could dispatch an unregistered task",
    },
    "m": {
        "status": "skipped",
        "reason": "second repository and card are not registered in this journey",
    },
}


def selected(journeys: list[str], slice_name: str | None) -> list[Journey]:
    if slice_name == "mvr":
        return [
            *(
                Journey("P1", surface, "Claude", repeat)
                for surface in ("cli", "mcp")
                for repeat in (1, 2)
            ),
            Journey("P5", "cli", "Claude", 1),
        ]
    result = []
    for item in journeys:
        parts = item.split(":")
        if (
            len(parts) != len(("project", "surface", "repeat"))
            or parts[0] not in {"P1", "P5"}
            or parts[1] not in {"cli", "mcp"}
        ):
            raise ValueError("journey must be P1|P5:cli|mcp:repeat")
        repeat = int(parts[2])
        if repeat < 1:
            raise ValueError("repeat must be positive")
        result.append(Journey(parts[0], parts[1], "Claude", repeat))
    return result


def planned_calls(journey: Journey) -> list[str]:
    descriptions = {
        "S1": "guarded GitHub repo create, starter push, three project onboardings",
        "S2": "guarded factory submit of fixture triple",
        "S3": "poll AIF task and usage with budget stop",
        "S4": "read GitHub PR, checks and merge",
        "S5": "guarded factory test at merge SHA, then local hidden suite",
        "X": "read CFactory card timeline",
    }
    return [
        f"{journey.project} {journey.surface} #{journey.repeat}: {stage} {descriptions[stage]}"
        for stage in STAGES
    ]


def run_live(  # noqa: PLR0915
    runs: list[Journey], campaign: str, evidence_root: Path
) -> list[dict[str, Any]]:
    registry = Registry(campaign, evidence_root)
    github = GitHub()
    services = Services(registry=registry)
    guard = Guard(registry, github.read_repo, services.read_resource)
    budget = Budget(guard)
    rows = []
    day = datetime.now(UTC).strftime("%Y%m%d")
    for journey in runs:
        name = f"e2e-{day}-{journey.project}-{time.time_ns()}"
        with tempfile.TemporaryDirectory(prefix="factory-e2e-work-") as temp:
            operations = LiveOperations(journey, guard, services, github, Path(temp) / name)
            stages = build(journey, guard, operations, name)

            def readback(  # noqa: PLR0911
                stage: str,
                surface: dict[str, Any],
                operations: LiveOperations = operations,
                name: str = name,
            ) -> dict[str, Any]:
                if stage == "S1":
                    live_repo = operations.github.read_repo(f"Freundcloud/{name}")
                    if live_repo is None:
                        raise RuntimeError("campaign repository unavailable")
                    repo = guard.check(
                        "github",
                        "repo",
                        live_repo["node_id"],
                    )
                    for service, identity in operations.projects.items():
                        guard.check(service, "project", identity)
                    guard.check("cfactory", "card", name)
                    return {
                        **surface,
                        "registered": bool(repo),
                        "branch_protection": bool(github.main_protection(f"Freundcloud/{name}")),
                        "projects": dict.fromkeys(operations.projects, 1),
                        "cards": 1,
                    }
                if stage == "S2":
                    session = services.read_resource(
                        "pfactory", "session", str(surface.get("session_id", ""))
                    )
                    task = (
                        services.read_resource("aifactory", "task", str(surface.get("task_id", "")))
                        if surface.get("task_id")
                        else None
                    )
                    review = (session or {}).get("review") or {}
                    findings = review.get("findings") or []
                    return {
                        **surface,
                        "ingested": bool(session),
                        "approved": bool(session and session.get("status") == "emitted"),
                        "emitted": bool(session and session.get("status") == "emitted"),
                        "from_plan": bool(task),
                        "review_findings": len(findings),
                        "needs_you": bool(
                            session
                            and (
                                session.get("status") == "rejected"
                                or surface.get("outcome") == "rejected"
                            )
                        ),
                    }
                if stage == "S3":
                    task_id = str(surface["task_id"])
                    task = services.read_resource("aifactory", "task", task_id) or {}
                    if task.get("id") != task_id:
                        raise RuntimeError("AIF task read-back mismatch")
                    usage = services.usage(task_id)
                    workers = usage.get("workers") or {}
                    models = {
                        row.get("phase"): row.get("model")
                        for row in workers.values()
                        if isinstance(row, dict) and row.get("model") and row.get("provider")
                    }
                    coder = models.get("coding") or models.get("coder")
                    reviewer = models.get("qa") or models.get("reviewer")
                    pr = github.pull_request(f"Freundcloud/{name}")
                    files = github.pull_files(f"Freundcloud/{name}", pr["number"])
                    changed = {row["filename"] for row in files if row.get("status") != "removed"}
                    code = {
                        path
                        for path in changed
                        if not path.startswith(("intent/", "spec/", "plan/"))
                        and not path.endswith(".lock")
                    }
                    report = services.qa_report(task_id)
                    return {
                        **surface,
                        "terminal": surface.get("status") == "completed",
                        "green": task.get("status") in {"done", "human_review"} and bool(report),
                        "code_diff": bool(code),
                        "plan_files_only": code <= {"wordfreq/cli.py", "tests/test_wordfreq.py"},
                        "review_recorded": bool(report and report.get("exists")),
                        "runtime_models": bool(coder and reviewer),
                        "coder_model": coder,
                        "reviewer_model": reviewer,
                        "cost_usd": usage.get("cost_usd", 0),
                    }
                if stage == "S4":
                    pr = github.pull_request(f"Freundcloud/{name}")
                    sha = pr.get("merge_commit_sha")
                    checks = github.check_runs(f"Freundcloud/{name}", str(sha))
                    successful = [
                        row
                        for row in checks.get("check_runs", [])
                        if row.get("name") == "tests"
                        and row.get("conclusion") == "success"
                        and row.get("head_sha") == sha
                    ]
                    return {
                        **surface,
                        "merged_by_service": bool(
                            pr.get("merged")
                            and str((pr.get("merged_by") or {}).get("login", "")).endswith("[bot]")
                        ),
                        "checks_green": bool(successful),
                        "triple_linked": all(
                            path in str(pr.get("body") or "")
                            for path in ("intent/", "spec/", "plan/")
                        ),
                        "merged_head": sha,
                        "checked_head": sha if successful else None,
                    }
                if stage == "S5":
                    verdict = services.verdict(str(surface["spec_id"]))
                    if verdict is None:
                        raise RuntimeError("TF verdict read-back unavailable")
                    rows = verdict["verdicts"].get("verdicts", [])
                    required = {
                        "coverage_delta_pct",
                        "stability",
                        "mutation",
                        "ci_parity",
                        "confidence",
                    }
                    complete = bool(rows) and all(
                        required <= set(row.get("signals_summary") or {}) for row in rows
                    )
                    return {
                        **surface,
                        "verdict_sha": verdict["verdict_sha"],
                        "signals": len(required) if complete else 0,
                    }
                if stage == "X":
                    key = str(surface.get("correlation_key") or "")
                    observed = services.timeline(key)
                    workitem = services.workitem(key)
                    events = (observed or {}).get("events", [])
                    times = [event.get("updated_at") for event in events]
                    slices = [
                        (workitem or {}).get(service, {}).get("usage") or {}
                        for service in ("pfactory", "aifactory", "tfactory")
                    ]
                    costs = [float(item.get("cost_usd") or 0) for item in slices]
                    token_row = next(
                        (
                            row
                            for row in services.tokens().get("by_work_item", [])
                            if row.get("correlation_key") == key
                        ),
                        None,
                    )
                    aif_cost = (
                        services.usage(str(surface.get("task_id")))["cost_usd"]
                        if (surface.get("task_id"))
                        else 0
                    )
                    anomalies = services.anomalies()
                    return {
                        **surface,
                        "events_ordered": bool(events) and times == sorted(times),
                        "registry_filtered": bool(
                            key and observed and observed.get("correlation_key") == key
                        ),
                        "cost_reconciled": bool(
                            token_row
                            and costs[1]
                            and abs(sum(costs) - float(token_row["cost_usd"]))
                            <= max(sum(costs) * 0.01, 0.01)
                            and abs(costs[1] - float(aif_cost)) <= max(costs[1] * 0.05, 0.01)
                        ),
                        "no_card_anomaly": not any(
                            item.get("correlation_key") == key for item in anomalies
                        ),
                    }
                return surface

            try:
                result = journey.run(
                    stages,
                    budget,
                    name,
                    readback=readback,
                    usage=services.usage,
                    remote=(services.stop, services.stop_status),
                )
                result["status"] = "passed"
            except Exception as exc:  # noqa: BLE001
                result = {
                    "project": journey.project,
                    "surface": journey.surface,
                    "model": journey.model,
                    "repeat": journey.repeat,
                    "status": "failed",
                    "failure": type(exc).__name__,
                }
            result["probes"] = {key: dict(value) for key, value in SKIPPED_PROBES.items()}
            for key, outcome in operations.probes.items():
                result["probes"][key] = {
                    "status": "passed" if matches(key, **outcome) else "failed",
                    "reason": outcome["reason"],
                }
            rows.append(result)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--journey", action="append", default=[])
    choice.add_argument("--slice", choices=["mvr"])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument("--campaign", default=datetime.now(UTC).strftime("e2e-campaign-%Y-%m-%d"))
    parser.add_argument("--evidence-root", type=Path, default=Path("evidence"))
    args = parser.parse_args(argv)
    try:
        runs = selected(args.journey, args.slice)
    except ValueError as exc:
        parser.error(str(exc))
    if args.live:
        live_rows = run_live(runs, args.campaign, args.evidence_root)
        path = args.evidence_root / args.campaign / "run.meta.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        evidence = [
            safe_fields(
                row,
                {
                    "project",
                    "surface",
                    "model",
                    "repeat",
                    "status",
                    "failure",
                    "stage_results",
                    "probes",
                    "expected_stop",
                },
            )
            for row in live_rows
        ]
        path.write_text(json.dumps({"journeys": evidence, "hosts": HOSTS}, sort_keys=True) + "\n")
        print(json.dumps(summarize(live_rows), indent=2))  # noqa: T201
        return 0 if all(row["status"] == "passed" for row in live_rows) else 1
    rows: list[dict[str, Any]] = []
    for run in runs:
        for call in planned_calls(run):
            print(call)  # noqa: T201
        rows.append(
            safe_fields(
                {
                    "project": run.project,
                    "surface": run.surface,
                    "model": run.model,
                    "repeat": run.repeat,
                    "status": "planned",
                },
                {"project", "surface", "model", "repeat", "status"},
            )
        )
    path = args.evidence_root / args.campaign / "run.meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"journeys": rows, "hosts": HOSTS}, sort_keys=True) + "\n")
    print(json.dumps(summarize(rows), indent=2))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
