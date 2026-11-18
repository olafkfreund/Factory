---
status: draft
issue: 1573
author: olafkfreund
---

# Intent: A missing runner image must not grade tests as failed

Issue: olafkfreund/TFactory#1573. Related, out of scope: TFactory#1574.

## Problem

When the docker runner image (`tfactory-runner-pytest:latest`) is absent,
`docker run` exits 125. TFactory treats 125 as a test result: every run is
`consistent_fail`, all tests are rejected, and a handback tells AIFactory to
fix code that is fine. Seen on aifactory-demo PR #610 (6/6 rejected, level 1 of
the 2026-11-18 e2e campaign). Same class as closed #1401 (exit 127).

The cluster deploy is not the cause: its pod has no docker binary and runs the
Nix Job / host-venv path. The campaign's `tfactory` MCP server runs the pipeline
in a local process on the workstation, which has docker but no runner images.

## Proposed outcome

Exit 125 is an environment error: the test is `not_run`, never a reject, and
never reaches a handback as a code defect. Applies to every lane and mutation
probe that already special-cases 126/127.

## Affected users and systems

TFactory verify on any host with a container runtime (workstation MCP,
docker-mode installs). e2e campaign levels 2 to 8 run there now.

## Constraints

Smallest change, no new classification path. Merges and release pre-approved.
Release restarts the live tfactory pod, so announce on the agent bus first and
wait for any running verify.

## Open questions

None. Pulling the published `ghcr.io/olafkfreund/tfactory-runner-*` images on
the workstation is a host action, not part of the code change.
