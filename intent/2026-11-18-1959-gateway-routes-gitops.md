---
status: approved
issue: 1959
author: olafkfreund
---

# Intent: model-routes ConfigMap and verifiers in factory-gitops

## Problem

The gateway (AIFactory `apps/model-gateway/gateway.py`, v3.14.0, deployed) resolves a
capability class (`local|cheap|balanced|frontier`) to a model from a flat JSON file at
`GATEWAY_ROUTES_PATH`, re-read on every request, and answers `X-Model-Route`. factory-gitops has no
`model-routes` ConfigMap and nothing sets `GATEWAY_ROUTES_PATH`, so the epic's "a route change is a
config edit with no redeploy" (AC-2) cannot be shown. The two acceptance checks (AC-1: no provider
key anywhere; AC-2: hot reload) have no repeatable verifier, and the Plane B bench test is described
in one paragraph only.

## Proposed outcome

- ConfigMap `model-routes` (namespace `gateway`) is generated from the hub catalog
  `apis/model-catalog.json` at a pinned Factory main SHA, committed, and a CI job fails when the
  committed copy differs from a fresh render.
- The model-gateway image is bumped from `sha-1c4cc96-gateway` (no route resolver; measured: the
  live pods run it) to `sha-24184c6-gateway` (AIFactory 3.15.0 main, contains #2107/#2108 and the
  CodeQL header fix). Without this the ConfigMap would be ignored.
- The model-gateway Deployment mounts it as an optional volume and sets `GATEWAY_ROUTES_PATH`.
  The mount is a directory mount without `subPath` (subPath mounts never receive updates) and the
  root filesystem stays read-only. Two replicas stay Ready; NetworkPolicies and Kyverno coverage are unchanged.
- `scripts/verify-no-provider-keys.sh` (AC-1) and `scripts/verify-route-hot-reload.sh` (AC-2) are
  read-only, never print secrets, and have cluster-free shell tests. AC-1 checks model-provider keys
  only (not the gateway's own key, not third-party keys such as LANGCHAIN/RAPIDAPI), and lists
  accepted residuals (Plane C login-file volumes) separately from violations. AC-2 proves the
  route by the file each gateway pod sees and the pod UIDs, because `X-Model-Route` carries the
  class, which does not change when its model does; the owner makes the change as a Git PR synced
  by Argo (an imperative edit is reverted by selfHeal).
- `docs/model-gateway.md` states the route-selection rule and carries the Plane B bench test as an
  owner-run checklist with exact commands (not run by us).

## Affected users and systems

factory-gitops (`apps/model-gateway`, `scripts/`, `docs/`, `.github/workflows`); the live
model-gateway Deployment (rolls once when the pod template changes); the owner (runs the bench test
and AC-2 edit); Factory hub catalog (read only).

## Constraints

- Nothing that needs an owner secret is enabled. `AIFACTORY_PHASE_ROUTES` and `AIFACTORY_RUNTIMES`
  stay unset. The volume is `optional`, so a missing ConfigMap cannot stall the rollout.
- ArgoCD selfHeals: changes only through PRs. No `kubectl apply`.
- The repo is public; verifiers read tokens only from files and never print them.
- Acceptance boxes on Factory#1959 are not ticked and the epic stays open.

## Open questions

1. The catalog holds Claude model ids and two placeholder ids (`ollama:<model>`,
   `ollama-cloud:<model>`), but the gateway's only upstream is Ollama Cloud, which cannot serve
   Claude ids. Recorded decision (owner delegation 2026-11-18): render the catalog rule as asked, skip
   placeholder ids, and add an optional committed overrides file so the owner can pin concrete
   upstream ids. The gateway rewrites a request only when its `model` is literally a class name; no client sends one
   until the owner enables `AIFACTORY_PHASE_ROUTES`, so existing traffic is unchanged. A class request
   before overrides exist would forward a Claude id to Ollama Cloud and fail, which the doc states.
