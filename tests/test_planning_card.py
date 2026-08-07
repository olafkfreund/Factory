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

from typing import Any

import contract_schema as cs
import pytest
from contract_schema import jsonschema

_SCHEMA_FILE = "planning-card.schema.json"
_TAXONOMY_FILE = "status-taxonomy.json"

_CARD_STATUSES = ("backlog", "ready", "in_progress", "blocked", "done")
# Owned by the server, never accepted from ANY request body (planning-card.md 3).
# `card_key` is deliberately not here: it is server-ASSIGNED but caller-SETTABLE
# on create, to mirror an id from an external tracker (Factory#554). It is
# immutable thereafter, which is why the patch body still refuses it.
_SERVER_OWNED = ("tenant_id", "created_at", "updated_at")


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
    # `count`, not `total`: it is the length of THIS response, not a total
    # across pages, and the service has always returned that name (Factory#371).
    assert doc["count"] == len(doc["cards"])


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
    doc = _example("card-planned")
    del doc["correlation_key"]
    assert any("correlation_key" in m for m in _errors(doc))


def test_correlation_key_is_bounded_where_the_service_bounds_it() -> None:
    """Unjoined is `null`; the join, once made, is at most 128 characters.

    This used to assert that "" is rejected on the RESOURCE, via a `minLength: 1`
    on the shared `$def`. Factory#554 moved every bound to the request bodies,
    because that is where the service enforces one: `CardCreate.correlation_key`
    carries `max_length=128` and nothing else, and the response model carries no
    constraint at all. An empty string is still meaningless - unjoined is `null`
    and "" is a third state nothing knows how to read - but that is now a rule
    with no enforcer, and the schema no longer pretends otherwise (CFactory#324).
    """
    body = {"correlation_key": "3" * 129}
    assert _errors(body, "card_patch") != [], "beyond what the service stores"
    assert _errors({"correlation_key": "302"}, "card_patch") == []


# --- vocabularies -------------------------------------------------------


def test_status_enum_is_closed_and_exact() -> None:
    assert tuple(_schema()["$defs"]["status"]["enum"]) == _CARD_STATUSES


def test_a_github_issue_state_is_not_a_card_status() -> None:
    doc = _example("card-planned")
    doc["status"] = "open"
    assert _errors(doc) != []


def test_tier_is_the_rfc0011_vocabulary_not_high() -> None:
    """RFC-0011 says `hard`; `high` is the mistake everyone makes once."""
    doc = _example("card-planned")
    doc["tier"] = "high"
    assert _errors(doc) != []
    doc["tier"] = "hard"
    assert _errors(doc) == []


def test_tier_is_nullable_because_an_unclassified_card_is_normal() -> None:
    doc = _example("card-planned")
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


def test_create_accepts_a_correlation_key_and_a_caller_supplied_key() -> None:
    """Both used to be rejected here, and the service has always taken them.

    The contract said a card is created as a plan and joined later over PATCH.
    That describes the board, not the importer: `issue_import.py` creates a card
    that is ALREADY joined to its GitHub issue, and a caller mirroring an
    external tracker supplies its own `card_key` so the two ids match. The
    schema's own `$defs.card_key` prose has said so since Factory#371 while
    `card_create` rejected it - the contract contradicted itself, and nothing
    could see that until Factory#554 compared it to the model.
    """
    assert _errors({"title": "Plan something", "correlation_key": "302"}, "card_create") == []
    assert _errors({"title": "Plan something", "card_key": "JIRA-1234"}, "card_create") == []


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


@pytest.mark.parametrize("field", (*_SERVER_OWNED, "card_key"))
def test_patch_rejects_server_owned_fields(field: str) -> None:
    """`card_key` is settable on create and immutable after: it is the path
    segment of every single-card route and the id other systems quote."""
    assert _errors({field: "nope"}, "card_patch") != []


@pytest.mark.parametrize("field", ("description", "issue_ref", "repository_id"))
def test_the_request_bodies_carry_every_field_a_caller_can_originate(field: str) -> None:
    """Three fields the service has always accepted and the schema refused.

    `description` holds an imported issue body, `issue_ref` adopts an issue, and
    `repository_id` targets one of the tenant's repositories. All three are
    writable on `CardCreate` and `CardUpdate`; `additionalProperties: false`
    meant the contract called each one an error. That is the shape of drift
    Factory#554 makes impossible: a field on the wire nobody was told about.
    """
    value: object = 4 if field == "repository_id" else "x"
    assert _errors({"title": "Plan something", field: value}, "card_create") == []
    assert _errors({field: value}, "card_patch") == []


@pytest.mark.parametrize(
    "field", ("issue_ref", "issue_state", "labels", "github_sync_error", "stage_runs")
)
def test_the_mirrored_fields_are_required_on_the_resource(field: str) -> None:
    """The service marks all five REQUIRED; the schema had them optional.

    They are the GitHub mirror plus the dispatch record, and the service emits
    every one of them on every read - `labels` as `[]` and the rest as `null`
    when there is nothing to mirror. A consumer told they were optional would
    reasonably branch on absence, which is a state the API never produces.
    """
    doc = _example("card-planned")
    del doc[field]
    assert any(field in m for m in _errors(doc))


def test_the_resource_asserts_no_bound_the_service_does_not_enforce() -> None:
    """Bounds live on the request bodies now, because that is where they bite.

    `CardCreate`/`CardUpdate` carry the `max_length` constraints; `Card` is the
    serialisation of a row and carries none. A `maxLength` on the resource would
    be a rule a consumer could use to REJECT a response the server legitimately
    sent - the same class of error as `priority: {minimum: 0}`, which the schema
    asserted and the server never enforced (Factory#371).
    """
    card = _schema()["$defs"]["card"]["properties"]
    defs = _schema()["$defs"]
    for name, node in card.items():
        target = defs[node["$ref"].removeprefix("#/$defs/")] if "$ref" in node else node
        assert not (set(target) & {"minLength", "maxLength", "minimum", "maximum", "pattern"}), name
    create = _schema()["$defs"]["card_create"]["properties"]
    assert create["title"]["maxLength"] == 512
    assert create["assignee"]["maxLength"] == 128


def test_a_new_card_lands_at_the_top_of_the_backlog_not_the_bottom() -> None:
    """`priority` defaults to 0, not 100.

    The schema's prose said 100 and the service has always used 0. Nobody could
    tell, because the default was described in English and never declared as a
    JSON Schema `default` - so there was nothing for anything to compare. It is
    declared now, and the conformance gate reads it.
    """
    create = _schema()["$defs"]["card_create"]["properties"]
    assert create["priority"]["default"] == 0
    assert create["status"]["default"] == "backlog"


# --- scalars ------------------------------------------------------------


def test_priority_is_an_integer_and_negatives_are_legal() -> None:
    """Negative priorities are how a card jumps above 0 (Factory#371).

    This test used to assert `minimum: 0`, matching a schema the service never
    enforced. It was guarding the contradiction rather than the contract: the
    board documents negatives as the way to insert above the top without
    renumbering every row beneath. The type bar stays — "20" is still not 20.
    """
    doc = _example("card-planned")
    doc["priority"] = "20"
    assert _errors(doc) != [], "a string is still not an integer"
    doc["priority"] = -1
    assert _errors(doc) == [], "negatives are legal; the server has always accepted them"
    doc["priority"] = 0
    assert _errors(doc) == []


def test_card_key_accepts_a_server_key_or_an_external_one() -> None:
    """Two origins, so there is no pattern to enforce (Factory#371).

    This test used to require `^FCT-[1-9][0-9]{0,8}$`, which describes only the
    keys the server assigns. A caller may supply its own to mirror an id from an
    external tracker, and the service accepts up to 128 characters — so the old
    assertion encoded a rule that would have rejected valid cards.

    The 128-character bound is now asserted on `card_create`, not on the
    resource: `CardCreate.card_key` carries `max_length=128` and the response
    model carries nothing, so that is the one place the rule has an enforcer
    (Factory#554).
    """
    doc = _example("card-planned")
    for good in ("FCT-42", "JIRA-1234", "gh-9", "42"):
        doc["card_key"] = good
        assert _errors(doc) == [], good
    assert _errors({"title": "x", "card_key": "y" * 129}, "card_create") != [], "beyond the column"
    assert _errors({"title": "x", "card_key": "y" * 128}, "card_create") == []


def test_acceptance_criteria_is_a_list_of_strings_and_may_be_empty() -> None:
    """An empty LIST is legal while planning; a blank ENTRY is no longer refused.

    The item used to carry `minLength: 1`. The service has never enforced it -
    `list[str]` on all three models, no per-item constraint - so the rule sat in
    the schema with no implementation behind it, which is the class of fiction
    Factory#554 removed. The reasoning survives in the field's prose and the
    service-side fix is CFactory#324; when it lands, the bound comes back here
    and the conformance gate keeps the two in step.
    """
    doc = _example("card-planned")
    doc["acceptance_criteria"] = []
    assert _errors(doc) == []
    doc["acceptance_criteria"] = [""]
    assert _errors(doc) == [], "not enforced by the service, so not asserted here"
    doc["acceptance_criteria"] = [3]
    assert _errors(doc) != [], "the element TYPE is still a bar"


def test_unknown_field_on_the_resource_is_rejected() -> None:
    """Including a field from the hierarchy Phase 1 deliberately does not ship."""
    doc = _example("card-planned")
    doc["workspace_id"] = "default"
    assert _errors(doc) != []
