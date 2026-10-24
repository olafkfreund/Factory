---
status: draft
issue: 322
intent: intent/2026-10-24-322-risk-acceptance.md
---
# Spec: accepted-risk entry for runtime isolation
**Design:** Add AR-001 to the risk-acceptance log (R-012, review 2027-04-24, six months). Update R-012 status, control-matrix rows (Runtime isolation, line 36 and 59), and runtime-isolation.md gaps 1 and 7.
**Evidence:** netpol `factory-gitops apps/factory-namespace/manifests/networkpolicy-sandbox-jobs.yaml:100`; Kyverno Enforce `apps/kyverno-policies/manifests/verify-factory-image-signatures.yaml:206`; Job seccomp/non-root `AIFactory apps/backend/core/job_dispatch.py:633-635`.
**Triggers:** untrusted multi-tenant workloads; runsc supports nix builds. Known residual: #517 3-5s egress window at pod start.
**Rejected:** forcing gVisor now (breaks nix builds); silently leaving R-012 open (no owner decision).
**Risks:** acceptance is time-boxed; lapses to open at the review date.
**Verification:** grep file:line citations resolve; markdown renders.
