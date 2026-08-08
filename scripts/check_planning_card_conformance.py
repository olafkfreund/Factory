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

AND ONE OBJECT-LEVEL KEYWORD: ``additionalProperties``, on the request bodies
only. This used to be recorded here as unreachable, and CFactory#322 is what made
it reachable. ``extra="forbid"`` is the one pydantic ``extra`` policy that
RENDERS into ``model_json_schema()``, as ``additionalProperties: false``, so once
``CardCreate``/``CardUpdate`` set it there is something on the service side to
compare the contract's assertion against. Not on the resource: there the keyword
is a statement about what the server EMITS, which is true and which pydantic
renders nothing for, so comparing it would be red forever for a promise the
service keeps.

``minProperties`` is still outside this gate, and this time permanently: pydantic
renders no such keyword for any ``extra`` policy or validator. CFactory enforces
it in ``CardUpdate.model_post_init`` and covers it with an over-the-wire test.
Named here so it is a known limit rather than a discovered one.

FOUR SUBJECTS, NOT ONE (CFactory#323). Everything above is the pydantic models.
CFactory states the same shape three more times by hand — ``openapi.yaml``, the
zod ``CardSchema`` in ``api.ts``, and the MCP board tools' input schemas — and
all three had drifted by the time the models stopped drifting. Those three are
compared on FIELD NAMES, in both directions, plus ``required`` on ``openapi.yaml``
where the keyword means the same thing; see the OTHER COPIES section below for why
names and not facets, and why the copies are measured rather than generated away.

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
    0 - every role's field set and facets agree, and all three hand-written
        copies name the same fields
    1 - the service and the contract disagree (or the self-test failed)
    2 - bad invocation: the schema, the service tree, the models, or any of the
        three copies could not be read. NEVER a silent pass — a check that cannot
        see its subject has to say so (Factory#500). In particular, a zod
        declaration this cannot locate is exit 2, not "no fields found", which
        would read as catastrophic drift.
"""

from __future__ import annotations

import importlib
import json
import re
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

# Roles on which the object-level `additionalProperties` IS compared. The request
# bodies, and only those, for a reason that is about what each object means
# rather than about convenience.
#
# On a REQUEST body `additionalProperties: false` is a server behaviour - an
# unknown key is refused - and pydantic renders exactly that keyword when the
# model sets `extra="forbid"`, so both sides can be read and compared. Until
# CFactory#322 the models set no `extra` policy at all, pydantic rendered
# nothing, and this comparison was impossible; that is why this gate's docstring
# recorded it as an unreachable limit rather than a missing feature.
#
# On the RESOURCE it is a statement about what the server EMITS, which is true
# (FastAPI serialises exactly the model's fields) and which pydantic renders
# nothing for, because `extra` governs input. Comparing it there would be red
# forever for a promise the service actually keeps.
#
# `minProperties` is still not compared anywhere: pydantic renders no such
# keyword for any `extra` policy or validator. CFactory enforces it in
# `CardUpdate.model_post_init` and covers it with an over-the-wire test, and the
# report below says so rather than letting a reader assume this gate has it.
_OBJECT_LEVEL_ROLES: tuple[str, ...] = ("card_create", "card_patch")

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


# --- the OTHER copies of the card shape (CFactory#323) ------------------------
#
# The comparison above closes the contract-vs-model gap. CFactory states the same
# shape THREE more times, by hand, and all three had drifted by the time the gate
# above landed:
#
#   openapi.yaml            `components.schemas.Card` declared 15 of the 22
#                           fields the service serves. Five of the seven missing
#                           ones the model marks REQUIRED, so the published API
#                           document described a card the service never returns.
#                           Its POST and PATCH bodies both `$ref`'d the RESOURCE,
#                           telling a client to send `tenant_id`, `created_at`
#                           and `updated_at` - which CFactory#322 now rejects.
#   api.ts (zod)            `CardSchema` had no `deleted_at` and no
#                           `github_sync_error`. `.passthrough()` means nothing
#                           breaks: the fields are parsed and thrown away. But
#                           `github_sync_error` is what makes a stale GitHub
#                           mirror legible, and the board cannot show what it
#                           does not model.
#   mcp.py `_CARD_FIELDS`   a fourth statement of which fields are WRITABLE,
#                           maintained beside CardCreate/CardUpdate.
#
# WHY EXTEND THIS GATE RATHER THAN ADD ANOTHER. All four subjects are statements
# of one shape, and the contract is the thing they are all supposed to agree
# with. Three separate checks would each have to re-derive the contract, and the
# fourth-copy problem is not solved by adding a fifth mechanism.
#
# WHY NOT DELETE THE COPIES INSTEAD, which is what CFactory#323 first proposed:
#
#   * openapi.yaml could be GENERATED from the FastAPI app. It is registered as a
#     Backstage API definition (`catalog-info.yaml`) and `techdocs/api.md` calls
#     it "curated" - most of its bulk is prose explaining WHY, which
#     `/openapi.json` does not carry and a generator cannot produce. Replacing it
#     with a generated file trades an accurate field list for a worse document.
#   * `_CARD_FIELDS` could be DERIVED from `CardCreate.model_json_schema()`. Its
#     value is its agent-facing descriptions - "RFC-0011 difficulty tier,
#     deciding which intake path builds it" - which pydantic does not carry
#     either. Deriving it would either lose them or need a description map, which
#     is the same copy under a new name.
#
# So they stay hand-written and are MEASURED instead.
#
# WHAT IS COMPARED: FIELD NAMES, in both directions, plus `required` on
# openapi.yaml where the keyword is the same keyword with the same meaning.
# Deliberately NOT the facets the model comparison reads. The three copies are
# written in three languages with three different vocabularies for the same idea
# - OpenAPI 3.0 `nullable: true`, zod `.nullish()`, a JSON Schema fragment for an
# MCP tool input - and reducing all three to comparable facets means
# re-implementing three type systems inside a gate. The drift that actually
# happened in all three is a field that is simply not there, and that is what
# this catches. Stated as a limit rather than discovered as one.

_OPENAPI = "openapi.yaml"
_ZOD_FILE = "apps/frontend-web/src/api.ts"
_MCP_MODULE = "cfactory.mcp"

# `components.schemas.<name>` for each role the document names. `card_list` is
# not a named schema - it is inline on the list route - so it is read by path.
_OPENAPI_SCHEMAS: tuple[tuple[str, str], ...] = (
    ("card", "Card"),
    ("card_create", "CardCreate"),
    ("card_patch", "CardUpdate"),
)
_OPENAPI_LIST_PATH: tuple[str, ...] = (
    "paths",
    "/api/cards",
    "get",
    "responses",
    "200",
    "content",
    "application/json",
    "schema",
)

# The MCP board tools that WRITE a card, and the role each one's arguments must
# be admissible against. `card_key` is dropped from the patch tools: it is the
# selector (the path segment over REST), not a body field, and `$defs.card_patch`
# rightly does not carry it because the key is immutable.
_MCP_TOOLS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("cfactory_create_card", "card_create", ()),
    ("cfactory_update_card", "card_patch", ("card_key",)),
    ("cfactory_move_card", "card_patch", ("card_key",)),
    ("cfactory_reprioritise_card", "card_patch", ("card_key",)),
)


def contract_properties(contract: dict[str, Any], role: str) -> set[str]:
    node = (contract.get("$defs") or {}).get(role) or {}
    return set(node.get("properties") or {})


def compare_names(
    where: str,
    role: str,
    want: set[str],
    got: set[str],
    *,
    subset: bool,
) -> list[str]:
    """Field-name disagreement between one copy and the contract.

    *subset* is one-directional on purpose and used only for the MCP tools: a
    tool that exposes FEWER fields than the model accepts is a deliberate
    product decision (``cfactory_move_card`` offers ``status`` and nothing else,
    so an agent's intent is legible in the call), not drift. A tool that offers
    a field the contract does not have is drift, and since CFactory#322 it is a
    422 at runtime - the arguments go straight into ``CardCreate``/``CardUpdate``
    and nothing validates them against the tool's own ``inputSchema`` first.
    """
    problems = [
        f"{where}: {role}.{name} is offered but the contract has no such field — "
        "under extra=forbid this is a rejected write, not a spare key"
        for name in sorted(got - want)
    ]
    if not subset:
        problems = [
            f"{where}: {role}.{name} is in the contract and missing from this copy — "
            "a consumer reading this file is told about a card the service does not serve"
            for name in sorted(want - got)
        ] + problems
    return problems


def openapi_copy(document: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    """`openapi.yaml` against the contract: names on four roles, plus `required`.

    `required` is compared here and nowhere else in this section because OpenAPI
    spells it the same way JSON Schema does and means the same thing by it. zod
    expresses optionality through `.nullish()`/`.default()` and an MCP tool
    through its own `required` list over a partial field set; neither reduces to
    the contract's notion cheaply, so neither is compared.
    """
    problems: list[str] = []
    schemas = ((document.get("components") or {}).get("schemas")) or {}
    roles = [
        (role, schemas.get(name), f"components.schemas.{name}") for role, name in _OPENAPI_SCHEMAS
    ]
    roles.append(("card_list", _walk(document, _OPENAPI_LIST_PATH), "GET /api/cards 200 body"))
    for role, node, label in roles:
        if not isinstance(node, dict) or "properties" not in node:
            problems.append(
                f"{_OPENAPI}: {label} is missing or declares no properties, so "
                f"`$defs.{role}` is documented nowhere — add it rather than "
                "letting the document describe three of the four roles"
            )
            continue
        want = contract_properties(contract, role)
        problems.extend(compare_names(_OPENAPI, role, want, set(node["properties"]), subset=False))
        want_required = set((contract.get("$defs") or {}).get(role, {}).get("required") or ())
        got_required = set(node.get("required") or ())
        if want_required != got_required:
            problems.append(
                f"{_OPENAPI}: {role} required differs — contract "
                f"{sorted(want_required)}, document {sorted(got_required)}"
            )
    return problems


def _walk(document: dict[str, Any], path: tuple[str, ...]) -> Any:
    node: Any = document
    for step in path:
        if not isinstance(node, dict):
            return None
        # YAML reads an unquoted `200:` as an int; the file quotes it, but a
        # future edit that does not must not silently take this branch to None.
        node = node.get(step, node.get(int(step)) if step.isdigit() else None)
    return node


# `export const CardSchema = z\n  .object({ ... \n  })`. A regex over a
# hand-written literal, which is unlovely and is the honest cost of the zod
# schema staying hand-written: it is a runtime PARSER, so it genuinely does
# something a generated type would not, and there is no way to ask TypeScript
# what it declares without running TypeScript. Failure to match is exit 2, never
# a pass - see `zod_copy`.
_ZOD_BLOCK = re.compile(r"export const CardSchema = z\s*\n\s*\.object\(\{\n(.*?)\n  \}\)", re.S)
_ZOD_KEY = re.compile(r"^    ([A-Za-z_]\w*):", re.M)


def zod_field_names(source: str) -> set[str] | None:
    """Top-level keys of `CardSchema`, or None if the block could not be found."""
    block = _ZOD_BLOCK.search(source)
    if block is None:
        return None
    return set(_ZOD_KEY.findall(block.group(1)))


def zod_copy(names: set[str], contract: dict[str, Any]) -> list[str]:
    return compare_names(
        _ZOD_FILE, "card", contract_properties(contract, "card"), names, subset=False
    )


def mcp_copy(tools: list[dict[str, Any]], contract: dict[str, Any]) -> list[str]:
    """The MCP card-write tools against the contract's write roles."""
    by_name = {tool.get("name"): tool for tool in tools}
    problems: list[str] = []
    for tool_name, role, selectors in _MCP_TOOLS:
        tool = by_name.get(tool_name)
        if tool is None:
            problems.append(
                f"{_MCP_MODULE}: no tool named {tool_name} — it was renamed or "
                "removed, and a tool this gate cannot find is a tool it is not "
                "checking; update _MCP_TOOLS deliberately"
            )
            continue
        offered = set((tool.get("inputSchema") or {}).get("properties") or {}) - set(selectors)
        problems.extend(
            compare_names(
                f"{_MCP_MODULE}.{tool_name}",
                role,
                contract_properties(contract, role),
                offered,
                subset=True,
            )
        )
    return problems


def load_copies(root: Path) -> tuple[dict[str, Any], set[str], list[dict[str, Any]]]:
    """Read all three copies. Raises rather than returning a partial answer.

    Every failure here is exit 2 at the call site, not a pass: a file that could
    not be parsed has been compared against nothing, and "I could not look" is
    not "nothing is wrong" (Factory#500).
    """
    import yaml  # noqa: PLC0415 — only this half of the gate needs it

    document = yaml.safe_load((root / _OPENAPI).read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{_OPENAPI} did not parse to a mapping")

    names = zod_field_names((root / _ZOD_FILE).read_text(encoding="utf-8"))
    if not names:
        raise ValueError(
            f"{_ZOD_FILE}: could not find the `export const CardSchema = z.object({{...}})` "
            "block, or it parsed to no fields — the declaration moved or was reformatted, "
            "and this gate will not report agreement it did not measure"
        )

    module = importlib.import_module(_MCP_MODULE)
    tools = getattr(module, "BOARD_TOOLS", None)
    if not isinstance(tools, list) or not tools:
        raise ValueError(f"{_MCP_MODULE}.BOARD_TOOLS is missing or empty")
    return document, names, tools


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
            if role in _OBJECT_LEVEL_ROLES:
                want = node.get("additionalProperties")
                got = service[role].get("additionalProperties")
                if want != got:
                    problems.append(
                        f"{role}: additionalProperties differs — contract {want!r}, "
                        f"service {got!r}. `false` on the service side is pydantic's "
                        'rendering of `model_config = ConfigDict(extra="forbid")`; its '
                        "absence means an unknown key is silently DISCARDED, which "
                        "tells a caller its write landed in full when part of it did "
                        "not (CFactory#322)"
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
    try:
        document, zod_names, tools = load_copies(root)
    except (OSError, ImportError, AttributeError, ValueError) as exc:
        _emit(f"ERROR: could not read the hand-written copies under {root}: {exc}")
        return _EXIT_BAD_INVOCATION
    problems = check(contract, service)
    problems.extend(openapi_copy(document, contract))
    problems.extend(zod_copy(zod_names, contract))
    problems.extend(mcp_copy(tools, contract))

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
    _emit("  and the three OTHER hand-written statements of the same shape (CFactory#323):")
    _emit(
        f"    - {_OPENAPI} [{digest(root / _OPENAPI)}]: "
        + ", ".join(f"{name} <-> $defs.{role}" for role, name in _OPENAPI_SCHEMAS)
        + ", GET /api/cards 200 body <-> $defs.card_list"
    )
    _emit(
        f"    - {_ZOD_FILE} [{digest(root / _ZOD_FILE)}]: "
        f"CardSchema <-> $defs.card: {', '.join(sorted(zod_names))}"
    )
    _emit(
        f"    - {_MCP_MODULE}.BOARD_TOOLS: "
        + ", ".join(f"{tool} <-> $defs.{role}" for tool, role, _sel in _MCP_TOOLS)
    )
    _emit(
        "  on those three, FIELD NAMES only (both directions), plus `required` on "
        f"{_OPENAPI} where the keyword is the same keyword. Facets are not compared: "
        "three languages, three vocabularies for nullability, and the drift that "
        "happened in all three was a field that was simply not there. The MCP tools "
        "are compared one-directionally - offering FEWER fields than the model "
        "accepts is a deliberate tool split, offering MORE is a 422."
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
            "additionalProperties": False,
            "properties": {"title": {"type": "string", "maxLength": 512}},
        },
        "card_patch": {
            "type": "object",
            "additionalProperties": False,
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

    from pydantic import BaseModel, ConfigDict, Field  # noqa: PLC0415

    class Card(BaseModel):
        card_key: str
        status: Literal["backlog", "done"]
        tier: Literal["low", "hard"] | None = None
        labels: list[str] = Field(default_factory=list)
        comment_count: int = 0

    class CardCreate(BaseModel):
        model_config = ConfigDict(extra="forbid")
        title: str = Field(max_length=512)

    class CardUpdate(BaseModel):
        model_config = ConfigDict(extra="forbid")
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

    _self_test_object_level(t, service)

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

    _self_test_copies(t)
    return t.finish()


def _self_test_object_level(t: SelfTest, service: dict[str, dict[str, Any]]) -> None:
    """`additionalProperties`, which only became comparable with CFactory#322."""
    import copy as copy_module  # noqa: PLC0415 - kept out of the gate's import path

    def problems(
        contract: dict[str, Any], svc: dict[str, dict[str, Any]] | None = None
    ) -> list[str]:
        return check(contract, svc if svc is not None else service)

    # OBJECT-LEVEL, on the request bodies. Until CFactory#322 the models set no
    # `extra` policy, pydantic rendered no `additionalProperties`, and this was a
    # limit this gate documented rather than a check it ran.
    for role in _OBJECT_LEVEL_ROLES:
        loosened = copy_module.deepcopy(_SELFTEST_CONTRACT)
        del loosened["$defs"][role]["additionalProperties"]
        t.req(
            any(f"{role}: additionalProperties differs" in p for p in problems(loosened)),
            f"{role}: a contract that stops forbidding extras while the model forbids them is red",
        )
        dropped_policy = dict(service)
        dropped_policy[role] = {
            k: v for k, v in service[role].items() if k != "additionalProperties"
        }
        t.req(
            any(
                f"{role}: additionalProperties differs" in p
                for p in problems(_SELFTEST_CONTRACT, dropped_policy)
            ),
            f'{role}: dropping extra="forbid" from the model is red (the CFactory#322 regression)',
        )
    # And it is NOT compared on the resource, where pydantic renders nothing for
    # a promise the service does keep. Asserted, so narrowing this to the request
    # bodies is a decision rather than an omission.
    resource_forbids = copy_module.deepcopy(_SELFTEST_CONTRACT)
    resource_forbids["$defs"]["card"]["additionalProperties"] = False
    t.req(
        problems(resource_forbids) == [],
        "the resource's additionalProperties is deliberately not compared",
    )


# The three other copies, mutated one at a time (CFactory#323). Synthetic
# subjects, so no CFactory checkout is needed: an openapi document as a dict, a
# zod declaration as a string, and a tool list as a list — which is exactly the
# shape each loader hands the comparison, so what runs here is what runs in CI.

_SELFTEST_OPENAPI: dict[str, Any] = {
    "components": {
        "schemas": {
            "Card": {
                "type": "object",
                "required": ["card_key", "status"],
                "properties": {
                    "card_key": {"type": "string"},
                    "status": {"type": "string"},
                    "tier": {"type": "string", "nullable": True},
                    "labels": {"type": "array"},
                    "comment_count": {"type": "integer"},
                },
            },
            "CardCreate": {"type": "object", "required": ["title"], "properties": {"title": {}}},
            "CardUpdate": {
                "type": "object",
                "properties": {"title": {}, "status": {}},
            },
        }
    },
    "paths": {
        "/api/cards": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["count", "cards"],
                                    "properties": {"count": {}, "cards": {}},
                                }
                            }
                        }
                    }
                }
            }
        }
    },
}

_SELFTEST_ZOD = """
export const CardSchema = z
  .object({
    card_key: z.string(),
    status: CardStatusSchema,
    tier: CardTierSchema.nullable(),
    labels: z.array(z.string()).default([]),
    // a comment, and a blank line, both of which the real file has
    comment_count: z.number().default(0),
  })
  .passthrough();
"""

_SELFTEST_TOOLS: list[dict[str, Any]] = [
    {
        "name": "cfactory_create_card",
        "inputSchema": {"type": "object", "properties": {"title": {}}},
    },
    {
        "name": "cfactory_update_card",
        "inputSchema": {"type": "object", "properties": {"card_key": {}, "title": {}}},
    },
    {
        "name": "cfactory_move_card",
        "inputSchema": {"type": "object", "properties": {"card_key": {}, "status": {}}},
    },
    {
        "name": "cfactory_reprioritise_card",
        "inputSchema": {"type": "object", "properties": {"card_key": {}}},
    },
]


def _self_test_copies(t: SelfTest) -> None:
    import copy  # noqa: PLC0415

    contract = _SELFTEST_CONTRACT

    def all_three(
        document: dict[str, Any] | None = None,
        zod: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        names = zod_field_names(_SELFTEST_ZOD if zod is None else zod) or set()
        return (
            openapi_copy(_SELFTEST_OPENAPI if document is None else document, contract)
            + zod_copy(names, contract)
            + mcp_copy(_SELFTEST_TOOLS if tools is None else tools, contract)
        )

    t.req(all_three() == [], "baseline: all three copies agree with the contract")

    # 1. openapi.yaml — a field the service serves and the document omits. This
    #    is the real defect, seven times over.
    doc = copy.deepcopy(_SELFTEST_OPENAPI)
    del doc["components"]["schemas"]["Card"]["properties"]["labels"]
    t.req(
        any(
            _OPENAPI in p and "card.labels" in p and "missing from this copy" in p
            for p in all_three(document=doc)
        ),
        "openapi.yaml: a field dropped from components.schemas.Card is red",
    )
    doc = copy.deepcopy(_SELFTEST_OPENAPI)
    doc["components"]["schemas"]["Card"]["required"] = ["card_key"]
    t.req(
        any(_OPENAPI in p and "card required differs" in p for p in all_three(document=doc)),
        "openapi.yaml: a field the service always sends and the document calls optional is red",
    )
    doc = copy.deepcopy(_SELFTEST_OPENAPI)
    doc["paths"]["/api/cards"]["get"]["responses"]["200"]["content"]["application/json"]["schema"][
        "properties"
    ] = {"total": {}, "cards": {}}
    t.req(
        any("total" in p for p in all_three(document=doc))
        and any("count" in p for p in all_three(document=doc)),
        "openapi.yaml: the count-vs-total defect is red on the inline list body too",
    )
    doc = copy.deepcopy(_SELFTEST_OPENAPI)
    del doc["components"]["schemas"]["CardCreate"]
    t.req(
        any("documented nowhere" in p for p in all_three(document=doc)),
        "openapi.yaml: a role the document does not describe at all is red, not skipped",
    )

    # 2. api.ts (zod) — the two fields it was actually missing.
    zod = _SELFTEST_ZOD.replace("    labels: z.array(z.string()).default([]),\n", "")
    t.req(
        any(
            _ZOD_FILE in p and "card.labels" in p and "missing from this copy" in p
            for p in all_three(zod=zod)
        ),
        "api.ts: a field the board does not model is red (the deleted_at/github_sync_error case)",
    )
    zod = _SELFTEST_ZOD.replace(
        "    card_key: z.string(),", "    card_key: z.string(),\n    workspace_id: z.string(),"
    )
    t.req(
        any(_ZOD_FILE in p and "workspace_id" in p for p in all_three(zod=zod)),
        "api.ts: a field the contract does not have is red too (both directions)",
    )
    # And the extractor must FAIL rather than report an empty field set, which
    # would make every contract field "missing" and read as catastrophic drift
    # when the truth is that the gate lost its subject.
    t.req(
        zod_field_names("export const CardSchema = somethingElse();") is None,
        "api.ts: a moved or reformatted declaration returns None, so the loader can exit 2",
    )

    # 3. mcp.py — a writable field the models do not have. Since CFactory#322
    #    that is a 422 at runtime, not a spare key.
    tools = copy.deepcopy(_SELFTEST_TOOLS)
    tools[0]["inputSchema"]["properties"]["tenant_id"] = {}
    t.req(
        any("cfactory_create_card" in p and "tenant_id" in p for p in all_three(tools=tools)),
        "mcp.py: a tool argument the contract has no field for is red",
    )
    # The other direction, asserted GREEN on purpose: cfactory_move_card offers
    # `status` and nothing else, and that is the product decision, not drift.
    t.req(
        all_three(tools=_SELFTEST_TOOLS) == [],
        "mcp.py: a tool offering FEWER fields than the model accepts stays green",
    )
    tools = [tool for tool in _SELFTEST_TOOLS if tool["name"] != "cfactory_move_card"]
    t.req(
        any("no tool named cfactory_move_card" in p for p in all_three(tools=tools)),
        "mcp.py: a renamed or removed tool is red, not silently unchecked",
    )


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
