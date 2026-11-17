---
status: approved
issue: 3737
author: olafkfreund
---

# Intent: git metadata baseline for PFactory and TFactory

## Problem

AIFactory records a baseline of the repo-local git config that can run a program
(`merge.*`, `filter.*`, `diff.*`, exec-bearing keys, `info/attributes`) when it creates a
worktree, and refuses to continue when an agent changes it (`core/git_metadata.py`,
#1746, #1747). PFactory and TFactory have no baseline. Their agents can add a
`merge.<x>.driver` or `filter.<x>.smudge` and bind it in `.git/info/attributes`; the
empty pins from `merge_driver_pins` stop a program that exists when the pins are
computed, but nothing tells the operator the config was tampered with, and a key added
between the probe and the git call is not caught.

## Proposed outcome

PFactory and TFactory record a baseline at worktree creation and verify it before every
agent-facing git call that already computes `merge_driver_pins`. A changed key,
a changed `info/attributes`, or a changed worktree config stops the operation with an
error that names the key and the re-baseline command. The logic lives once in the hub
`agent_sandbox` package (vendored behind the `.hub-sha` drift gates) and is bound as the
optional `check` that `merge_driver_pins` already accepts.

## Affected users and systems

Factory hub `shared/factory-sandbox`; PFactory and TFactory `core/worktree.py`,
`core/child_env.py`, `core/workspace/git_utils.py`, `tools/git_writer.py`; AIFactory
re-vendors only (it keeps its own `core/git_metadata.py`).

## Constraints

- Hub first, then vendor byte-identical copies; no hand edits of vendored files.
- The base-SHA records of the AIFactory module are not ported (no PF/TF reader).
- Web-server routes that run git on a user's own repository are not bound: a user edit
  of `.git/config` must not block the UI.
- No secret handling; stdlib only.

## Open questions

None. Decided under the owner delegation of 2026-11-17: port into the hub package, not
per service, because the hub already owns `merge_driver_pins(check=...)`; AIFactory keeps
its own module until a later dedup.
