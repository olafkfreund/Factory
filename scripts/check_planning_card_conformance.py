#!/usr/bin/env python3
"""Does CFactory's card model still say what the hub contract says? (Factory#554)

``apis/planning-card.schema.json`` is the hub-owned, CODEOWNERS-reviewed contract
for the RFC-0019 planning card. ``CFactory``'s ``cfactory.cards`` module is the
running implementation. Until this gate existed the two were kept in step BY HAND,
and they did not stay in step:

* The schema landed with RFC-0019 phase 1 and contradicted the service in six
  places within a day (Factory#371). Reconciling it took a 247-line diff.
* Reconciling it did not hold either. Measured against the LIVE service the day
  Factory#554 was worked, the reconciled schema still disagreed in fifteen
  places — five fields the service always returns and the schema had optional,
  five fields the service accepts on create and the schema rejected outright,
  three on patch, a create default of 100 against the service's 0, and bounds
  the schema asserted on a response model that enforces none.

Nothing detected any of that, because ``tests/test_planning_card.py`` validates
the committed EXAMPLES against the schema. The examples and the schema agreed
with each other while both disagreed with the service — a closed loop that
cannot see outside itself. This gate is the thing outside it.

DIRECTION OF TRUTH: the CONTRACT. The hub schema stays hand-written, because
what it carries beyond the field list is the reasoning — why ``count`` is not
``total``, why ``issue_state`` is not a ``status``, why ``comment_count`` and
``comments_synced_at`` must be read together, why ``correlation_key`` is
deliberately reused across stages. A generator emits none of that. Generating
the schema FROM the models would also mean a careless service edit silently
redefines the contract for every consumer with no review, which is the failure
mode this hub exists to prevent. So the service is measured against the
contract, not the other way round, and this is that measurement.

WHAT IS COMPARED, AND WHY THAT AND NOT BYTES
--------------------------------------------
Byte comparison is the fleet's usual drift mechanism
(``check_verification_core_drift.py``) and is the wrong tool here: the two sides
are a hand-written JSON Schema carrying paragraphs of prose and a pydantic
model, and they can never be byte-equal. What CAN be equal is the STRUCTURE, so
each side is reduced to the same per-field facet set and those are compared:

    required   is the field always present / mandatory in the body
    types      the JSON type set, INCLUDING null
    enum       the closed vocabulary, if any
    format     date-time and friends
    items      the element facets of an array, recursively
    default    the declared default, when it is not null
    bounds     pattern / minLength / maxLength / minimum / maximum

Descriptions and titles are deliberately NOT compared: the prose is the half of
the contract a generator cannot produce and a model does not carry.

A CONSEQUENCE WORTH STATING, because it looks like a loss and is not. A bound
is compared wherever it is declared, so the contract may only declare one where
the service actually enforces it — which for this API is the REQUEST bodies
(``CardCreate`` / ``CardUpdate`` carry the ``max_length`` constraints; ``Card``,
being the serialisation of a row, carries none). The reconciliation for
Factory#554 therefore moved every bound off the shared ``$defs`` and onto the
request-body declarations, as ``$ref`` siblings. The reasoning for each bound
still lives once, in the ``$def``'s prose. What is gone is the *assertion* of a
bound on a response that nothing checks — which is the same class of fiction as
``priority: {minimum: 0}``, a rule the schema stated and the server never
enforced, and one of the six contradictions Factory#371 had to unpick.

A field TYPE change is the drift that actually breaks a consumer and the one a
field-name comparison misses, so it is the case the self-test leads with:
narrowing ``str`` to ``Literal["a", "b"]`` adds an ``enum`` facet and moves
nothing else, and it must be red.

WHAT THIS GATE DOES NOT REACH, said out loud so it is a known limit rather than
a discovered one. The comparison is per-FIELD, so the object-level keywords
``additionalProperties`` and ``minProperties`` are outside it. Both express
BEHAVIOUR — "an unknown field is a 400", "an empty patch is an error" — and
pydantic's default ``extra="ignore"`` renders neither into the model schema, so
there is nothing on the service side to compare them against. That is not
theoretical: the contract asserted both, and the service honours neither (an
unknown key on POST /api/cards is silently discarded, and an empty PATCH body is
accepted as a no-op). Rather than leave the assertions standing where nothing
checks them, the Factory#554 reconciliation removed them from the request
bodies and filed the service-side fix as CFactory#322. Adding ``extra="forbid"``
there is what puts them back.

THE ONE CARVE-OUT, STATED RATHER THAN HIDDEN
---------------------------------------------
On the PATCH role only, ``null`` is dropped from the type set on BOTH sides
before comparing. The reason is that pydantic's partial-update idiom is
``field: X | None = None``, where ``None`` means "the caller did not send this",
not "the caller may send null". The service therefore reports every patchable
field as nullable whether or not null is a legal value, and the information the
gate would need to tell those apart is simply not in the model. Comparing it
anyway would force the contract to either document a null that crashes the
service (``{"title": null}`` against a NOT NULL column) or to deny a null that
is legal (clearing a ``tier``).

Nullability is fully compared on the RESOURCE and on CREATE, where it is real.
The self-test asserts this carve-out does not leak: on the patch role a type
change, an enum narrowing, and a field appearing or disappearing are all still
red.

Usage:
    # In CFactory's CI, out of a hub checkout pinned by HUB_PIN_SHA:
    python3 scripts/check_planning_card_conformance.py --root /path/to/CFactory

    # Point at a schema other than this checkout's (rarely needed):
    python3 scripts/check_planning_card_conformance.py \
        --root /path/to/CFactory --schema apis/planning-card.schema.json

    # Built-in self-test: synthetic pydantic models, no CFactory checkout, and
    # the mutations are performed rather than described.
    python3 scripts/check_planning_card_conformance.py --self-test

Exit codes:
    0 - every role's field set and facets agree
    1 - the service and the contract disagree (or the self-test failed)
    2 - bad invocation: the schema, the service tree or the models could not be
        read. NEVER a silent pass — a check that cannot see its subject has to
        say so (Factory#500).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

# Sibling module in this same scripts/ directory; consumers run this gate out of
# a full hub checkout, so it resolves there too (see gate_evidence's docstring).
from gate_evidence import digest
from selftest_report import SelfTest, gate_argparser

_EXIT_BAD_INVOCATION = 2

_DEFAULT_SCHEMA = Path(__file__).resolve().parents[1] / "apis" / "planning-card.schema.json"

# Where CFactory keeps the models, and which `$defs` each one implements. The
# names differ on the two sides (`card_patch` / `CardUpdate`) and always have;
# pretending otherwise would mean renaming one of them to please a gate.
_SERVICE_SYS_PATH = "apps/backend"
_SERVICE_MODULE = "cfactory.cards"
_ROLES: tuple[tuple[str, str], ...] = (
    ("card", "Card"),
    ("card_create", "CardCreate"),
    ("card_patch", "CardUpdate"),
    ("card_list", "CardList"),
)

# The role on which `null` is pydantic's unset sentinel rather than a value.
# See "THE ONE CARVE-OUT" above. Exactly one role, named, so that widening this
# is a visible edit rather than a silent behaviour.
_UNSET_SENTINEL_ROLE = "card_patch"

# Facet keys carried straight across from a schema node when present.
_SCALAR_FACETS: tuple[str, ...] = (
    "format",
    "default",
    "pattern",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
)


def _emit(message: str) -> None:
    # A CLI gate: its stdout report IS its purpose, so the no-print rule is
    # suppressed at the single output sink.
    print(message)  # noqa: T201


def _resolve(node: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    """A schema node with any local ``$ref`` resolved and siblings overlaid.

    JSON Schema 2020-12 permits keywords beside ``$ref`` (draft-07 did not), and
    the contract uses that: a request body writes
    ``{"$ref": "#/$defs/title", "maxLength": 512}`` so the prose lives once in
    ``$defs`` while the bound lives where the service actually enforces it. The
    sibling wins, which matches the implicit-allOf reading for the narrowing
    keywords this gate compares.
    """
    ref = node.get("$ref")
    if not isinstance(ref, str):
        return node
    if not ref.startswith("#/$defs/"):
        raise ValueError(f"only local #/$defs/ refs are supported, got {ref!r}")
    target = root.get("$defs", {}).get(ref.removeprefix("#/$defs/"))
    if target is None:
        raise ValueError(f"unresolvable ref {ref!r}")
    merged = dict(_resolve(target, root))
    merged.update({k: v for k, v in node.items() if k != "$ref"})
    return merged


def _branches(node: dict[str, Any], root: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten ``anyOf``/``oneOf`` into the leaf nodes they union over.

    pydantic renders ``str | None`` as ``anyOf: [{string}, {null}]`` while a
    hand-written schema writes ``type: ["string", "null"]``. Both mean one field
    with two admissible types, so both reduce to the same facet set.
    """
    resolved = _resolve(node, root)
    union = resolved.get("anyOf") or resolved.get("oneOf")
    if not isinstance(union, list):
        return [resolved]
    out: list[dict[str, Any]] = []
    for branch in union:
        out.extend(_branches(branch, root))
    return out


def _types(branch: dict[str, Any]) -> set[str]:
    """The JSON types one leaf admits, from ``type`` or from a nullable enum."""
    declared = branch.get("type")
    if isinstance(declared, str):
        return {declared}
    if isinstance(declared, list):
        return {t for t in declared if isinstance(t, str)}
    # A bare `enum: [...]` with no `type` still tells us the types.
    enum = branch.get("enum")
    if isinstance(enum, list):
        return {"null" if v is None else type(v).__name__.replace("str", "string") for v in enum}
    return set()


def facets(node: dict[str, Any], root: dict[str, Any], *, required: bool | None) -> dict[str, Any]:
    """Reduce one schema node to the comparable facets defined in the docstring.

    *required* is threaded in rather than read from the node because "required"
    is a property of the PARENT object's ``required`` list, not of the field.
    Passing ``None`` omits the facet entirely, which is what array *items* need
    (an element is not required or optional, it just is).
    """
    branches = _branches(node, root)
    types: set[str] = set()
    enum: set[Any] = set()
    scalars: dict[str, Any] = {}
    items: dict[str, Any] | None = None
    for branch in branches:
        types |= _types(branch)
        values = branch.get("enum")
        if isinstance(values, list):
            enum |= {v for v in values if v is not None}
            if None in values:
                types.add("null")
        for key in _SCALAR_FACETS:
            if key in branch and branch[key] is not None:
                # A null default is pydantic's "no default"; treating it as
                # absent keeps the two sides symmetric without either having to
                # spell `"default": null` out eleven times.
                scalars[key] = branch[key]
        child = branch.get("items")
        if isinstance(child, dict):
            items = facets(child, root, required=None)
    facet: dict[str, Any] = {"types": tuple(sorted(types))}
    if required is not None:
        facet["required"] = required
    if enum:
        # Sorted by repr so a mixed-type enum still has one stable order.
        facet["enum"] = tuple(sorted(enum, key=repr))
    if items is not None:
        facet["items"] = items
    facet.update(scalars)
    return facet


def role_facets(
    obj: dict[str, Any], root: dict[str, Any], *, role: str
) -> dict[str, dict[str, Any]]:
    """Per-field facets for one object schema (one ``$def`` or one model)."""
    required = set(obj.get("required") or ())
    out: dict[str, dict[str, Any]] = {}
    for name, node in (obj.get("properties") or {}).items():
        facet = facets(node, root, required=name in required)
        if role == _UNSET_SENTINEL_ROLE:
            facet["types"] = tuple(t for t in facet["types"] if t != "null")
        out[name] = facet
    return out


def compare_role(
    role: str,
    contract: dict[str, dict[str, Any]],
    service: dict[str, dict[str, Any]],
) -> list[str]:
    """Every way *role* disagrees between the contract and the service."""
    problems = [
        f"{role}.{name}: in the contract, absent from the service model — the "
        "contract promises a field nothing serves"
        for name in sorted(set(contract) - set(service))
    ]
    problems.extend(
        f"{role}.{name}: served by the model, absent from the contract — a field "
        "on the wire that no consumer was told about"
        for name in sorted(set(service) - set(contract))
    )
    for name in sorted(set(contract) & set(service)):
        want, got = contract[name], service[name]
        for key in sorted(set(want) | set(got)):
            if want.get(key) != got.get(key):
                problems.append(
                    f"{role}.{name}: {key} differs — contract {want.get(key)!r}, "
                    f"service {got.get(key)!r}"
                )
    return problems


def load_schema(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def load_service_models(root: Path) -> dict[str, dict[str, Any]]:
    """``role -> model_json_schema()`` for each model in :data:`_ROLES`.

    Imported rather than parsed: an AST reading of ``cards.py`` would have to
    re-implement pydantic's type resolution, and the thing worth comparing is
    what pydantic actually emits — that is the shape FastAPI serves and the
    shape a client validates against.
    """
    sys.path.insert(0, str((root / _SERVICE_SYS_PATH).resolve()))
    module = importlib.import_module(_SERVICE_MODULE)
    out: dict[str, dict[str, Any]] = {}
    for role, model_name in _ROLES:
        model = getattr(module, model_name, None)
        if model is None:
            raise AttributeError(
                f"{_SERVICE_MODULE}.{model_name} not found — the model backing "
                f"`$defs.{role}` was renamed or removed; update _ROLES together "
                "with the contract rather than dropping the role"
            )
        out[role] = model.model_json_schema()
    return out


def unmapped_roles(contract: dict[str, Any]) -> list[str]:
    """`$defs` that describe an OBJECT but that :data:`_ROLES` maps to no model.

    The gate's own scope, asked from the contract's side rather than the map's
    (Factory#523, one repo along). Everything else here compares what ``_ROLES``
    points at, so deleting a line from ``_ROLES`` removes that role from the
    gate's world entirely: the `$def` stays in the contract, consumers keep
    reading it, and the report simply lists one role fewer — which reads exactly
    like nothing being wrong. That mutation is how ``card_list`` came to be the
    one part of this contract nothing compared, and it is the part the
    ``count``/``total`` defect lived in for months.

    An object `$def` is identified by carrying ``properties``; the scalar `$defs`
    (``title``, ``status``, the rest) are field vocabularies and are compared
    wherever a role refs them, not on their own.
    """
    mapped = {role for role, _model in _ROLES}
    return [
        f"{name}: `$defs.{name}` describes an object but _ROLES maps it to no model, "
        "so nothing compares it — add it to _ROLES or fold it into a role that is mapped"
        for name, node in sorted((contract.get("$defs") or {}).items())
        if isinstance(node, dict) and "properties" in node and name not in mapped
    ]


def check(contract: dict[str, Any], service: dict[str, dict[str, Any]]) -> list[str]:
    """Every disagreement across every role, contract-side and service-side."""
    problems: list[str] = unmapped_roles(contract)
    defs = contract.get("$defs") or {}
    for role, _model in _ROLES:
        node = defs.get(role)
        if node is None:
            problems.append(
                f"{role}: no `$defs.{role}` in the contract, so the model backing "
                "it is compared against nothing"
            )
            continue
        try:
            problems.extend(
                compare_role(
                    role,
                    role_facets(node, contract, role=role),
                    role_facets(service[role], service[role], role=role),
                )
            )
        except ValueError as exc:
            # A dangling `$ref` is drift too, and the loudest kind: deleting a
            # `$def` another role points at used to raise out of the gate
            # instead of failing it, and a traceback is not a verdict.
            problems.append(f"{role}: the contract does not resolve — {exc}")
    return problems


def run_check(schema_path: Path, root: Path) -> int:
    """Compare one CFactory checkout against one contract. Return an exit code."""
    if not schema_path.is_file():
        _emit(f"ERROR: contract not found: {schema_path}")
        return _EXIT_BAD_INVOCATION
    if not (root / _SERVICE_SYS_PATH).is_dir():
        _emit(
            f"ERROR: {root / _SERVICE_SYS_PATH} is not a directory — is --root a CFactory checkout?"
        )
        return _EXIT_BAD_INVOCATION
    contract = load_schema(schema_path)
    try:
        service = load_service_models(root)
    except (ImportError, AttributeError) as exc:
        # Never downgraded to a pass: an import failure means the gate did not
        # look at anything, and "I could not look" is not "nothing is wrong".
        _emit(f"ERROR: could not load {_SERVICE_MODULE} from {root}: {exc}")
        return _EXIT_BAD_INVOCATION
    problems = check(contract, service)

    models_file = root / _SERVICE_SYS_PATH / f"{_SERVICE_MODULE.replace('.', '/')}.py"
    _emit(
        f"planning-card conformance: {schema_path} [{digest(schema_path)}] "
        f"vs {models_file} [{digest(models_file)}]"
    )
    _emit("  compared (each line is a role and the fields the verdict was read from):")
    for role, model_name in _ROLES:
        fields = sorted(service[role].get("properties") or {})
        _emit(f"    - $defs.{role} <-> {_SERVICE_MODULE}.{model_name}: {', '.join(fields)}")
    _emit(
        f"  scanned the contract for an object `$def` that _ROLES maps nowhere; "
        f"mapped roles: {', '.join(role for role, _m in _ROLES)}"
    )
    _emit(
        "  facets compared per field: required, types (incl. null), enum, format, "
        "items, default, pattern, minLength, maxLength, minimum, maximum. "
        "Descriptions are NOT compared - the prose is the contract's own. "
        "Object-level additionalProperties/minProperties are NOT compared - "
        "pydantic renders neither, see this script's docstring."
    )
    _emit(
        f"  NOT compared on $defs.{_UNSET_SENTINEL_ROLE}: null in the type set. "
        "pydantic's partial-update idiom `X | None = None` uses None to mean "
        "'not sent', so the model cannot express whether null is a legal value."
    )
    if problems:
        _emit(f"planning-card DRIFT - the service and the contract disagree ({len(problems)}):")
        for problem in problems:
            _emit(f"  - {problem}")
        _emit(
            "\nThe hub contract is the source of truth (Factory#554). Two ways out, "
            "and only two:\n"
            "  1. The SERVICE is wrong -> fix the model in CFactory to match\n"
            "     apis/planning-card.schema.json.\n"
            "  2. The CONTRACT is to change -> land it in the hub first, in a\n"
            "     CODEOWNERS-reviewed PR that carries the reasoning in the field's\n"
            "     description, then bump HUB_PIN_SHA in CFactory's\n"
            "     planning-card-conformance workflow to the hub commit carrying it.\n"
            "Never edit whichever side is easier to reach: that is the hand-\n"
            "maintenance this gate replaced, and it drifted twice."
        )
        return 1
    _emit("OK: every role above agrees with the contract on every facet.")
    return 0


# --- self-test ----------------------------------------------------------------
# Synthetic models, so the gate's logic is verified with no CFactory checkout and
# no network. Every case MUTATES one side and asserts the gate goes red, per
# docs/dev/gate-honesty.md: a gate nobody has watched fail is a gate nobody has
# reason to believe.

_SELFTEST_CONTRACT: dict[str, Any] = {
    "$defs": {
        "status": {"type": "string", "enum": ["backlog", "done"]},
        "card": {
            "type": "object",
            "required": ["card_key", "status"],
            "properties": {
                "card_key": {"type": "string"},
                "status": {"$ref": "#/$defs/status"},
                "tier": {"type": ["string", "null"], "enum": ["low", "hard", None]},
                "labels": {"type": "array", "items": {"type": "string"}},
                "comment_count": {"type": "integer", "default": 0},
            },
        },
        "card_create": {
            "type": "object",
            "required": ["title"],
            "properties": {"title": {"type": "string", "maxLength": 512}},
        },
        "card_patch": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "status": {"$ref": "#/$defs/status"}},
        },
        "card_list": {
            "type": "object",
            "required": ["count", "cards"],
            "properties": {
                "count": {"type": "integer"},
                "cards": {"type": "array", "items": {"$ref": "#/$defs/card"}},
            },
        },
    }
}


def _selftest_service() -> dict[str, dict[str, Any]]:
    """The synthetic service side, rendered by pydantic exactly as CFactory is."""
    from typing import Literal  # noqa: PLC0415 - kept out of the gate's import path

    from pydantic import BaseModel, Field  # noqa: PLC0415

    class Card(BaseModel):
        card_key: str
        status: Literal["backlog", "done"]
        tier: Literal["low", "hard"] | None = None
        labels: list[str] = Field(default_factory=list)
        comment_count: int = 0

    class CardCreate(BaseModel):
        title: str = Field(max_length=512)

    class CardUpdate(BaseModel):
        title: str | None = None
        status: Literal["backlog", "done"] | None = None

    class CardList(BaseModel):
        count: int
        cards: list[Card]

    # `tier` and `labels` carry defaults, so pydantic marks them optional; the
    # contract above matches that. `card_list.cards` renders as an array of a
    # $ref, which reduces to types=("array",) with no comparable item facet on
    # either side - the element shape is `$defs.card`, already compared as its
    # own role.
    return {
        "card": Card.model_json_schema(),
        "card_create": CardCreate.model_json_schema(),
        "card_patch": CardUpdate.model_json_schema(),
        "card_list": CardList.model_json_schema(),
    }


def _mutated(role: str, field: str, **changes: Any) -> dict[str, Any]:
    """A copy of the contract with one field's node changed."""
    import copy  # noqa: PLC0415

    doc = copy.deepcopy(_SELFTEST_CONTRACT)
    node = doc["$defs"][role]["properties"][field]
    node.pop("$ref", None)
    node.update(changes)
    return doc


def _self_test() -> int:
    t = SelfTest("planning-card-conformance")
    service = _selftest_service()

    def problems(
        contract: dict[str, Any], svc: dict[str, dict[str, Any]] | None = None
    ) -> list[str]:
        return check(contract, svc if svc is not None else service)

    t.req(problems(_SELFTEST_CONTRACT) == [], "baseline: the matched pair is clean")

    # THE CASE A SHALLOW COMPARISON MISSES. The field is present on both sides
    # with the same name and the same JSON type; only the vocabulary narrowed.
    # This is the drift that actually breaks a consumer.
    widened = _mutated("card", "status", type="string")
    widened["$defs"]["status"] = {"type": "string"}
    t.req(
        any("status: enum differs" in p for p in problems(widened)),
        "narrowing str to Literal[...] on the resource is red (the type-change case)",
    )
    narrow = _mutated("card", "status", type="string", enum=["backlog", "done", "archived"])
    t.req(
        any("status: enum differs" in p for p in problems(narrow)),
        "an enum value the service does not have is red",
    )

    # A plain type swap, and a nullability swap, on the resource.
    t.req(
        any(
            "card_key: types differs" in p
            for p in problems(_mutated("card", "card_key", type="integer"))
        ),
        "a str -> int type change on the resource is red",
    )
    t.req(
        any(
            "card_key: types differs" in p
            for p in problems(_mutated("card", "card_key", type=["string", "null"]))
        ),
        "making a non-nullable resource field nullable is red",
    )

    # Field set, both directions.
    added = _mutated("card", "card_key")
    added["$defs"]["card"]["properties"]["workspace_id"] = {"type": "string"}
    t.req(
        any("workspace_id" in p and "absent from the service" in p for p in problems(added)),
        "a contract field the model does not serve is red",
    )
    dropped = _mutated("card", "card_key")
    del dropped["$defs"]["card"]["properties"]["labels"]
    t.req(
        any("labels" in p and "absent from the contract" in p for p in problems(dropped)),
        "a served field the contract does not mention is red",
    )

    # required, bounds, defaults, item facets, format.
    optional = _mutated("card", "card_key")
    optional["$defs"]["card"]["required"] = ["status"]
    t.req(
        any("card_key: required differs" in p for p in problems(optional)),
        "a field the service always sends and the contract calls optional is red",
    )
    t.req(
        any(
            "title: maxLength differs" in p
            for p in problems(_mutated("card_create", "title", maxLength=256))
        ),
        "a bound that disagrees on a request body is red",
    )
    t.req(
        any(
            "comment_count: default differs" in p
            for p in problems(_mutated("card", "comment_count", default=100))
        ),
        "a declared default that disagrees is red (the priority-100-vs-0 case)",
    )
    t.req(
        any(
            "labels: items differs" in p
            for p in problems(_mutated("card", "labels", items={"type": "integer"}))
        ),
        "an array element type change is red",
    )

    # The card_list envelope: the role the count/total defect lived in.
    renamed = _mutated("card_list", "count")
    renamed["$defs"]["card_list"]["properties"]["total"] = renamed["$defs"]["card_list"][
        "properties"
    ].pop("count")
    renamed["$defs"]["card_list"]["required"] = ["total", "cards"]
    t.req(
        any("total" in p for p in problems(renamed))
        and any("count" in p for p in problems(renamed)),
        "the count-vs-total defect is red (both the missing name and the invented one)",
    )

    # THE CARVE-OUT MUST NOT LEAK. On card_patch, null is dropped from both
    # sides - and nothing else is.
    t.req(
        problems(_mutated("card_patch", "title", type=["string", "null"])) == [],
        "card_patch: nullability is deliberately not compared (the stated carve-out)",
    )
    t.req(
        any(
            "card_patch.title: types differs" in p
            for p in problems(_mutated("card_patch", "title", type="integer"))
        ),
        "card_patch: a type change is still red under the carve-out",
    )
    patch_enum = _mutated("card_patch", "status", type="string")
    patch_enum["$defs"]["status"] = {"type": "string"}
    t.req(
        any("card_patch.status: enum differs" in p for p in problems(patch_enum)),
        "card_patch: an enum narrowing is still red under the carve-out",
    )
    patch_dropped = _mutated("card_patch", "title")
    del patch_dropped["$defs"]["card_patch"]["properties"]["status"]
    t.req(
        any(
            "card_patch.status" in p and "absent from the contract" in p
            for p in problems(patch_dropped)
        ),
        "card_patch: a field disappearing is still red under the carve-out",
    )

    # A role that vanishes from the contract must be red, not skipped. Dropping
    # `$defs.card` used to be the cheapest way to make a comparison pass.
    missing_role = _mutated("card", "card_key")
    del missing_role["$defs"]["card"]
    t.req(
        any(p.startswith("card: no `$defs.card`") for p in problems(missing_role)),
        "a role missing from the contract is red, not silently unchecked",
    )

    # And an EMPTY contract is red rather than vacuously clean. This is the
    # always-green shape the fleet keeps re-finding: a comparison that ran
    # against nothing and reported nothing wrong.
    t.req(problems({}) != [], "an empty contract compares nothing and must be red")
    t.req(problems({"$defs": {}}) != [], "a contract with no $defs must be red")

    # THE GATE'S OWN SCOPE, held against a constant subject (Factory#523's shape,
    # one repo along). Everything above mutates what is compared; this mutates
    # what the gate LOOKS at. Dropping a role from _ROLES used to remove it from
    # the gate's world with no trace but one fewer line in the report.
    kept = globals()["_ROLES"]
    globals()["_ROLES"] = tuple(r for r in kept if r[0] != "card_list")
    try:
        shrunk = problems(
            _SELFTEST_CONTRACT, {k: v for k, v in service.items() if k != "card_list"}
        )
        t.req(
            any("card_list" in p and "maps it to no model" in p for p in shrunk),
            "dropping a role from _ROLES must flag the now-unmapped `$def`, not go green",
        )
    finally:
        globals()["_ROLES"] = kept

    return t.finish()


def main(argv: list[str] | None = None) -> int:
    # The shared preamble, not a fourth copy of it: gate_argparser already wires
    # the RawDescription parser and --self-test that every watchdog here needs,
    # and hand-rolling it again is the paste the clone budget caught going in.
    parser = gate_argparser(__doc__)
    parser.add_argument("--root", help="path to the CFactory repo root")
    parser.add_argument(
        "--schema",
        default=str(_DEFAULT_SCHEMA),
        help="path to planning-card.schema.json (default: this checkout's)",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if not args.root:
        parser.error("--root is required (or pass --self-test)")
    return run_check(Path(args.schema), Path(args.root))


if __name__ == "__main__":
    sys.exit(main())
