"""Factory#3865: provenance.source_artifacts, human_approval, and submission_id."""

from __future__ import annotations

from typing import Any

import pytest
from contract_schema import error_messages, schema

_SHA40 = "0123456789abcdef0123456789abcdef01234567"
_SHA64 = "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"


def _contract(**provenance: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "contract_version": "2",
        "feature": "factory-cli",
        "workflow_type": "feature",
        "phases": [{"phase": 1, "name": "p1", "subtasks": [{"id": "s1", "description": "d"}]}],
    }
    if provenance:
        doc["provenance"] = provenance
    return doc


def _valid_artifact(stage: str = "intent", **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "stage": stage,
        "path": f"{stage}/2026-11-23-3865-factory-cli.md",
        "blob_sha": _SHA40,
        "approve_commit_sha": _SHA40,
        "approve_commit_author": "Alice <alice@example.com>",
        "attested_by": "client",
    }
    item.update(overrides)
    return item


def _valid_human_approval(**overrides: Any) -> dict[str, Any]:
    approval: dict[str, Any] = {
        "user_id": "usr_123",
        "approver_display": "Alice",
        "auth_kind": "acw_user_key",
        "approved_at": "2026-11-23T09:00:00Z",
        "plan_hash": _SHA64,
    }
    approval.update(overrides)
    return approval


def test_valid_without_new_provenance_fields() -> None:
    s = schema("task-contract.schema.json")
    assert error_messages(s, _contract()) == []
    assert error_messages(s, _contract(source="pfactory", session_id="sess-1")) == []


def test_valid_with_all_new_provenance_fields() -> None:
    s = schema("task-contract.schema.json")
    doc = _contract(
        source="pfactory",
        source_artifacts=[
            _valid_artifact("intent"),
            _valid_artifact("spec"),
            _valid_artifact("plan"),
        ],
        human_approval=_valid_human_approval(),
        submission_id=_SHA64,
        extra_provenance_key="allowed",
    )
    assert error_messages(s, doc) == []


@pytest.mark.parametrize(
    "bad_sha",
    [
        "short",
        "0123456789abcdef0123456789abcdef0123456",  # 39 chars
        "0123456789abcdef0123456789abcdef012345678",  # 41 chars
        "0123456789ABCDEF0123456789abcdef01234567",  # uppercase
        "g123456789abcdef0123456789abcdef01234567",  # non-hex
    ],
)
def test_bad_artifact_shas_rejected(bad_sha: str) -> None:
    s = schema("task-contract.schema.json")
    assert error_messages(s, _contract(source_artifacts=[_valid_artifact(blob_sha=bad_sha)]))
    assert error_messages(
        s, _contract(source_artifacts=[_valid_artifact(approve_commit_sha=bad_sha)])
    )


@pytest.mark.parametrize(
    "bad_submission_id",
    [
        "short",
        _SHA40,
        _SHA64[:-1],
        _SHA64 + "0",
        _SHA64.upper(),
        "z" * 64,
    ],
)
def test_bad_submission_id_rejected(bad_submission_id: str) -> None:
    s = schema("task-contract.schema.json")
    assert error_messages(s, _contract(submission_id=bad_submission_id))


def test_artifact_constraints_enforced() -> None:
    s = schema("task-contract.schema.json")
    assert error_messages(s, _contract(source_artifacts=[_valid_artifact(stage="other")]))
    assert error_messages(s, _contract(source_artifacts=[_valid_artifact(attested_by="server")]))
    assert error_messages(
        s, _contract(source_artifacts=[_valid_artifact(approve_commit_author="a" * 201)])
    )
    missing = _valid_artifact()
    del missing["blob_sha"]
    assert error_messages(s, _contract(source_artifacts=[missing]))


def test_human_approval_required_fields_enforced() -> None:
    s = schema("task-contract.schema.json")
    for key in ("user_id", "approver_display", "auth_kind", "approved_at", "plan_hash"):
        incomplete = _valid_human_approval()
        del incomplete[key]
        assert error_messages(s, _contract(human_approval=incomplete)), f"missing {key} must fail"
