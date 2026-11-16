---
status: approved
issue: 3702
author: olafkfreund
---

# Intent: multi-org cockpit feed without widening any key

## Problem

#3679 confines an `acw_` key on `/ws/events` to the one org it was minted for
(`_may_receive` in each factory). CFactory holds one token per factory
(`Settings.token_for`, `upstream_ws.start_subscribers`), so on a multi-org
install the cockpit sees one org per factory. #3702 asks for a way to cover
several orgs. The owner deferred the choice: one key bound to several orgs, or
one socket per org key.

## Proposed outcome

CFactory can open one `/ws/events` socket per extra org key for a factory, each
key still bound to exactly one org. Unset by default, so nothing changes until
the owner mints the keys and sets them.

## Affected users and systems

CFactory `config.py`, `upstream_ws.py` and their tests. No change to AIFactory,
PFactory or TFactory, so no key gains any visibility.

## Constraints

- CFactory merges every upstream feed into one store with no org context. That already holds for one key; the cockpit operator who configures several org keys is deliberately choosing to see those orgs together. Per-org isolation inside CFactory is out of scope (Codex review, unresolved by design).
- Default off: no extra token configured means exactly today's behaviour.
- No key schema change, no new scope: that is the rejected multi-org key.
- Tokens are secrets: never logged, `repr=False`.

## Open questions

Owner decision, not made here: is a multi-org key (schema change in three
factories, a wider key to protect) preferred over per-org keys long term?
This slice does not preclude it. Minting the keys and setting them in the
cluster is the owner's.
