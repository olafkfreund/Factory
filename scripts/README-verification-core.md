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
cross-repo, behaviour-affecting change that deserves its own staged PRs. The
per-repo CI drift-gate **workflows** are likewise a fast follow (deferred): this
increment ships the canonical source-of-truth statement plus the gate + tests in
the hub only.

## Honest status: known drift (the gate will flag TFactory)

Because these modules were vendored at different times and lightly edited
in-place, the live service copies do **not** all match this canonical
byte-for-byte yet. In particular:

- **TFactory `verification_gate.py`** was reconciled to its local lint bar rather
  than to the hub: the loop variable was renamed (`l` -> `lvl`, for E741), the
  `TypedDict` definitions were dropped in favour of plain `dict` type hints, and
  the module-level self-tests were removed. These are **behaviour-equivalent**
  changes, but they make the file byte-divergent, so the drift gate **will flag
  TFactory's gate copy** until it is reconciled.
- The other existing copies (AIFactory `factory_sandbox.py` / `nix_provisioner.py`,
  TFactory `nix_provisioner.py`) similarly carry minor local edits and will flag
  until reconciled.

This is expected and intentional: this PR establishes the source of truth and the
gate. **Reconciling each live service copy back to the canonical (or, where a
service edit is genuinely wanted, landing it in the hub canonical first and
re-vendoring) is a deferred, behaviour-checked follow-on** — done per service so
each change is small, reviewable and verified, not a risky cross-repo rewrite in
one shot.

## CODEOWNERS note

Because this is fleet-wide infrastructure, changes to the canonical modules in
`scripts/` should be reviewed by the verification-layer owners. A change to a
canonical module is a fleet change — land it here first (CODEOWNERS-reviewed),
then propagate to the service copies and re-pin their SHA. Do **not** edit a
service copy to fix the gate; fix the canonical and re-vendor.
