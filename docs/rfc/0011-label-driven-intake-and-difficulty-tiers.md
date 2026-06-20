---
layout: default
title: "RFC-0011: Label-Driven Intake & Difficulty Tiers"
permalink: /rfc/label-driven-intake/
---

# RFC-0011 — Label-Driven Intake & Difficulty Tiers across the Fleet

> **Status:** Implemented (epic #123 — tiers classifier, poller, /from-issue, tier_profile/tier_floor, autonomy_tier, merge_policy) · **Created:** 2026-06-20 · **Updated:** 2026-06-20 · **Extends:** [RFC-0002](./0002-task-contract.md) (task contract), [RFC-0006](./0006-verification-assurance-levels.md) (assurance levels), [RFC-0009](./0009-ci-gated-auto-merge.md) (CI-gated auto-merge), [RFC-0010](./0010-code-aware-planning-and-behavioral-equivalence.md) (code-aware planning + equivalence) · **Affects:** PFactory, AIFactory, TFactory, CFactory
>
> Create an issue or work-item, label it `factory:low | factory:medium | factory:hard`, and the fleet picks it up, classifies its difficulty, routes it through PARR (plan → code → test → observe), and delivers a review-ready, correct result — uniformly across **GitHub, GitLab, and Azure DevOps**. The difficulty tier is the single knob that drives **model, planning depth, human gate, verification floor, and merge behaviour**. Rewrites and hard implementation/testing get the heaviest treatment.

## 1. The goal — "label it and the fleet runs it, honestly"

Today work enters the fleet ad hoc. A handful of GitHub-Actions-on-label
workflows (`pfactory:run` / `aifactory:run` / `tfactory:run`) POST to each
factory; GitLab and Azure DevOps have no intake path at all; and difficulty and
model are inferred *after* a build rather than declared up front. This RFC makes
intake **uniform, declarative, and idempotent**:

1. A human (or another system) opens an issue/work-item and applies one
   difficulty label.
2. A provider-agnostic **poller** reads new labelled items across every host
   behind one abstraction, classifies the tier, and routes it through PARR.
3. The tier deterministically selects the routing policy in §3, so the same
   label produces the same treatment on every host, every time.

This is deliberately **composition over invention**: most of the machinery —
the label classifier, the GitLab/ADO providers behind a `GitProvider` protocol,
the contract's tier fields, the VAL ladder (RFC-0006), the correlation key
(RFC-0001), evidence gates (RFC-0001a), and migration/equivalence
(RFC-0010) — already exists. This RFC adds a thin intake layer and, above all,
a **standard**.

## 2. The taxonomy

Labels are the user-facing contract. Three difficulty labels drive routing; two
lifecycle labels make intake idempotent and observable; the existing
governance/routing and descriptive labels are carried through unchanged.

| Label | Role | Meaning |
|---|---|---|
| `factory:low` | difficulty | Cheap, fast, unattended. Local model, no planning, auto-merge when green. |
| `factory:medium` | difficulty | Standard. A capable hosted model, light planning, async human approval. |
| `factory:hard` | difficulty | Heavy. Frontier model, full PFactory decomposition, blocking human approval, deepest verification. |
| `factory:queued` | lifecycle | Applied by the poller the instant an item is accepted. The idempotency marker. |
| `factory:failed` | lifecycle | Applied on a **terminal** intake/routing failure. The item is never silently dropped. |

Carried-through (unchanged by this RFC):

- **Governance / routing:** `pfactory`, `handoff:aifactory`, `handoff:tfactory`,
  `epic`.
- **Descriptive:** `type:*` (e.g. `type:feature`, `type:bugfix`),
  `plan-type:*`, `priority:*`. These are passed through to the contract and
  surface in the cockpit; they do **not** change tier routing.

The difficulty labels live in `.github/labels.yml` (the canonical set) and are
synced to every host (§7).

## 3. Tier routing policy (normative)

The tier is the single input that selects every downstream decision. This table
is normative — each per-repo module asserts against exactly this mapping (see
the E2E harness, `scripts/verify_rfc0011_e2e.py`).

| Tier | model | planning | human gate (`review_tier`) | VAL floor (RFC-0006) | TFactory lanes | merge |
|---|---|---|---|---|---|---|
| **factory:low** | `ollama:<m>` → `haiku` fallback | skip | none (`auto`) | VAL-1 | unit (+api) | auto-merge when green + VAL ≥ floor + `ci_parity=yes` |
| **factory:medium** | `sonnet` | skip (lite) | async approval (`async`) | VAL-2 | unit, api, integration | merge after async approval |
| **factory:hard** | `opus` | **PFactory full decompose** | blocking (`blocking`) | VAL-3 (+ equivalence if rewrite) | unit, api, integration, mutation (+ equivalence) | blocking approval, then merge |

Notes:

- **Model.** `low` probes a local Ollama daemon and uses it when reachable,
  falling back to `haiku` otherwise; `medium` uses `sonnet`; `hard` uses `opus`.
  The provider is inferred from the model id by the existing phase-config
  routing, so both `ollama:*` and `haiku`/`sonnet`/`opus` resolve without
  special-casing.
- **Planning.** `low` and `medium` take the trusted-plan fast path (skip /
  skip-lite) into AIFactory; `hard` goes through PFactory's full decomposition
  (epic + children + signed contract) before any code is written.
- **Human gate** maps directly to the contract's `execution.review_tier`
  (`auto` / `async` / `blocking`), which the RFC-0009 merge policy reads.
- **VAL floor** is the RFC-0006 assurance level the change must reach before it
  may merge. A `hard` **rewrite** additionally requires the equivalence lane
  (RFC-0010): the new implementation must be proven behaviourally equivalent to
  the old one.
- **Merge** composes RFC-0009: nothing merges on red; nothing merges below its
  VAL floor; `low` auto-merges only when green **and** `ci_parity=yes` (no fake
  green).

### Precedence and migration

- **Precedence is highest-wins:** if an item carries more than one difficulty
  label (e.g. both `factory:low` and `factory:hard`), the **hardest** tier
  applies (`hard` > `medium` > `low`). This makes the system fail safe — an
  ambiguous item is treated more carefully, never less.
- **A rewrite forces hard.** When the change is a migration —
  `change_mode == migration` in the contract (RFC-0010), e.g. a
  Python→Rust port — the tier is forced to `hard` regardless of the applied
  label, and the equivalence lane is required. A rewrite is never run cheap.

The classifier is **scoped-label tolerant**: it recognises the
`factory:<tier>` form and ignores unrelated labels.

## 4. The autonomy_tier contract field

The tier is carried into the task contract (RFC-0002) as an additive,
back-compatible field, so every downstream service reads the same value rather
than re-deriving it:

```json
"execution": {
  "autonomy_tier": "low | medium | hard",
  "review_tier":   "auto | async | blocking",
  "model":         "ollama:... | haiku | sonnet | opus",
  "skip_planning": true,
  "change_mode":   "create | modify | migration"
}
```

`execution.autonomy_tier` is already merged into
`apis/task-contract.schema.json`. Semantics:

- Set from the difficulty label at intake (after precedence + migration are
  applied).
- Drives `model`, `skip_planning`, `review_tier`, the TFactory `lanes` /
  `equivalence` block, and the VAL floor — i.e. the whole §3 row.
- **Absent ⇒ derived from `complexity`** (back-compat). Existing contracts that
  predate RFC-0011 continue to route exactly as before.

PFactory's emitter writes `autonomy_tier` from the classified tier; AIFactory's
fast path builds the `execution` block inline for `low`/`medium`; TFactory reads
it to select the VAL floor and lane rigor; the RFC-0009 merge policy reads it
(with `review_tier`) to decide auto / hold-async / hold-blocking.

## 5. How it composes the rest of the stack

RFC-0011 is the intake and routing layer; it delegates the actual work to RFCs
already in place:

- **RFC-0002 (task contract).** The tier is expressed as
  `execution.autonomy_tier` and fans out to the existing
  `execution.{model, skip_planning, review_tier}` and `tfactory.{lanes,
  equivalence}` fields. No new contract shape — one new field.
- **RFC-0006 (verification assurance levels).** Each tier sets a **VAL floor**.
  TFactory's quality gate enforces the floor; the merge policy refuses to merge
  below it. The honesty rule from RFC-0006 stands: an over-claimed level is
  downgraded by `scripts/verification_gate.py`, never trusted.
- **RFC-0009 (CI-gated auto-merge).** The merge column of §3 *is* the RFC-0009
  policy, parameterised by tier: `low` opts into native auto-merge-when-green;
  `medium` holds for async approval; `hard` holds for blocking approval. Every
  tier still requires all host checks green + the `TFactory / tests` check +
  the VAL floor.
- **RFC-0010 (code-aware planning + equivalence).** A `hard` rewrite reuses
  RFC-0010's migration detection and equivalence lane. `change_mode=migration`
  forces `hard` (§3) and requires equivalence proof before merge.

Pipeline view:

```
issue/work-item + factory:<tier>
   → poller (provider-agnostic reader; factory:queued on accept)
      ├── low / medium → AIFactory governed ingest (skip / skip-lite plan, RFC-0002 fast path)
      └── hard         → PFactory full decompose → human approve → emit contract
   → AIFactory build → open PR/MR
   → host CI + TFactory lanes (VAL floor by tier; +equivalence for a rewrite)
   → RFC-0009 merge policy (auto | hold-async | hold-blocking by tier)
   → CFactory threads PLAN→CODE→TEST→MERGED by issue number (RFC-0001)
```

## 6. The cross-tracker contract

The whole point is uniformity across hosts. The standard is:

- **Same labels everywhere.** The identical `factory:low|medium|hard`,
  `factory:queued`, and `factory:failed` labels exist on GitHub, GitLab, and
  Azure DevOps. They are created and kept in sync from the single canonical
  `.github/labels.yml` (GitHub via a label-sync action; GitLab and ADO via
  `scripts/sync_labels.py` using the `GitProvider.create_label` abstraction).
- **The poller is the uniform reader.** One service reads new labelled items
  through the `GitProvider` protocol (`fetch_issues(IssueFilters(labels, since))`),
  so GitHub issues, GitLab issues, and ADO work-items are all consumed the same
  way. Host-specific quirks live behind the provider, never in the orchestrator.
  Hosts that lack a primitive degrade explicitly, never silently (carried from
  RFC-0009).
- **`factory:queued` is the idempotency key.** When the poller accepts an item
  it (a) records the item in a durable processed-table (`INSERT OR IGNORE`,
  outbox-style) **and** (b) applies the `factory:queued` label; subsequent
  fetches exclude already-queued items. The two guards are belt-and-braces:
  polling the same item twice, killing the poller mid-tick, or deleting the
  local DB still results in **exactly one** downstream submission. A terminal
  failure applies `factory:failed` + an explanatory comment (never a silent
  drop); a transient failure is retried on the next tick.
- **The issue number is the correlation key** (RFC-0001) threaded end-to-end, so
  the cockpit can stitch PLAN→CODE→TEST→MERGED for the item on any host.

The GitHub fast path (the existing `*:run` on-label workflows) is kept for
low-latency interactive use; the poller is the uniform floor that guarantees
100% pickup including on GitLab/ADO.

## 7. Labels, templates, and the difficulty applier

- **Canonical labels:** `.github/labels.yml` defines the difficulty + lifecycle
  + carried-through set with colours and descriptions; a pinned label-sync
  workflow (`.github/workflows/label-sync.yml`) reconciles them on GitHub, and
  `scripts/sync_labels.py` (stdlib + the `GitProvider` concept, dry-run-able,
  no live creds required in CI) documents and performs GitLab/ADO creation.
- **Issue forms:** `.github/ISSUE_TEMPLATE/factory-task.yml` is a GitHub issue
  form with a **Difficulty dropdown (Low / Medium / Hard)** plus title, context,
  acceptance criteria, and target repo. Because GitHub forms cannot label
  conditionally, a tiny workflow
  (`.github/workflows/factory-task-label.yml`, on issues opened/edited) reads the
  rendered Difficulty field and applies the matching `factory:<tier>` label.
  Equivalent templates ship for GitLab (`.gitlab/issue_templates/factory-task.md`)
  and Azure DevOps (a documented work-item template).

## 8. Honesty + safety (carried forward)

- **No merge on red, ever** (RFC-0009): required checks are hard gates for every
  tier.
- **No auto-merge below the VAL floor** (RFC-0006): `low` auto-merge requires
  VAL ≥ floor **and** `ci_parity=yes`. A change TFactory could only lint does
  not auto-merge.
- **No rewrite run cheap** (RFC-0010): `change_mode=migration` forces `hard` +
  equivalence.
- **No silent drop** (this RFC): a terminal intake failure is labelled
  `factory:failed` with a reason; a transient one retries.
- **Fail safe on ambiguity:** multiple difficulty labels resolve to the hardest.

## 9. Rollout

1. **Standard + contract.** This RFC + `execution.autonomy_tier` (done).
2. **Labels + templates.** `labels.yml`, label-sync, `sync_labels.py`, the
   issue forms, and the difficulty→label applier.
3. **Tier classifier + profile.** `classify_tier` (highest-wins, migration⇒hard)
   and the tier→config profile that overrides execution / review_tier /
   tfactory blocks, wired into the contract emitter.
4. **Poller + governed ingest.** The provider-agnostic poller with SQLite +
   `factory:queued` idempotency and `factory:failed` handling, plus the
   `/api/tasks/from-issue` endpoint.
5. **Merge policy + TFactory rigor.** The RFC-0009 merge policy parameterised by
   tier, and the TFactory `tier_floor` → VAL floor + lane rigor.
6. **E2E.** One labelled test issue per tier on the demo repo (+ a rewrite),
   asserting each emits its exact §3 row; repeat the `low` case on GitLab and
   ADO to prove the cross-tracker contract.

## 10. Acceptance

A contributor opens an issue/work-item on any supported host and applies one
difficulty label. The poller picks it up exactly once (idempotent under retries,
restarts, and DB loss), classifies the tier (highest-wins; a rewrite forces
`hard`), and routes it through PARR with the §3 policy: the emitted contract
carries `execution.autonomy_tier` and the matching model / planning / review_tier
/ lanes; a `low`, green, `ci_parity=yes` change auto-merges with no human; a
`hard` change is held for blocking approval and a rewrite additionally proves
equivalence — and the same behaviour is observable on GitHub, GitLab, and Azure
DevOps without host-specific code in the orchestrator.
