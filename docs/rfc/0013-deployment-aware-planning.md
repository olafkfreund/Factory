---
layout: default
title: "RFC-0013: Deployment-Aware Planning"
permalink: /rfc/deployment-aware-planning/
---

# RFC-0013 — Deployment-Aware Planning

> **Status:** Implemented (epic #147 closed) — contract `deployment` block, deploy verification profile, and the **DRY-RUN deploy lane are live in the TFactory kubejob verify pipeline**: `agents/verify_pipeline.py` calls `maybe_run_deploy_lane` between the evaluator and the triager on the reference deployment (`TFACTORY_VERIFY_EXEC=kubejob`). The lane only *triggers* when the contract's `deployment.risk_class == "high"` or `production_classification == "production"`; for repos with no IaC it no-ops. The live ceiling is **VAL-2** (dry-run/plan) by code, and VAL-4 (production apply) is never autonomous (`ProductionApplyError` on effectful verbs). The deployment-metrics MCP (DORA) remains an honest stub (`available: false`). · **Created:** 2026-06-20 · **Updated:** 2026-07-02 · **Extends:** [RFC-0002](./0002-task-contract.md) (contract), [RFC-0005](./0005-environment-manifest-and-toolchain-provisioning.md) (environment manifest), [RFC-0006](./0006-verification-assurance-levels.md) (assurance levels), [RFC-0009](./0009-ci-gated-auto-merge.md) (CI-gated auto-merge), [RFC-0010](./0010-code-aware-planning-and-behavioral-equivalence.md) (code-aware planning) · **Affects:** PFactory (discovers), AIFactory/TFactory (honor), CFactory (surfaces)
>
> The fleet already reads the code before it plans (RFC-0010) and verifies honestly against an assurance ladder (RFC-0006). What it does **not** yet understand is how a change **ships**: which CI system runs it, how it deploys, which environments it can reach, and how risky that is. This RFC makes planning **deployment-aware**. PFactory discovers the delivery surface, derives a risk/scan/system-gate policy from it, pulls best-effort DORA context from a deployment-metrics MCP, and records all of it in a new additive `deployment` contract block. Verification of a deploy is **DRY-RUN by policy**: production is **VAL-4 and never autonomous**.

## 1. The goal — "plan for how it ships, not just what it does"

Today a Task Contract describes the *what* (the plan), the *how* (the
environment manifest, RFC-0005), and the *verify* (the assurance ladder,
RFC-0006). It is silent on **delivery**. A change that edits a request handler
and a change that rewrites a production GitOps manifest look the same to the
planner — same risk, same gates, same verification floor. That is wrong: the
second can take down a service, and the fleet should know that **before** it
writes a line of code.

This RFC adds the missing dimension as a **single additive block**:

1. PFactory **discovers** the delivery surface from the repo (CI system, deploy
   mechanism, target environments) the same way RFC-0010 discovers code.
2. It **derives a policy** from that surface — a `risk_class`, the
   `required_scans`, and the `system_gates` that must clear before deploy.
3. It pulls **best-effort delivery health** (DORA) from a deployment-metrics MCP,
   which **degrades, never fabricates**.
4. It records a **DRY-RUN deploy-verification policy** that caps autonomous
   deploy verification well below a real production apply.

This is **composition over invention**: it reuses the contract envelope
(RFC-0002), the VAL ladder and honest-reporting shape (RFC-0006), the
per-artifact verification profiles, the RFC-0007 access classes for ephemeral
targets, and the provider abstraction of RFC-0009. It adds a thin discovery
layer, one contract block, one MCP contract, and one verification profile.

## 2. The `deployment` contract block

`deployment` is a new **OPTIONAL, top-level, additive** block on the Task
Contract (`$defs.deployment` in `apis/task-contract.schema.json`).
`contract_version` stays `"2"`. It is an open object: consumers that do not
understand it ignore it, so old contracts and old consumers keep working.

| Field | Meaning |
|---|---|
| `ci_system` | `github-actions` \| `gitlab-ci` \| `azure-pipelines` \| `none` — the detected CI provider. |
| `ci_exists` | A CI pipeline definition already exists in the repo. |
| `ci_pipeline_paths` | Paths to the discovered pipeline files. |
| `needs_pipeline` | The task must create/extend a pipeline (none usable exists). |
| `deploy_system` | `argocd` \| `helm` \| `terraform` \| `kubectl` \| `unknown` \| `none` — the deploy mechanism. |
| `deploy_target_environments` | Environments the change can reach, e.g. `["dev","staging","production"]`. |
| `production_classification` | `production` \| `preprod` \| `internal` \| `unknown` — highest blast-radius class. |
| `risk_class` | `low` \| `medium` \| `high` — drives the scan/gate floors (§3). |
| `required_scans` | Scans that MUST run before deploy, e.g. `["sast","iac-scan","secret-scan"]`. |
| `system_gates` | Named pre-deploy gates that MUST pass, e.g. `["ci-green","human-approval"]`. |
| `dora_context` | Best-effort DORA delivery context from the metrics MCP (§4). |
| `readiness` | Deploy-readiness checklist; every non-pass carries a `reason` (§5). |
| `deploy_verification` | The DRY-RUN deploy-verification policy (§6). |

Absent `deployment` => the task has no deployment dimension (a library change, a
docs PR). The block is documented in the contract spec under
[RFC-0002 §2.1](./0002-task-contract.md).

## 3. Risk, scans, and system gates (policy)

`risk_class` is derived deterministically from the discovered surface plus the
RFC-0010 `baseline.blast_radius`:

- **high** — `production_classification: production`, OR `destructive_iac` is
  non-empty (resource replacement/destruction), OR the change edits the deploy
  pipeline itself.
- **medium** — reaches `preprod`/`staging`, or touches deploy manifests without
  destructive IaC.
- **low** — internal-only, no deploy-manifest changes.

The class sets **floors** (a planner may add scans/gates, never remove the
floor):

| `risk_class` | `required_scans` floor | `system_gates` floor |
|---|---|---|
| low | `secret-scan` | `ci-green` |
| medium | `secret-scan`, `sast`, `dependency-audit` | `ci-green` |
| high | `secret-scan`, `sast`, `dependency-audit`, `iac-scan` | `ci-green`, `human-approval` |

`production_classification: production` always carries `human-approval` — the
production path is **never autonomous** (§6). These gates compose with the
RFC-0009 CI-gated auto-merge policy: a `high`/production change cannot
auto-merge, and the required scans surface as required checks on the PR.

## 4. The deployment-metrics MCP (`dora_context`)

`dora_context` is populated from a small, provider-agnostic **deployment-metrics
MCP** (contract: `apis/deployment-metrics.mcp.md`) with two tools:

- `deploy_history(repo, env?)` — recent deploy events, newest first.
- `dora_metrics(repo, env?)` — DORA delivery context (success rate, lead-time
  p50, change-fail rate, last deploy) — the exact shape of
  `$defs.deployment.dora_context`.

The MCP is **stubbed now, real provider later**. The dependency-free reference
provider is `scripts/deployment_metrics_stub.py`. Its defining property is
**honesty**: with no backend it returns `available: false` with a `reason` and
**null** metrics — it **degrades, never fabricates**. A real provider (GitHub
Deployments / Argo CD / Datadog) implements the same two tools behind the same
envelope, so PFactory adopts it with no change.

Normative consequence: `available: false` means delivery health is **UNKNOWN**,
not healthy. The §3 policy **never relaxes a gate** on the strength of missing
metrics.

## 5. Deploy readiness

`readiness` is a checklist of deploy preconditions (`ci-pipeline-present`,
`rollback-defined`, `secrets-provisioned`, `scans-configured`, …). It mirrors the
RFC-0006 honest-reporting shape: each entry has a `status` of `pass` / `fail` /
`not_run`, and **every `fail`/`not_run` MUST carry a `reason`** (enforced in the
schema). Each non-pass may also carry an `action` — the remediation the planner
recommends. This is the deploy analogue of the verification block: it never
claims readiness it cannot show.

## 6. DRY-RUN verification policy (production = VAL-4, never autonomous)

Deploy verification maps onto the RFC-0006 VAL ladder via a new `deploy`
artifact profile (`scripts/verification_profiles.py`):

| Level | Deploy meaning |
|---|---|
| VAL-0 | Pipeline/manifest lint (actionlint, gitlab-ci-lint, schema check). |
| VAL-2 | **Dry-run**: `helm template`, `terraform plan`, `kubectl --dry-run`. |
| VAL-3 | Apply to a **disposable/ephemeral** target the pipeline owns, assert healthy, tear down (RFC-0007 class C). |
| VAL-4 | Production apply — **never run by the fleet.** |

The profile's planned ladder **caps at VAL-3 by design**: there is no autonomous
VAL-4 rung. `deploy_verification` records the policy as `target_level` plus a
`mode` (`dry-run` / `plan-only` / `ephemeral-apply` / `production-apply`). For a
production change, deploy verification stops at a dry-run/plan, and the real
`production-apply` (VAL-4) is held behind the `human-approval` system gate from
§3. The fleet proves the deploy *would* work; a human authorizes the deploy that
*does*.

The live deploy lane (`agents/deploy_lane.py` +
`tools/runners/deploy_runner.py`) currently assembles only dry-run/plan steps —
`tofu init`/`validate` (VAL-0) and `tofu plan` with no apply (VAL-2),
`helm template`, `kubectl apply --dry-run` — so its **effective ceiling in the
running pipeline is VAL-2**. This is enforced in code, not by convention: any
step that would apply to a real environment raises `ProductionApplyError`
rather than run. VAL-3 (ephemeral-apply against a disposable target) remains the
design headroom above the live lane, and VAL-4 is never produced.

## 7. Compatibility

Strictly additive and back-compatible:

- `contract_version` stays `"2"`; the block and its schema def are optional and
  open (`additionalProperties: true`). Consumers ignore unknown fields.
- The `deploy` verification profile is new; existing artifact detection and
  profiles are unchanged.
- The deployment-metrics MCP is stubbed (`available: false`) by default — no new
  runtime dependency, no fabricated data.

## 8. Scope and delivery status

The foundation PR delivered the **contract + policy + stub**: the `deployment`
schema block, the MCP contract and dependency-free stub provider, the `deploy`
verification profile, and this normative spec.

Since then the consuming side has shipped. The **DRY-RUN deploy lane is wired
into the live TFactory kubejob verify pipeline**: `agents/verify_pipeline.py`
runs `maybe_run_deploy_lane` between the evaluator and the triager, and the
reference deployment runs with `TFACTORY_VERIFY_EXEC=kubejob`, so the lane
executes inside the per-verify Kubernetes Job. It is **conditional, not
per-task**: it only triggers when the contract's `deployment.risk_class ==
"high"` or `production_classification == "production"`, and for a repo with no
IaC it no-ops. The triager's deploy gate reads the lane's honest RFC-0006
verification block. In the running pipeline the lane caps at **VAL-2**
(dry-run/plan) by code, and a production apply (VAL-4) is never autonomous —
`deploy_runner.py` raises `ProductionApplyError` on any effectful verb (§6).

Still outstanding: DORA delivery history and the deployment-metrics MCP remain
honest stubs (`available: false`) pending a real provider; the VAL-3
ephemeral-apply rung (§6) is design headroom, not yet exercised in the live
lane.
