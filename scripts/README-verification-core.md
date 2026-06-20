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

| File | Role |
| --- | --- |
| `verification_gate.py` | RFC-0006 never-overclaim gate: recomputes an honest `achieved_level` from real lane outcomes so a verification block can never overclaim. |
| `verification_profiles.py` | Verification profile selection / construction. |
| `verification_runner.py` | Verification lane runner. |
| `factory_sandbox.py` | Unprivileged-sandbox helper (bubblewrap-based isolation). |
| `nix_provisioner.py` | Per-task Nix environment provisioner. |

Service-specific files that live alongside the vendored copies in some repos are
**not** part of this canonical contract and are intentionally out of scope.

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

| Service | Vendored modules | Path (relative to repo root) |
| --- | --- | --- |
| PFactory | (none today) | — |
| AIFactory | `factory_sandbox.py`, `nix_provisioner.py` | `apps/backend/core/` |
| TFactory | `verification_gate.py`, `nix_provisioner.py` | `apps/backend/agents/`, `apps/backend/tools/runners/` |

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
