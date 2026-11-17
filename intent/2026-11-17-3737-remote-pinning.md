---
status: approved
issue: 3737
author: olafkfreund
---

# Intent: pin remotes other than origin

## Problem

The remote-program pins from #3709 name `remote.origin.*` only
(`-c remote.origin.uploadpack=git-upload-pack` and `receivepack` on fetch and push).
An agent can add a second remote with `remote.<name>.uploadpack=<program>` (or a
`remote.<name>.vcs` helper) and fetch or push it. Checking the claim on git 2.54 also
shows the origin pins do not work: git keeps the first value of `uploadpack` and
`receivepack`, and the repo file comes before `-c`, so a configured program still runs.

## Proposed outcome

No remote, `origin` included, can run a repo-configured program on fetch or push from a
sandboxed call, for keys present when the call is prepared (a key added concurrently after
the probe is not covered, as for the other pins). A repo that sets such a key is refused with an error naming the key.

## Affected users and systems

Hub `agent_sandbox.git_pins.merge_driver_pins`; every service that calls it before git
(PFactory, TFactory git writer and merge paths; AIFactory only vendors it).

## Constraints

- A refusal, not a pin, because a `-c` override cannot beat the repo file and `.vcs` cannot
  be blanked. Fail closed, as the other pins do.
- A repo that legitimately sets `remote.<name>.uploadpack` (rare) must run the
  re-baseline-free fix: unset the key.
- Hub first, then vendor.

## Open questions

None. Decided under the owner delegation of 2026-11-17: refuse rather than pin or rewrite
call sites with `--upload-pack`, as the least risky to operate.
