---
layout: default
title: "RFC-0006: Verification Assurance Levels & Honest Reporting"
permalink: /rfc/verification-assurance/
---

# RFC-0006 — Verification Assurance Levels & Honest Reporting

> **Status:** Proposed · **Created:** 2026-06-15 · **Extends:** [RFC-0001a](./0001a-completion-evidence-gates.md) (evidence gates), [RFC-0005](./0005-environment-manifest-and-toolchain-provisioning.md) (provisioning) · **Affects:** PFactory, AIFactory, TFactory, CFactory
> RFC-0001a said *no green without proof*. This RFC says *declare **how much** was
> proven, and **never** present a lower assurance level as a higher one.* The
> single rule: **we never tell the user something is tested when it isn't.**
> Credibility is the product; one inflated "✓ tested" loses it.

## 1. The problem — the verifiability ceiling

Some tasks cannot be fully verified by the factory alone. "Write an Ansible role
and test it" can be **statically** checked (lint/syntax) and **converged in an
ephemeral container** (Molecule), but truly proving it requires applying it
against real, prod-like hosts — which may need a sandbox cloud account we don't
have. The danger is reporting `tested ✓` when we only linted. The fix is not to
test less; it is to **measure and declare the assurance level honestly**, and to
make "built, but only verifiable to level N" a first-class, surfaced outcome.

## 2. Verification Assurance Levels (VAL)

| Level | Name | What it proves | How (examples) | Needs |
|---|---|---|---|---|
| **VAL-0** | Static | It parses / lints / type-checks / scans clean | `ansible-lint`, `--syntax-check`, `ruff`, `mypy`, `terraform validate`, `tflint`, `hadolint` | toolchain only |
| **VAL-1** | Unit | Pure logic behaves, deterministically, no external deps | `pytest`, `cargo test`, `go test` | toolchain |
| **VAL-2** | Integration (ephemeral, local) | It works against **real but disposable** deps in the sandbox | **devenv services** (Postgres ✔ validated), testcontainers, **Molecule** converge+idempotence+verify (testinfra) for Ansible, `terraform plan` | sandbox + ephemeral deps |
| **VAL-3** | System (sandbox target) | It works applied against a **disposable prod-like target** | throwaway VM (QEMU/libvirt) or **sandbox cloud** account: `ansible-playbook` apply + assert, `terraform apply` + destroy, k8s deploy to ephemeral cluster | disposable target + creds + **cost guard + auto-teardown** |
| **VAL-4** | Production parity | It works in the user's real environment | — | the user's prod — **never done autonomously** |

**VAL-2 covers far more than people expect** — Molecule, testcontainers and
devenv services give high confidence for most "effectful" code without any cloud.
VAL-3 is the opt-in step up; VAL-4 is always the user's.

## 3. How we discover what's needed (per-technology verification profiles)

A registry (sibling to TFactory's `lang_registry`) maps an **artifact type** to its
assurance ladder + each tier's requirements. Detection is from the deliverable +
the plan's acceptance criteria (we already detect language/commands, RFC-0005).

Worked example — **Ansible role**:

| Level | Command | Requirement | Autonomous? |
|---|---|---|---|
| VAL-0 | `ansible-lint`, `ansible-playbook --syntax-check`, `yamllint` | ansible toolchain (Nix/devenv) | ✅ always |
| VAL-1 | (n/a — roles have little pure-unit logic) | — | — |
| VAL-2 | `molecule test` (Docker/Podman driver: create → converge → **idempotence** → verify) | ephemeral container target | ✅ in the sandbox |
| VAL-3 | `ansible-playbook -i <sandbox-inventory>` apply + assert | a real sandbox host/VM/cloud + creds | ⚠ only if a disposable target is provisioned |
| VAL-4 | apply to prod | the user's hosts | ❌ never |

The planner emits a **Verification Plan** in the RFC-0002 contract:
`target_level`, the per-level commands, and each level's `requires` (toolchain /
service / target / credentials). TFactory executes the **highest level whose
requirements are satisfied**, and records where it stopped.

The reference registry is [`scripts/verification_profiles.py`](../../scripts/verification_profiles.py)
(`detect_artifact_type()` + `plan_verification(files, available)`): it detects the
artifact type, returns the ladder with each un-achievable level pre-marked
`not_run` + `reason`, and composes directly with the #72 gate
(`verification_gate.normalize_verification`) to produce an honest, never-overclaiming
result.

## 4. The decision: simulate locally, sandbox-cloud only when justified

- **Default: climb as high as is achievable locally/ephemerally (up to VAL-2).**
  This is cheap, deterministic, reproducible, and — via Nix/devenv (RFC-0005) —
  fully controlled. Most tasks should reach VAL-2.
- **VAL-3 is opt-in and gated.** Only when (a) the artifact is genuinely effectful
  beyond what ephemeral simulation covers, **and** (b) a disposable target +
  scoped credentials are provisioned, **and** (c) a **cost guard + mandatory
  auto-teardown** are in place (precedent: the `run-aws-demo` cost-guarded
  ephemeral pattern). Prefer a **local VM** (QEMU/libvirt) over cloud when it
  suffices.
- **VAL-4 is never attempted.** We never touch the user's production.
- "Do we simulate a production environment?" → **Yes, ephemerally and disposably
  (VAL-2/VAL-3), never the real one (VAL-4).**

## 5. The honesty contract (the core of this RFC)

Every completion carries a `verification` block (extends RFC-0001a `evidence`):

```json
"verification": {
  "target_level": "VAL-3",
  "achieved_level": "VAL-2",
  "levels": [
    {"level": "VAL-0", "status": "passed", "ran": ["ansible-lint","--syntax-check"]},
    {"level": "VAL-2", "status": "passed", "ran": ["molecule test"], "evidence": "idempotence: 0 changed"},
    {"level": "VAL-3", "status": "not_run",
     "reason": "no sandbox target provisioned (needs disposable host + creds)",
     "risk": "role not proven against real hosts; apply-time failures possible"}
  ],
  "claim": "Built and verified to VAL-2 (ephemeral container). NOT verified against real infrastructure (VAL-3)."
}
```

Rules:
1. **A status is reported at `achieved_level`, never above.** "passed" means
   "passed *at the level we reached*", and the level is always shown next to it.
2. **Every gap is explicit** — each un-run level carries a `reason` and a `risk`,
   in plain language, surfaced in the CFactory cockpit and the PR summary.
3. **No silent upgrade.** As RFC-0001a downgrades "no evidence" to failed, this
   downgrades "claimed higher than achieved" — a producer that omits
   `verification` is treated as **VAL-0 at best**, never "tested".
4. **The user-facing line is mandatory and honest**, e.g.: *"Built the Ansible
   role; passed lint + an ephemeral Molecule converge with idempotence; **I could
   not test it against real hosts (no sandbox target), so apply-time behavior is
   unproven.**"* — never just "✅ tested".

## 6. Where it plugs in

- **PFactory / planner** — emit the Verification Plan (target level + per-level
  requirements) into the RFC-0002 contract; flag when the target needs a sandbox
  cloud/VM so the user can decide up front.
- **AIFactory** — produce the test scaffolding the levels need (e.g. a
  `molecule/` scenario), and the RFC-0005 env to run them.
- **TFactory** — run the ladder bottom-up, stop at the highest satisfiable level,
  emit the `verification` block; never report above `achieved_level`.
- **CFactory** — render `achieved_level` + gaps prominently (a VAL-2 result must
  not look like a VAL-3/“done” result).

## 7. Phasing
1. VAL schema + the honesty contract in RFC-0002 + the never-overclaim gate
   (extends RFC-0001a). **Lands the integrity guarantee first.**
2. Verification-profile registry; Ansible + Terraform + web-app + library profiles.
3. VAL-0/1/2 execution via the RFC-0005 sandbox (devenv services / Molecule /
   testcontainers).
4. VAL-3 opt-in: disposable VM, then cost-guarded sandbox-cloud, with auto-teardown.
5. CFactory surfacing + PR-summary wording.

## 8. Validated foundation
RFC-0005 prototype (`prototypes/env-provisioning/`) already proves the substrate:
`nix develop` materializes toolchains (VAL-0/1) and **`devenv test` ran a real
ephemeral Postgres and a query against it (VAL-2), then tore it down** — locally,
no cloud.
