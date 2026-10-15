---
status: draft
issue: 3591
author: olafkfreund
---

# Intent: make rejected designs easy to find before proposing one again

## Problem

A design that was considered and rejected is recorded in the
`## Alternatives rejected` section of the spec that rejected it (14 files in
`spec/`) and in two RFCs (`docs/rfc/`, "Alternatives rejected" /
"Alternatives considered"). Nothing tells a later agent or contributor that
these sections exist or to read them before proposing a design, so the same
idea can come back without new evidence. #818's source material keeps a
`rejected/` directory for this; #3591 asks whether the hub needs one.

## Proposed outcome

Someone about to propose a design in the hub knows, from a place they read
anyway, where earlier rejections are recorded and how to search them in one
command. Whether that needs a central `rejected/` index is decided and the
decision is recorded.

## Affected users and systems

Agents and people writing `intent/`, `spec/` and RFCs in the Factory hub.
No code, CI or service.

## Constraints

- Docs only.
- Must not create a second copy of what the spec sections already say: a
  copy nobody is required to update goes stale.

## Open questions

None.
