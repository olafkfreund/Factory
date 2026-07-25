# Factory Planning Card (RFC-0019 Phase 1)

> Normative contract for the CFactory planning-board card resource served at
> `/api/cards`. Implements
> [RFC-0019](../docs/rfc/0019-agent-native-planning-control-plane.md) section 3.1
> (issue #302). Machine-readable schema:
> [`planning-card.schema.json`](./planning-card.schema.json).
> Reference instances: [`examples/planning-cards/`](./examples/planning-cards/).

CFactory today is a read-only cockpit over `work_items`: it threads what the
factory *did*. It has nowhere to say what should be done *next*. A card is that
missing resource - the human-owned, editable unit of planned work - and Phase 1
is the data model plus its read/write REST surface.

The card is not a new source of truth for delivery. GitHub still holds the issues
and PRs (RFC-0019 section 3.5), and `work_items` still holds the runtime
timeline. The board is where humans plan; the card joins to everything else by
one nullable field.

## 1. Cards are a separate table from work_items

This is the design law of Phase 1, and the one place a shortcut costs real data.

`work_items` is a **correlation store**. CFactory re-materialises it from
upstream completion events: `store.py`'s reconcile pass rebuilds rows from what
the four services report, and its prune pass drops rows the upstreams no longer
account for. That is correct behaviour for a projection of runtime state, and it
is fatal for a plan. A card carries fields no completion event has ever heard of
- title, acceptance criteria, priority, milestone, assignee, board status - and a
reconcile would overwrite them with nothing while a prune would delete a card
that has not entered the factory yet, which is *every card on the backlog*.

So:

- Cards live in their **own table**, written only by the card API.
- Reconcile and prune **never touch it**. They keep operating on `work_items`
  exactly as they do today.
- Where the two overlap - a card that is in flight - the human-owned fields on
  the card win over a reconcile, per RFC-0019 section 7.

### correlation_key is the join

```
card (planned)                  card (in the factory)
  correlation_key: null   --->    correlation_key: "302"  ---> work_items row "302"
                                                               (RFC-0001 timeline,
                                                                events, VAL verdict)
```

- **NULL** for as long as the card is only planned. Most of the backlog is NULL,
  permanently, and that is not a defect.
- **Set once**, when the card enters the factory: the dispatcher writes the
  RFC-0001 correlation key (the GitHub issue number as a string, or a synthetic
  `<prefix>-<id>` fallback) onto the card.
- **Write-once.** A server MUST reject an attempt to repoint an already-joined
  card at a different key. A card is one unit of work; repointing it silently
  reattributes its history to another one.
- A consumer that wants the runtime timeline for a card follows this key into
  the existing work-item routes. The card never duplicates timeline state - if
  the board needed to store what the factory is doing, it would be a second
  source of truth, which is exactly what section 3.5 forbids.

## 2. The resource

| Field | Type | Owner | Meaning |
|---|---|---|---|
| `card_key` | string `FCT-N` | server | Stable, immutable id; the path segment of every single-card route |
| `tenant_id` | string | server | Owning tenant, derived from the credential - never from a body |
| `title` | string | human | One line: what is to be done |
| `acceptance_criteria` | string[] | human | What `done` means, one testable statement per entry |
| `status` | enum | human or runtime | `backlog` / `ready` / `in_progress` / `blocked` / `done` |
| `priority` | integer | human | Backlog order, **lower is higher** |
| `tier` | enum or null | human or classifier | RFC-0011 `low` / `medium` / `hard` |
| `assignee` | string or null | human | A person, or a factory runtime once in flight |
| `milestone` | string or null | human | Free-form milestone name |
| `correlation_key` | string or null | dispatcher | RFC-0001 join to `work_items`; see section 1 |
| `created_at` / `updated_at` | date-time | server | Set on create; `updated_at` rewritten on every accepted mutation |

**Every field is always present in a response.** The nullable ones carry an
explicit `null` rather than being omitted, so a consumer never has to
distinguish "not set" from "not sent by this version of the server".

### card_key

`FCT-42`, from a per-tenant sequence. Immutable once issued: humans quote it in
commit messages and agents keep it, so a rename breaks every reference held
outside the database. This settles the RFC-0019 open question for Phase 1 - one
sequence per tenant with a fixed `FCT-` prefix, no workspace or board segment,
because Phase 1 ships a flat backlog and a scheme with room for a hierarchy that
does not exist yet is a scheme that will be wrong when it does.

It is **not** the correlation key. `FCT-42` identifies the plan; the correlation
key identifies the work, and only exists once there is work.

### status

Five columns, no more. `ready` is the one with behaviour attached: a `ready` card
**with a tier** is a first-class intake source alongside a labelled GitHub issue
(RFC-0019 section 3.2), so moving a card to `ready` is what dispatches it. A
`ready` card with a NULL tier is not dispatched - it sits visible on the board
until someone or something classifies it, which is a better failure than guessing
a tier and routing a rewrite through a cheap model.

**Do not classify a card status through
[`status-taxonomy.json`](./status-taxonomy.json).** That taxonomy normalises the
four services' *runtime* statuses, and two of its token sets collide with this
vocabulary head-on: `ready` is a `done` token there, and `blocked` is a `failed`
token. Fed through it, a card waiting to be picked up reads as finished and a
card a human deliberately parked reads as a failure. Card statuses are a closed
enum owned by this contract; the taxonomy applies to what the *services* report
against the joined work item.

### priority

An integer, lower first, ties legal. Not an enum, so a card can be dropped
between two others without renumbering the column. The server orders by
`(priority ASC, created_at ASC, card_key ASC)` so two identical requests return
the same order. Omitted on create, it defaults to `100`, which leaves room to
insert both above and below without touching anything else.

### tier

The RFC-0011 vocabulary, unchanged: `low`, `medium`, `hard` - `hard`, never
`high`. Same values as the `factory:<tier>` labels and as
`execution.autonomy_tier` in the RFC-0002 task contract, because the tier the
human puts on the card is the tier that drives model, planning depth, human gate,
VAL floor and merge behaviour once it dispatches. NULL means unclassified.

## 3. REST surface

| Method | Path | Body | Returns |
|---|---|---|---|
| `GET` | `/api/cards` | - | `$defs.card_list` |
| `POST` | `/api/cards` | `$defs.card_create` | the created card, `201` |
| `GET` | `/api/cards/{card_key}` | - | one card |
| `PATCH` | `/api/cards/{card_key}` | `$defs.card_patch` | the updated card |
| `DELETE` | `/api/cards/{card_key}` | - | `204` |

**Filters** on `GET /api/cards`: `status`, `milestone`, `assignee`, `tier`.
Repeated or comma-joined values are ANDed across fields and ORed within one. An
unknown filter value is an empty result, not an error - a board view that asks
for a tier nobody has used yet is a legitimate question.

The list response is an envelope (`{"cards": [...], "total": N}`) rather than a
bare array, so pagination and echoed filters can be added additively. Until
pagination exists, `total` equals `len(cards)`.

**One route moves and reprioritises.** `PATCH` accepts any mutable field, so
dragging a card to another column is `{"status": "in_progress"}` and
reprioritising is `{"priority": 15}` - the same call, no `/move` or `/reorder`
endpoints. This is what makes RFC-0019 section 3.3 (programmatic equivalence)
cheap to keep true: there is no cockpit gesture that needs an API surface of its
own.

**Server-owned fields are rejected, not ignored.** `card_key`, `tenant_id`,
`created_at` and `updated_at` are absent from the create and patch schemas, and
both set `additionalProperties: false`. A client that sends `"tenant_id":
"someone-else"` gets a `400`, not a silently dropped field - a body that appears
to be accepted while part of it is discarded is how a caller comes to believe
something it did was applied.

`POST` does not accept `correlation_key` either. A card is created as a plan; the
join is made later, by whatever dispatches it, over `PATCH`.

`DELETE` removes the card and nothing else. If the card was joined, the
`work_items` row and its timeline survive - the plan is deleted, the record of
what the factory did is not.

## 4. Tenant scoping

Every route is scoped to the tenant on the calling credential, reusing the
existing CFactory auth (`CFACTORY_API_KEYS`, scoped tokens, `CFACTORY_MULTI_TENANT`).

- **Reads** return only that tenant's cards. `GET /api/cards` filters by tenant
  before it filters by anything a caller asked for.
- **Writes** require a scoped-write credential (RFC-0019 section 7: board
  mutations widen the cockpit's attack surface, so they are not covered by a
  read token).
- `tenant_id` is **derived, never accepted**. It appears in responses so a
  consumer can assert what it is reading; it appears in no request schema.
- A `card_key` belonging to another tenant is a `404`, not a `403`. `FCT-42`
  exists in every tenant that has 42 cards, and answering "wrong tenant" would
  confirm the existence of a card the caller may not know about.

## 5. Every mutation is audit-chained

`POST`, `PATCH` and `DELETE` each append an entry to CFactory's tamper-evident
audit chain (`CFACTORY_AUDIT_HMAC_SECRET`, the RFC-0001a chain), before the
response is returned. The entry records the actor (which credential, human or
agent), the `card_key`, the operation, and the changed fields with their before
and after values.

This is not decoration. The board is the point where a human intent enters the
factory, and the same REST surface is used by autonomous agents (RFC-0019 section
3.3). "Who moved this card to `ready` and set it to `hard` at 03:00" must be
answerable afterwards, and it can only be answered if the mutation was chained at
the time. Reads are not chained; nothing about reading a backlog needs proving.

## 6. Versioning

The schema is additive. New optional fields keep the shape; **consumers MUST
ignore unknown fields**. Removing a field, or adding a value to the `status` or
`tier` enum, is breaking: a `status` a client has no column for is worse than an
error, because the card silently vanishes from every view. Either change needs a
new contract version here first.

## 7. Non-goals

- **No custom-fields engine, no time tracking, no Gantt** (RFC-0019 section 4).
  The field list above is the whole card.
- **No workspace or board hierarchy in Phase 1.** Cards are a flat, tenant-scoped
  backlog. The hierarchy in RFC-0019 section 3.1 arrives when there is a second
  board to justify it.
- **No timeline on the card.** Runtime state stays on the work item; follow
  `correlation_key`.
- **No GitHub mirroring yet.** That is Phase 6, and it is what `milestone` holds
  a title rather than an id for.

## 8. Related

- [RFC-0019](../docs/rfc/0019-agent-native-planning-control-plane.md) - the
  agent-native planning control plane (this is section 3.1, phase 1).
- [RFC-0001](../docs/rfc/0001-correlation-key-and-completion-event.md) - the
  correlation key `correlation_key` holds.
- [RFC-0011](../docs/rfc/0011-label-driven-intake-and-difficulty-tiers.md) - the
  difficulty tiers `tier` reuses.
- [RFC-0002](../docs/rfc/0002-task-contract.md) - the task contract a dispatched
  card's acceptance criteria and tier flow into.
- [`status-taxonomy.json`](./status-taxonomy.json) - the runtime status taxonomy
  that card statuses are deliberately NOT read through (section 2).
- [`agent-skills-manifest.md`](./agent-skills-manifest.md) - RFC-0019 phase 4,
  the discovery manifest that will advertise these card skills.
