---
status: approved
issue: 1775
author: olafkfreund
---

# Intent: scope the correlation key to the repository, and let the newest task own a stage

Tracks olafkfreund/AIFactory#1775 and olafkfreund/CFactory#484 (one problem,
two repos).

## Problem

The RFC-0001 correlation key is the issue number on its own: `"7"`
(`docs/rfc/0001-correlation-key-and-completion-event.md` §2, "the integer
issue number rendered as a string"). An issue number only identifies an issue
inside one repository, so issue #7 in repo A and issue #7 in repo B get the
same key. CFactory then puts both on one work-item row and one card:

- AIFactory `apps/web-server/server/services/completion.py:206`
  `correlation_key()` returns `str(issue_number)`.
- CFactory `apps/backend/cfactory/card_intake.py:498` `_upstream_key` copies
  that rule to join a card at dispatch, and `cards.py:813`
  `get_by_correlation_key` returns the oldest card on the key, so the newer
  card never settles.
- CFactory's three poll adapters (`adapters/aifactory.py:47`,
  `pfactory.py:46`, `tfactory.py:131`) key polled rows on the bare issue
  number too.
- TFactory falls back to the bare number when it has no contract key
  (`agents/triager.py:728`, `agents/handback/send.py:83`).
- PFactory already qualifies the key for a plan that came from an issue
  (`plan/completion.py:61` `origin_key`, `owner/repo#7`), but falls back to
  the bare epic number. So today a hard-tier plan and its build don't even
  share a key: PFactory sends `owner/repo#7` and AIFactory sends `7`.

A second problem lives on the same row. Tasks with the same key share one
`work_items` row. CFactory#483 stopped a stalled task fighting its re-run by
using list order (`progress.py:121-134`) and task identity
(`store.py:567-572`), because the row cannot tell which task is newer. The
trade-off it accepted: if task `a` finished and a later re-run `c` stalls,
the card keeps showing `a`'s done status and hides the stall.

## Proposed outcome

- Issue #7 in two repos gives two cards and two work-item rows, and each card
  settles from its own build.
- A plan, its build and its test for one issue land on the same row.
- When several tasks share a key, the one the upstream created last owns the
  stage, whether it is alive or dead, so a stalled re-run is visible.
- Cards and events already in flight when this ships still settle.

## Affected users and systems

- CFactory (consumer): card intake, poll adapters, work-item store, progress
  poller.
- AIFactory, PFactory, TFactory (producers of the key).
- RFC-0001 §2 in the Factory hub (the key's canonical form).
- People watching the CFactory board.

## Constraints

- In-flight events and cards carry the old key. The consumer must accept old
  and new keys for a stated window, and the producers switch after it. A
  follow-up issue removes the old-key path when the window ends.
- The repository must come from data both sides already have (the issue's
  repository, as each service already stores it), not a new setting.
- "Newest" must come from a timestamp the upstream really returns. Where one
  doesn't, keep the #483 rule.
- Don't change the 24 h stalled-row pruning (`store.prune_dead`) beyond what
  the key change needs.
- Don't lose completed history or token usage that rows already hold.
- One PR per service repo (base `dev`), plus this hub PR. The merge order is
  part of the plan.

## Open questions

None for the approver. Decisions made conservatively are recorded in the spec.
