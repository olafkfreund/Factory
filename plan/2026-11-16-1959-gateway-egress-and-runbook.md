---
status: draft
issue: 1959
spec: spec/2026-11-16-1959-gateway-egress-and-runbook.md
coders:   # every file-editing step is done by the lead: small, security-sensitive edits where a handoff costs more than it saves
  all: lead
reviewers:
  - codex   # independent read-only review of the diff (agy is off by owner decision)
---

# Plan: Model gateway: upstream egress policy, owner runbook, recorded decisions

Decisions carried over from the approved spec:

Add NetworkPolicy `allow-provider-egress` to namespace `gateway`: egress TCP 443 to `0.0.0.0/0` except `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `100.64.0.0/10`, for pods labelled `app: model-gateway`. Add `docs/model-gateway.md` with the decisions and owner steps (secrets only from files, shredded after).

## Steps

1. factory-gitops `apps/model-gateway/manifests/manifests.yaml`: append `allow-provider-egress`, fix the DNS-only comment. Check: `kustomize build`.
2. factory-gitops `docs/model-gateway.md`: new runbook. Check: read; no secret values.

## Tests

`kustomize build apps/model-gateway/manifests | grep -c 'kind: NetworkPolicy'` is 4.

## Rollback

Revert the commit; egress returns to DNS only.
