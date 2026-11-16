---
status: draft
issue: 1959
author: olafkfreund
---

# Intent: Model gateway: upstream egress policy, owner runbook, recorded decisions

## Problem

Epic #1959 has the gateway running (2 Pods) but unusable: no Secret, DNS-only egress, and no consolidated owner procedure. The owner delegated the open decisions to the recommendations on the issue.

## Proposed outcome

- Egress: the recommended option, TCP 443 to public addresses minus private, link-local and CGNAT ranges.
- Plane C (CLI login files) is accepted and documented as a residual.
- A runbook gives the owner the exact Secret and bench-test steps. Plane B stays blocked on the owner's bench test.

## Affected users and systems

factory-gitops `apps/model-gateway` and `docs/model-gateway.md`. Live: the gateway pods get an egress path, but without the Secret the gateway answers 503 and calls nothing.

## Constraints

No secret handled. Do not touch the live cluster beyond the Argo sync of this PR. CFactory manifest wiring waits for a CFactory release (none exists; live image is 0.1.0).

## Open questions

Plane B (`ANTHROPIC_BASE_URL` with OAuth) and the provider-terms question are the owner's.
