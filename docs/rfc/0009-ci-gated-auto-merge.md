---
layout: default
title: "RFC-0009: Provider-Agnostic CI-Gated Auto-Merge"
permalink: /rfc/ci-gated-auto-merge/
---

# RFC-0009 — Provider-Agnostic CI-Gated Auto-Merge

> **Status:** Proposed · **Created:** 2026-06-18 · **Extends:** [RFC-0001](./0001-correlation-key-and-completion-event.md) (correlation key), [RFC-0002](./0002-task-contract.md) (contract), [RFC-0006](./0006-verification-assurance-levels.md) (assurance levels), [RFC-0008](./0008-autonomous-parr-completion.md) (autonomous completion) · **Affects:** AIFactory, TFactory, CFactory, PFactory
>
> A team submits intent; the pipeline builds it, the host's **own CI pipeline** runs on the PR, TFactory adds an independent verification **check**, and — when every required check is green and the change's assurance level clears the policy — the PR **auto-merges, with a human in the loop only where risk demands it.** The gate lives in the PR people already trust, and it works the same across **GitHub, GitLab, Azure DevOps, Bitbucket, Gitea** (and future hosts) behind one provider abstraction.

## 1. The goal — "green PR merges itself, honestly"

RFC-0008 makes a build *complete*. This RFC makes a completed build *land*: the
artifact is opened as a pull/merge request, the repository's existing CI runs,
TFactory's verdict is published as a first-class status check, and a policy
decides whether the merge happens automatically or waits for a human. Nothing
merges on red; nothing un-reviewed merges above its risk class.

This is the mature-team pattern — **required status checks + auto-merge** — with
an AI test factory added as one of the required checks. It is deliberately
*not* a bespoke merge engine: it leans on each host's native branch-protection,
checks, and auto-merge primitives.

## 2. What already exists (build on, don't rebuild)

- **AIFactory provider abstraction** — `runners/github/providers/` has a
  `GitProvider` protocol + a `ProviderType` enum (`github`, `gitlab`,
  `bitbucket`, `gitea`, `azure_devops`) with concrete **GitHubProvider,
  GitLabProvider, AzureDevOpsProvider** and a `factory.py`. PR create/merge,
  comments, labels, permissions are already provider-agnostic.
- **AIFactory `merge/auto_merger.py`** — auto-merge machinery (today it can merge
  without gating on the host's combined check status).
- **TFactory `agents/quality_gate.py`** — turns `verdicts.json` into a single
  pass/fail against a `.tfactory.yml` `quality_gate:` policy ("PR-native gate"),
  and tracks per-test **`ci_parity`** (`yes` / `mocked-subject` / `no`).
- **TFactory `tools/pr_status.py`** — posts a host commit status
  (`context: "TFactory / tests"`, `success`/`failure`). Opt-in today.
- **RFC-0006 assurance levels (VAL-N)** — the honest measure of how far a change
  was verified; the natural input to the human-in-the-loop decision.

## 3. The loop

```
intent → PFactory plan (signed contract, RFC-0002)
       → AIFactory build → open PR/MR (provider.create_pr)
            │
            ├── host CI runs on the PR (build/lint/unit)      ── required check: "ci/*"
            └── TFactory runs its lanes → quality_gate →
                provider.post_check(context="TFactory / tests") ── required check: "TFactory / tests"
            │
       merge policy: all required checks green
                     AND assurance ≥ policy floor (RFC-0006)
                     AND required approvals satisfied (by risk)
            │
       provider.enable_auto_merge() / merge when gate clears
            → merged; CFactory threads PLAN→CODE→TEST→MERGED by issue (RFC-0001)
```

## 4. The provider contract (extension)

Add a small, host-neutral capability set to the existing `GitProvider` protocol
so every host implements the same gate. Each maps to the host's native API:

| Capability | GitHub | GitLab | Azure DevOps |
|---|---|---|---|
| `post_check(sha, context, state, summary)` | Checks API / commit status | commit status / pipeline status | PR status |
| `get_combined_status(sha) -> {context: state}` | combined status + check-runs | commit statuses + pipeline | PR policy evaluations |
| `set_required_checks(branch, contexts)` | branch protection | push rules / approval rules | branch policies |
| `enable_auto_merge(pr, method)` | native auto-merge / merge queue | "Merge when pipeline succeeds" | auto-complete |
| `required_approvals(pr) -> int satisfied?` | reviews | approval rules | required reviewers |

Hosts that lack a primitive degrade explicitly (e.g. no native auto-merge →
the orchestrator polls `get_combined_status` and merges when green), never
silently. Unknown providers are a named error, not a guess.

## 5. The merge policy (where the human goes)

A change auto-merges iff **all** hold; otherwise it waits for a human, with the
reason surfaced:

1. **All required checks green** — host CI + `TFactory / tests` (+ any others).
2. **Assurance floor met** — the change's RFC-0006 VAL level ≥ the repo's policy
   floor. A change TFactory could only lint (VAL-low) does not auto-merge even if
   "green"; it requires a human. Honesty rule carried forward: never auto-merge
   on a green that was never really exercised (`ci_parity != yes` blocks auto).
3. **Approvals by risk class** — trivial/low-risk (docs, config, small diffs):
   zero human approvals. Standard: one approval or auto if assurance is high.
   High-risk (auth, data-migration, infra, public surface): always human.

Policy lives in `.tfactory.yml` (gate thresholds) + a repo merge-policy block;
defaults are conservative (human-in-the-loop unless explicitly opted out).

## 6. CI/CD pipeline creation (the `cicd` subtask, reframed)

RFC-0008 / #616 makes AIFactory's coder treat `testing`/`cicd` subtasks as
**handoff** (it no longer fails the build on them). This RFC gives the `cicd`
subtask a real home: AIFactory should **generate a host-appropriate pipeline**
(`.github/workflows/*.yml`, `.gitlab-ci.yml`, `azure-pipelines.yml`, …) from the
contract's environment manifest (RFC-0005) so the host CI in §3 exists. The
pipeline is provider-templated; the provider abstraction picks the right file.

## 7. Honesty + safety (carried from RFC-0006/0008)

- **No merge on red, ever** — required checks are hard gates.
- **No auto-merge above risk** — assurance + approval policy is a hard gate.
- **No fake green** — `ci_parity` must be `yes` for an auto-merge path; a
  mocked-out subject blocks auto and flags for a human.
- **No silent host gap** — a provider missing a primitive degrades loudly.

## 8. Rollout

1. Extend `GitProvider` with `post_check` + `get_combined_status` (GitHub first,
   then GitLab + ADO); enable TFactory `quality_gate`/`pr_status` to post the
   `TFactory / tests` check.
2. Gate `auto_merger` on `get_combined_status` (all-green) + a conservative
   policy (human approval required) — prove the gate end-to-end on one repo.
3. Add the assurance floor (RFC-0006) + risk-classed approval policy; allow
   opt-in auto-merge for low-risk + high-assurance changes.
4. `set_required_checks` / `enable_auto_merge` per host; AIFactory generates the
   provider-appropriate pipeline (§6).
5. CFactory: add a MERGED stage to the work-item timeline; surface the gate state
   (which checks green/red, why a merge is held).

## 9. Acceptance

A built change opens a PR/MR on any supported host; the host CI + the
`TFactory / tests` check both run; a low-risk, high-assurance, `ci_parity=yes`
change auto-merges with no human; a high-risk or under-verified change is held
with a named reason and waits for approval — and the same behaviour is
observable on GitHub, GitLab, and Azure DevOps without pipeline-specific code in
the orchestrator.
