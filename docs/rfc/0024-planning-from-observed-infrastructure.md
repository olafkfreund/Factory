---
layout: default
title: "RFC-0024: Planning from Observed Infrastructure — read the account, not just the repo"
permalink: /rfc/planning-from-observed-infrastructure/
---

# RFC-0024 — Planning from Observed Infrastructure

> **Status:** Proposed · **Created:** 2026-08-25 · **Owner:** PFactory (`apps/backend/pfactory_secrets/`), consumed by the planner ·
> **Extends:**
> [RFC-0013](./0013-deployment-aware-planning.md) (deployment-aware planning — this moves it from *declared* to *observed*),
> [RFC-0010](./0010-code-aware-planning-and-behavioral-equivalence.md) (code-aware planning — same argument, different input),
> [RFC-0007](./0007-access-and-credential-provisioning.md) (access provisioning — the credential posture) ·
> **Affects:** PFactory's planner; `pfactory_secrets/broker.py`; the RFC-0002 task contract if §5 goes one way rather than the other.

## 1. Motivation

RFC-0013 made planning deployment-aware **from files**: PFactory discovers IaC in
the repo and writes a `deployment` block into the contract. That is a real
improvement and it has a ceiling — the repo describes what someone *intended* to
deploy, and the account holds what is *actually running*.

The gap between those two is where bad plans come from:

| The card says | The repo says | The account says | The plan should |
|---|---|---|---|
| "add a queue" | nothing | SQS already in use | use SQS, not propose Kafka |
| "migrate the schema" | three RDS modules | one is behind `api-prod` | name which one |
| "give the service S3 access" | no IAM | the role exists, already has it | do far less than the card implies |

A planner that cannot see the third column proposes work that is redundant,
misdirected, or larger than needed. Nothing catches that: the plan is coherent,
the build implements it, the tests pass, and the result is wrong in a way no
gate is looking for.

## 2. The capability already exists and is not connected

`apps/backend/pfactory_secrets/` is a complete secrets layer: a
`CredentialBroker` with `resolve_cloud(provider)` for `gcp` / `aws` / `azure` /
`kubernetes`, vault and AWS Secrets Manager backends, an egress gate, and a CLI.

Every importer of it lives **inside `pfactory_secrets/` itself**. A grep across
`agents/` and `planner_lib/` for `CredentialBroker`, `resolve_cloud` or
`pfactory_secrets` returns nothing. The planner never touches it.

So this RFC is not "build cloud access for PFactory". It is "connect two things
that already exist, under a permission model that makes it safe". That is a much
smaller and much more reviewable change than it first appears.

## 3. Read-only must be structural, not a convention

TFactory logs in to **deploy and verify** — it legitimately mutates, and RFC-0013
constrains it by *verb*: `ProductionApplyError` on effectful operations, VAL-4
never autonomous.

A planner has no reason to mutate anything, ever. So the constraint should be
stronger and sit one layer lower:

- **A distinct credential.** The planner resolves a `plan-readonly` role, not the
  verification role with better manners. Same-credential-different-intent is one
  bug away from a production change, and the bug would be in an LLM-driven code
  path.
- **Deny by IAM, not by code.** The role's policy is read-only. Then a planner
  defect is a 403, not an incident. Code-level verb filtering is a second line,
  not the first.
- **No credential materialisation to disk unless a tool needs a file.** The
  broker already writes kubeconfig/ADC JSON at 0600 and wipes on close; planning
  should prefer the env path and take the file path only where a CLI demands it.

The asymmetry is the point: verification earns broader access by running in a
sandbox against a reference deployment. Planning runs on every card.

## 4. Egress stays off by default

The broker is already off unless `egress.enabled` (RFC-0007 design decision D4),
and that default should not be relaxed for planning. Two reasons specific to this
use:

**Frequency.** Planning runs far more often than verification — every card, every
re-plan. An always-on cloud read is a different cost and audit profile from an
occasional one.

**Blast radius of a mistake in the other direction.** A planner that silently
fails to reach the account should produce a plan that says so, not one that
quietly reverts to repo-only planning and reads identically. See §6.

## 5. What gets observed, and where it goes

Scope the first cut to **inventory**, not metrics or logs:

```
compute     instances / services / functions, by name and tag
storage     buckets, volumes, databases (existence and engine, NOT contents)
network     vpcs, subnets, load balancers, DNS records
identity    roles and their attached policies (to answer "does this already exist")
k8s         namespaces, deployments, services, ingresses
```

**Never** object contents, database rows, secret values, or logs. The planner
needs the shape of the estate, not the data in it.

Two open placements (§8): a new `observed` block on the RFC-0002 contract
alongside `deployment`, or a planner-only context that never persists. The first
is auditable and joinable; the second cannot leak an account inventory into a
repo.

## 6. An unreachable account must be visible in the plan

This is the failure mode this RFC most needs to avoid, and the fleet has a
history with it: a capability that fails open and silently degrades looks exactly
like one that was never asked for.

Four instances this week are catalogued in Factory#971 — a terminal status
recorded where nobody reads it, a lane whose progress field never advanced,
evidence that uploaded nowhere. Every one failed toward "looks fine".

So: when cloud observation is enabled and does not succeed, the plan records
`observed: {status: "unavailable", reason: ...}` and the planner says in its
output that it planned without it. A plan that silently reverts to repo-only is
indistinguishable from a plan that never needed the account, and the reader
cannot tell which they are holding.

## 7. Phases

| Phase | Delivers | Done when |
|---|---|---|
| 0 | wire `CredentialBroker` into the planner, still gated off | a planner run with egress enabled resolves a credential and logs it |
| 1 | read-only role + IAM policy for one provider (AWS) | an effectful call returns 403 from the provider, not from our code |
| 2 | inventory collection for that provider | a plan cites a real resource that is not in the repo |
| 3 | `observed` placement decided (§8) + unavailable-path (§6) | a blocked account yields a plan that says so |
| 4 | second provider (GCP or k8s) | the collector interface survives a provider it was not designed against |

Phase 4 is scheduled, not deferred, for the reason RFC-0023 gives: an interface
with one implementation is an interface nobody has tested.

## 8. Open questions

1. **Where does `observed` live?** Contract block (auditable, joinable, and now
   an account inventory sits in a repo) or planner-only context (safer, invisible
   to review). This RFC does not settle it.
2. **Which account does a card map to?** Multi-account estates are the norm. The
   repo does not say, and guessing wrong means planning against the wrong
   environment — worse than not planning against one at all.
3. **How stale may an observation be?** Cache it and the plan may cite a resource
   deleted an hour ago; do not, and every card pays a round trip.
4. **PFactory's broker is a FORK of TFactory's, not a vendored copy** — they
   differ today. Does the cloud-read path become hub-canonical, or stay forked?
   Getting this wrong reproduces the drift class in Factory#971.

## 9. What this does not do

- **No writes, ever** — not behind a flag, not for "just this once". §3.
- **No secret or data reads.** Inventory only. §5.
- **Not a replacement for RFC-0013.** Declared deployment stays the contract's
  backbone; observation informs the plan, and where the two disagree that
  disagreement is itself worth surfacing rather than silently resolving.
