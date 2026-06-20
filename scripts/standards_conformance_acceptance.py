#!/usr/bin/env python3
"""RFC-0012 standards-conformance acceptance harness — the "trust" bar.

This is the gate we must clear before we permit the fleet to ground itself in
external knowledge sources (team wikis, Backstage TechDocs, ...). It proves the
``standards_conformance`` gate works in **both** directions on realistic
contracts:

  - POSITIVE: a contract with a retrieved, hashed house standard, a declared
    config that reflects it, no unwaived deviations, and a verification block
    showing the declared lanes ran  ->  the gate returns ``pass``.
  - NEGATIVE: the *same* standard retrieved, but the build ignores it (the
    config does not reference the tool, or the lane never ran)  ->  the gate
    returns ``fail`` with the precise reason.

A retrieval that cannot be shown to have been applied is not grounding; it is
decoration. Run: ``python3 scripts/standards_conformance_acceptance.py``
(exit 0 only when positive passes AND every negative fails).
"""

from __future__ import annotations

import sys

try:
    from standards_conformance_gate import (
        FAIL,
        PASS,
        evaluate_standards_conformance,
    )
except ImportError:  # allow running from the repo root
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    from standards_conformance_gate import (  # type: ignore
        FAIL,
        PASS,
        evaluate_standards_conformance,
    )

_STANDARD_HASH = "sha256:houserules-v1"


def _house_standards() -> dict:
    """A realistic RFC-0012 manifest: ruff+mypy convention, backstage ref."""
    return {
        "available": True,
        "sources": [
            {
                "source": "baseline",
                "kind": "conventions",
                "conventions": {
                    "code_quality_tools": ["ruff", "mypy"],
                    "version_managers": ["uv"],
                },
                "content_hash": _STANDARD_HASH,
            },
            {
                "source": "backstage",
                "kind": "component",
                "entity_ref": "component:default/aifactory",
                "techdocs_refs": ["dir:./docs/best-practices.md"],
                "lifecycle": "production",
                "content_hash": "sha256:backstage-component",
            },
        ],
    }


def _positive_contract() -> dict:
    """Standards retrieved AND applied AND executed."""
    return {
        "epic_context": {"house_standards": _house_standards()},
        "required_commands": ["uv", "ruff", "mypy", "pytest"],
        "tfactory": {"lanes": ["unit"], "frameworks": {"unit": "pytest"}},
        "verification": {
            "target_level": "VAL-1",
            "levels": [
                {"level": "VAL-0", "status": "passed", "ran": ["ruff", "mypy"]},
                {"level": "VAL-1", "status": "passed", "ran": ["pytest"]},
            ],
        },
    }


def _negative_ignored_config() -> dict:
    """Same standard retrieved, but the config never references ruff/mypy."""
    c = _positive_contract()
    c["required_commands"] = ["uv", "pytest"]
    c["tfactory"] = {"lanes": ["unit"], "frameworks": {"unit": "pytest"}}
    return c


def _negative_lane_not_run() -> dict:
    """Declared the lane, but the verification block shows it never ran."""
    c = _positive_contract()
    c["verification"] = {
        "target_level": "VAL-1",
        "levels": [
            {"level": "VAL-0", "status": "not_run", "reason": "lint lane skipped"},
            {"level": "VAL-1", "status": "passed", "ran": ["pytest"]},
        ],
    }
    return c


def _negative_unwaived_deviation() -> dict:
    """A declared deviation whose waiver hash matches no retrieved standard."""
    c = _positive_contract()
    hs = c["epic_context"]["house_standards"]
    hs["deviations"] = [{"rule": "skip-mypy", "waiver": {"content_hash": "sha256:does-not-match"}}]
    return c


_CASES = [
    ("positive: retrieved + applied + executed", _positive_contract(), PASS),
    ("negative: standard ignored in config", _negative_ignored_config(), FAIL),
    ("negative: declared lane never ran", _negative_lane_not_run(), FAIL),
    ("negative: unwaived deviation", _negative_unwaived_deviation(), FAIL),
]


def run() -> bool:
    ok = True
    for name, contract, expected in _CASES:
        verdict = evaluate_standards_conformance(contract)
        got = verdict["status"]
        passed = got == expected
        ok = ok and passed
        mark = "OK " if passed else "XX "
        print(f"  {mark}{name}: expected={expected} got={got}")
        if not passed or got == FAIL:
            for reason in verdict["reasons"]:
                print(f"        - {reason}")
    return ok


if __name__ == "__main__":
    print("standards_conformance acceptance harness (RFC-0012):")
    success = run()
    print(
        "\nACCEPTANCE: PASS — positive passes and every negative fails."
        if success
        else "\nACCEPTANCE: FAIL — the gate did not behave as required."
    )
    sys.exit(0 if success else 1)
