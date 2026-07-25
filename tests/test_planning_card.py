#!/usr/bin/env python3
"""Self-test for the RFC-0019 planning-card contract.

Behaviour-locking tests for `apis/planning-card.schema.json` and the reference
instances under `apis/examples/planning-cards/`:

1. The schema is itself a valid Draft 2020-12 schema.
2. Every committed example validates - a planned card, a card that has entered
   the factory, and a list response.
3. The join works both ways: `correlation_key` is nullable while planned and a
   string once in the factory, and it may not be dropped from the resource.
4. The guardrails bite: server-owned fields are rejected on create, an empty
   patch is rejected, and the status/tier vocabularies are closed.
5. Card statuses are NOT the runtime status taxonomy - asserted against
   `apis/status-taxonomy.json`, which is exactly why they need their own enum.

Skips cleanly when jsonschema is unavailable (e.g. outside the Nix devShell);
`tests/test_agent_skills_manifest.py` has the same optional dependency.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import contract_schema as cs
import pytest

jsonschema = pytest.importorskip("jsonschema")

_SCHEMA_FILE = "planning-card.schema.json"
_TAXONOMY_FILE = "status-taxonomy.json"

_CARD_STATUSES = ("backlog", "ready", "in_progress", "blocked", "done")
# Owned by the server, never accepted from a request body (planning-card.md 3).
_SERVER_OWNED = ("card_key", "tenant_id", "created_at", "updated_at")


def _example(name: str) -> dict[str, Any]:
    return cs.example("planning-cards", name)


def _schema() -> dict[str, Any]:
    return cs.schema(_SCHEMA_FILE)


def _subschema(ref: str | None = None) -> dict[str, Any]:
    """The whole schema, or one `$defs` entry kept resolvable against the root."""
    schema = _schema()
    if ref is None:
        return schema
    sub: dict[str, Any] = dict(schema["$defs"][ref])
    # $defs comes along so the sub-schema's internal $refs still resolve.
    sub["$defs"] = schema["$defs"]
    return sub


def _errors(doc: Any, ref: str | None = None) -> list[str]:
    validator = jsonschema.Draft202012Validator(_subschema(ref))
    return [e.message for e in validator.iter_errors(doc)]


def test_schema_is_valid_draft_2020_12() -> None:
    jsonschema.Draft202012Validator.check_schema(_schema())


@pytest.mark.parametrize("name", ["card-planned", "card-in-factory"])
def test_card_examples_validate(name: str) -> None:
    assert _errors(_example(name)) == []


def test_card_list_example_validates() -> None:
    doc = _example("card-list")
    assert _errors(doc, "card_list") == []
    assert doc["total"] == len(doc["cards"])


def test_list_is_ordered_by_priority_then_created_at_then_key() -> None:
    """planning-card.md section 3: two identical requests return one order."""
    cards = _example("card-list")["cards"]
    keys = [(c["priority"], c["created_at"], c["card_key"]) for c in cards]
    assert keys == sorted(keys)


# --- the join -----------------------------------------------------------


def test_a_planned_card_has_a_null_correlation_key() -> None:
    """NULL is the normal state of the backlog, not a defect."""
    assert _example("card-planned")["correlation_key"] is None


def test_a_card_in_the_factory_carries_the_rfc0001_key() -> None:
    assert _example("card-in-factory")["correlation_key"] == "302"


def test_correlation_key_must_be_present_even_when_null() -> None:
    """Every field is always present, so a consumer never guesses at absence."""
    doc = deepcopy(_example("card-planned"))
    del doc["correlation_key"]
    assert any("correlation_key" in m for m in _errors(doc))


def test_correlation_key_may_not_be_an_empty_string() -> None:
    """Unjoined is `null`; "" would be a third state nothing knows how to read."""
    doc = deepcopy(_example("card-planned"))
    doc["correlation_key"] = ""
    assert _errors(doc) != []


# --- vocabularies -------------------------------------------------------


def test_status_enum_is_closed_and_exact() -> None:
    assert tuple(_schema()["$defs"]["status"]["enum"]) == _CARD_STATUSES


def test_a_github_issue_state_is_not_a_card_status() -> None:
    doc = deepcopy(_example("card-planned"))
    doc["status"] = "open"
    assert _errors(doc) != []


def test_tier_is_the_rfc0011_vocabulary_not_high() -> None:
    """RFC-0011 says `hard`; `high` is the mistake everyone makes once."""
    doc = deepcopy(_example("card-planned"))
    doc["tier"] = "high"
    assert _errors(doc) != []
    doc["tier"] = "hard"
    assert _errors(doc) == []


def test_tier_is_nullable_because_an_unclassified_card_is_normal() -> None:
    doc = deepcopy(_example("card-planned"))
    doc["tier"] = None
    assert _errors(doc) == []


def test_card_statuses_would_be_misread_by_the_runtime_taxonomy() -> None:
    """Why cards need their own enum (planning-card.md section 2).

    `apis/status-taxonomy.json` normalises what the four SERVICES report. Two of
    its token sets collide with this vocabulary head-on, so a card status routed
    through it lies: a card waiting to be picked up reads as finished, and a card
    a human parked reads as a failure.
    """
    states = cs.schema(_TAXONOMY_FILE)["states"]
    assert "ready" in states["done"]["tokens"]
    assert "blocked" in states["failed"]["tokens"]
    assert {"ready", "blocked"} <= set(_CARD_STATUSES)


# --- request bodies -----------------------------------------------------


@pytest.mark.parametrize("field", _SERVER_OWNED)
def test_create_rejects_server_owned_fields(field: str) -> None:
    """Rejected, not ignored: a partly-discarded body misleads the caller."""
    body = {"title": "Rate-limit the completion-event ingress", field: "nope"}
    assert _errors(body, "card_create") != []


def test_create_rejects_a_correlation_key() -> None:
    """A card is created as a plan; the join is made later, over PATCH."""
    body = {"title": "Plan something", "correlation_key": "302"}
    assert _errors(body, "card_create") != []


def test_create_needs_a_title_and_nothing_else() -> None:
    assert _errors({"title": "Plan something"}, "card_create") == []
    assert _errors({"priority": 10}, "card_create") != []


def test_patch_moves_and_reprioritises_through_one_route() -> None:
    assert _errors({"status": "in_progress"}, "card_patch") == []
    assert _errors({"priority": 15}, "card_patch") == []
    assert _errors({"status": "done", "priority": 0}, "card_patch") == []


def test_patch_sets_the_join_when_the_card_enters_the_factory() -> None:
    assert _errors({"correlation_key": "302"}, "card_patch") == []


def test_empty_patch_is_a_mistake_not_a_no_op() -> None:
    assert _errors({}, "card_patch") != []


@pytest.mark.parametrize("field", _SERVER_OWNED)
def test_patch_rejects_server_owned_fields(field: str) -> None:
    assert _errors({field: "nope"}, "card_patch") != []


# --- scalars ------------------------------------------------------------


def test_priority_is_an_integer_and_never_negative() -> None:
    doc = deepcopy(_example("card-planned"))
    doc["priority"] = "20"
    assert _errors(doc) != []
    doc["priority"] = -1
    assert _errors(doc) != []
    doc["priority"] = 0
    assert _errors(doc) == []


def test_card_key_must_look_like_fct_n() -> None:
    doc = deepcopy(_example("card-planned"))
    for bad in ("42", "FCT-0", "fct-42", "FCT-", "FCT-42-1"):
        doc["card_key"] = bad
        assert _errors(doc) != [], bad


def test_acceptance_criteria_entries_may_not_be_blank() -> None:
    doc = deepcopy(_example("card-planned"))
    doc["acceptance_criteria"] = [""]
    assert _errors(doc) != []
    doc["acceptance_criteria"] = []
    assert _errors(doc) == []


def test_unknown_field_on_the_resource_is_rejected() -> None:
    """Including a field from the hierarchy Phase 1 deliberately does not ship."""
    doc = deepcopy(_example("card-planned"))
    doc["workspace_id"] = "default"
    assert _errors(doc) != []
