# Multi-language hardening pass (2026-06-14)

A five-language "hello world" smoke run (Go, Rust, Java, C++, Python — each a
greeting library + CLI, one per language) was used to exercise the full PARR
pipeline end to end. The run surfaced a chain of real defects across all four
services; this note records what was found, what shipped, and what remains.

## Goal

Drive five small, independent specs through PFactory (plan + sign) -> AIFactory
(code) -> TFactory (verify) with live CFactory visibility, and confirm each
language is planned, built, and tested correctly.

## Defects found and fixed

| # | Service | Defect | Fix |
|---|---------|--------|-----|
| 1 | TFactory | `/api/tasks` rows omitted the PARR correlation key, so the cockpit could not attach a TFactory task to its work item — the **test-stage lane stayed empty**. | #377: `_resolve_correlation_issue()` populates `TaskMetadata.githubIssueNumber` from the RFC-0002 contract / `source.json`. |
| 2 | AIFactory | A `blocked` subtask status was outside the `Subtask.status` Literal, so one blocked subtask 500'd the **entire** `/api/tasks` list — blinding the cockpit. | #583: add `blocked` to the Literal. |
| 3 | AIFactory, PFactory, TFactory | An unpinned `fastapi>=…` pulled `0.137.0`, which broke route introspection (`prometheus get_route_name` -> `_IncludedRouter` has no `.path`) and **500'd every `/api` route**. | Pin `fastapi==0.136.3` / `starlette==1.3.1` fleet-wide (TFactory #377, AIFactory #584, PFactory #143). |
| 4 | AIFactory (infra) | The coder pod was OOMKilled running 5 concurrent agents at a 2Gi limit (node has 96Gi). | GitOps: raise the memory limit to 12Gi. |
| 5 | PFactory | The RFC-0001a evidence gate marked a successful **trusted-plan** handoff `failed` because it created no GitHub issue (by design) — a false `plan stage failed` anomaly. | #143: count a started `aifactory_task_id` as evidence (`proof_kind: "contract"`). |
| 6 | AIFactory | The planner matched the **existing repo's** language over the spec's, so a Rust/Java/C++ spec dropped into a Go repo silently produced Go and was marked complete. | #585: `planner.md` PHASE 0.0 — the spec's language wins; scaffold it or HALT with a `LANGUAGE CONFLICT`. |
| 7 | AIFactory (image) | The coder sandbox shipped only `g++`/Python/Node — Rust/Go/Java/CMake specs could be written but not built or tested (`cannot execute cargo`). | #586/#587: `apk add go-1.25 rust-1.90 maven-3.9 openjdk-21-default-jdk cmake build-base` with a fail-fast build-time verification. |
| 8 | AIFactory | Successful parallel builds were reported `failed`: `mark_complete` loaded the plan from the worktree spec dir and swallowed the error when it was absent, leaving the canonical plan at 0 completed. | #588: `record_subtask_completion()` falls back to the canonical source plan and never fails silently. |

## Validated

After #585 + #586/#587, a clean re-run (one empty repo per language) produced the
**correct language for all five** (was 1/5), and the toolchains build + test for
real — verified live in-pod: `go test ./...` -> ok, `cargo test` -> 6 passed.

## Open finding — AC fidelity (not yet fixed)

The coder deviates from the acceptance criteria: it reproduces well-known
tutorials (e.g. the "Learn Go with Tests" multi-language greeter), uses the wrong
function name/signature, drops the required `!`, and adds unrequested
dependencies — and it writes tests that assert **its own** implementation. So
"tests pass" does not mean "spec met". This is precisely what TFactory's
independent verification against the ACs is meant to catch; provisioning the same
toolchains into the TFactory image is the prerequisite for that.

## Operational notes

- `deploy.yml` has `paths-ignore: ['**/*.md']`; agent prompts live in
  `apps/backend/prompts/*.md` and are baked into the image, so a prompt-only PR
  merges without deploying — trigger it with `gh workflow run deploy.yml --ref main`.
- Deployments are ArgoCD-managed from `factory-gitops`; `kubectl patch` is
  reverted, so resource/config changes go through that repo.
