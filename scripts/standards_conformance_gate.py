#!/usr/bin/env python3
"""RFC-0012 standards-conformance gate (reference implementation).

The companion to ``scripts/verification_gate.py``. Where that gate enforces
"never claim a higher *assurance* than was proven", this one enforces "never
claim the team's *house standards* were applied unless they were". It takes a
Task Contract (RFC-0002) carrying ``epic_context.house_standards`` (RFC-0012)
plus the producer's RFC-0006 ``verification`` block, and returns a normalized,
**fail-closed** verdict.

It asks four questions, in order (RFC-0012 section 6):

  1. retrieved?  -- does ``house_standards`` carry hashed sources?
                    available == false (or block absent) => ``not_applicable``
                    (nothing to enforce -- an honest pass, not a silent one).
                    present-but-malformed / available-with-no-hashed-sources
                    => FAIL (``not_retrieved``).
  2. declared?   -- do the retrieved convention tools (ruff, mypy, ...) actually
                    appear in the build's declared lanes (``required_commands`` /
                    ``tfactory``)? Retrieved but not reflected => FAIL
                    (``declared_but_not_applied``). The key negative case.
  3. waived?     -- every declared deviation must carry a waiver whose
                    ``content_hash`` matches a retrieved source. An unwaived
                    deviation => FAIL (``unwaived_deviation``).
  4. executed?   -- the declared lanes must actually have RUN per the
                    verification block (a ``passed`` level, not
                    ``not_run``/``skipped``). Declared-but-not-executed => FAIL
                    (``declared_but_not_executed``).

Fail-closed: missing inputs, malformed blocks, and unknowns resolve to ``fail``,
never ``pass``. Pure + dependency-free so PFactory / AIFactory / TFactory /
CFactory can each vendor it. Run directly for the self-tests:
``python3 scripts/standards_conformance_gate.py``.
"""

from __future__ import annotations

PASS = "pass"
FAIL = "fail"
NOT_APPLICABLE = "not_applicable"

_PASSED = "passed"
# Convention buckets we know how to check against declared lanes.
_CHECKABLE_TOOL_KEYS = ("code_quality_tools", "test_tools", "tools")


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, (str, int, float)):
        return [value]
    return []


def _declared_tokens(contract: dict) -> set[str]:
    """Lower-cased tokens describing what the build actually declared it runs.

    Drawn from the top-level + execution ``required_commands`` and the
    ``tfactory`` lanes/frameworks. A convention tool is "declared" when its name
    appears as a substring of any of these tokens.
    """
    tokens: list[str] = []
    tokens += _as_list(contract.get("required_commands"))
    execution = contract.get("execution")
    if isinstance(execution, dict):
        tokens += _as_list(execution.get("required_commands"))
    tf = contract.get("tfactory")
    if isinstance(tf, dict):
        tokens += _as_list(tf.get("lanes"))
        frameworks = tf.get("frameworks")
        if isinstance(frameworks, dict):
            tokens += [str(v) for v in frameworks.values()]
        else:
            tokens += _as_list(frameworks)
    return {str(t).strip().lower() for t in tokens if str(t).strip()}


def _required_tools(sources: list[dict]) -> list[str]:
    """The concretely-checkable convention tools across all retrieved sources."""
    tools: list[str] = []
    for src in sources:
        conventions = src.get("conventions")
        if not isinstance(conventions, dict):
            continue
        for key in _CHECKABLE_TOOL_KEYS:
            for tool in _as_list(conventions.get(key)):
                name = str(tool).strip().lower()
                if name:
                    tools.append(name)
    # de-dupe, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in tools:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _passed_ran(verification: dict) -> tuple[bool, set[str]]:
    """(any level passed?, the union of ``ran`` tokens across passed levels)."""
    if not isinstance(verification, dict):
        return False, set()
    any_passed = False
    ran: list[str] = []
    for lvl in _as_list(verification.get("levels")):
        if isinstance(lvl, dict) and lvl.get("status") == _PASSED:
            any_passed = True
            ran += [str(r).strip().lower() for r in _as_list(lvl.get("ran"))]
    return any_passed, {r for r in ran if r}


def _tool_present(tool: str, tokens: set[str]) -> bool:
    return any(tool in tok for tok in tokens)


def evaluate_standards_conformance(contract: dict | None) -> dict:
    """Return a fail-closed ``{status, reasons, checks}`` conformance verdict."""
    try:
        return _evaluate(contract)
    except Exception as exc:  # fail-closed: a gate that crashes must not pass
        return {
            "status": FAIL,
            "reasons": [f"gate_error: {type(exc).__name__}: {exc}"],
            "checks": {
                "retrieved": FAIL,
                "declared": FAIL,
                "waived": FAIL,
                "executed": FAIL,
            },
        }


def _evaluate(contract: dict | None) -> dict:
    checks = {
        "retrieved": NOT_APPLICABLE,
        "declared": NOT_APPLICABLE,
        "waived": NOT_APPLICABLE,
        "executed": NOT_APPLICABLE,
    }
    reasons: list[str] = []

    if not isinstance(contract, dict):
        return {
            "status": FAIL,
            "reasons": ["malformed_contract: not an object"],
            "checks": dict.fromkeys(checks, FAIL),
        }

    epic_context = contract.get("epic_context")
    house = epic_context.get("house_standards") if isinstance(epic_context, dict) else None

    # 1. retrieved? -----------------------------------------------------------
    if house is None:
        # No standards attached at all -> nothing to enforce (honest pass).
        return {
            "status": NOT_APPLICABLE,
            "reasons": ["no house_standards on the contract; nothing to enforce"],
            "checks": checks,
        }
    if not isinstance(house, dict):
        return {
            "status": FAIL,
            "reasons": ["not_retrieved: house_standards is malformed (not an object)"],
            "checks": {**checks, "retrieved": FAIL},
        }
    if not house.get("available", False):
        # Retrieval was attempted but unavailable -> not_applicable, never a false pass.
        checks["retrieved"] = NOT_APPLICABLE
        return {
            "status": NOT_APPLICABLE,
            "reasons": [
                "house_standards unavailable "
                f"({house.get('error') or 'no reason given'}); scored not_applicable"
            ],
            "checks": checks,
        }

    sources = [
        s for s in _as_list(house.get("sources")) if isinstance(s, dict) and s.get("content_hash")
    ]
    if not sources:
        return {
            "status": FAIL,
            "reasons": ["not_retrieved: available=true but no hashed sources"],
            "checks": {**checks, "retrieved": FAIL},
        }
    checks["retrieved"] = PASS

    # 2. declared? ------------------------------------------------------------
    required = _required_tools(sources)
    declared = _declared_tokens(contract)
    if not required:
        # Only advisory sources (e.g. backstage refs) -- nothing concretely
        # checkable, but retrieval succeeded. Declared/executed are N/A.
        checks["declared"] = NOT_APPLICABLE
    else:
        missing = [t for t in required if not _tool_present(t, declared)]
        if missing:
            checks["declared"] = FAIL
            reasons.append(
                "declared_but_not_applied: retrieved standard tool(s) "
                f"{missing} absent from declared lanes {sorted(declared) or '[]'}"
            )
        else:
            checks["declared"] = PASS

    # 3. waived? --------------------------------------------------------------
    source_hashes = {s["content_hash"] for s in sources}
    deviations = _as_list(house.get("deviations"))
    if not deviations:
        checks["waived"] = NOT_APPLICABLE
    else:
        unwaived = []
        for dev in deviations:
            if not isinstance(dev, dict):
                unwaived.append(repr(dev))
                continue
            waiver = dev.get("waiver")
            wh = waiver.get("content_hash") if isinstance(waiver, dict) else None
            if not wh or wh not in source_hashes:
                unwaived.append(dev.get("rule") or dev.get("standard") or repr(dev))
        if unwaived:
            checks["waived"] = FAIL
            reasons.append(
                "unwaived_deviation: deviation(s) without a waiver hash matching a "
                f"retrieved standard: {unwaived}"
            )
        else:
            checks["waived"] = PASS

    # 4. executed? ------------------------------------------------------------
    if checks["declared"] in (PASS,):
        any_passed, ran = _passed_ran(contract.get("verification"))
        if not any_passed:
            checks["executed"] = FAIL
            reasons.append(
                "declared_but_not_executed: no passed verification level; the "
                "declared standard lanes were not shown to run"
            )
        elif ran and not any(_tool_present(t, ran) for t in required):
            # A passed level exists but none of the required tools is in its `ran`.
            checks["executed"] = FAIL
            reasons.append(
                "declared_but_not_executed: passed levels ran "
                f"{sorted(ran)}, none covering required tool(s) {required}"
            )
        else:
            checks["executed"] = PASS
    else:
        checks["executed"] = NOT_APPLICABLE

    status = PASS
    if any(v == FAIL for v in checks.values()):
        status = FAIL
    elif all(v == NOT_APPLICABLE for v in checks.values()):
        status = NOT_APPLICABLE

    if status == PASS and not reasons:
        reasons.append("house standards retrieved, declared, and executed")
    return {"status": status, "reasons": reasons, "checks": checks}


# ── self-tests ──────────────────────────────────────────────────────────────
def _baseline(tools, hash_="sha256:abc"):
    return {
        "available": True,
        "sources": [
            {
                "source": "baseline",
                "kind": "conventions",
                "conventions": {"code_quality_tools": tools},
                "content_hash": hash_,
            }
        ],
    }


def _test() -> None:
    # 1. No house_standards at all -> not_applicable (nothing to enforce).
    r = evaluate_standards_conformance({})
    assert r["status"] == NOT_APPLICABLE, r

    # 2. available=false -> not_applicable, never a false pass.
    r = evaluate_standards_conformance(
        {"epic_context": {"house_standards": {"available": False, "error": "no catalog"}}}
    )
    assert r["status"] == NOT_APPLICABLE and r["checks"]["retrieved"] == NOT_APPLICABLE, r

    # 3. available=true but no hashed sources -> FAIL not_retrieved.
    r = evaluate_standards_conformance(
        {"epic_context": {"house_standards": {"available": True, "sources": []}}}
    )
    assert r["status"] == FAIL and r["checks"]["retrieved"] == FAIL, r

    # 4. POSITIVE: retrieved + declared + executed -> pass.
    contract = {
        "epic_context": {"house_standards": _baseline(["ruff", "mypy"])},
        "required_commands": ["uv", "ruff", "mypy", "pytest"],
        "verification": {
            "levels": [
                {"level": "VAL-0", "status": "passed", "ran": ["ruff", "mypy"]},
                {"level": "VAL-1", "status": "passed", "ran": ["pytest"]},
            ]
        },
    }
    r = evaluate_standards_conformance(contract)
    assert r["status"] == PASS, r
    assert r["checks"] == {
        "retrieved": PASS,
        "declared": PASS,
        "waived": NOT_APPLICABLE,
        "executed": PASS,
    }, r

    # 5. NEGATIVE (the key case): standard retrieved but ignored in the config.
    ignored = dict(contract, required_commands=["uv", "pytest"])  # no ruff/mypy
    r = evaluate_standards_conformance(ignored)
    assert r["status"] == FAIL and r["checks"]["declared"] == FAIL, r
    assert any("declared_but_not_applied" in x for x in r["reasons"]), r

    # 6. NEGATIVE: declared but the lane never ran -> declared_but_not_executed.
    not_run = {
        "epic_context": {"house_standards": _baseline(["ruff"])},
        "required_commands": ["ruff", "pytest"],
        "verification": {
            "levels": [
                {"level": "VAL-0", "status": "not_run", "reason": "skipped lint"},
            ]
        },
    }
    r = evaluate_standards_conformance(not_run)
    assert r["status"] == FAIL and r["checks"]["executed"] == FAIL, r
    assert any("declared_but_not_executed" in x for x in r["reasons"]), r

    # 7. Deviation without a matching waiver -> FAIL.
    dev = {
        "epic_context": {
            "house_standards": {
                **_baseline(["ruff"]),
                "deviations": [{"rule": "no-ruff-here", "waiver": {"content_hash": "sha256:nope"}}],
            }
        },
        "required_commands": ["ruff"],
        "verification": {"levels": [{"level": "VAL-0", "status": "passed", "ran": ["ruff"]}]},
    }
    r = evaluate_standards_conformance(dev)
    assert r["status"] == FAIL and r["checks"]["waived"] == FAIL, r

    # 8. Deviation WITH a matching waiver hash -> passes the waiver check.
    ok_dev = {
        "epic_context": {
            "house_standards": {
                **_baseline(["ruff"], hash_="sha256:abc"),
                "deviations": [{"rule": "x", "waiver": {"content_hash": "sha256:abc"}}],
            }
        },
        "required_commands": ["ruff"],
        "verification": {"levels": [{"level": "VAL-0", "status": "passed", "ran": ["ruff"]}]},
    }
    r = evaluate_standards_conformance(ok_dev)
    assert r["status"] == PASS and r["checks"]["waived"] == PASS, r

    # 9. Malformed house_standards block -> fail-closed.
    r = evaluate_standards_conformance({"epic_context": {"house_standards": "nope"}})
    assert r["status"] == FAIL, r

    # 10. Only advisory (backstage) source, no checkable tools -> pass (N/A checks).
    adv = {
        "epic_context": {
            "house_standards": {
                "available": True,
                "sources": [
                    {
                        "source": "backstage",
                        "kind": "component",
                        "entity_ref": "component:default/x",
                        "content_hash": "sha256:z",
                    }
                ],
            }
        }
    }
    r = evaluate_standards_conformance(adv)
    assert r["status"] == PASS and r["checks"]["declared"] == NOT_APPLICABLE, r

    print("standards_conformance_gate self-tests: 10 passed")


if __name__ == "__main__":
    _test()
