---
status: draft
issue: 1961
author: olafkfreund
---

# Intent: governance fields in the PFactory run signature

## Problem

PFactory writes a run signature (`<slug>.run.json`, built in
`apps/backend/plan/emit/docs/render.py` on `dev`, `SIGNATURE_SCHEMA = 1`). It
records where a plan came from: the correlation key, content hash, version, lens
scores, gates and criteria count. It records nothing about how the change was
governed. A supervisory review asks: "which changes touched control X, were they
agent- or human-authored, at what autonomy tier, and who approved each?" Today we
cannot answer any part of that, even though the run already holds most of the
data.

The 2026-09-06 plan comment on #1961 corrected the epic's gap table. These are
the corrections this intent works from:

- `risk_class` is already derived by `_derive_risk_class` from the deploy
  surface. Stamping it copies a value; nothing new has to be worked out.
- `autonomy_tier` comes from the `factory:low|medium|hard` label. PFactory
  receives it on the from-issue lane and gets `None` on every other lane.
  RFC-0014's `autonomy` verdict measures something else.
- `controls[]` has no vocabulary. #324 lists 14 domains and gives no control IDs.
- `data_classification` already has an authoritative vocabulary in the
  data-classification policy: Public, Internal, Confidential, Regulated.
- `originator` is not free. PFactory captures no actor anywhere, and the portal
  ingest routes have no auth.
- `approved_by` and `approved_at` are missing from the epic. Both are already
  held on `session.review.human_approval`.
- Nothing in the fleet reads `signature_schema` yet.

Nothing has landed since 06-09. PFactory `dev` still has schema 1, and the hub
has no control catalog.

## Proposed outcome

- A newly emitted `run.json` carries every governance field that playbook §6.2
  lists:
  - fields the run already knows: `risk_class`, `autonomy_tier`, `data_classification`, `approved_by` and `approved_at`;
  - `controls[]`, taken from a hub control catalog;
  - `change_id`, `originator`, `agent_identity` and `model_route`, which stay `null`
    until their source exists.
- None of these fields ever holds a plausible-looking wrong value. A field the run
  could not establish says `unknown` or `null`, never a believable default such as
  `"low"`.
- One command answers the supervisory question from the registry and prints how
  much it covered, for example "scanned N, M had signatures, K matched". That way an
  empty answer cannot pass as a clean one.
- Signatures already written under schema 1 still parse. A fixture copied from
  the live file proves it.

## Affected users and systems

- Factory hub: a new `apis/control-catalog.json`, with a drift check against `control-matrix.md`.
- PFactory `dev`: the emit code (`render.py`, `emit_docs.py`), a vendored copy of the catalog, and a new query CLI.
- The registry rows written by TFactory's fork of the emit code, which have no
  signature. The reader must count them, not drop them.
- No running service changes behaviour apart from what PFactory emits.

## Constraints

- `render.py` stays pure: no clock, no network, no file reads. The catalog is
  loaded in `emit_docs.py` and passed in, the same way the version already is.
  A mutation test proves this.
- Fields are added only; existing keys keep their meaning. Schema 1 goes to 2.
- Reuse the existing vocabularies (#324's domains, the classification policy). No
  second taxonomy.
- Vendor the catalog the same proven way as `task-contract.schema.json`, with a
  byte-identical drift check.
- Work that needs #1959, #1960 or an ITSM integration is out of scope.

## Open questions

1. **Scope.** Do we deliver the independent stages now (catalog, the fields the
   run already knows, `controls[]`, query CLI) and leave `originator` until #1960
   defines the actor format? *Recommend yes.*
2. **What `controls[]` means.** Is it "the control domains this run's gates
   engaged", which PFactory can prove, or "the controls this change touches",
   which PFactory cannot know at plan time? The second would belong in AIFactory
   at merge time, as a different epic. *Recommend the first.*
3. **Field layout.** Flat keys, or a nested `governance{}` block? *Recommend
   flat, to match every existing key.* Whatever we pick is fixed, because changing
   it later changes what the fields mean.
4. **Portal ingest auth.** Should the portal ingest routes require auth?
   Without it, `originator` stays `null` on the portal lane. *Recommend
   deferring this with stage 3; it is not needed for questions 1 to 3.*
5. **Where the artifacts live.** The intent, spec and plan go here in Factory,
   where the issue lives. Most of the code PRs go to PFactory and link back.
   *Recommend this.*
