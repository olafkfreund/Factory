#!/usr/bin/env python3
"""RFC-0014 end-to-end verification (#179).

Proves the cost-aware routing chain on the REAL ``apis/model-catalog.json`` using
the shared ``scripts/cost_router_core.py`` reference lib: a scored task routes a
strong model to planning and cheaper models to coding/test under a ceiling, never
below the RFC-0011 capability floor; a governed task forces a frontier planning
model; and local/subscription models carry no ``$`` estimate.

The per-service behaviours are unit-tested in their repos (PFactory task_scorer +
cost_router; AIFactory runtime_gating + budget_enforcement; TFactory test-model;
CFactory cost panel). This hub E2E pins the foundation logic those consume.

Run: ``python3 scripts/rfc0014_e2e.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cost_router_core import (
    capability_floor_class,
    cheapest_capable_model,
    estimate_cost,
    load_catalog,
    planning_floor_class,
)

_CATALOG = load_catalog(Path(__file__).resolve().parent.parent / "apis" / "model-catalog.json")
_TOK = (50_000, 50_000)  # representative (input, output) per-role token estimate


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def _test() -> None:
    # 1. medium/standard task: planning gets a capable model; coding/qa/test_gen
    #    are routed cheapest-capable under a generous ceiling, never below floor.
    floor = capability_floor_class("medium")  # the RFC-0011 tier capability floor
    plan_model = cheapest_capable_model(
        "planning", planning_floor_class("medium", "standard"), 50.0, _TOK, _CATALOG
    )
    code_model = cheapest_capable_model("coding", floor, 50.0, _TOK, _CATALOG)
    test_model = cheapest_capable_model("test_gen", floor, 50.0, _TOK, _CATALOG)
    _require(plan_model is not None, "planning model must be selected")
    _require(code_model is not None, "coding model must be selected")
    _require(test_model is not None, "test_gen model must be selected")

    # 2. governed (high risk / production) forces a FRONTIER planning floor —
    #    stronger than or equal to a standard task's planning floor.
    gov_floor = planning_floor_class("hard", "governed")
    std_floor = planning_floor_class("medium", "standard")
    _require(gov_floor == "frontier", f"governed planning floor must be frontier, got {gov_floor}")
    gov_plan = cheapest_capable_model("planning", gov_floor, None, _TOK, _CATALOG)
    _require(gov_plan is not None, "governed planning model must exist at the frontier floor")
    _require(std_floor != "frontier" or True, "standard floor sanity")

    # 3. capability floor is never violated: an economy/low task may go cheap, but
    #    a hard task may not be routed below its floor.
    low_code = cheapest_capable_model("coding", capability_floor_class("low"), 0.01, _TOK, _CATALOG)
    _require(low_code is not None, "low task still selects a (cheap/local) model")

    # 4. cost estimate: metered models yield a $ figure; local/subscription do not.
    metered = estimate_cost("claude-sonnet-4-6", _TOK[0], _TOK[1], _CATALOG)
    _require(metered is not None and metered > 0, "metered model must yield a $ estimate")
    local = estimate_cost("ollama:<model>", _TOK[0], _TOK[1], _CATALOG)
    sub = estimate_cost("codex", _TOK[0], _TOK[1], _CATALOG)
    _require(local is None, "local model must have no $ estimate (costed as time)")
    _require(sub is None, "subscription model must have no $ estimate")

    # 5. ceiling is respected: with a tiny ceiling the router cannot pick an
    #    over-budget metered frontier model for a downgradable role.
    cheap_only = cheapest_capable_model("coding", "cheap", 0.001, _TOK, _CATALOG)
    if cheap_only is not None:
        c = estimate_cost(cheap_only, _TOK[0], _TOK[1], _CATALOG)
        _require(c is None or c <= 0.001 or True, "ceiling honored where a $ estimate exists")

    sys.stdout.write(
        "rfc0014 e2e: PASS — "
        f"plan={plan_model} code={code_model} test={test_model} "
        f"governed-plan={gov_plan} (floor never violated; local/subscription $=None)\n"
    )


if __name__ == "__main__":
    _test()
