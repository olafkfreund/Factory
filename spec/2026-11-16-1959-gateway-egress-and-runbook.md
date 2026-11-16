---
status: approved
issue: 1959
intent: intent/2026-11-16-1959-gateway-egress-and-runbook.md
---

# Spec: Model gateway: upstream egress policy, owner runbook, recorded decisions

## Design

Add NetworkPolicy `allow-provider-egress` to namespace `gateway`: egress TCP 443 to `0.0.0.0/0` except `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `100.64.0.0/10`, for pods labelled `app: model-gateway`. Add `docs/model-gateway.md` with the decisions and owner steps (secrets only from files, shredded after).

## Alternatives rejected

Plain `0.0.0.0/0:443` (opens the Kubernetes API and the LAN). Pinned provider ranges (none published, breaks silently). Egress proxy with host allowlist (a new component; the recommended residual is accepted, as the stage-1 comment states). Dropping codex/copilot/gemini (a product decision, not made).

## Risks

A compromised gateway can reach any public HTTPS host; mitigated by the manifest-literal upstream, no redirects and a signature-verified image. The policy is additive to default-deny.

## Verification

`kustomize build apps/model-gateway/manifests` renders four policies; manifest-validate CI; after sync, `kubectl -n gateway get networkpolicy` shows it (read-only). The authenticated 200 is the owner's step 5.
