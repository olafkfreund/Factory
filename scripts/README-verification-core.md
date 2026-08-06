# verification-core (canonical reference modules)

The Factory hub's `scripts/` directory is the **single source of truth** for the
verification-core layer — the reference modules that PFactory, AIFactory and
TFactory hand-vendor into their own backends.

This was established by the Phase-1 deduplication work in the Factory
code-quality program (epic Factory#154, issue Factory#158): the same
verification / sandbox / provisioning code was being copied into several service
repos, and the copies had begun to diverge.

## What lives here

The canonical set is exactly the deduped verification-core surface — nothing
service-specific:

This table is `CANONICAL_MODULES` in `scripts/check_verification_core_drift.py`.
That tuple is the contract; this table is a description of it, so when they
disagree the tuple is right — run `--list` to settle it.

| File | Role |
| --- | --- |
| `verification_gate.py` | RFC-0006 never-overclaim gate: recomputes an honest `achieved_level` from real lane outcomes so a verification block can never overclaim. |
| `factory_sandbox.py` | Unprivileged-sandbox helper (bubblewrap-based isolation). |
| `nix_provisioner.py` | Per-task Nix environment provisioner. |
| `artifact_store.py` | RFC-0016 artifact store. |
| `cost_router_core.py` | RFC-0014 cost router. |
| `ratchet_helpers.py` | The rules every service's lint ratchet must agree on (Factory#403, Factory#590). |
| `job_dispatch.py` | Job manifest naming, labelling and hardening rules (Factory#477, Factory#483). |

`verification_profiles.py` and `verification_runner.py` were **removed** from the
canonical set in Factory#401: they were listed but vendored by nobody, so the
gate never compared them anywhere. The files still live in `scripts/`; they are
simply no longer claimed to be a vendored contract.

Service-specific files that live alongside the vendored copies in some repos are
**not** part of this canonical contract and are intentionally out of scope.

## Acknowledged forks (not byte-exact, still gated)

Some shared code is not vendored byte-exact and never will be. The five lint
ratchets — the hub's `scripts/ratchet_lint.py`, the same path in PFactory,
TFactory and CFactory, and AIFactory's `scripts/cq_ratchet.py` — are
structurally different programs. They gate different package layouts and run
mypy five genuinely different ways (in place with `MYPYPATH`, from inside the
package with `--explicit-package-bases`, from a temp copy next to the file, from
a temp dir, from a git worktree). Demanding byte equality there would turn every
repo red for divergence that is real.

Each copy nonetheless carried a docstring citing the hub original — a **fork with
a citation**, which the byte comparison is structurally unable to catch because
there is no vendored file to compare. Factory#590 measured what that costs: one
defect in a rule restated nine times across the five forks took **five PRs to
fix**, and one of those five shipped a half-fix that read as complete.

So `PORTED_RATCHETS` in the drift gate asks the question that IS answerable of a
legitimate fork: does it **import** the shared rules from the byte-exact
canonical it sits next to (`ratchet_helpers.py`), or has it restated them inline?
Registered names live in `_REQUIRED_RATCHET_RULES`, and the check is: the file
exists, it imports each name, it calls each name, and it does not restate a rule
it should import.

To add a shared rule, in this order — the order matters, see below:

1. extract it into `ratchet_helpers.py` (hub PR)
2. re-vendor and rewire every fork, bumping each `HUB_PIN_SHA`
3. only then add the name to `_REQUIRED_RATCHET_RULES`

Step 3 last, because the drift CHECKER is fetched from hub `main` in every
consumer while the CANONICAL is pinned (Factory#405). Registering a rule the
forks cannot yet satisfy turns all four repos red at once.

The hub's own ratchet is the fifth fork and cannot be reached by a map that runs
against service checkouts; it is named in `HUB_PORTED_RATCHET` and asserted by
the hub's own test suite.

## How the services consume it (pinned-vendor + drift-gate)

Today this is a **vendor-canonical + drift-gate** model, deliberately:

1. The hub holds the canonical copy here in `scripts/`.
2. `scripts/check_verification_core_drift.py` diffs a service's vendored copies
   against this canonical, file-by-file, **byte-exact**, and exits non-zero on
   divergence. The per-service vendored layout (which modules each service carries
   and where) is encoded in that script's `SERVICE_LAYOUTS`; run
   `python scripts/check_verification_core_drift.py --list` to see it.
3. Each service is expected to vendor these modules at a **pinned hub SHA** and
   run the drift gate in its own CI so the copies cannot silently re-diverge.

The services deliberately vendor **different subsets** at **different paths**:

Run `python scripts/check_verification_core_drift.py --list` for the live map —
`SERVICE_LAYOUTS` in that script is the contract, and this table has been stale
before (it claimed PFactory vendored nothing long after it vendored three
modules). Treat it as orientation, not as the source of truth.

`job_dispatch.py` is a second-order case worth calling out (Factory#483):
AIFactory vendors it and calls `build_job_manifest` wholesale, while TFactory
vendors it and builds its own manifests — it seeds credentials through an
initContainer, forwards a provider-env allowlist, and needs a service-account
token — so it consumes the *policy* helpers (`task_pod_labels`, `job_labels`,
`assert_job_policy`) instead. Both are legitimate; what is not legitimate is the
third option TFactory used to take, which was restating the rules by hand under a
comment citing the hub file. Nothing compares a constant to its source.

We are **not** rewriting imports across the repos in this change. Full package
consumption (publishing `verification-core` as an installable package and deleting
the per-repo copies) is a tracked follow-on; it is deferred here because it is a
cross-repo, behaviour-affecting change that deserves its own staged PRs.

The per-repo CI drift-gate **workflows** ship alongside the reconciliation
(Factory#158): each affected service now runs the hub drift gate in its own CI
(`.github/workflows/verification-core-drift.yml`, blocking) so the copies cannot
silently re-diverge.

## Status: reconciled (the gate is green fleet-wide)

The live service copies were reconciled to this canonical, byte-for-byte, as part
of Factory#158. The reconciliation was **behaviour-preserving** and, where a
service copy genuinely carried *more* than the hub, the canonical adopted the
superset rather than deleting tested behaviour:

- **TFactory `verification_gate.py`** had been edited to its local lint bar
  (loop variable `l` -> `lvl` for E741, `TypedDict` definitions dropped for plain
  `dict` hints, module self-tests removed). The hub canonical already carries the
  `lvl` name; the service copy was restored to the canonical (TypedDicts and the
  module self-tests re-added) — all behaviour-equivalent.
- **`nix_provisioner.py`** (TFactory `tools/runners/`, AIFactory `core/`) carried
  the `_PY_PKG_ALIASES` pip->nixpkgs map and the RFC-0005 §3.2 Tier C content-
  addressing layer (`_TIER_BY_METHOD`, `resolve_tier`, `manifest_digest`), with
  passing tests in TFactory `tests/test_nix_provisioner.py`. These are genuine,
  tested functionality, so the **canonical adopted the superset** and both copies
  were re-vendored byte-identical to it.
- **AIFactory `factory_sandbox.py`** carried only a cosmetic line-wrap; it was
  restored to the canonical byte-for-byte.

Going forward, a change to a canonical module is a fleet change: land it here
first (CODEOWNERS-reviewed), then re-vendor the service copies and re-pin. The
per-repo `verification-core-drift.yml` CI gate blocks any silent re-divergence.

## CODEOWNERS note

Because this is fleet-wide infrastructure, changes to the canonical modules in
`scripts/` should be reviewed by the verification-layer owners. A change to a
canonical module is a fleet change — land it here first (CODEOWNERS-reviewed),
then propagate to the service copies and re-pin their SHA. Do **not** edit a
service copy to fix the gate; fix the canonical and re-vendor.
