---
status: draft
issue: 3745
author: olafkfreund
---

# Intent: pin-freshness must watch the vendored factory_common package

## Problem

Factory#3745 added an Anthropic key pattern (`sk-ant-...`) to the hub's
`shared/factory-common/factory_common/secrets.py`. None of the vendored copies
(AIFactory apps/backend and apps/web-server, PFactory, TFactory, CFactory) has
it: each `.hub-sha` still pins a hub commit from before #3745, so each byte-exact
drift gate is green. A log line or error body carrying an `sk-ant-` key is not
redacted in any service until someone bumps the pins, and nothing says so.

The hub's `scripts/check_pin_freshness.py` exists for exactly this ("is my pin
still the current canonical?") but its gates only read workflow-variable pins.
The factory_common pins live in `.hub-sha` files, so the package is invisible to it.

## Proposed outcome

The daily pin-freshness watchdog reads every service's `factory_common/.hub-sha`
and fails, naming the moved commits, when the hub's `factory_common` has moved
past a pin for longer than the grace budget. Re-vendoring the copies is the
fix the watchdog then asks for; it is a separate per-repo change.

## Affected users and systems

Hub `scripts/check_pin_freshness.py`, `tests/test_pin_freshness.py`. Consumers
are only read (public raw fetch), never changed.

## Constraints

Stdlib only. No consumer repo edits here. The watchdog will go red on its next
scheduled run until the four repos re-vendor: that is the intended signal.

## Open questions

None.
