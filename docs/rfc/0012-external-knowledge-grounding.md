---
layout: default
title: "RFC-0012: External-Knowledge Grounding from Backstage"
permalink: /rfc/external-knowledge-grounding/
---

# RFC-0012 — External-Knowledge Grounding from Backstage

> **Status:** Implemented (epic #124 closed — house-standards adapter, fail-closed standards_conformance gate + acceptance, coder/QA/planner prompt injection) · **Created:** 2026-06-20 · **Updated:** 2026-06-20 · **Extends:** [RFC-0002](./0002-task-contract.md) (contract), [RFC-0006](./0006-verification-assurance-levels.md) (assurance levels), [RFC-0010](./0010-code-aware-planning-and-behavioral-equivalence.md) (baseline reconnaissance) · **Affects:** PFactory (planning), AIFactory (coding/QA), TFactory (testing)
>
> A team has a house wiki: best-practices, code-style, testing guides, golden-path service templates. Today the fleet plans, codes, and verifies **without ever reading them** — it follows whatever it infers from the spec and the repo, and the team's standards are silently absent from the work. This RFC pulls those standards from the live **Backstage** (Software Catalog + TechDocs + Scaffolder templates, reachable over the connected MCP) into the contract, injects them into the planning/coding/testing prompts, and then **proves** they were both retrieved AND applied with a fail-closed `standards_conformance` gate. The gate is the bar the fleet must clear before we let it trust any external knowledge source.

## 1. Motivation — house standards are invisible to the fleet

The fleet already grounds itself in two things: the spec (PFactory) and the
target repo's own code (RFC-0010 reconnaissance). It does **not** read the
organization's standards, which live outside any single repo:

- **Best-practices / code-style / testing guides** — published as TechDocs on
  catalog entities (`backstage.io/techdocs-ref` annotation).
- **Golden-path templates** — Scaffolder templates that encode the blessed stack
  (e.g. `typescript-service` = Fastify + pnpm + Nix flake; `rust-service` =
  axum + Nix; `terraform-azure` = devenv + flake). These are the canonical "this
  is how we build a service here."
- **Ownership / lifecycle metadata** — catalog `spec.type`, `spec.lifecycle`,
  `spec.owner` that say what a component *is* and who owns it.

Backstage is **live and reachable** over MCP. A query of the catalog returns 80+
components (each carrying `github.com/project-slug` = `owner/name` and a
`backstage.io/techdocs-ref`) and 11 Scaffolder templates. The data needed to
ground the fleet in house standards is already there; nothing consumes it.

**The trust failure has two halves, and both must be closed:**

1. **Retrieval** — the standards never enter the contract, so the planner, coder,
   and tester cannot follow them.
2. **Conformance** — even if we inject them, an agent can *ignore* them. Pulling a
   wiki page and then not following it is worse than not pulling it: it looks
   grounded but is not. So retrieval without a conformance check is theatre.

**One fact already in place makes the retrieval half cheap:** RFC-0010 already
**detects** the repo's own `baseline.conventions` (linters, formatters,
test-layout) during reconnaissance — and then never injects them anywhere. This
RFC surfaces those *and* adds the Backstage pull, under one manifest.

## 2. The bright line — best-effort retrieval, fail-closed conformance

Two rules govern this RFC, in tension by design:

> **Retrieval degrades, never raises.** The Backstage adapter is best-effort: if
> the catalog is unreachable, the repo has no matching entity, or a TechDocs ref
> is missing, the adapter records an honest "unavailable" manifest and the run
> continues. A standards lookup that throws would block every plan.

> **Conformance fails closed.** The `standards_conformance` gate (§5) treats a
> *missing or unproven* answer as a FAIL, never a pass. "We could not show the
> standard was applied" is a failing state, mirroring the never-overclaim
> discipline of `verification_gate.py`.

The asymmetry is the whole point: it is fine to *not have* a standard (greenfield
team, empty wiki); it is **not** fine to *have* one, declare it, and silently
ignore it. The first is `not_applicable`; the second is the failure this gate
exists to catch.

## 3. The Backstage adapter (retrieval)

A new PFactory module, `plan/emit/house_standards.py`, exposes one entry point:
`attach_house_standards(contract, plan)`, wired into
`contract_emit.assemble_contract` **after `attach_constraints`** (so it sits
beside the other `epic_context` enrichment). It is pure-ish — it performs a
best-effort Backstage lookup behind a soft, injectable client and **never
raises** — mirroring `attach_constraints`.

It assembles the manifest from two sources:

1. **RFC-0010 `baseline.conventions`** — the linters/formatters/test-layout the
   reconnaissance already detected in the target repo. Already in the contract,
   never previously surfaced for the agents to honour. This is recorded with
   `source: "baseline"` and is always available offline.
2. **Backstage catalog + TechDocs + templates**, keyed off `provenance.repo`
   (`owner/name`):
   - `catalog_query-catalog-entities` filtered on
     `github.com/project-slug == provenance.repo` → the matching Component
     entity, from which we read `spec.type`, `spec.lifecycle`, `spec.owner`,
     `tags`, and the `backstage.io/techdocs-ref` annotation.
   - The TechDocs ref(s) are recorded as `techdocs_refs` (URIs, not inlined
     bodies — the agents fetch on demand via the existing runtime-knowledge
     mechanisms, RFC-0003 MCP call-home / WebFetch).
   - Golden-path **Scaffolder templates** whose `tags` intersect the entity's
     stack (e.g. a Rust repo → `rust-service`) are recorded as `templates`
     (name + title + tags) — the blessed stack the build should match.

Each recorded standard carries a **content-hash** (a stable digest of its
source-of-truth: the conventions object, or the entity ref + techdocs ref +
template set). The hash is what the conformance gate and any deviation waiver
bind to, so a standard cannot be silently swapped after approval.

The manifest lands at `contract.epic_context.house_standards` (§4).

## 4. Contract changes (RFC-0002, additive)

All changes are additive; **`contract_version` stays `"2"`**. The new block is an
optional, open object so existing v2 consumers ignore it. Landed in
`apis/task-contract.schema.json` as `$defs.house_standards`, referenced from
`epic_context.house_standards`:

```jsonc
"house_standards": {
  "available": true,                 // false => could not retrieve; gate treats as not_applicable
  "sources": [
    {
      "source": "baseline",          // RFC-0010 repo conventions, always offline-available
      "kind": "conventions",
      "content_hash": "sha256:...",
      "conventions": { "linter": "ruff", "formatter": "black", "test_layout": "tests/" }
    },
    {
      "source": "backstage",
      "kind": "component",
      "entity_ref": "component:default/aifactory",
      "techdocs_refs": ["url:https://github.com/olafkfreund/AIFactory/tree/dev"],
      "lifecycle": "experimental",
      "spec_type": "service",
      "content_hash": "sha256:..."
    },
    {
      "source": "backstage",
      "kind": "template",
      "entity_ref": "template:default/rust-service",
      "tags": ["rust", "service", "axum", "nix"],
      "content_hash": "sha256:..."
    }
  ],
  "error": null                      // why retrieval was unavailable, when available=false
}
```

The `provenance.repo` field (already present, RFC-0010) is the lookup key. A
note is added to RFC-0002 documenting the additive block. The schema is vendored
twice (canonical here + a copy under PFactory's `plan/emit/contracts/`), so the
same delta is applied to both, per the RFC-0010 schema-drift discipline.

## 5. Injection points (where standards reach the agents)

The manifest is inert until the agents read it. Three injection points, each its
own scoped change:

- **PFactory** — `attach_house_standards` in `assemble_contract` (the retrieval
  point itself, §3). The planner already consumes `baseline`; surfacing the
  conventions into the manifest makes them available to everything downstream.
- **AIFactory** — `prompts_pkg/prompts.py`: `get_coding_prompt` and
  `get_qa_reviewer_prompt` read `contract.epic_context.house_standards` and
  render a **`## HOUSE STANDARDS`** block (reusing the existing MCP-section
  injection marker) listing the conventions, the linked TechDocs the coder must
  consult, and the golden-path template to match. The QA reviewer is told to
  *flag* code that diverges from the declared standards.
- **TFactory** — `prompts_pkg get_tfactory_planner_prompt`: a fourth block beside
  profile/registry/catalog carrying the house **testing** standards, so the test
  plan exercises the declared lint/type/test lanes.

These two agent injections (AIFactory, TFactory) live in their own repos and are
tracked as separate child issues; they are not required for the gate to be
correct (the gate checks the contract + verification evidence, not the prompts).

## 6. The `standards_conformance` gate (the "prove it" half)

A pure, dependency-free module — `scripts/standards_conformance_gate.py`,
modelled on `scripts/verification_gate.py` (never-overclaim) — takes the contract
plus the producer's verification block and returns a normalized, fail-closed
verdict. It asks four questions, in order:

1. **retrieved?** — does `epic_context.house_standards` carry sources with
   content-hashes? If `available == false`, the verdict is **`not_applicable`**
   (no standard to enforce — a pass, honestly labelled). If the block is malformed
   or claims `available` with no hashed sources → **FAIL** (`not_retrieved`).
2. **declared?** — does the build's declared configuration/dependencies reference
   the retrieved standards (the conventions tools appear in the declared lanes,
   the golden-path template's stack matches the environment)? A standard present
   but not reflected in the artifact's declared config → **FAIL**
   (`declared_but_not_applied`). *This is the key negative case: standards present
   but ignored.*
3. **deviations waived?** — any declared deviation must carry a waiver whose
   `content_hash` matches the standard it waives (a waiver cannot float free of
   the thing it excuses). An unwaived deviation → **FAIL**.
4. **executed?** — the declared lint/type/test lanes must have actually **run**
   per the RFC-0006 verification block (a `passed` level, not `not_run`/`skipped`).
   Declared-but-not-executed → **FAIL** (`declared_but_not_executed`).

The verdict is `{status, reasons, checks}` where `status ∈ {pass, fail,
not_applicable}` and every fail enumerates explicit reasons. **Fail-closed:**
missing inputs, malformed blocks, and unknowns all resolve to `fail`, never
`pass`. It runs at four points — PFactory emit (sanity), AIFactory trailing gate,
TFactory verify, CFactory merge gate — so an ignored standard cannot reach merge.

## 7. The "ready to trust external sources" bar (acceptance)

The acceptance harness (`scripts/standards_conformance_acceptance.py`) is the
trust gate for this whole capability. It proves both directions:

- **Positive** — a contract with a retrieved, hashed standard, a declared config
  that reflects it, no unwaived deviations, and a verification block showing the
  declared lanes ran → the gate returns **pass**.
- **Negative** — the *same* standard retrieved, but the build ignores it (config
  does not reflect it, or the lane never ran) → the gate returns **fail** with the
  precise reason.

Only when this harness passes — positive passes AND negative fails — do we permit
the fleet to ground itself in external wikis. A retrieval that cannot be shown to
have been applied is not grounding; it is decoration.

## 8. Phasing

1. **RFC + schema** (this hub): the document + the additive `house_standards`
   contract block. *(this change)*
2. **PFactory adapter**: `house_standards.py` (baseline conventions + best-effort
   Backstage lookup) + wire into `assemble_contract`; unit tests with the
   Backstage layer mocked.
3. **The gate**: `standards_conformance_gate.py` (fail-closed) + unit tests
   including the negative (standards present, ignored → fail).
4. **Acceptance harness**: positive-passes / negative-fails (the trust bar).
5. **Agent injections** (own repos, own child issues): AIFactory coder/QA prompts;
   TFactory planner prompt. Not required for the gate's correctness; deferred and
   tracked separately.

## 9. Risks

- **Standards theatre** — pulling a wiki page and ignoring it. Mitigated by the
  fail-closed gate's `declared` + `executed` checks; the negative acceptance case
  asserts the gate catches exactly this.
- **Backstage unavailability blocking plans** — mitigated by the §2 best-effort
  rule: retrieval degrades to a `baseline`-only manifest, and the gate scores an
  absent standard as `not_applicable`, never a false pass.
- **Stale / swapped standards** — every recorded standard carries a content-hash;
  waivers bind to that hash, so a standard cannot be silently changed after the
  human approved the plan.
- **TechDocs body bloat** — refs (URIs) are recorded, not inlined bodies; agents
  fetch on demand, keeping the contract small.
- **Schema drift between the two vendored copies** (a known issue) — the same
  delta is applied to both, per RFC-0010's drift discipline.
- **Over-trusting external sources generally** — this RFC scopes trust to
  Backstage (an owned, authenticated catalog) and gates it; broadening to
  arbitrary wikis is explicitly out of scope until the acceptance bar holds.
