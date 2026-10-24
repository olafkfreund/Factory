---
status: approved
issue: 322
author: olafkfreund
---
# Intent: accept runtime-isolation baseline as the control (#322)

**Problem:** #322 asks for gVisor/microVM on untrusted-code Jobs; #274 deferred it (nix local builds fail under runsc). The register shows R-012 "Partially mitigated" with no decision, and there is no CIS baseline.
**Outcome:** The live baseline is formally accepted as the isolation control, with revisit triggers and a review date, so #322 can close.
**Affected:** `docs/compliance/` risk-register, control-matrix, policies/runtime-isolation.md.
**Constraints:** Claim only controls with file:line evidence. No new frameworks.
**Decided (lead, user-approved 2026-10-24):** accept baseline; gVisor/microVM are revisit triggers; CIS recorded "not assessed; kube-bench run is the revisit action".
**Open questions:** None.
