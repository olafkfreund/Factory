---
status: approved
issue: 1962
intent: intent/2026-10-07-1962-autonomy-matrix.md
---

# Spec: publish the autonomy matrix and control mapping, generated from code

All references are AIFactory `origin/dev` @ `df22b943`, read on 2026-10-07,
unless they name another repo. The work lands in AIFactory. The hub gets one
protection-script line in PR 1 and links in PR 2.

## What the matrix must describe (findings that shape the design)

The policy that gates a merge is **two layers**, and a matrix of only one of
them would be wrong.

1. **The policy:** `apps/backend/merge/merge_policy.py`.
   - `decide_merge` (L258):
     - an unknown or blank tier gives `HOLD_BLOCKING`;
     - the RFC-0013 overlay (`deployment_block_reasons`, L200) blocks first;
     - `hard` gives `HOLD_BLOCKING` and `medium` gives `HOLD_ASYNC`;
     - `low` gives `AUTO_MERGE` only when CI is green, the verdict passes, the
       VAL floor is met and CI parity holds, and `HOLD_ASYNC` otherwise.
   - `_val_meets_floor` (L145), `floor_from_paths` (L81, which fails closed
     to `blocking`) and `raise_review_tier` (never lowers).
2. **The live wiring:** `apps/web-server/server/services/pr_endgame.py`
   changes the policy's inputs and switches it on or off.
   - `merge_disposition` (L442) decides a **blank tier as `low`**, while
     `decide_merge` alone holds it blocking. Publishing only the policy would
     overstate how strict the live path is.
   - `apply_path_risk_floor` (L190) applies the path floor **only when
     `AIFACTORY_PATH_RISK_FLOOR_ENFORCE` is truthy**. Otherwise it is recorded
     and advisory.
   - `is_auto_merge_enabled` gates merging at all on `AIFACTORY_AUTO_MERGE`.
   - Both flags default **off** (`_flag`, L98: "Both default OFF").
   - Live, measured today: on the `aifactory` Deployment neither flag is set.
     Only `AIFACTORY_AUTO_PR=true` is. So the path floor is currently
     **advisory**, and auto-merge is off unless a project turns it on.
   - The PR review verdict that `watch_and_finish` waits for comes from an
     **injected** `review_fn`. With `AIFACTORY_PR_REVIEWER=aifactory` (the
     default), that is `server.services.pr_review_service`, which is wired in
     `completion_orchestration.py` ~L300-L345.

So the published artefact has three sections: **policy**, **wiring** and
**gate determinism**. Each is derived by running or reading code. Nothing is
restated.

## Design

### 0. The `enforce_admins` experiment (approved prerequisite, not code)

This is a scratch private repo, `olafkfreund/protection-probe-1962`, with
main's protection shape:
- one required status check, made to fail by a workflow that exits 1;
- `strict: true` and `enforce_admins: false`.

Open a PR, then try to merge it as the account AIFactory uses, two ways:
- `gh pr merge --squash`, AIFactory's exact call (`merge_pr`, L712);
- the REST `PUT /repos/{o}/{r}/pulls/{n}/merge`, which is what a non-gh caller
  would use.

Record both outcomes verbatim in the plan's implementation record, then delete
the repo.

- **Both refused:** the claim "a red required check cannot be merged past" may
  appear in PR 2's mapping.
- **Either succeeds:** the mapping says "admin bypass possible while
  `enforce_admins` is false" and the issue is filed under #943/#1963.

The result feeds PR 2 only. PR 1 makes no branch-protection claim.

### PR 1: generator, staleness gate, determinism prober

**`scripts/gen_autonomy_matrix.py`** is dependency-free beyond the AIFactory
venv. It follows the shape of the hub's `scripts/gen_contracts.py`: a generated
banner, a single output sink, `--check` mode, and an exit code that's non-zero
on drift.

- **Imports:** put `apps/backend` and `apps/web-server` on `sys.path`, the
  way CI installs both (`ci.yml:64-66`).
  - Import `merge.merge_policy`, `review_tier` and
    `server.services.pr_endgame` **eagerly**. Any `ImportError` is fatal
    (exit 2, naming the module).
  - It must never render `floor_from_paths`'s fail-closed `"blocking"` as if it
    were the policy.
- **Section A, policy:** derived by calling the functions.
  - **Tiers:** for every key in `_TIER_ALIASES`, plus `""` and an unknown
    probe, call `decide_merge` over the full cross-product of the four
    booleans:
    - `host_ci_green`;
    - verdict pass/fail;
    - VAL met/unmet, using probes `achieved=2/floor=1` and
      `achieved=1/floor=2`;
    - `ci_parity`;

    with `deployment=None`. Collapse to one row per canonical bucket listing
    the condition set under which each disposition occurs. The collapse is
    computed: group cross-product rows by result. No hand-written condition
    text.
  - **Overlay:** call `deployment_block_reasons` over probe deployments:
    - `risk_class` ∈ {high, medium, low, ""};
    - `production_classification` ∈ {production, staging, dev, ""};
    - `system_gates` = ["human-approval", "security-scan"] with satisfied ∈
      {none, partial, all}.

    Render each probe's returned reason strings **verbatim**, and the
    `decide_merge` result for a `low` tier with all-green signals under that
    deployment.
  - **VAL semantics:** call `_val_meets_floor` over the probe set
    `(achieved, floor)`: `(2, None)`, `(2, "")`, `(2, "VAL-three")`,
    `(1, 2)`, `(2, 2)`, `(3, 2)`, `(None, 2)`, `("VAL-2 (3 lanes)", 2)`.
    Render the booleans.
  - **Path floor:** call `floor_from_paths` on probe paths, one per
    `review_tier.HIGH_RISK_PATTERNS` entry plus two non-matching ones. Render
    the results and the pattern list itself, read from the module, not
    restated.
- **Section B, wiring:** derived by calling the live functions.
  - Call `merge_disposition(tmp_spec_dir, tier)` for a blank tier and for
    `"low"`, with a temp `task_metadata.json` carrying all-green signals.
    Render whether blank equals low. This is how the generator *observes* the
    back-compat rule rather than stating it.
  - Call `is_auto_merge_enabled(None)` and `path_floor_enforced(None)` with
    the two env vars unset, then set to `"1"`. Render the defaults and the env
    var names (`PATH_RISK_FLOOR_ENV` read from the module).
  - Call `apply_path_risk_floor` against a temp git repo whose diff touches
    one high-risk path, with enforcement off and then on. Render whether the
    tier changed in each case.
  - Live deployment values are configuration, not code. The page says
    "defaults shown; per-project and per-deployment overrides apply" and
    doesn't claim live values.
- **Section C, gate determinism:** a static prober, `ast` only, no
  execution.
  - **Entry points**, declared in the generator as `(label, module)` pairs:
    - the merge policy: `merge.merge_policy`;
    - the PR review verdict: `server.services.pr_review_service`;
    - the endgame orchestration: `server.services.pr_endgame`.
  - **The walk:** for each entry point, walk the transitive import closure over
    files resolved under `apps/backend` and `apps/web-server`. This includes
    lazy, function-level imports, because those are how this codebase imports.
  - **The label:** "model-assisted" if the closure reaches a pinned
    model-client set:
    - third-party roots `anthropic`, `openai`, `claude_agent_sdk`,
      `google.genai` and `ollama`;
    - AIFactory's own client modules `core.client`, `core.simple_client` and
      `providers` (the default path spawns the `claude` CLI through these, and
      an import walk would not see a subprocess).
  - Otherwise the label is "deterministic".
  - **Non-vacuity:** a resolved closure smaller than a per-entry-point minimum
    (set in the plan from a measured run) is an **error**, never
    "deterministic".
  - **The honest limit:** the review verdict is *injected*
    (`review_fn`), so `pr_endgame`'s own closure may not reach a model client.
    The page therefore shows the review verdict as a separate gate component.
  - PFactory's `plan.review.gates.run_gates` and TFactory's
    `agents.evaluator._run_evaluator_session` are listed as
    **"declared, unverified (other repo)"**, with their source citations. The
    citations are the one listed literal, and they're marked as such.
- **Outputs:**
  - `docs/docs/compliance/autonomy-matrix.md`, an auditor-readable page with
    the generated banner, three sections and plain-English column headers;
  - `docs/static/compliance/autonomy-matrix.json`, the same data, stable
    keys, sorted.
- **`--check`:**
  - regenerate in memory and compare byte-for-byte with both committed files;
  - first assert row counts: Section A ≥ the minimum per bucket and overlay
    probes ≥ 12; Section C has 3 entry points, each closure ≥ its minimum;
  - on a mismatch, print the first differing line.

**`.github/workflows/autonomy-matrix.yml`** copies the design of the hub's
`contracts.yml`, **including its comment explaining why there is no `paths:`
filter** (Factory#489).
- It runs on every PR and every push to `dev` and `main`.
- Setup: the same venv as `ci.yml`. Run `python scripts/gen_autonomy_matrix.py --check`.
- Job name: `autonomy matrix matches the policy (--check, blocking)`.

**Required context:** the hub `scripts/apply_branch_protection.sh` adds that
job name to AIFactory's check list for `dev` and `main` (11 → 12 on `dev`), and
it's applied. Without this, the gate is advisory, which is a dark gate.

**Tests:** `tests/test_gen_autonomy_matrix.py`
- The generator's output contains each disposition string read from
  `merge_policy`.
- The prober returns "deterministic" for `merge.merge_policy` and
  "model-assisted" for `server.services.pr_review_service`.
- A prober pointed at a fake entry point with an empty closure raises.
- `--check` fails on a tampered committed file.

### PR 2: control-objective mapping, publication, links

- **`docs/compliance/control-objectives.yaml`**, the only hand-maintained
  input. One row per derived control id, which the generator emits in
  Section A/B/C. Each row has:
  - `control` (the derived id);
  - `objective` (one line);
  - `evidence` (a path or URL);
  - `frameworks` (clause references, e.g. SOC 2 CC8.1, ISO 27001 A.8.32);
  - `claim` text where a human judgement is needed (the branch-protection
    wording from step 0).
- The generator joins it and renders a fourth section, **Control-objective
  mapping**. `--check` also fails on an orphan in either direction: a derived
  control without a row, or a row without a derived control.
- The page goes into the docs sidebar and is published by the existing
  `docs.yml` deploy on push to `main`.
- The hub `docs/compliance/control-matrix.md` gets **links** to the published
  page from the evidence cells of the "Agentic-AI governance (#323)" and
  "Change mgmt & SoD (#316)" rows. No content is copied.

## Alternatives rejected

- **Generator in the hub.** The gate must fire in the PR that changes the
  policy. A hub job fetching AIFactory finds out a day late, and cross-repo
  fetch has broken deploys here before.
- **Rendering the epic's risk × environment grid.** There is no environment
  axis, so that grid would invent two columns in its first render.
- **Only the policy layer (`merge_policy.py`).** It omits blank → low,
  advisory-by-default path floor, and auto-merge off by default. That would
  make the page stricter than reality, which is the worst direction for a
  control document to err in.
- **Hardcoded "model-assisted" labels.** That's transcription. The prober
  derives the labels, and its non-vacuity check stops a resolver that walked
  nothing from claiming "deterministic".
- **Probing PFactory and TFactory from AIFactory.** AIFactory can't import
  them, and adding that would turn this into a three-repo build. They're shown
  as declared-unverified, with a follow-up for per-service
  `gate-manifest.json` files.
- **A runtime import hook for the prober.** It would execute the import graph,
  which is slow, has side effects and needs the full environment. `ast` is
  enough and is pure.

## Risks

- **Importing `pr_endgame` in the generator** pulls in `build_backend` and
  `task_branch`. CI has the deps (`ci.yml:64-66`). Locally it needs the same
  venv. An import failure is a loud exit 2, never a silent partial page.
- **`apply_path_risk_floor` needs a git diff.** Section B builds a throwaway
  git repo in a temp dir. If the differ's call shape changes, the generator
  fails loudly. That is the gate doing its job.
- **The prober's closure includes lazy imports**, so the merge policy's
  closure includes `review_tier`, which is correct. If the backend grows an
  import path from the policy to a model client, the label flips to
  "model-assisted" and `--check` fails until it's regenerated. That's
  intended, and it's exactly the drift the page exists to surface.
- **Probe-set completeness.** A new `decide_merge` input would not be probed
  automatically. Mitigation: the generator compares `decide_merge`'s signature
  (via `inspect.signature`) against the parameters it probes, and fails on an
  unknown parameter.
- **Required-context rollout.** Registering the check before the workflow
  exists on `dev` would wedge every PR. Ordering is in the plan: merge the
  workflow first, then apply protection.
- **The experiment** creates and deletes a scratch repo under the owner's
  account. It's an outward-facing action, so it's done only with the plan
  approved.

## Verification

1. **Unit tests** (above) pass, and the full AIFactory suite is green.
2. **The three mutations from #1962's plan**, each on a scratch branch and
   reverted:
   - **A, value:** change `HOLD_ASYNC = "hold-async"` to `"hold-async-v2"`
     without regenerating. `--check` fails, naming the changed cell.
   - **B, shape:** add a `production_classification == "staging"` block
     reason. `--check` fails. (A hardcoded row list would survive A but not
     B.)
   - **Control:** an unrelated change. `--check` passes, and the log shows the
     non-zero row counts.
   - **Plus D, wiring:** change `merge_disposition`'s blank-tier default to
     `"medium"`. `--check` fails. This proves Section B is derived.
3. **The live CI run on PR 1** shows the new job, and after protection is
   applied the PR page lists it as **Required**.
4. **The experiment's outcome** is recorded verbatim (commands and responses)
   in the plan's implementation record.
5. **PR 2:** the page is reachable at the docs URL after the `main` deploy. The
   hub links resolve. Removing one YAML row, or adding an orphan row, fails
   `--check`.
