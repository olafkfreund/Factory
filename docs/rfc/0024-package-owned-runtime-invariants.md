---
layout: default
title: "RFC-0024: Package-Owned Runtime Invariants — every package declares what must hold, or says why nothing does"
permalink: /rfc/package-owned-runtime-invariants/
---

# RFC-0024 — Package-Owned Runtime Invariants

> **Status:** Proposed · **Created:** 2026-10-15 · **Owner:** each service, PFactory first ·
> **Extends:** the PFactory pilot (`apps/backend/factory_invariants`, `scripts/check_invariant_ownership.py`, PFactory#622) ·
> **See also:** [RFC-0006](./0006-verification-assurance-levels.md) (VAL levels, a different axis; see §5) ·
> **Affects:** PFactory now; CFactory, TFactory and AIFactory later, each behind the gate in §6.
>
> Tracking: Factory#818. Intent, spec and plan: `intent/`, `spec/` and
> `plan/2026-10-14-818-package-owned-invariants.md`.

## 1. Problem

A check that was never written, never wired up, or quietly stopped running
looks exactly like a check that passed. Factory#818 records six cases:
Factory #805, #807 and #816, AIFactory #1351, and PFactory #595 and #601. Its
comments add five more found after those fixes: Factory #932 and #858,
TFactory #1148, and AIFactory #1387 and #1390. Each was fixed on its own, and
new ones kept appearing. The #971 audit then found the runtime form of the
same class: final statuses that never reach the place they are read.

PFactory has a pilot of the fix. Measured on 2026-10-14, it falls short in
three ways:

- **3 of 32 packages are covered.**
- **The ownership checker reads a hand-written list** (`COVERED`), so it
  can't see a new package. That is the very gap the pattern exists to close.
- **Nothing runs in production.** Checks need `FACTORY_INVARIANTS=1` and a
  caller of `registry.verify_all()`, and app startup has neither.

## 2. Decision

Adopt package-owned runtime invariants **one service at a time, with every
package covered within each service it takes on**. PFactory goes first.
Partial coverage inside a service is not allowed: as #818 says, covering only
the riskiest packages gives up the property that makes the pattern work.

## 3. Coverage

### 3.1 The unit is the top-level package

A package is a directory with an `__init__.py` directly under one of the
service's declared source roots. For PFactory those roots are `apps/backend`
and `apps/web-server`.

The pilot asks for one declaration per **module**. PFactory's backend packages
hold 560 non-test modules, 155 of them in `plan` alone. At that size most
declarations would be written reasons, which is noise. So the rule counts
packages. Each package has one companion, `<pkg>/_invariants.py`, which
registers at least one check or one written reason. A companion may still
register per-module checks when that is the natural boundary.

### 3.2 Discovered, not listed

The checker walks the declared source roots and requires a companion for
every package it finds. Three things fail CI:

- a package with no declaration;
- a declaration naming a package that no longer exists, because coverage then
  looks complete while watching nothing;
- a source root with no packages, which means the root itself is wrong.

The only hand-written inputs are the list of source roots and a map of
vendored exceptions. `factory_common` is vendored byte-for-byte from the hub,
and its drift gate rejects extra files inside it. So its companion stays a
sibling file, `factory_common_invariants.py`. Every entry in the exception map
must exist on disk.

### 3.3 Guards kept from the pilot

- A written reason that matches `_PLACEHOLDER` (`todo`, `tbd`, `n/a`, `none`,
  `placeholder`, `grandfathered`) is rejected.
- So is a reason shorter than `_EMPTY_REASON_MIN_WORDS` (6) words.
- Registering the same package twice is an error.
- Passing both a check and a reason, or neither, is an error.

The checker keeps its `--self-test`, which proves it can fail for each
source root.

## 4. Running in production

### 4.1 Readiness, not liveness

PFactory's readiness and liveness probes both call `/api/health` (factory-gitops
`apps/pfactory/manifests/manifests.yaml`). If an invariant failed
`/api/health`, liveness would fail too and the pod would restart in a loop.
So the RFC makes three changes:

- It adds **`/api/ready`**. That endpoint runs the critical invariants through
  `registry.check_all()`, caches the result for one probe period (10 s), and
  returns 503 with the failing packages if any check fails.
- **Only the readiness probe moves** to `/api/ready`. Liveness stays on
  `/api/health`.
- `register()` gains **`critical: bool = False`**. The owning package opts in
  for each check.

A critical check must be cheap and local. It makes no network calls, so a
slow dependency can't take every pod out of service.

### 4.2 Non-critical checks

Non-critical checks run on a timer inside the app. The service sets the
period, and the default is 5 minutes. Each violation does two things:

- logs at error level, naming the owning package;
- increments `factory_invariant_violations_total{service,package}`.

### 4.3 Switches

- `FACTORY_INVARIANTS` now **defaults to on**. Setting it to `0` turns all
  checks off.
- `FACTORY_INVARIANTS_ONLY` (allowlist) and `FACTORY_INVARIANTS_SKIP`
  (blocklist) stay as they are.

### 4.4 Promotion

A new check runs non-critical for one release. It becomes critical only if it
raised no false positive in that release. This turns the pilot's "a check
earns production" rule into a concrete test.

## 5. How this relates to existing checks

- **RFC-0006 VAL levels are a different axis.** VAL-0 to VAL-4 grade how far
  a factory validated the output it produced for a user's task. Invariants
  watch the factories' own runtime. A task can reach VAL-2 while a factory
  invariant fails, and the reverse is also possible. Neither replaces the
  other.
- **`scripts/check_gate_liveness.py` and `scripts/check_test_collection.py`**
  in the hub already reuse the pilot's placeholder rule. They answer "did
  this CI gate run". Invariants answer "does this relation hold in the
  running service". Together they are the CI half and the runtime half of the
  same idea. This RFC does not change them.

## 6. Rollout and cost

1. **PFactory.**
   - The discovery checker and companions for the 29 uncovered packages.
     Most companions are a written reason of a few lines.
   - `critical`, `/api/ready`, the timer and the metric. That is roughly
     150 lines across the registry, the endpoint and the checker.
   - Move the readiness probe in factory-gitops, after the previous item is
     deployed.
2. **Gate.** The next service starts only after PFactory has two things:
   full coverage, and one release run with the checks on in production.
3. **Order after PFactory:**

   | Order | Service | Packages | Why this place |
   | --- | --- | --- | --- |
   | 1 | CFactory | 3 | It proves the pattern ports to another service. |
   | 2 | TFactory | 31 | |
   | 3 | AIFactory | 30 | |

4. **No shared library.** Each service copies `factory_invariants`, which is
   about 180 lines. A copy costs less than a new vendored dependency.

## 7. Alternatives rejected

| Alternative | Why rejected |
| --- | --- |
| Per-module coverage, as the pilot does it | 560 declarations in PFactory alone, mostly written reasons. The cost buries the signal. |
| The whole fleet at once | About 95 companions before the pattern has proved itself in one production service. |
| Retiring the pilot | The failure class keeps recurring (11 cases), and the hub already depends on the pilot's rules. |
| Failing `/api/health` | It is also the liveness probe, so the result would be a restart loop. |
| Stopping startup on any violation | One false positive would take a whole service down. |
| A shared package vendored from the hub | A new vendored dependency for about 180 lines. |

## 8. Risks

- **A false positive in a critical check removes every pod from service.**
  The one release as non-critical, the ban on network calls in critical
  checks, and `FACTORY_INVARIANTS=0` each limit this.
- **Probe cost.** `/api/ready` runs every 10 s. Results are cached for one
  period, and critical checks are local.
- **Written reasons decaying into boilerplate.** The placeholder guard only
  catches the obvious cases. Code review is the remaining control, and this
  RFC claims no more than that.

## 9. Follow-up issues

| Repo | Issue | What |
| --- | --- | --- |
| PFactory | [PFactory#864](https://github.com/olafkfreund/PFactory/issues/864) | A checker that finds every package on disk, plus companions for all packages (§3) |
| PFactory | [PFactory#865](https://github.com/olafkfreund/PFactory/issues/865) | `critical`, `/api/ready`, the timer and the metric (§4) |
| factory-gitops | [factory-gitops#283](https://github.com/olafkfreund/factory-gitops/issues/283) | Move PFactory's readiness probe to `/api/ready`, after PFactory#865 is deployed |
| Factory | [Factory#3591](https://github.com/olafkfreund/Factory/issues/3591) | A `rejected/` record of designs, the side idea in #818 |

CFactory, TFactory and AIFactory issues are filed when the gate in §6 opens.

## Appendix: measurements

Taken on 2026-10-15 against each repo's `origin/dev`, in a clone, read-only.

```bash
# Top-level packages under the service's source roots (§3.1, §6)
git ls-tree -r --name-only origin/dev apps/backend apps/web-server \
  | grep -cE '^apps/(backend|web-server)/[^/]+/__init__\.py$'
# PFactory 32 · TFactory 31 · AIFactory 30 · CFactory 3

# PFactory non-test modules in backend packages (§3.1)
git ls-tree -r --name-only origin/dev apps/backend \
  | grep -E '^apps/backend/[^/]+/.*\.py$' \
  | grep -vcE '/tests?/|/test_|_invariants\.py$'
# 560

# Who calls the registry in PFactory (§1): only the pilot, its tests and the checker
git grep -l -E 'factory_invariants|verify_all' origin/dev -- '*.py'
```
