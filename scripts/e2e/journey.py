"""Stage runner for one project, surface, model and repeat."""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scripts.e2e.config import HOSTS, LIMITS
from scripts.e2e.cost import Budget
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

    def run(
        self,
        stages: dict[str, Callable[[], dict]],
        budget: Budget,
        lane: str,
        *,
        now: Callable[[], float] = time.monotonic,
        remote: tuple[Callable[[str], object], Callable[[str], dict]] | None = None,
    ) -> dict:
        if (
            self.project not in LIMITS
            or self.surface not in {"cli", "mcp", "ui"}
            or self.repeat < 1
        ):
            raise ValueError("invalid journey")
        budget.reserve(lane, LIMITS[self.project].usd)
        deadline = now() + LIMITS[self.project].minutes * 60
        results = {}
        for stage in STAGES:
            if now() >= deadline:
                if remote is not None and results.get("S2", {}).get("task_id"):
                    budget.cap(lane, results["S2"]["task_id"], *remote)
                raise TimeoutError(f"{stage} deadline reached")
            result = stages[stage]()
            validate(stage, result, self.project)
            results[stage] = result
            if self.project == "P5" and result.get("needs_you"):
                results["X"] = stages["X"]()
                validate("X", results["X"], self.project)
                return {
                    "project": self.project,
                    "surface": self.surface,
                    "model": self.model,
                    "repeat": self.repeat,
                    "stage_results": results,
                    "expected_stop": True,
                }
            if now() >= deadline and stage != "X":
                if remote is None or not results.get("S2", {}).get("task_id"):
                    budget.blocked.add(lane)
                    raise TimeoutError("deadline reached without a confirmable remote stop")
                budget.cap(lane, results["S2"]["task_id"], *remote)
                raise TimeoutError(f"{stage} deadline reached; remote stop confirmed")
            spent = sum(row.get("cost_usd", 0) for row in results.values())
            if spent >= LIMITS[self.project].usd and stage != "X":
                if remote is None or not results.get("S2", {}).get("task_id"):
                    budget.blocked.add(lane)
                    raise ValueError("cap reached without a confirmable remote stop")
                budget.cap(lane, results["S2"]["task_id"], *remote)
                raise ValueError("journey cap reached; remote stop confirmed")
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


def write_meta(path: Path, result: dict) -> None:
    """Record the pinned endpoints alongside one journey's evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**result, "hosts": HOSTS}, sort_keys=True) + "\n", encoding="utf-8")


def validate(stage: str, result: dict, project: str) -> None:
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
        and result.get("branch_protection")
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
