---
status: draft
issue: 1962
author: olafkfreund
---

# Intent: publish the autonomy matrix and control mapping, generated from code

Child of epic #1958. Refines #1962's original framing using the implementation
research in its comments (6 Sep), re-checked against AIFactory `origin/dev` @
`df22b943` on 2026-10-07.

## Problem

What an agent is allowed to merge on its own is decided in
`AIFactory/apps/backend/merge/merge_policy.py`. The rules there are enforced
and correct, but only someone who reads Python can see them.

A CISO, a head of engineering and an auditor can't agree on what "the agent is
allowed to do" means without reading the code. Nothing records when that
permission widens, which is the ASI09 trust-drift risk named in playbook
§8.5.

A hand-written document wouldn't fix this. It would drift from the code within
a quarter, and a governance document that has drifted is worse than none,
because people believe it.

## What the code actually is (re-verified 2026-10-07)

The epic's description of the matrix is wrong in two ways that matter. A
generator built on it would invent content in its very first render.

- **There is no environment axis.** No dev/staging/prod enum exists.
  - `production_classification == "production"` is a single block predicate in
    the RFC-0013 overlay (`deployment_block_reasons`, L200).
  - Every other value produces no overlay.
  - So the real shape is **tier × overlay predicate → disposition**, not
    risk × environment.
- **VAL floors are per-task inputs, not policy constants.**
  - `val_floor` comes from `task_metadata.json`.
  - The only thing that can be published is *how* the floor is enforced
    (`_val_meets_floor`, L145): absent is satisfied; unparseable or missing
    achieved fails closed.
  - There is no tier → VAL table to publish.
- **A path floor the epic missed.** `floor_from_paths` (L81) sets the review
  tier to `blocking` for paths matching `review_tier._RISK_RE` (auth, secrets,
  migrations, infra, CI). It also fails closed if that pattern table can't be
  imported.
- The dispositions (`AUTO_MERGE` / `HOLD_ASYNC` / `HOLD_BLOCKING`, L48-50) and
  `decide_merge` (L258) are as described.

## Proposed outcome

1. **A generated autonomy matrix, readable without Python, published at
   AIFactory's docs site** (`https://olafkfreund.github.io/AIFactory/`, Pages
   status `built`; `docs.yml` deploys on push to `main`). It covers:
   - each tier and its aliases → disposition, with the conditions under which
     `low` actually auto-merges;
   - each overlay predicate → block;
   - VAL-floor enforcement semantics;
   - the path floor and its pattern.

   The same data is also emitted as JSON for #324 and Fides to consume.
2. **Derived, not transcribed.** The generator *calls* `decide_merge`,
   `deployment_block_reasons`, `_val_meets_floor` and `floor_from_paths` over
   probe inputs and renders what they return. Changing the policy and not
   regenerating fails CI.
3. **A control-objective mapping** (playbook §8.4): control → implementation
   → evidence location → framework clause.
   - Framework clauses can't be derived from code. They live in one small
     committed table that the generator joins to the derived rows.
   - The check fails on an orphan in either direction.
4. **Honest about determinism.** Each gate is labelled deterministic or
   model-assisted.
   - The verify gate is model-assisted (#1963), and the artefact says so.
   - Gates in other repos that AIFactory can't analyse are shown as "declared,
     unverified", not claimed.
5. **#324's hub `control-matrix.md` links to the artefact** instead of
   duplicating it.

## Affected users and systems

- AIFactory:
  - a new generator script next to `merge_policy.py`;
  - generated docs and JSON under `docs/`;
  - a new CI staleness workflow;
  - one more required status check on `dev` and `main`.
- Hub (Factory):
  - `scripts/apply_branch_protection.sh`, to register the new required check;
  - `docs/compliance/control-matrix.md`, which gains links.
- Readers: auditors, security reviewers and the owner. Fides and #324 consume
  the JSON.
- No change to merge behaviour. This work describes the policy; it doesn't
  alter it.

## Constraints

- **Generate, never transcribe.** No hardcoded row lists, disposition strings
  or "deterministic" labels.
  - The proof is mutation, in both directions:
    - changing a disposition value fails the check;
    - adding a new overlay predicate fails the check;
    - an unrelated change passes, with a non-zero row count in the log.
- **No vacuous pass.**
  - The check asserts a minimum row count.
  - The determinism prober treats an empty import closure as an error, never
    as "deterministic".
  - The workflow has no `paths:` filter (the Factory#489 lesson).
  - The workflow is a *required* status check. An advisory one is a dark gate.
- **Fail loudly on import trouble.** If `review_tier` can't be imported, the
  generator errors. It must not render the fail-closed `blocking` answer as if
  it were the policy.
- **The gate lives in AIFactory**, the repo that owns the policy, so it fires
  in the same PR that changes it. No cross-repo fetch.
- **The artefact claims only what holds.** "Branch protection where
  configured": tenant repos are outside our control.
- Out of scope:
  - probing PFactory and TFactory gate code from AIFactory (that's a follow-up
    via per-service `gate-manifest.json`);
  - any change to `merge_policy.py` behaviour;
  - the #1963 floor work itself.

## Open questions

1. **Prerequisite: the `enforce_admins` experiment (#1963).**
   - `enforce_admins` is `false` on `main` in all four repos (measured today),
     and AIFactory merges as a repo admin.
   - `merge_pr()` shells out to `gh pr merge` without `--admin`.
     - On Factory#3514 this session, gh refused a blocked merge client-side
       without `--admin`.
     - Whether the *server* would refuse an admin merging past a red required
       check hasn't been tested.
   - That answer decides whether the published matrix may say "a red required
     check cannot be merged past". Options:
     - **A (recommended):** run the scratch-repo experiment first, as part of
       this task's plan, and let the result set the wording. If the merge
       succeeds, file the `enforce_admins: true` change under #943/#1963, not
       here.
     - **B:** publish now with the claim worded conditionally ("enforced by
       branch protection; admin bypass not yet ruled out"), and tighten the
       wording later.
2. **Scope of the first PR.** The generator, staleness gate and determinism
   prober are one unit: without the prober, the determinism column would be
   transcribed.
   - The control-objective mapping (outcome 3) and the #324 link (outcome 5)
     could follow in a second PR.
   - Recommended: **one task, two PRs.**
     - PR 1: matrix, gate and prober.
     - PR 2: mapping and links.
   - Publication waits for PR 2, so nothing goes public half-done.
3. **Review cadence** (#1962's "rubber-stamp rate" item). Recording a cadence
   is a process decision, not code. Should it go in the published page as a
   stated policy, or be dropped from this task?
