---
status: approved
issue: 818
intent: intent/2026-10-14-818-package-owned-invariants.md
---

# Spec: RFC-0024, package-owned runtime invariants

## Design

The deliverable is `docs/rfc/0024-package-owned-runtime-invariants.md`. It
adopts the pattern **per service**, PFactory first, and replaces the pilot's
three gaps with the mechanisms below. Facts measured on PFactory `origin/dev`,
2026-10-15.

### 1. Unit of coverage: the top-level package, discovered from disk

| Measure | PFactory today |
| --- | --- |
| Top-level packages (dir with `__init__.py`) | 32: 30 under `apps/backend`, 2 under `apps/web-server` (`server`, `factory_common`) |
| Non-test modules in those backend packages | 560 (`plan` alone has 155) |
| Packages covered by the pilot | 3 |

The pilot's checker (`scripts/check_invariant_ownership.py`) demands one
declaration per **module** inside each covered package. At 560 modules that is
not affordable, and most module-level declarations would be the written-reason
form, which is noise. The RFC makes the **package** the unit: every top-level
package has one companion, `<pkg>/_invariants.py`, which registers at least
one check or one written reason. A package may register per-module checks
inside its companion if it wants, but the rule only counts packages.

The checker stops reading the hand-written `COVERED` tuple. It walks the
service's declared source roots (`apps/backend`, `apps/web-server`) and treats
every directory with an `__init__.py` as a package that must be covered. A new
package fails CI until it has a companion. The only hand-written input left is
the list of source roots, and a source root with no packages is itself an
error.

Vendored packages (`factory_common`) keep the pilot's sibling-file companion
(`factory_common_invariants.py`), because the drift gate forbids extra files
inside them. The checker carries a small, explicit map of these exceptions,
and each entry must exist on disk.

The pilot's guards stay: `_PLACEHOLDER`, `_EMPTY_REASON_MIN_WORDS`, duplicate
registration rejected, and a stale declaration (one naming a package that no
longer exists) fails.

### 2. Running in production, and what a failure does

Measured trap: PFactory's readiness **and** liveness probes both hit
`/api/health` (factory-gitops `apps/pfactory/manifests/manifests.yaml:425-426`).
Failing `/api/health` would fail liveness too and restart-loop the pod. So:

- Add `/api/ready`, which runs `registry.check_all()` on the critical
  invariants (cached for one probe period) and returns 503 if any fail. Move
  only the readiness probe to it; liveness stays on `/api/health`.
- `register()` gains `critical: bool = False`. The owner opts in per check.
- Non-critical checks run on a timer in the app (period set by the service,
  default 5 minutes). Each violation logs at error level, naming the owning
  package, and increments a metric
  `factory_invariant_violations_total{service,package}`.
- `FACTORY_INVARIANTS` changes meaning: it now defaults to on, and `=0` is
  the kill switch. The allowlist and blocklist variables stay.
- Promotion rule: a new critical check runs non-critical for one release
  first. It becomes critical only if it raised no false positive in that
  release. This is the pilot's "earn production" rule, made concrete.

### 3. Relationship to existing checks

- **RFC-0006 VAL levels do not overlap.** VAL-0 to VAL-4 grade how far a
  factory validated the *output it produced for a user's task*. Invariants
  watch the *factories' own runtime*. The RFC says this in one paragraph and
  cross-links both ways (a one-line "See also" added to RFC-0006).
- **`check_gate_liveness.py` and `check_test_collection.py`** in the hub
  already reuse the pilot's placeholder rule. They answer "did a CI gate
  run". Invariants answer "does a runtime relation hold". The RFC names them
  as the CI-side half of the same idea and changes neither.

### 4. Rollout and cost

1. PFactory: discovery-based checker, then 29 new companions (the 3 existing
   ones stay), then `critical`, `/api/ready`, the timer and the metric, then
   the gitops readiness-probe change. Estimate: 29 small files (most are
   written reasons) plus about 150 lines of registry, endpoint and checker
   change.
2. The next service adopts only after PFactory has full coverage and has run
   one release with the checks on in production. Measured package counts:
   TFactory 29, AIFactory 28, CFactory 3. Order: CFactory (smallest, proves
   the pattern ports), then TFactory, then AIFactory.
3. The pattern lives in each repo; there is no shared library. `factory_invariants`
   is about 180 lines, and copying it per service matches the constraint of
   "no new vendored dependency".

The RFC ends with the follow-up issues to file, one per rollout step above.
They are filed when the RFC merges, and their numbers are added to it.

Separately, one small issue proposes a `rejected/` record of designs, the side
idea in #818.

## Alternatives rejected

- **Per-module coverage, as the pilot does.** 560 declarations in PFactory
  alone, mostly written reasons. The cost buries the signal.
- **Whole fleet at once.** About 90 companions before the pattern has proven
  itself in one production service. Rejected in the intent decisions.
- **Retire the pilot.** The failure class in #818 keeps recurring (11 cases),
  and the hub already depends on the pilot's rules.
- **Fail `/api/health` on a critical violation.** It is also the liveness
  probe, so the pod would restart-loop instead of being taken out of service.
- **Every violation stops startup.** One false positive would take a service
  down. Rejected in the intent decisions.
- **A shared `factory-invariants` package vendored from the hub.** It is a new
  vendored dependency, and the registry is small enough to copy.

## Risks

- **False positives in production.** A critical check that misfires removes
  every pod from service. Mitigations: one release as non-critical first,
  and the `FACTORY_INVARIANTS=0` kill switch.
- **Probe cost.** Checks on `/api/ready` run every 10 s. Mitigations:
  results are cached for one period, and critical checks must be cheap and
  local (the RFC forbids network calls in them).
- **Written reasons decaying into boilerplate.** The placeholder guard only
  catches obvious cases. Review is the remaining control. The RFC says so
  rather than claiming more.
- **This task:** none at runtime. It is docs only.

## Verification

- The RFC is in `docs/rfc/0024-package-owned-runtime-invariants.md` and
  follows the header format of 0023 (status, dates, extends, affects).
- Every number in the RFC matches a command shown in the RFC's appendix, and
  rerunning each command gives the same number.
- RFC-0006 gains its one-line cross-link.
- The hub's docs CI (markdown lint and link check) is green on the PR.
- The follow-up issues are filed and linked from the RFC.
