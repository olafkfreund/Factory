"""Stage runner for one project, surface, model and repeat."""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.e2e.config import HOSTS, LIMITS
from scripts.e2e.cost import Budget
from scripts.e2e.evidence import safe_fields
from scripts.e2e.probes import PROBES, verify

STAGES = ("S1", "S2", "S3", "S4", "S5", "X")
SIGNAL_COUNT = 5


@dataclass(frozen=True)
class Journey:
    project: str
    surface: str
    model: str
    repeat: int
    ablation: bool = False

    def run(  # noqa: PLR0913, PLR0915
        self,
        stages: dict[str, Callable[[float, Callable[..., None]], dict[str, Any]]],
        budget: Budget,
        lane: str,
        *,
        readback: Callable[[str, dict[str, Any]], dict[str, Any]],
        usage: Callable[[str], dict[str, Any]] | None = None,
        now: Callable[[], float] = time.monotonic,
        remote: tuple[Callable[[str], object], Callable[[str], dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        if (
            self.project not in LIMITS
            or self.surface not in {"cli", "mcp", "ui"}
            or self.repeat < 1
        ):
            raise ValueError("invalid journey")
        allocation = min(LIMITS[self.project].usd, budget.cap_usd - budget.spent)
        budget.reserve(lane, allocation)
        deadline = now() + LIMITS[self.project].minutes * 60
        results: dict[str, dict[str, Any]] = {}
        current_task: tuple[str, str, str] | None = None
        spent = 0.0

        def poll(
            task_id: tuple[str, str, str] | str | None = None, cost_usd: float | None = None
        ) -> None:
            nonlocal current_task, spent
            if task_id:
                current_task = (
                    task_id if isinstance(task_id, tuple) else ("aifactory", "task", task_id)
                )
            if usage is not None and current_task:
                spent = max(spent, float(usage(current_task[2]).get("cost_usd") or 0))
            if cost_usd is not None:
                spent = max(spent, cost_usd)
            timed_out = now() >= deadline
            capped = spent >= allocation
            if timed_out or capped:
                if remote is None or current_task is None:
                    budget.blocked.add(lane)
                    raise TimeoutError("deadline or cap reached without a confirmable remote stop")
                resource = current_task
                current_task = None
                budget.cap(lane, resource, *remote)
                if timed_out:
                    raise TimeoutError("deadline reached; remote stop confirmed")
                raise ValueError("journey cap reached; remote stop confirmed")

        completed = False
        current_stage: str | None = None
        try:
            for stage in STAGES:
                current_stage = stage
                poll()
                result = stages[stage](deadline, poll)
                if result.get("dispatched"):
                    current_task = tuple(result["dispatched"])
                elif result.get("task_id"):
                    current_task = ("aifactory", "task", result["task_id"])
                spent = max(
                    spent,
                    sum(float(row.get("cost_usd") or 0) for row in (*results.values(), result)),
                )
                poll()
                observed = readback(stage, result)
                validate(stage, result, self.project, observed)
                results[stage] = observed
                if self.project == "P5" and observed.get("needs_you"):
                    result = stages["X"](deadline, poll)
                    poll()
                    observed = readback("X", result)
                    validate("X", result, self.project, observed)
                    results["X"] = observed
                    completed = True
                    return {
                        "project": self.project,
                        "surface": self.surface,
                        "model": self.model,
                        "repeat": self.repeat,
                        "stage_results": results,
                        "expected_stop": True,
                    }
            completed = True
        except Exception as exc:
            # run.py reports this as failure_stage; it was always None.
            if not hasattr(exc, "e2e_stage"):
                exc.e2e_stage = current_stage  # type: ignore[attr-defined]
            # A failed journey keeps what it measured: run.meta.json had no cost or stages.
            exc.e2e_stage_results = dict(results)  # type: ignore[attr-defined]
            exc.e2e_cost_usd = spent  # type: ignore[attr-defined]
            raise
        finally:
            if not completed and current_task is not None:
                if remote is None:
                    budget.blocked.add(lane)
                else:
                    try:
                        budget.cap(lane, current_task, *remote)
                    except Exception:  # noqa: BLE001
                        budget.blocked.add(lane)
            budget.release(lane, spent)
        return {
            "project": self.project,
            "surface": self.surface,
            "model": self.model,
            "repeat": self.repeat,
            "ablation": self.ablation,
            "stage_results": results,
        }


def matrix() -> list[Journey]:
    runs = [
        Journey("P1", surface, "Claude", repeat)
        for surface in ("cli", "mcp", "ui")
        for repeat in (1, 2)
    ]
    runs += [
        Journey("P2", "cli", model, repeat)
        for model in ("Claude", "Codex", "Gemini")
        for repeat in (1, 2)
    ]
    runs += [Journey("P3", "mcp", model, 1) for model in ("Claude", "Codex")]
    runs += [Journey("P4", "ui", model, 1) for model in ("Claude", "Gemini")]
    runs += [Journey("P5", surface, "Claude", 1) for surface in ("cli", "ui")]
    runs.append(Journey("P1", "cli", "Claude", 1, ablation=True))
    return runs


def write_meta(path: Path, result: dict[str, Any]) -> None:
    """Record the pinned endpoints alongside one journey's evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                **safe_fields(
                    result,
                    {
                        "project",
                        "surface",
                        "model",
                        "repeat",
                        "ablation",
                        "stage_results",
                        "expected_stop",
                        "billing_mode",
                        "cost_usd",
                        "total_tokens",
                    },
                ),
                "hosts": HOSTS,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def validate(
    stage: str, result: dict[str, Any], project: str, observed: dict[str, Any] | None = None
) -> None:
    if observed is None:
        raise AssertionError("independent read-back required")
    result = observed
    for name, outcome in result.get("probes", {}).items():
        if name not in PROBES or PROBES[name].stage != stage:
            raise AssertionError(f"probe {name} belongs to another stage")
        verify(name, **outcome)
    if project == "P5" and result.get("needs_you"):
        if stage not in {"S2", "S3"} or result.get("review_findings", 0) < 1:
            raise AssertionError("P5 stopped without a review finding")
        return
    if stage == "S1" and not (
        result.get("registered")
        and (result.get("branch_protection") or result.get("branch_protection_note"))
        and result.get("projects") == {"aifactory": 1, "pfactory": 1, "tfactory": 1}
        and result.get("cards") == 1
    ):
        raise AssertionError("S1 onboarding incomplete")
    if stage == "S2" and not (
        result.get("ingested")
        and result.get("approved")
        and result.get("emitted")
        and result.get("from_plan")
        and (project not in {"P4", "P5"} or result.get("review_findings", 0) >= 1)
    ):
        raise AssertionError("S2 plan chain incomplete")
    if stage == "S3" and not (
        result.get("terminal")
        and result.get("green")
        and result.get("code_diff")
        and result.get("plan_files_only")
        and result.get("review_recorded")
        and result.get("reviewer_model") != result.get("coder_model")
        and result.get("runtime_models")
    ):
        raise AssertionError("S3 build evidence incomplete")
    if stage == "S4" and not (
        result.get("merged_by_service")
        and result.get("checks_green")
        and result.get("triple_linked")
        and result.get("merged_head") == result.get("checked_head")
    ):
        raise AssertionError("S4 merge evidence incomplete")
    if stage == "S5" and not (
        result.get("verdict_sha") == result.get("merge_sha") == result.get("hidden_suite_sha")
        and result.get("signals") == SIGNAL_COUNT
        and result.get("hidden_green")
    ):
        raise AssertionError("S5 verdict evidence incomplete")
    if stage == "X" and not (
        result.get("events_ordered")
        and result.get("registry_filtered")
        and result.get("cost_reconciled")
        and result.get("no_card_anomaly")
    ):
        raise AssertionError("X observability evidence incomplete")
