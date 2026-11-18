---
status: approved
issue: 1959
author: olafkfreund
---

# Intent: gateway admission proofs, client wiring check, provider-key report in CI

## Problem

Epic Factory#1959 (model gateway) has acceptance 5: the gateway image must show a PASS row in the
Kyverno PolicyReport (not merely no failure), and a deliberate unsigned tag must be denied. Nothing
repeatable checks either today, and the deny has only been tried by hand, with nothing recorded or repeatable. Separately, the per-service
migration flags (AIFactory#2070, TFactory#1520, CFactory#513, wired by factory-gitops#365) have no
guard that keeps their wiring intact, and `scripts/verify-no-provider-keys.sh` (AC-1, 18 violations
live today) runs only by hand, so the count is invisible in review.

## Proposed outcome

- A cluster-free-testable script `scripts/verify-gateway-policyreport.sh` (report mode, `--strict`
  later) that reports the gateway PolicyReport rows and whether the deployed gateway image has a PASS
  row from policy `verify-factory-image-signatures` whose message names that exact image (a
  "verified from cache" row does not count). An unavailable report is reported as such, never as zero
  findings. Its fixture test runs in CI.
- Live read-only evidence on #1959: a PASS row for `sha-24184c6-gateway`, and a server-side dry-run
  of a Pod with an existing unsigned tag in namespace `gateway` denied by admission, the denial
  attributed to `verify-factory-image-signatures` ("no signatures found"), and the same Pod spec with
  only the image changed to the signed gateway tag admitted as the control (both observed live today). Nothing is created. The procedure is in docs/model-gateway.md.
- A CI check that the three client Deployments keep their optional gateway Secret refs and that the
  task-Job egress policy keeps its gateway 8080 peer. Any gap found today is fixed; none is expected.
- `verify-no-provider-keys.sh` gains an explicit static input (rendered Deployments from a file; Jobs
  stay live-only, so zero Jobs is allowed only in that mode and is printed as `static`), reusing the
  existing classification. CI runs it as a report-only step (non-blocking) that prints the count
  from the rendered manifests and says so loudly when it could not inspect (never a silent 0), and docs/model-gateway.md states when to switch it to `--strict`.

## Affected users and systems

factory-gitops scripts, one CI workflow, docs/model-gateway.md; Factory hub artifacts. Live cluster:
read-only `get` and server-side dry-run only.

## Constraints

- Create or seed no Secret, restart no Deployment, run no Plane B bench test, rotate no key.
- No acceptance box on #1959 is ticked without live proof; the epic stays open.
- Everything migration-related stays off. The CI report step must never block a PR.
- Scripts print names and counts, never values.

## Open questions

None. Decision (owner delegation 2026-11-18): CI has no cluster, so its report runs against the
rendered Deployments (Jobs are built by service code and stay covered by the live run); the output
says `static` so the two counts are not confused. Chosen as the least risky way to make the count
visible without giving CI cluster credentials.
