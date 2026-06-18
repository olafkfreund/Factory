---
layout: default
title: "RFC-0010: Code-Aware Planning over Existing Repositories"
permalink: /rfc/code-aware-planning/
---

# RFC-0010 — Code-Aware Planning over Existing Repositories (Brownfield + Migration)

> **Status:** Proposed · **Created:** 2026-06-18 · **Extends:** [RFC-0002](./0002-task-contract.md) (contract), [RFC-0005](./0005-environment-manifest-and-toolchain-provisioning.md) (environment), [RFC-0006](./0006-verification-assurance-levels.md) (assurance levels) · **Affects:** PFactory (planner), AIFactory (coder), TFactory (verifier)
>
> A team submits a plan to **change code that already exists** — "modify our AWS EKS Terraform" or "rewrite the payments module from Python to Rust." Today PFactory plans **blind**: it reads the spec document and never the target repository, so it guesses the language, emits empty file footprints, and the human approves a plan that isn't grounded in what is actually there. This RFC makes PFactory **read the repo statically, react to what exists, and emit a delta-aware contract** — and adds a behavioral-**equivalence** lane so a language rewrite is proven against the original, not just asserted.

## 1. Motivation — the planner is blind to the code it changes

Two concrete scenarios, both currently mis-served:

- **Scenario A — modify existing infrastructure code.** A team asks to change an
  existing AWS EKS deployment (Terraform/Helm already in the repo). A good plan
  must know which modules and resources exist, which files to modify vs create,
  and what would be destructively replaced. PFactory knows none of this.
- **Scenario B — rewrite Python to Rust.** The existing Python is the behavioral
  source of truth; the deliverable is Rust that behaves identically. PFactory has
  no notion of *source* vs *target* language (the spec/repo language mismatch
  looks like a conflict to halt on), AIFactory only ever generates in the repo's
  native language, and TFactory has no way to prove the two implementations agree.

### Where each service stands today (code-grounded)

| | PFactory (plan) | AIFactory (build) | TFactory (verify) |
|---|---|---|---|
| Reads the target repo's code? | **No.** `PlanService.process()` plans from spec text only. Language is guessed from plan keywords — `emit/tfactory_block.py:57` `unit_fw = "pytest" if (python_ish or not node_ish) else "jest"`; `emit/environment_block.py` then `language = "python" if unit_fw == "pytest" else "typescript"`. | **Yes.** Checks out the base branch into a worktree (`core/workspace/setup.py`) and edits in place; detects language from repo structure (`project/stack_detector.py`). | **Yes**, but only the *built artifact*: clones `source_branch`, runs lanes hermetically (`tools/runners/{nix_provisioner,docker_runner}.py`). |
| Delta-aware? | **No.** `files_to_modify`/`files_to_create` emitted empty (`emit/contract_builder.py::_subtask`); `ac_to_code_map` emitted empty (`tfactory_block.py:73`). | Edits whatever the spec implies; no plan-time footprint. | Authors its own tests from acceptance criteria. |
| Migration-aware? | `workflow_type:"migration"` enum exists with **no logic**; the #585 fix makes spec≠repo language "spec wins or HALT" — which would wrongly halt a legitimate rewrite. | **No** rewrite mode — generates in the repo's native language. | **No** cross-language equivalence / golden-oracle / parity at all. |

**The trust failure:** because the plan is ungrounded, the human approves
guesses, and AIFactory silently overrides them at build time. The known
wrong-language bug (#585) is a symptom of this blindness, not an isolated defect.

**Two facts make the fix tractable:** (1) PFactory **already vendors the detector
package** (`apps/backend/project/` — `StackDetector`, `ProjectAnalyzer`,
`StructureAnalyzer`, `FrameworkDetector`), currently wired only into
`security/profile.py` and never into the planner; reconnaissance is mostly
*wiring existing local code*. (2) TFactory **already owns a hardened ephemeral
sandbox** (`docker_runner.py`, `--network=none --read-only`) — the one safe place
to execute untrusted legacy code to capture a behavioral oracle.

## 2. The bright line — plan reads statically, never executes

The single most important rule of this RFC:

> **PFactory reads target-repo code statically only** — Git checkout, manifest
> parsing, AST inspection, tolerant HCL/YAML scanning. It **never executes**
> repo code: no `npm install`, no `terraform init`, no build scripts, no git
> hooks, no submodule fetch. Any execution of untrusted code (capturing the
> migration golden oracle in §5) happens **only** inside TFactory's existing
> `--network=none --read-only` sandbox.

This keeps planning a pure, side-effect-free component and concentrates the
untrusted-execution risk where it is already contained.

## 3. Reconnaissance — PFactory reads the repo (Scenario A)

A new **Repository Reconnaissance** stage runs inside `PlanService.process()`,
between `detect_apply` (software/non-software is known; skip recon for
non-software) and `plan_type_apply` (plan-type, decomposition, and language
reconciliation all consume the result).

1. **Safe read-only checkout** (`plan/recon/clone.py`): shallow single-branch
   clone at the requested `base_ref`, with `core.hooksPath=/dev/null`,
   `GIT_CONFIG_NOSYSTEM=1`, **no submodule update**, into a `mkdtemp()` with
   size/file-count caps and a wall-clock timeout, torn down in a `finally`. The
   clone is the only network egress; everything after is offline file IO.
   Failure (private/unreachable/bad ref) **degrades, never raises** →
   `RepoMap(available=False, error=...)` and the run continues greenfield with an
   honest finding.
2. **RepoMap** (`plan/recon/reconnoiter.py`, reusing `apps/backend/project/*`):
   languages + pinned versions, package managers, frameworks, databases, cloud
   providers, directory/module layout, discovered test command, entrypoints, and
   code conventions (linters/formatters/test layout).
3. **IaC inventory** (`plan/recon/iac_probe.py`, static HCL/YAML scan — the heart
   of Scenario A): for Terraform, the `resource`/`module`/`data`/`variable`/
   `output` blocks and the files they live in (so the planner can say *"the EKS
   cluster `main` is in `eks.tf`, node groups in `node_groups.tf`"*); for
   Helm/K8s, `Chart.yaml` + the `kind:` set under `templates/`.

The RepoMap is carried in the contract's new top-level **`baseline`** block, so
the contract is self-describing about what the plan saw.

### 3.1 Delta-aware decomposition

With a RepoMap, decomposition (`decompose/planner.py` + new `plan/recon/delta.py`)
matches acceptance criteria against the layout/IaC inventory/dependency graph to
populate the contract fields that were always empty:

- `subtask.files_to_modify` (existing files) vs `files_to_create` (genuinely new);
- real `depends_on` across actual modules;
- `subtask.patterns_from` (exemplar neighbor files to imitate);
- pre-seeded `tfactory.ac_to_code_map` (AC → existing symbols/files);
- repo `conventions` carried as build constraints (`handoff_sanitize.py`);
- a **blast radius** (touched files ∪ their reverse-dependents; destructive-IaC
  changes flagged high-severity).

### 3.2 The `change_mode` classifier

`plan/recon/change_mode.py` produces a verdict **grounded in the RepoMap, not
plan text**, recorded in the contract's new top-level `change_mode` field:

- `greenfield` — recon unavailable, or empty/near-empty repo, or no target repo.
- `modify` — existing code/IaC present and the spec's stack reconciles with it
  (Scenario A). The repo's language wins.
- `migration` — existing code in language X, spec intends language Y, **and** a
  directional rewrite is requested (§5). The only case a language change is
  legitimate.

This gives real logic to the previously inert `migration`/`refactor`
`workflow_type` enums.

### 3.3 Language reconciliation (preserves #585)

`plan/recon/language_reconcile.py`, run after the RepoMap exists:

- **No conflict** (spec language absent or ⊆ repo languages) → use the repo's
  grounded language. Fixes the keyword-guess bug at the source: emit reads
  `repo_map.languages/versions`, falling back to the text heuristic only when
  recon is unavailable.
- **Conflict, `change_mode != migration`** → a **hard, non-waivable-by-default
  `language-reconciled` readiness check** fails with the explicit conflict
  (preserves #585's "spec wins or HALT"): a human corrects the spec,
  re-classifies as migration, or records a waiver.
- **`change_mode == migration`** → the conflict is intended; record both
  languages and skip the halt.

## 4. Grounded approval (trust)

Reconnaissance is the thing the human signs off on, so a **stable digest of the
RepoMap** (baseline commit + `change_mode` + resolved language + footprint set)
is folded into `NormalizedPlan.canonical_content()`. Re-running recon on the
*same* commit is idempotent (no spurious invalidation); a different baseline
commit or a changed footprint invalidates the approval. A new
`change-footprint-surfaced` readiness check renders "this plan was built against
`owner/name@<sha>`; it will modify `eks.tf`, `node_groups.tf`; detected stack
Terraform 1.7 + Helm; existing tests via `make test`" in the audit pack — and
**hard-fails when `change_mode ∈ {modify, migration}` but recon was unavailable
or the footprint is empty** (the precise failure this RFC exists to prevent).

## 5. Migration mode + behavioral equivalence (Scenario B)

### 5.1 Recognize and decompose (PFactory)

`detect/migration_classifier.py` fires on a **directional** pattern
("rewrite/port/migrate X **from** `<L1>` **to** `<L2>`") where `<L1>` matches the
detected repo language — this is what disambiguates a legitimate migration from a
#585 conflict. `detect/source_inspector.py` (AST-only) extracts the **behavioral
contract**: public API surface + signatures, existing tests, and the module
import DAG. `decompose/migration_planner.py` builds:

- **Phase 0 — declare** the behavior spec and a **golden-corpus manifest**
  (input vectors only — *no expected outputs*, which would require execution).
- **Phases 1..N — implement** the target module-by-module, one subtask per source
  module, ordered by the import DAG (reuse `contract_builder.py::_dependency_levels`
  over the *source* graph). Each subtask carries `source_module → target_module`.
- **Phase N+1 — parity verification** (the equivalence lane).

The planner auto-detects migration and asks **at most one** question — placement
and transition: a new crate/dir alongside the original (default, coexist /
strangler) vs a new repo; keep the original running vs replace.

### 5.2 The golden / reference-oracle (where execution lives)

PFactory only **declares** input vectors (statically, from existing test
fixtures/parametrize cases and the public-function I/O contract) into the
`tfactory.equivalence.golden_corpus_ref` manifest. **Expected outputs are
captured by a new TFactory phase-0 oracle step** that runs the legacy source over
those vectors inside the hardened sandbox, serializing each `input → output`
(and error class) into a language-neutral, content-hash-addressed
`findings/golden_corpus.json`. That corpus is the reference for both
implementations.

### 5.3 Rewrite mode (AIFactory)

Keyed on `change_mode == "migration"`: `core/workspace/setup.py` mounts the legacy
source **read-only** (under `.aifactory/oracle/`, excluded from the edit
allowlist) and `place_target()` scaffolds the target (default `rust/<crate>/`
coexisting with Python). `resolve_generation_language(spec)` returns
`target_language`, bypassing repo detection (fixes "generates in the repo's native
language"). `core/migration_mapper.py` feeds the coder each
`source_module → target_module` pair with the read-only source, its extracted
signatures, and the relevant golden-corpus slice as acceptance examples. The
existing mutation ledger / AI-merge subsystems are reused unchanged (target files
are net-new creates).

### 5.4 Differential verification + honest reporting (TFactory)

A new `equivalence` lane + `differential` framework (`agents/equivalence_runner.py`):
(0) capture the oracle (§5.2); (1) feed the *same* corpus inputs to the legacy
source (replay) and the new target (run in the RFC-0005 Nix env), comparing
structurally with numeric tolerance and an explicit error-class map; (2) a
`parity_ratio` verdict with critical-vector gating. Native target lanes
(`cargo test`) and mutation (`cargo-mutants`, added to `mutation_dispatch.py`)
still run.

Per **RFC-0006**, the lane maps to **VAL-2** (it exercises the assembled artifact
against real reference behavior in an ephemeral env). The crux is honesty about
**partial** parity: the verification gate folds `parity_ratio` and the
uncovered-module count into the `claim`, and uncovered modules are emitted as
`not_run` with `reason`/`risk`. A 95%-parity run can **never** read as full
equivalence.

## 6. Contract changes (RFC-0002, additive)

All changes are additive; **`contract_version` stays `"2"`** — every new field is
optional or a wider enum on an open object, so existing v2 consumers ignore
unknowns. Landed in `apis/task-contract.schema.json`:

- `provenance.base_ref` + `provenance.baseline_commit` — the tree the plan was
  grounded on.
- top-level `change_mode` — `greenfield | modify | migration` (the recon verdict,
  distinct from `workflow_type`, the work-shape).
- `environment.source_language` + `environment.target_language` — migration only;
  `environment.language` stays populated (= target) for old consumers.
- top-level `baseline` (`$defs.baseline`) — the RepoMap summary (repo, base_ref,
  commit, available/error, languages/versions, iac/iac_resources, layout,
  existing_test_command, entrypoints, conventions, dependency_graph,
  blast_radius).
- `tfactory.equivalence` (`golden_corpus_ref`, `parity_threshold`,
  `differential_lanes`, `module_map`) + `"equivalence"` added to `tfactory.lanes`.
- Already-present fields now actually populated: `subtask.files_to_modify` /
  `files_to_create` / `patterns_from`, `tfactory.ac_to_code_map`,
  `environment.language` / `toolchain`.

**Schema-drift note:** the schema is vendored twice — canonical here and a copy in
`PFactory/apps/backend/plan/emit/contracts/task-contract.schema.json` (the copies
already differ). Every delta must be applied to both, the structural-fallback
enums in `PFactory .../plan/emit/task_contract.py` updated, and a CI diff added to
PFactory to keep them in lockstep.

## 7. Smooth for users

The user contract is unchanged: **spec + repo + base branch**. Reconnaissance is
automatic and degrades silently to greenfield when the repo is unreachable. For a
rewrite the planner auto-detects migration and asks at most one placement
question. In every case the reviewer approves a plan grounded in real
findings — the `baseline` summary and the surfaced footprint — rather than prose.

## 8. Phasing

1. **Schema + RFC** (this hub): additive deltas + this document. *(landed in this change)*
2. **PFactory plumbing**: thread `repo`/`base_ref` from ingest → session →
   `process()`; add the `RepoMap` model.
3. **PFactory reconnaissance**: `clone.py`, `reconnoiter.py`, `iac_probe.py`;
   wire into `process()`. *First visible increment — Scenario A grounding.*
4. **PFactory classify + reconcile**: `change_mode.py`, `language_reconcile.py`
   + the `language-reconciled` check.
5. **PFactory delta-aware emit**: `delta.py`; language from RepoMap; populate
   footprints + `ac_to_code_map`; approval-hash digest; `change-footprint-surfaced`
   check; vendored-schema sync + drift CI.
6. **Migration (Scenario B)**: PFactory migration planner + `source_inspector`
   → TFactory equivalence lane + RFC-0006 honesty → AIFactory rewrite mode.

## 9. Risks

- **Untrusted-code execution** — mitigated by the §2 bright line; oracle capture
  confined to TFactory's existing locked sandbox. A test asserts no detected
  build/install command is ever invoked during recon.
- **Schema drift between the two copies** (a present bug) — fixed by applying
  deltas to both plus shipping the diff CI in the same change.
- **Golden-corpus fidelity / partial parity** — statically-derived vectors may
  under-cover; report public-surface coverage explicitly, treat uncovered modules
  as `not_run` (never `passed`), allow property-based fuzz augmentation.
- **Non-deterministic behavior & cross-language semantics** (int overflow, float
  repr, Unicode, error taxonomy) — the capture env already freezes time/creds;
  nondeterministic vectors are quarantined as `unprovable`; the differential
  comparator carries a normalization + error-class map, and mismatches there are
  real findings, not comparator bugs.
- **Approval-hash churn** — include only stable recon facts (commit SHA +
  footprint), tested for idempotence.
- **Private-repo access** — recon needs a scoped read-only token; absent it,
  degrade to greenfield (documented env var).
- **IaC parser brittleness / monorepo cost** — `python-hcl2` behind a soft import
  with a tolerant-regex fallback; size caps and confine recon to spec-referenced
  paths.
