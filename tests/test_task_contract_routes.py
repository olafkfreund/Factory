"""Factory#1959 stage 3: execution.route / phase_routes use the catalog class vocabulary."""

from __future__ import annotations

from contract_schema import error_messages, schema

_CLASSES = {m["class"] for m in schema("model-catalog.json")["models"].values()}


def _execution() -> dict:
    return schema("task-contract.schema.json")["properties"]["execution"]["properties"]


def _doc(**execution: object) -> dict:
    phase = {"phase": 1, "name": "p", "subtasks": [{"id": "t", "description": "d"}]}
    return {
        "contract_version": "2",
        "feature": "f",
        "workflow_type": "feature",
        "phases": [phase],
        "execution": execution,
    }


def test_enum_is_the_catalog_class_set():
    ex = _execution()
    assert set(ex["route"]["enum"]) == _CLASSES
    assert set(ex["phase_routes"]["additionalProperties"]["enum"]) == _CLASSES


def test_routes_validate_and_phase_models_still_does():
    s = schema("task-contract.schema.json")
    ok = _doc(route="cheap", phase_routes={"coding": "local"}, phase_models={"coding": "x"})
    assert error_messages(s, ok) == []
    assert error_messages(s, _doc()) == []


def test_unknown_route_rejected():
    s = schema("task-contract.schema.json")
    assert error_messages(s, _doc(route="tier-frontier"))
    assert error_messages(s, _doc(phase_routes={"qa": "premium"}))
