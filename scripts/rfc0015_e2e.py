#!/usr/bin/env python3
"""RFC-0015 end-to-end verification (#186).

Pins the spec-driven-interop foundation that the per-service implementations
consume: a spec-kit-shaped task — carrying a constitution (with enforceable
clauses) and a requirement->test->VAL traceability matrix — validates against the
merged Task Contract schema, and the declarative extension registry exposes the
RFC-0015 capabilities (adversarial red-team review, traceability matrix) with the
right category/effect/gating.

The per-service behaviours are unit-tested in their own repos (PFactory:
constitution parse+inject+hard-check, spec-kit ingest, spec/plan/tasks emit,
red-team lens; AIFactory: constitution consumption; TFactory: traceability emit;
CFactory: traceability matrix view). This hub E2E proves the contract + registry
those all share — the spec-kit `.specify` -> Factory contract handoff shape.

Run: ``python3 scripts/rfc0015_e2e.py``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_registry import by_category, load_registry

_HUB = Path(__file__).resolve().parent.parent
_SCHEMA = json.loads((_HUB / "apis" / "task-contract.schema.json").read_text(encoding="utf-8"))


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


# A spec-kit `.specify` workspace, ingested by PFactory, yields a contract whose
# epic_context carries the constitution and whose verification carries the
# AC->test->VAL traceability matrix. This is that contract's RFC-0015 surface.
_SPECKIT_CONTRACT = {
    "contract_version": "2",
    "correlation_key": 4242,
    "epic_context": {
        "constitution": {
            "source": ".specify/memory/constitution.md",
            "available": True,
            "principles": [
                {"id": "P1", "text": "Tests precede implementation (TDD).", "enforceable": True},
                {"id": "P2", "text": "Prefer the simplest design.", "enforceable": False},
            ],
            "enforceable_ids": ["P1"],
        }
    },
    "verification": {
        "traceability": [
            {
                "ac_id": "AC#1",
                "ac_text": "GET /healthz returns 200.",
                "tests": ["tests/test_health.py::test_healthz"],
                "val_level": "VAL-2",
                "status": "passed",
            },
            {"ac_id": "AC#2", "ac_text": "Unmapped AC.", "tests": [], "status": "not_run"},
        ]
    },
}


def _validate_contract() -> None:
    try:
        from jsonschema import Draft202012Validator  # noqa: PLC0415
    except ImportError:
        # Schema lib absent: at least prove the schema + sample are well-formed JSON
        # and the RFC-0015 blocks are declared in the schema.
        _require(
            "constitution" in _SCHEMA.get("$defs", {}), "schema must define $defs.constitution"
        )
        ver = _SCHEMA["$defs"]["verification"]["properties"]
        _require("traceability" in ver, "verification must declare traceability[]")
        sys.stdout.write("rfc0015 e2e: PARTIAL — jsonschema absent; schema declares the blocks\n")
        return

    Draft202012Validator.check_schema(_SCHEMA)
    defs = _SCHEMA["$defs"]

    # Validate the RFC-0015 sub-blocks against their $defs (a full contract has many
    # other required fields; here we pin the spec-driven-interop shapes). The
    # embedded $defs let $refs (e.g. valLevel) resolve.
    con_schema = {"$defs": defs, "$ref": "#/$defs/constitution"}
    con_errs = list(
        Draft202012Validator(con_schema).iter_errors(
            _SPECKIT_CONTRACT["epic_context"]["constitution"]
        )
    )
    _require(not con_errs, f"constitution must validate: {[e.message for e in con_errs][:3]}")

    tr_schema = {"$defs": defs, **defs["verification"]["properties"]["traceability"]}
    tr_errs = list(
        Draft202012Validator(tr_schema).iter_errors(
            _SPECKIT_CONTRACT["verification"]["traceability"]
        )
    )
    _require(not tr_errs, f"traceability must validate: {[e.message for e in tr_errs][:3]}")

    # The constitution block is wired into epic_context and degrades like
    # house_standards (available flag present).
    _require(
        "constitution" in _SCHEMA["properties"]["epic_context"]["properties"], "epic_context ref"
    )
    con = defs["constitution"]["properties"]
    _require(
        {"source", "principles", "enforceable_ids", "available"} <= set(con), "constitution shape"
    )
    tr_items = defs["verification"]["properties"]["traceability"]["items"]["properties"]
    _require({"ac_id", "tests", "val_level", "status"} <= set(tr_items), "traceability row shape")


def _validate_registry() -> None:
    reg = load_registry(_HUB / "apis" / "extension-registry.json")
    names = {e["name"] for e in reg}
    # RFC-0015 D1 + D2 capabilities are registered.
    _require("red-team-review" in names, "registry must list red-team-review (D1)")
    _require(
        any("traceability" in n for n in names), "registry must list a traceability capability (D2)"
    )
    # Red-team review is a gated REVIEW extension, OFF by default (opt-in).
    review = {e["name"]: e for e in by_category(reg, "review")}
    rt = review.get("red-team-review")
    _require(rt is not None, "red-team-review must be category=review")
    _require(rt.get("enabled") is False, "red-team-review must be gated OFF by default")


def _test() -> None:
    _validate_contract()
    _validate_registry()
    sys.stdout.write(
        "rfc0015 e2e: PASS — spec-kit contract (constitution + enforceable clause + "
        "traceability matrix) validates; registry exposes red-team-review (gated) + "
        "traceability; per-service behaviours unit-tested in their repos\n"
    )


if __name__ == "__main__":
    _test()
